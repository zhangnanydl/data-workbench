from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


def _fields(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


class SortRowsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.sort_rows", name="多字段排序", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按一个或多个字段对全部数据稳定排序", icon="arrows-left-right", color="#2563eb", category="筛选与字段",
        config_fields=(
            ConfigField("fields", "排序字段（按选择顺序）", "columns", required=True),
            ConfigField("direction", "排序方向", "select", default="ascending", options=[
                {"label": "升序", "value": "ascending"}, {"label": "降序", "value": "descending"},
            ]),
            ConfigField("nulls_last", "空值排在最后", "boolean", default=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        fields = [field for field in _fields(config.get("fields")) if field in frame.columns]
        if not fields:
            raise ValueError("请至少选择一个有效的排序字段")
        descending = config.get("direction", "ascending") == "descending"
        return frame.sort(fields, descending=descending, nulls_last=bool(config.get("nulls_last", True)), maintain_order=True)


class MissingValuesPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.missing_values", name="缺失值处理", kind=PluginKind.TRANSFORM, group="数据处理",
        description="删除含空值的行，或用固定值、前值、后值填充", icon="squares-four", color="#0f766e", category="筛选与字段",
        config_fields=(
            ConfigField("fields", "处理字段", "columns", required=True),
            ConfigField("mode", "处理方式", "select", default="drop", options=[
                {"label": "删除含空值的行", "value": "drop"}, {"label": "填写固定值", "value": "fixed"},
                {"label": "使用上一条有效值", "value": "forward"}, {"label": "使用下一条有效值", "value": "backward"},
            ]),
            ConfigField("value", "固定值", default="", help_text="仅“填写固定值”时使用；会尽量保持原字段类型"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        fields = [field for field in _fields(config.get("fields")) if field in frame.columns]
        if not fields:
            raise ValueError("请至少选择一个有效字段")
        mode = str(config.get("mode", "drop"))
        if mode == "drop":
            return frame.drop_nulls(fields)
        if mode in {"forward", "backward"}:
            strategy = "forward" if mode == "forward" else "backward"
            return frame.with_columns(pl.col(field).fill_null(strategy=strategy).alias(field) for field in fields)
        if mode == "fixed":
            raw_value = config.get("value", "")
            expressions = []
            for field in fields:
                dtype = frame.schema[field]
                value = pl.lit(raw_value).cast(dtype, strict=False)
                expressions.append(pl.col(field).fill_null(value).alias(field))
            return frame.with_columns(expressions)
        raise ValueError(f"不支持的缺失值处理方式: {mode}")


class JoinInputsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.join_inputs", name="按键关联两路数据", kind=PluginKind.TRANSFORM, group="数据处理",
        description="类似 SQL JOIN，按左右键把两个上游数据表进行关联", icon="rows", color="#4f46e5", category="聚合与结构", accepts_multiple=True,
        config_fields=(
            ConfigField("left_key", "第一路关联字段", "column", required=True),
            ConfigField("right_key", "第二路关联字段", "column", required=True),
            ConfigField("how", "关联方式", "select", default="left", options=[
                {"label": "左关联（保留第一路全部）", "value": "left"}, {"label": "内关联（只保留匹配项）", "value": "inner"},
                {"label": "全关联（保留两路全部）", "value": "full"}, {"label": "半关联（第一路已匹配）", "value": "semi"},
                {"label": "反关联（第一路未匹配）", "value": "anti"},
            ]),
            ConfigField("suffix", "重名字段后缀", default="_右表"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        if len(inputs) != 2:
            raise ValueError("按键关联必须连接且只能连接两个上游节点")
        left, right = inputs
        left_key, right_key = str(config["left_key"]), str(config["right_key"])
        if left_key not in left.columns:
            raise ValueError(f"第一路数据不存在字段: {left_key}")
        if right_key not in right.columns:
            raise ValueError(f"第二路数据不存在字段: {right_key}")
        return left.join(
            right, left_on=left_key, right_on=right_key, how=str(config.get("how", "left")),
            suffix=str(config.get("suffix", "_右表") or "_右表"), maintain_order="left_right",
        )


class RegexExtractPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.regex_extract", name="正则提取", kind=PluginKind.TRANSFORM, group="数据处理",
        description="从日志或文本中按正则表达式提取捕获组", icon="text-t", color="#0891b2", category="文本处理",
        config_fields=(
            ConfigField("source_field", "来源字段", "column", required=True),
            ConfigField("pattern", "正则表达式", required=True, placeholder="例如：user=(\\w+)"),
            ConfigField("group", "捕获组序号", "number", default=1),
            ConfigField("output_name", "结果列名", default="提取结果", required=True),
            ConfigField("all_matches", "提取全部完整匹配并展开为多行", "boolean", default=False),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source, pattern = str(config["source_field"]), str(config["pattern"])
        output = str(config.get("output_name", "提取结果") or "提取结果").strip()
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"正则表达式无效: {exc}") from exc
        column = pl.col(source).cast(pl.String)
        if bool(config.get("all_matches", False)):
            result = frame.with_columns(column.str.extract_all(pattern).alias(output))
            return result.explode(output)
        group = max(0, int(config.get("group", 1) or 0))
        return frame.with_columns(column.str.extract(pattern, group_index=group).alias(output))


def _flatten_json(value: Any, prefix: str = "", depth: int = 0, max_depth: int = 4) -> dict[str, Any]:
    if not isinstance(value, dict) or depth >= max_depth:
        return {prefix.rstrip("."): json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}{key}"
        if isinstance(item, dict) and depth + 1 < max_depth:
            result.update(_flatten_json(item, f"{name}.", depth + 1, max_depth))
        else:
            result[name] = json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else item
    return result


class JsonFlattenPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.json_flatten", name="JSON 展平", kind=PluginKind.TRANSFORM, group="数据处理",
        description="把字段中的 JSON 对象展开成普通列，适合告警详情和嵌套日志", icon="columns", color="#d97706", category="字段转换",
        config_fields=(
            ConfigField("source_field", "JSON 字段", "column", required=True),
            ConfigField("prefix", "新列前缀", default="", placeholder="例如：详情_"),
            ConfigField("max_depth", "最大展开层级", "number", default=4),
            ConfigField("keep_source", "保留原 JSON 字段", "boolean", default=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source = str(config["source_field"])
        prefix = str(config.get("prefix", ""))
        max_depth = min(12, max(1, int(config.get("max_depth", 4) or 4)))
        rows: list[dict[str, Any]] = []
        for row_number, row in enumerate(frame.iter_rows(named=True), 1):
            raw = row.get(source)
            if raw in (None, ""):
                parsed = {}
            elif isinstance(raw, dict):
                parsed = raw
            else:
                try:
                    parsed = json.loads(str(raw))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"第 {row_number} 行不是有效 JSON") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"第 {row_number} 行 JSON 顶层必须是对象")
            flattened = {f"{prefix}{key}": value for key, value in _flatten_json(parsed, max_depth=max_depth).items()}
            base = dict(row)
            if not bool(config.get("keep_source", True)):
                base.pop(source, None)
            base.update(flattened)
            rows.append(base)
        return pl.DataFrame(rows, infer_schema_length=None) if rows else frame


class DateTimeFeaturesPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.datetime_features", name="时间解析与拆分", kind=PluginKind.TRANSFORM, group="数据处理",
        description="解析时间字段并生成年、月、日、小时、星期和 Unix 时间戳", icon="history", color="#7c3aed", category="字段转换",
        config_fields=(
            ConfigField("source_field", "时间字段", "column", required=True),
            ConfigField("format", "时间格式（可选）", default="", placeholder="例如：%Y-%m-%d %H:%M:%S", help_text="留空时自动识别常见格式"),
            ConfigField("output_name", "解析后时间列", default="标准时间", required=True),
            ConfigField("parts", "需要生成的时间字段", "option_selector", default=["年", "月", "日", "小时", "星期", "Unix时间戳"], options=[
                {"label": name, "value": name} for name in ["年", "月", "日", "小时", "分钟", "秒", "星期", "Unix时间戳"]
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source = str(config["source_field"])
        output = str(config.get("output_name", "标准时间") or "标准时间")
        fmt = str(config.get("format", "") or "").strip() or None
        parsed = pl.col(source).cast(pl.String).str.to_datetime(format=fmt, strict=False).alias(output)
        result = frame.with_columns(parsed)
        parts = set(_fields(config.get("parts")))
        expressions: list[pl.Expr] = []
        date_column = pl.col(output).dt
        mapping = {
            "年": date_column.year(), "月": date_column.month(), "日": date_column.day(),
            "小时": date_column.hour(), "分钟": date_column.minute(), "秒": date_column.second(),
            "星期": date_column.weekday(), "Unix时间戳": date_column.epoch("s"),
        }
        for name, expression in mapping.items():
            if name in parts:
                expressions.append(expression.alias(name))
        return result.with_columns(expressions) if expressions else result


class IocExtractPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.ioc_extract", name="IOC 指标提取", kind=PluginKind.TRANSFORM, group="数据处理",
        description="从文本中提取 IP、URL、域名、邮箱和常见哈希，每个指标展开为一行", icon="network", color="#dc2626", category="安全与隐私",
        config_fields=(
            ConfigField("source_field", "文本字段", "column", required=True),
            ConfigField("types", "提取类型", "option_selector", default=["IP", "URL", "域名", "邮箱", "哈希"], required=True, options=[
                {"label": name, "value": name} for name in ["IP", "URL", "域名", "邮箱", "哈希"]
            ]),
            ConfigField("keep_unmatched", "保留未发现指标的原始行", "boolean", default=False),
        ),
    )

    _patterns = {
        "URL": re.compile(r"https?://[^\s\"'<>，。；：、（）【】]+", re.I),
        "邮箱": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "哈希": re.compile(r"\b(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32})\b"),
        "IP": re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"),
        "域名": re.compile(r"(?<![@\w.-])(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}\b", re.I),
    }

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source = str(config["source_field"])
        selected = [name for name in _fields(config.get("types")) if name in self._patterns]
        if not selected:
            raise ValueError("请至少选择一种 IOC 类型")
        output: list[dict[str, Any]] = []
        for row in frame.iter_rows(named=True):
            text = "" if row.get(source) is None else str(row[source])
            found: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for ioc_type in selected:
                for match in self._patterns[ioc_type].finditer(text):
                    value = match.group(0).rstrip(".,;:)，。；：")
                    if ioc_type == "IP":
                        try:
                            ipaddress.ip_address(value)
                        except ValueError:
                            continue
                    item = (ioc_type, value)
                    if item not in seen:
                        seen.add(item)
                        found.append(item)
            if found:
                for ioc_type, value in found:
                    output.append({**row, "IOC类型": ioc_type, "IOC值": value})
            elif bool(config.get("keep_unmatched", False)):
                output.append({**row, "IOC类型": None, "IOC值": None})
        schema = {**frame.schema, "IOC类型": pl.String, "IOC值": pl.String}
        return pl.DataFrame(output, schema=schema, strict=False) if output else pl.DataFrame(schema=schema)


class HashDigestPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.hash_digest", name="SHA 哈希摘要", kind=PluginKind.TRANSFORM, group="数据处理",
        description="生成 SHA-1、SHA-256 或 SHA-512 摘要，支持盐值和新结果列", icon="lock", color="#9333ea", category="加密与编码",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("algorithm", "算法", "select", default="sha256", options=[
                {"label": "SHA-256（推荐）", "value": "sha256"}, {"label": "SHA-512", "value": "sha512"}, {"label": "SHA-1", "value": "sha1"},
            ]),
            ConfigField("salt", "盐值（可选）", default=""),
            ConfigField("suffix", "结果列后缀", default="_哈希", help_text="留空时覆盖原字段"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        algorithm = str(config.get("algorithm", "sha256"))
        if algorithm not in {"sha1", "sha256", "sha512"}:
            raise ValueError(f"不支持的摘要算法: {algorithm}")
        salt, suffix = str(config.get("salt", "")), str(config.get("suffix", "_哈希"))

        def digest(value: Any) -> str | None:
            return None if value is None else hashlib.new(algorithm, f"{salt}{value}".encode("utf-8")).hexdigest()

        expressions = []
        for field in _fields(config.get("fields")):
            if field in frame.columns:
                expressions.append(pl.col(field).map_elements(digest, return_dtype=pl.String).alias(f"{field}{suffix}"))
        if not expressions:
            raise ValueError("请至少选择一个有效字段")
        return frame.with_columns(expressions)


ANALYSIS_PLUGINS = [
    SortRowsPlugin, MissingValuesPlugin, JoinInputsPlugin, RegexExtractPlugin,
    JsonFlattenPlugin, DateTimeFeaturesPlugin, IocExtractPlugin, HashDigestPlugin,
]
