from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event, RLock
from typing import Any

import webview

from dataworkbench.engine import PipelineCancelledError, PipelineEngine
from dataworkbench.mysql_utils import mysql_connect_kwargs, quote_mysql_identifier
from dataworkbench.registry import PluginRegistry
from dataworkbench.worker import execute_pipeline_job, list_mysql_databases_job, list_mysql_tables_job, worker_ready_job


class DesktopBridge:
    def __init__(self, project_root: Path, use_worker: bool = False) -> None:
        # pywebview recursively inspects every public attribute when generating
        # its JavaScript API. Keep internal object graphs private; exposing the
        # engine/registry/window makes that inspection walk thousands of cyclic
        # objects and was the cause of the frozen EXE memory growth.
        self._project_root = project_root.resolve()
        self._project_root.mkdir(parents=True, exist_ok=True)
        self._projects_dir = self._project_root / "projects"
        self._projects_dir.mkdir(exist_ok=True)
        self._storage_config_path = self._project_root / "storage.json"
        external_dir = self._project_root / "plugins_external"
        external_dir.mkdir(exist_ok=True)
        self._registry = PluginRegistry([external_dir])
        self._engine = PipelineEngine(self._registry)
        self._use_worker = use_worker
        self._worker: Any = None
        self._worker_lock = RLock()
        self._preview_lock = RLock()
        self._active_preview_cancel: Event | None = None
        self._run_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dataworkbench-run")
        self._run_jobs: dict[str, dict[str, Any]] = {}
        self._run_cancel_events: dict[str, Event] = {}
        self._run_lock = RLock()
        self._window = None

    def _ensure_worker(self) -> Any:
        with self._worker_lock:
            if self._worker is None:
                import multiprocessing
                from concurrent.futures import ProcessPoolExecutor

                self._worker = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
            return self._worker

    def warm_worker(self) -> None:
        if self._use_worker:
            self._ensure_worker().submit(worker_ready_job).result(timeout=30)

    def _execute_pipeline(self, pipeline: dict[str, Any], preview: bool, target_node_id: str | None, preview_limit: int, preview_page: int = 1) -> dict[str, Any]:
        assessment = self._assess_pipeline(pipeline)
        execution_variables = {
            "assessment": assessment,
            "source_estimates": assessment["sources"],
            "fast_preview": preview and assessment["fastPreview"],
            "preview_sample_limit": 50_000,
        }
        if not self._use_worker:
            return self._engine.execute(pipeline, preview=preview, target_node_id=target_node_id, preview_limit=preview_limit, preview_page=preview_page, project_dir=self._project_root, execution_variables=execution_variables)
        timeout = 120 if preview else 3600
        return self._ensure_worker().submit(execute_pipeline_job, str(self._project_root), pipeline, preview, target_node_id, preview_limit, preview_page, execution_variables).result(timeout=timeout)

    def close(self) -> None:
        with self._run_lock:
            for cancel_event in self._run_cancel_events.values():
                cancel_event.set()
        self._run_executor.shutdown(wait=False, cancel_futures=True)
        self._cancel_worker()

    def _cancel_worker(self) -> None:
        with self._worker_lock:
            worker, self._worker = self._worker, None
        if worker is None:
            return
        processes = list((getattr(worker, "_processes", None) or {}).values())
        worker.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            if process.is_alive():
                process.terminate()

    def cancel_preview(self) -> dict[str, Any]:
        with self._preview_lock:
            cancel_event = self._active_preview_cancel
        if cancel_event is not None:
            cancel_event.set()
        self._cancel_worker()
        return {"ok": True, "message": "已停止当前加载"}

    def attach_window(self, window: Any) -> None:
        self._window = window

    def health(self) -> dict[str, Any]:
        return {"ok": True, "pluginCount": len(self._registry.list_definitions()), "time": datetime.now().isoformat()}

    def list_plugins(self) -> list[dict[str, Any]]:
        return self._registry.list_definitions()

    @staticmethod
    def _estimate_file(path_text: str) -> dict[str, Any]:
        path = Path(path_text)
        if not path.is_file():
            return {"estimatedRows": None, "sizeBytes": 0, "large": False}
        size = path.stat().st_size
        estimated_rows = None
        if path.suffix.lower() in {".csv", ".txt", ".log", ".out", ".trace", ".jsonl", ".ndjson"} and size:
            with path.open("rb") as handle:
                sample = handle.read(min(size, 1024 * 1024))
            sampled_lines = sample.count(b"\n") or (1 if sample else 0)
            if sampled_lines:
                estimated_rows = max(sampled_lines, round(size / (len(sample) / sampled_lines)))
        large = size >= 32 * 1024 * 1024 or bool(estimated_rows and estimated_rows >= 250_000)
        return {"estimatedRows": estimated_rows, "sizeBytes": size, "large": large}

    def _assess_pipeline(self, pipeline: dict[str, Any]) -> dict[str, Any]:
        sources: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        estimated_rows = 0
        has_estimated_rows = False
        database_source = False
        indexed_source = False
        for node in pipeline.get("nodes", []):
            plugin_id = str(node.get("pluginId", ""))
            if not plugin_id.startswith("input."):
                continue
            config = node.get("config", {})
            estimate = self._estimate_file(str(config.get("path", ""))) if config.get("path") else {"estimatedRows": None, "sizeBytes": 0, "large": False}
            if plugin_id in {"input.mysql", "input.sqlite"}:
                database_source = True
                estimate["large"] = True
            if plugin_id == "input.pcap":
                indexed_source = True
            sources[str(node.get("id"))] = estimate
            total_bytes += int(estimate.get("sizeBytes") or 0)
            if estimate.get("estimatedRows") is not None:
                estimated_rows += int(estimate["estimatedRows"])
                has_estimated_rows = True
        large = database_source or any(bool(item.get("large")) for item in sources.values())
        strategy = "磁盘索引分页" if indexed_source else "大数据快速样本预览 + 后台全量运行" if large else "完整预览 + 后台全量运行"
        return {
            "estimatedRows": estimated_rows if has_estimated_rows else None,
            "estimatedBytes": total_bytes,
            "nodeCount": len(pipeline.get("nodes", [])),
            "sourceCount": len(sources),
            "largeData": large,
            "fastPreview": large,
            "strategy": strategy,
            "sources": sources,
        }

    def assess_pipeline(self, pipeline: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "data": self._assess_pipeline(pipeline)}
        except Exception as exc:
            return {"ok": False, "error": f"数据量评估失败：{exc}"}

    def _run_pipeline_job(self, job_id: str, pipeline: dict[str, Any], assessment: dict[str, Any]) -> None:
        started = time.perf_counter()
        with self._run_lock:
            cancel_event = self._run_cancel_events[job_id]

        def report(payload: dict[str, Any]) -> None:
            with self._run_lock:
                job = self._run_jobs.get(job_id)
                if job is not None:
                    if payload.get("currentNodeId") != job.get("currentNodeId") or payload.get("phase") in {"preparing", "executing"}:
                        for key in ("processedRows", "outputRows", "finalRows", "inputRows", "totalRows", "batchIndex", "batchCount", "batchSize", "detail"):
                            job.pop(key, None)
                    job.update(payload)
                    job["elapsedSeconds"] = round(time.perf_counter() - started, 2)

        report({"status": "running", "phase": "preparing", "percent": 0})
        try:
            result = self._engine.execute(
                pipeline, preview=False, preview_limit=100, project_dir=self._project_root,
                execution_variables={"assessment": assessment, "source_estimates": assessment.get("sources", {}), "cancel_event": cancel_event}, progress_callback=report,
            )
            report({
                "status": "success", "phase": "complete", "percent": 100,
                "result": result, "finalRows": int(result.get("stats", {}).get("rowCount", 0)),
                "message": "全量数据处理和导出完成，结果完整",
            })
        except Exception as exc:
            if cancel_event.is_set() or isinstance(exc, PipelineCancelledError):
                report({"status": "cancelled", "phase": "cancelled", "message": "任务已安全停止"})
            else:
                report({"status": "error", "phase": "error", "error": str(exc), "message": f"运行失败：{exc}"})
        finally:
            with self._run_lock:
                self._run_cancel_events.pop(job_id, None)

    def start_pipeline_run(self, pipeline: dict[str, Any]) -> dict[str, Any]:
        try:
            assessment = self._assess_pipeline(pipeline)
            job_id = uuid.uuid4().hex
            job = {
                "jobId": job_id, "status": "queued", "phase": "queued", "percent": 0,
                "createdAt": datetime.now().isoformat(), "elapsedSeconds": 0,
                "estimatedRows": assessment.get("estimatedRows"), "estimatedBytes": assessment.get("estimatedBytes", 0),
                "nodeCount": assessment.get("nodeCount", 0), "strategy": assessment.get("strategy"),
                "largeData": assessment.get("largeData", False), "complete": False,
            }
            with self._run_lock:
                self._run_jobs[job_id] = job
                self._run_cancel_events[job_id] = Event()
            self._run_executor.submit(self._run_pipeline_job, job_id, pipeline, assessment)
            return {"ok": True, "job": dict(job), "message": "全量任务已启动"}
        except Exception as exc:
            return {"ok": False, "error": f"启动任务失败：{exc}"}

    def cancel_pipeline_run(self, job_id: str) -> dict[str, Any]:
        with self._run_lock:
            job = self._run_jobs.get(str(job_id))
            cancel_event = self._run_cancel_events.get(str(job_id))
            if job is None:
                return {"ok": False, "error": "运行任务不存在或已结束"}
            if job.get("status") not in {"queued", "running", "cancelling"}:
                return {"ok": True, "job": dict(job), "message": "任务已经结束"}
            if cancel_event is not None:
                cancel_event.set()
            job.update({"status": "cancelling", "phase": "cancelling", "message": "正在安全停止，当前数据库事务将回滚"})
            return {"ok": True, "job": dict(job), "message": "已发送停止请求"}

    def get_pipeline_run(self, job_id: str) -> dict[str, Any]:
        with self._run_lock:
            job = self._run_jobs.get(str(job_id))
            if job is None:
                return {"ok": False, "error": "运行任务不存在或已结束"}
            payload = dict(job)
        payload["complete"] = payload.get("status") == "success"
        return {"ok": True, "job": payload}

    def preview_pipeline(self, pipeline: dict[str, Any], target_node_id: str | None = None, limit: int = 100, page: int = 1) -> dict[str, Any]:
        try:
            return {"ok": True, "data": self._execute_pipeline(pipeline, True, target_node_id, min(max(int(limit), 1), 1000), max(int(page), 1))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def preview_node_input(self, pipeline: dict[str, Any], target_node_id: str, limit: int = 100, page: int = 1) -> dict[str, Any]:
        incoming = [edge for edge in pipeline.get("edges", []) if edge.get("target") == target_node_id]
        if len(incoming) <= 1 and not (incoming and incoming[0].get("sourceHandle")):
            target = incoming[0]["source"] if incoming else target_node_id
            return self.preview_pipeline(pipeline, target, limit, page)
        preview_id = "__multi_input_preview__"
        preview_pipeline = {
            **pipeline,
            "nodes": [*pipeline.get("nodes", []), {"id": preview_id, "pluginId": "transform.merge_inputs", "label": "输入数据", "config": {"mode": "union", "add_source": len(incoming) > 1, "source_field": "数据来源"}}],
            "edges": [*pipeline.get("edges", []), *[{"id": f"__input_{index}", "source": edge["source"], "sourceHandle": edge.get("sourceHandle"), "target": preview_id} for index, edge in enumerate(incoming)]],
        }
        return self.preview_pipeline(preview_pipeline, preview_id, limit, page)

    def pcap_page(self, path: str, page: int = 1, page_size: int = 100, protocol: str = "") -> dict[str, Any]:
        cancel_event = Event()
        with self._preview_lock:
            self._active_preview_cancel = cancel_event
        try:
            from dataworkbench.pcap_index import ensure_pcap_index, pcap_page

            index_path = ensure_pcap_index(path, self._project_root / ".cache" / "pcap", cancel_event)
            result = pcap_page(index_path, page, page_size, protocol)
            payload = PipelineEngine._serialize_frame(result["frame"], {"id": "pcap-page", "pluginId": "input.pcap"}, True)
            payload["stats"].update({"rowCount": result["total"], "page": result["page"], "pageSize": result["pageSize"], "paged": True})
            return {"ok": True, "data": payload}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            with self._preview_lock:
                if self._active_preview_cancel is cancel_event:
                    self._active_preview_cancel = None

    def pcap_sessions(self, path: str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        cancel_event = Event()
        with self._preview_lock:
            self._active_preview_cancel = cancel_event
        try:
            from dataworkbench.pcap_index import ensure_pcap_index, pcap_sessions

            index_path = ensure_pcap_index(path, self._project_root / ".cache" / "pcap", cancel_event)
            result = pcap_sessions(index_path, page, page_size)
            payload = PipelineEngine._serialize_frame(result["frame"], {"id": "pcap-sessions", "pluginId": "ctf.session_group"}, True)
            payload["stats"].update({"rowCount": result["total"], "page": result["page"], "pageSize": result["pageSize"], "paged": True})
            return {"ok": True, "data": payload}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            with self._preview_lock:
                if self._active_preview_cancel is cancel_event:
                    self._active_preview_cancel = None

    def run_pipeline(self, pipeline: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._execute_pipeline(pipeline, False, None, 100)
            return {"ok": True, "data": result, "message": "流程运行完成"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _default_storage_config() -> dict[str, Any]:
        return {
            "mode": "local",
            "mysql": {
                "host": "127.0.0.1", "port": 3306, "username": "root", "password": "",
                "database": "dataworkbench", "table": "projects", "charset": "utf8mb4",
                "timezone": "+08:00", "ssl_mode": "disabled", "connect_timeout": 5,
                "read_timeout": 30, "write_timeout": 30,
            },
        }

    def get_storage_config(self) -> dict[str, Any]:
        defaults = self._default_storage_config()
        if not self._storage_config_path.exists():
            return defaults
        try:
            saved = json.loads(self._storage_config_path.read_text(encoding="utf-8"))
            mode = saved.get("mode") if saved.get("mode") in {"local", "mysql"} else "local"
            return {"mode": mode, "mysql": {**defaults["mysql"], **(saved.get("mysql") or {})}}
        except (OSError, ValueError, TypeError):
            return defaults

    def _prepare_mysql_storage(self, mysql_config: dict[str, Any]) -> dict[str, Any]:
        import pymysql

        database = str(mysql_config.get("database", "")).strip()
        table = str(mysql_config.get("table", "")).strip()
        charset = str(mysql_config.get("charset", "utf8mb4")).strip().lower()
        if charset not in {"utf8mb4", "utf8", "gbk", "latin1"}:
            raise ValueError("不支持的数据库字符集")
        meta_table = f"{table[:59]}_meta"
        quoted_database = quote_mysql_identifier(database, "配置数据库")
        quoted_table = quote_mysql_identifier(table, "配置表")
        quoted_meta_table = quote_mysql_identifier(meta_table, "元数据表")
        root_connection = pymysql.connect(**mysql_connect_kwargs(mysql_config))
        try:
            with root_connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {quoted_database} CHARACTER SET {charset}")
            root_connection.commit()
        finally:
            root_connection.close()
        connection = pymysql.connect(**mysql_connect_kwargs(mysql_config, database=database))
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS {quoted_table} ("
                    "`name` VARCHAR(255) NOT NULL PRIMARY KEY, "
                    "`pipeline` LONGTEXT NOT NULL, "
                    "`created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), "
                    "`updated_at` DATETIME(6) NOT NULL) CHARACTER SET " + charset
                )
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS {quoted_meta_table} ("
                    "`meta_key` VARCHAR(128) NOT NULL PRIMARY KEY, "
                    "`meta_value` TEXT NOT NULL, "
                    "`updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) "
                    f"ON UPDATE CURRENT_TIMESTAMP(6)) CHARACTER SET {charset}"
                )
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema=%s AND table_name=%s AND index_name=%s",
                    (database, table, "idx_updated_at"),
                )
                if int(cursor.fetchone()[0]) == 0:
                    cursor.execute(f"CREATE INDEX `idx_updated_at` ON {quoted_table} (`updated_at`)")
                cursor.execute(
                    f"INSERT INTO {quoted_meta_table} (`meta_key`, `meta_value`) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE `meta_value`=VALUES(`meta_value`)",
                    ("schema_version", "1"),
                )
            connection.commit()
        finally:
            connection.close()
        return {"database": database, "projectTable": table, "metaTable": meta_table, "schemaVersion": 1}

    def test_storage_connection(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            if config.get("mode", "local") == "local":
                self._projects_dir.mkdir(exist_ok=True)
                return {"ok": True, "message": "本地项目目录可用"}
            import pymysql

            mysql_config = {**self._default_storage_config()["mysql"], **(config.get("mysql") or {})}
            connection = pymysql.connect(**mysql_connect_kwargs(mysql_config))
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            finally:
                connection.close()
            return {"ok": True, "message": "MySQL 连接成功，可以进行初始化"}
        except Exception as exc:
            return {"ok": False, "error": f"存储连接失败：{exc}"}

    def _write_storage_config(self, config: dict[str, Any]) -> None:
        temporary = self._storage_config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._storage_config_path)

    def initialize_storage(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            mode = str(config.get("mode", "local"))
            if mode not in {"local", "mysql"}:
                return {"ok": False, "error": "不支持的存储模式"}
            normalized = {"mode": mode, "mysql": {**self._default_storage_config()["mysql"], **(config.get("mysql") or {})}}
            if mode == "local":
                self._projects_dir.mkdir(parents=True, exist_ok=True)
                details = {"directory": str(self._projects_dir)}
                message = "本地存储初始化完成并已保存配置"
            else:
                details = self._prepare_mysql_storage(normalized["mysql"])
                message = f"初始化完成：已创建或校验数据库 {details['database']}、项目表 {details['projectTable']} 和元数据表 {details['metaTable']}"
            self._write_storage_config(normalized)
            return {"ok": True, "config": normalized, "details": details, "message": message}
        except Exception as exc:
            return {"ok": False, "error": f"初始化存储失败：{exc}"}

    def configure_storage(self, config: dict[str, Any]) -> dict[str, Any]:
        mode = str(config.get("mode", "local"))
        if mode not in {"local", "mysql"}:
            return {"ok": False, "error": "不支持的存储模式"}
        normalized = {"mode": mode, "mysql": {**self._default_storage_config()["mysql"], **(config.get("mysql") or {})}}
        tested = self.test_storage_connection(normalized)
        if not tested["ok"]:
            return tested
        self._write_storage_config(normalized)
        return {"ok": True, "config": normalized, "message": "存储模式已保存"}

    def _mysql_storage_values(self) -> tuple[dict[str, Any], str, str]:
        config = self.get_storage_config()["mysql"]
        database = str(config.get("database", "")).strip()
        table = quote_mysql_identifier(config.get("table"), "配置表")
        return config, database, table

    def save_project(self, pipeline: dict[str, Any], name: str = "未命名流程") -> dict[str, Any]:
        safe_name = "".join(char for char in name if char not in '<>:"/\\|?*').strip() or "未命名流程"
        payload = {**pipeline, "name": safe_name, "updatedAt": datetime.now().isoformat()}
        if self.get_storage_config()["mode"] == "mysql":
            import pymysql

            config, database, table = self._mysql_storage_values()
            connection = pymysql.connect(**mysql_connect_kwargs(config, database=database))
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {table} (`name`, `pipeline`, `updated_at`) VALUES (%s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE `pipeline`=VALUES(`pipeline`), `updated_at`=VALUES(`updated_at`)",
                        (safe_name, json.dumps(payload, ensure_ascii=False), datetime.now()),
                    )
                connection.commit()
            finally:
                connection.close()
            return {"ok": True, "path": f"mysql:{safe_name}", "message": f"已保存 {safe_name} 到 MySQL"}
        path = self._projects_dir / f"{safe_name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(path), "message": f"已保存 {safe_name}"}

    def list_projects(self) -> list[dict[str, Any]]:
        if self.get_storage_config()["mode"] == "mysql":
            import pymysql

            config, database, table = self._mysql_storage_values()
            connection = pymysql.connect(**mysql_connect_kwargs(config, database=database))
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT `name`, `updated_at` FROM {table} ORDER BY `updated_at` DESC")
                    return [{"name": name, "path": f"mysql:{name}", "updatedAt": updated_at.isoformat()} for name, updated_at in cursor.fetchall()]
            finally:
                connection.close()
        projects: list[dict[str, Any]] = []
        for path in sorted(self._projects_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            projects.append({"name": path.stem, "path": str(path), "updatedAt": datetime.fromtimestamp(path.stat().st_mtime).isoformat()})
        return projects

    def load_project(self, path: str) -> dict[str, Any]:
        try:
            if path.startswith("mysql:"):
                import pymysql

                name = path.removeprefix("mysql:")
                config, database, table = self._mysql_storage_values()
                connection = pymysql.connect(**mysql_connect_kwargs(config, database=database))
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT `pipeline` FROM {table} WHERE `name`=%s", (name,))
                        row = cursor.fetchone()
                finally:
                    connection.close()
                if not row:
                    return {"ok": False, "error": "数据库中未找到项目"}
                return {"ok": True, "data": json.loads(row[0])}
            return {"ok": True, "data": json.loads(Path(path).read_text(encoding="utf-8"))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def list_mysql_databases(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            items = self._ensure_worker().submit(list_mysql_databases_job, config).result(timeout=20) if self._use_worker else list_mysql_databases_job(config)
            return {"ok": True, "items": items, "message": f"已读取 {len(items)} 个数据库"}
        except Exception as exc:
            return {"ok": False, "items": [], "error": f"MySQL 连接失败：{exc}"}

    def list_mysql_tables(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            database = str(config.get("database", "")).strip()
            if not database:
                return {"ok": False, "items": [], "error": "请先选择数据库"}
            items = self._ensure_worker().submit(list_mysql_tables_job, config).result(timeout=20) if self._use_worker else list_mysql_tables_job(config)
            return {"ok": True, "items": items, "message": f"已读取 {len(items)} 张表"}
        except Exception as exc:
            return {"ok": False, "items": [], "error": f"读取数据表失败：{exc}"}

    def pick_file(self, extensions: list[str] | None = None) -> dict[str, Any]:
        if self._window is None:
            return {"ok": False, "error": "窗口尚未初始化"}
        patterns = ";".join(f"*.{extension}" for extension in (extensions or ["csv", "xlsx", "txt", "log", "evtx", "json", "jsonl", "db", "sqlite", "pcap", "pcapng"]))
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=(f"支持的数据文件 ({patterns})", "所有文件 (*.*)"))
        return {"ok": True, "path": result[0] if result else ""}

    def pick_save_file(self, extension: str = "csv") -> dict[str, Any]:
        if self._window is None:
            return {"ok": False, "error": "窗口尚未初始化"}
        result = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"处理结果.{extension}", file_types=(f"{extension.upper()} 文件 (*.{extension})", "所有文件 (*.*)"))
        return {"ok": True, "path": result[0] if result else ""}
