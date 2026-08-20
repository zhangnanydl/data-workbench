from __future__ import annotations

import hashlib
import json
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any, Callable

import polars as pl

from dataworkbench.models import ExecutionContext, PluginKind
from dataworkbench.registry import PluginRegistry


class PipelineValidationError(ValueError):
    pass


class PipelineEngine:
    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or PluginRegistry()
        self._cache: OrderedDict[str, pl.DataFrame] = OrderedDict()
        self._cache_sizes: dict[str, int] = {}
        self._cache_bytes = 0
        self._cache_limit = 16
        self._cache_budget = 128 * 1024 * 1024
        self._cache_entry_limit = 32 * 1024 * 1024
        self._lock = RLock()

    def validate(self, pipeline: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        nodes = pipeline.get("nodes", [])
        edges = pipeline.get("edges", [])
        node_map = {node["id"]: node for node in nodes}
        if len(node_map) != len(nodes):
            errors.append("存在重复的节点 ID")
        for node in nodes:
            try:
                plugin = self.registry.get(node["pluginId"])
            except KeyError as exc:
                errors.append(str(exc))
                continue
            errors.extend(f"{node.get('label', plugin.definition.name)}：{item}" for item in plugin.validate(node.get("config", {})))
        for edge in edges:
            if edge.get("source") not in node_map or edge.get("target") not in node_map:
                errors.append("连线引用了不存在的节点")
        try:
            self._topological_order(nodes, edges)
        except PipelineValidationError as exc:
            errors.append(str(exc))
        return errors

    def execute(
        self,
        pipeline: dict[str, Any],
        *,
        preview: bool = True,
        target_node_id: str | None = None,
        preview_limit: int = 100,
        preview_page: int = 1,
        project_dir: str | Path = "",
        execution_variables: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        nodes = pipeline.get("nodes", [])
        edges = pipeline.get("edges", [])
        node_map = {node["id"]: node for node in nodes}
        parents: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            parents[edge["target"]].append(edge["source"])

        required = self._required_nodes(target_node_id, parents) if target_node_id else set(node_map)
        scoped_pipeline = {
            "nodes": [node for node in nodes if node["id"] in required],
            "edges": [edge for edge in edges if edge["source"] in required and edge["target"] in required],
        }
        errors = self.validate(scoped_pipeline)
        if errors:
            raise PipelineValidationError("；".join(errors))
        order = [node_id for node_id in self._topological_order(nodes, edges) if node_id in required]
        frames: dict[str, pl.DataFrame] = {}
        cache_keys: dict[str, str] = {}
        preview_limit = min(max(int(preview_limit), 1), 1000)
        preview_page = max(int(preview_page), 1)
        context = ExecutionContext(preview=preview, preview_limit=preview_limit, project_dir=str(project_dir))
        context.variables.update({
            "preview_target_node_id": target_node_id,
            "preview_page": preview_page,
            "preview_page_size": preview_limit,
            **(execution_variables or {}),
        })
        context.variables["progress_callback"] = progress_callback
        context.variables["direct_pcap_export"] = any(
            node.get("pluginId") == "output.pcap_index"
            and len(parents[node["id"]]) == 1
            and node_map[parents[node["id"]][0]].get("pluginId") == "input.pcap"
            for node in nodes
        )

        started_at = perf_counter()
        source_rows = 0
        with self._lock:
            for node_index, node_id in enumerate(order):
                node = node_map[node_id]
                plugin = self.registry.get(node["pluginId"])
                self._report_progress(progress_callback, {
                    "status": "running", "phase": "executing", "percent": round(node_index / max(len(order), 1) * 100, 1),
                    "nodeIndex": node_index + 1, "nodeCount": len(order), "currentNodeId": node_id,
                    "currentNode": node.get("label") or plugin.definition.name, "pluginId": node["pluginId"],
                    "sourceRows": source_rows, "elapsedSeconds": round(perf_counter() - started_at, 2),
                })
                input_frames = [frames[parent_id] for parent_id in parents[node_id]]
                parent_keys = [cache_keys[parent_id] for parent_id in parents[node_id]]
                parent_labels = [node_map[parent_id].get("label") or node_map[parent_id].get("pluginId") for parent_id in parents[node_id]]
                # Preview pagination is a presentation concern. Cached node frames
                # must contain the complete result so downstream nodes never run on
                # just the visible page.
                is_direct_pcap_page = preview and node.get("pluginId") == "input.pcap" and node_id == target_node_id
                page_partition = preview_page * 10_000 + preview_limit if is_direct_pcap_page else None
                cache_key = self._cache_key(node, parent_keys, page_partition, parent_labels)
                cache_keys[node_id] = cache_key
                if preview and cache_key in self._cache:
                    frames[node_id] = self._cache[cache_key]
                    self._cache.move_to_end(cache_key)
                    continue
                context.variables["current_node_id"] = node_id
                context.variables["current_node_index"] = node_index
                context.variables["current_node_count"] = len(order)
                context.variables["current_node_label"] = node.get("label") or plugin.definition.name
                context.variables["direct_parent_plugins"] = [node_map[parent_id].get("pluginId") for parent_id in parents[node_id]]
                context.variables["direct_parent_labels"] = [node_map[parent_id].get("label") or self.registry.get(node_map[parent_id]["pluginId"]).definition.name for parent_id in parents[node_id]]
                frame = plugin.execute(input_frames, node.get("config", {}), context)
                if plugin.definition.kind == PluginKind.INPUT:
                    source_rows += frame.height
                sampled = context.variables.get("sampled_sources", {}).get(node_id)
                if sampled is not None:
                    sampled["sampleRows"] = frame.height
                if preview:
                    frame_size = int(frame.estimated_size())
                    if frame_size <= self._cache_entry_limit:
                        self._cache[cache_key] = frame
                        self._cache_sizes[cache_key] = frame_size
                        self._cache_bytes += frame_size
                        self._cache.move_to_end(cache_key)
                        while len(self._cache) > self._cache_limit or self._cache_bytes > self._cache_budget:
                            evicted_key, _ = self._cache.popitem(last=False)
                            self._cache_bytes -= self._cache_sizes.pop(evicted_key, 0)
                frames[node_id] = frame
                self._report_progress(progress_callback, {
                    "status": "running", "phase": "node_complete", "percent": round((node_index + 1) / max(len(order), 1) * 100, 1),
                    "nodeIndex": node_index + 1, "nodeCount": len(order), "currentNodeId": node_id,
                    "currentNode": node.get("label") or plugin.definition.name, "pluginId": node["pluginId"],
                    "inputRows": sum(item.height for item in input_frames), "outputRows": frame.height,
                    "sourceRows": source_rows, "processedRows": sum(item.height for item in frames.values()),
                    "elapsedSeconds": round(perf_counter() - started_at, 2),
                })

        final_id = target_node_id or (order[-1] if order else None)
        if final_id is None:
            return {"columns": [], "rows": [], "stats": {"rowCount": 0, "previewCount": 0}}
        already_paged = final_id in context.variables.get("pre_paged_nodes", set())
        result = self._serialize_frame(
            frames[final_id], node_map[final_id], preview,
            page=1 if already_paged else preview_page, page_size=preview_limit,
        )
        if already_paged:
            result["stats"]["page"] = preview_page
        override = context.variables.get("row_count_overrides", {}).get(final_id)
        if override is not None:
            result["stats"]["rowCount"] = int(override)
        sampled_sources = context.variables.get("sampled_sources", {})
        if sampled_sources:
            estimated_input = sum(int(item.get("estimatedRows") or 0) for item in sampled_sources.values())
            sampled_input = sum(int(item.get("sampleRows") or 0) for item in sampled_sources.values())
            estimated_output = round(frames[final_id].height * estimated_input / sampled_input) if sampled_input and estimated_input else None
            result["stats"].update({
                "sampled": True, "complete": False, "processingScope": "sample",
                "sampleInputRows": sampled_input, "estimatedInputRows": estimated_input or None,
                "estimatedRowCount": estimated_output, "sampleLimit": max(int(item.get("sampleLimit") or 0) for item in sampled_sources.values()),
            })
        else:
            result["stats"].update({"sampled": False, "complete": not preview, "processingScope": "full"})
        return result

    @staticmethod
    def _report_progress(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            callback(payload)
        except Exception:
            # Progress reporting must never affect data correctness.
            pass

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_sizes.clear()
            self._cache_bytes = 0

    @staticmethod
    def _cache_key(node: dict[str, Any], parent_keys: list[str], preview_limit: int | None, parent_labels: list[str] | None = None) -> str:
        payload = json.dumps(
            {"plugin": node["pluginId"], "config": node.get("config", {}), "parents": parent_keys, "parentLabels": parent_labels or [], "limit": preview_limit},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
        indegree = {node["id"]: 0 for node in nodes}
        children: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge["source"] in indegree and edge["target"] in indegree:
                children[edge["source"]].append(edge["target"])
                indegree[edge["target"]] += 1
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for child in children[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(nodes):
            raise PipelineValidationError("处理流程中存在循环连线")
        return order

    @staticmethod
    def _required_nodes(target: str, parents: dict[str, list[str]]) -> set[str]:
        required = {target}
        stack = [target]
        while stack:
            current = stack.pop()
            for parent in parents[current]:
                if parent not in required:
                    required.add(parent)
                    stack.append(parent)
        return required

    @staticmethod
    def _serialize_frame(
        frame: pl.DataFrame,
        node: dict[str, Any],
        preview: bool,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        row_count = frame.height
        paged = page is not None and page_size is not None
        display_frame = frame.slice((max(page or 1, 1) - 1) * max(page_size or 1, 1), max(page_size or 1, 1)) if paged else frame
        rows = display_frame.to_dicts()
        normalized = [{key: PipelineEngine._json_value(value) for key, value in row.items()} for row in rows]
        columns = [{"key": name, "label": name, "type": str(dtype)} for name, dtype in zip(frame.columns, frame.dtypes)]
        return {
            "columns": columns,
            "rows": normalized,
            "stats": {
                "rowCount": row_count,
                "previewCount": len(normalized),
                "columnCount": frame.width,
                "nodeId": node["id"],
                "pluginId": node["pluginId"],
                "preview": preview,
                "paged": paged,
                "page": max(page or 1, 1),
                "pageSize": max(page_size or len(normalized) or 1, 1),
            },
        }

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
