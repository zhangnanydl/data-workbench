from __future__ import annotations

import json
import re
import shlex
import sqlite3
import xml.etree.ElementTree as ET
from itertools import islice
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
from Evtx.Evtx import Evtx

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.mysql_utils import mysql_advanced_config_fields, mysql_sqlalchemy_engine, quote_mysql_identifier
from dataworkbench.plugins.base import DataPlugin


def _normalized_rows_frame(rows: list[dict[str, Any]], empty_columns: list[str] | None = None) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame({column: [] for column in (empty_columns or [])})
    keys = list(dict.fromkeys(key for row in rows for key in row))
    normalized = [{key: row.get(key) for key in keys} for row in rows]
    return pl.from_dicts(normalized, infer_schema_length=None, strict=False)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _normalize_json_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    return {"内容": _normalize_json_value(value)}


def _parse_evtx_xml(xml_text: str, include_xml: bool = False) -> dict[str, Any]:
    namespace = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
    root = ET.fromstring(xml_text)

    def text(path: str) -> str:
        element = root.find(path, namespace)
        return (element.text or "") if element is not None else ""

    provider = root.find("e:System/e:Provider", namespace)
    created = root.find("e:System/e:TimeCreated", namespace)
    security = root.find("e:System/e:Security", namespace)
    execution = root.find("e:System/e:Execution", namespace)
    row: dict[str, Any] = {
        "记录号": text("e:System/e:EventRecordID"),
        "时间": created.attrib.get("SystemTime", "") if created is not None else "",
        "事件ID": text("e:System/e:EventID"),
        "提供程序": provider.attrib.get("Name", "") if provider is not None else "",
        "通道": text("e:System/e:Channel"),
        "计算机": text("e:System/e:Computer"),
        "级别": text("e:System/e:Level"),
        "用户SID": security.attrib.get("UserID", "") if security is not None else "",
        "进程ID": execution.attrib.get("ProcessID", "") if execution is not None else "",
        "线程ID": execution.attrib.get("ThreadID", "") if execution is not None else "",
    }
    event_values: dict[str, Any] = {}
    for index, element in enumerate(root.findall("e:EventData/e:Data", namespace), 1):
        event_values[element.attrib.get("Name") or f"字段{index}"] = element.text or ""
    if event_values:
        row["事件数据"] = json.dumps(event_values, ensure_ascii=False)
        for key, value in event_values.items():
            row[f"数据_{key}"] = value
    if include_xml:
        row["原始XML"] = xml_text
    return row


def _normalize_event_ids(value: Any) -> set[str]:
    items = value if isinstance(value, (list, tuple, set)) else re.split(r"[,，;；\s]+", str(value or ""))
    return {str(item).strip() for item in items if str(item).strip()}


def _preview_source_limit(context: ExecutionContext, default: int = 50_000) -> int | None:
    if not context.preview or not context.variables.get("fast_preview"):
        return None
    node_id = str(context.variables.get("current_node_id", ""))
    estimate = context.variables.get("source_estimates", {}).get(node_id, {})
    if estimate and not estimate.get("large", False):
        return None
    limit = max(1_000, int(context.variables.get("preview_sample_limit", default)))
    context.variables.setdefault("sampled_sources", {})[node_id] = {
        "estimatedRows": estimate.get("estimatedRows"), "sampleLimit": limit,
    }
    return limit


def _mark_database_sample(context: ExecutionContext, total: int, limit: int) -> None:
    node_id = str(context.variables.get("current_node_id", ""))
    context.variables.setdefault("sampled_sources", {})[node_id] = {
        "estimatedRows": total, "sampleLimit": limit,
    }


def _report_source_progress(context: ExecutionContext, processed_rows: int) -> None:
    callback = context.variables.get("progress_callback")
    if callback is None:
        return
    node_id = str(context.variables.get("current_node_id", ""))
    estimate = context.variables.get("source_estimates", {}).get(node_id, {})
    estimated_rows = int(estimate.get("estimatedRows") or 0)
    node_index = int(context.variables.get("current_node_index", 0))
    node_count = max(1, int(context.variables.get("current_node_count", 1)))
    node_fraction = min(processed_rows / estimated_rows, 0.98) if estimated_rows else 0
    callback({
        "status": "running", "phase": "reading", "percent": round((node_index + node_fraction) / node_count * 100, 1),
        "nodeIndex": node_index + 1, "nodeCount": node_count, "currentNodeId": node_id,
        "currentNode": context.variables.get("current_node_label", "读取数据源"),
        "sourceRows": processed_rows, "processedRows": processed_rows, "estimatedRows": estimated_rows or None,
    })


def _set_source_estimated_rows(context: ExecutionContext, total: int) -> None:
    node_id = str(context.variables.get("current_node_id", ""))
    estimate = context.variables.setdefault("source_estimates", {}).setdefault(node_id, {})
    estimate["estimatedRows"] = total
    estimate["large"] = True


def _frames_from_sql_chunks(chunks, context: ExecutionContext) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    processed = 0
    for chunk in chunks:
        frame = pl.from_pandas(chunk)
        frames.append(frame)
        processed += frame.height
        _report_source_progress(context, processed)
    return pl.concat(frames, how="vertical", rechunk=False) if frames else pl.DataFrame()


class DemoInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.demo", name="示例数据", kind=PluginKind.INPUT, group="数据输入",
        description="用于体验流程的内置访问日志", icon="database", color="#3b82f6",
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        rows = [
            {"时间": "2026-08-19 10:15:23", "IP地址": "183.232.231.174", "手机号": "13800138000", "请求方法": "GET", "状态码": 200, "路径": "/api/user/login", "协议": "HTTP"},
            {"时间": "2026-08-19 10:15:25", "IP地址": "183.232.231.174", "手机号": "13800138000", "请求方法": "GET", "状态码": 200, "路径": "/api/user/info", "协议": "HTTP"},
            {"时间": "2026-08-19 10:15:27", "IP地址": "112.25.16.8", "手机号": "18612345678", "请求方法": "POST", "状态码": 200, "路径": "/api/order/create", "协议": "HTTP"},
            {"时间": "2026-08-19 10:15:31", "IP地址": "112.25.16.8", "手机号": "18612345678", "请求方法": "GET", "状态码": 200, "路径": "/api/order/list", "协议": "HTTP"},
            {"时间": "2026-08-19 10:15:33", "IP地址": "221.196.13.12", "手机号": "15987655678", "请求方法": "GET", "状态码": 404, "路径": "/api/product/123", "协议": "HTTP"},
            {"时间": "2026-08-19 10:15:36", "IP地址": "221.196.13.12", "手机号": "15987655678", "请求方法": "GET", "状态码": 200, "路径": "/api/product/list", "协议": "HTTP"},
        ]
        return pl.DataFrame(rows)


class DelimitedInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.csv", name="Excel / CSV", kind=PluginKind.INPUT, group="数据输入",
        description="读取 Excel 或 CSV 表格文件", icon="file-csv", color="#10b981",
        config_fields=(
            ConfigField("path", "文件路径", "file", required=True, placeholder="选择 .xlsx / .csv 文件"),
            ConfigField("delimiter", "CSV 分隔符", "text", default=","),
            ConfigField("encoding", "字符编码", "select", default="utf8", options=[{"label": "UTF-8", "value": "utf8"}, {"label": "GBK", "value": "gbk"}]),
            ConfigField("sheet", "工作表", "text", default="0"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        path = Path(config["path"])
        sample_limit = _preview_source_limit(context)
        if path.suffix.lower() in {".xlsx", ".xls"}:
            data = pd.read_excel(path, sheet_name=config.get("sheet", 0), nrows=sample_limit)
            return pl.from_pandas(data)
        estimate = context.variables.get("source_estimates", {}).get(str(context.variables.get("current_node_id", "")), {})
        if not context.preview and estimate.get("large"):
            reader = pl.scan_csv(
                path, separator=config.get("delimiter", ","), encoding=config.get("encoding", "utf8"),
                infer_schema_length=1000,
            )
            batches: list[pl.DataFrame] = []
            processed = 0
            for batch in reader.collect_batches(chunk_size=50_000, engine="streaming"):
                batches.append(batch)
                processed += batch.height
                _report_source_progress(context, processed)
            return pl.concat(batches, how="vertical", rechunk=False) if batches else pl.DataFrame()
        return pl.read_csv(path, separator=config.get("delimiter", ","), encoding=config.get("encoding", "utf8"), n_rows=sample_limit, infer_schema_length=1000)


class TextInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.text", name="TXT", kind=PluginKind.INPUT, group="数据输入",
        description="按行或分隔符读取文本文件", icon="file-text", color="#14b8a6",
        config_fields=(
            ConfigField("path", "文件路径", "file", required=True),
            ConfigField("delimiter", "分隔符", "text", default=""),
            ConfigField("encoding", "字符编码", "select", default="utf-8", options=[{"label": "UTF-8", "value": "utf-8"}, {"label": "GBK", "value": "gbk"}]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        delimiter = config.get("delimiter")
        sample_limit = _preview_source_limit(context)
        if delimiter:
            return pl.read_csv(config["path"], separator=delimiter, n_rows=sample_limit)
        with Path(config["path"]).open("r", encoding=config.get("encoding", "utf-8"), errors="replace") as handle:
            selected_lines = handle if sample_limit is None else islice(handle, sample_limit)
            lines = [line.rstrip("\r\n") for line in selected_lines]
        return pl.DataFrame({"行号": range(1, len(lines) + 1), "内容": lines})


class SecurityLogInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.log", name="安全日志 LOG", kind=PluginKind.INPUT, group="数据输入",
        description="逐行读取日志，并支持自动、键值对、JSON Lines、分隔符和正则解析", icon="file-text", color="#ef4444",
        config_fields=(
            ConfigField("path", "日志文件", "file", required=True, placeholder="选择 .log / .out / .trace 文件"),
            ConfigField("parse_mode", "解析方式", "select", default="auto", options=[
                {"label": "自动识别（推荐）", "value": "auto"}, {"label": "每行一条", "value": "line"},
                {"label": "键值对 key=value", "value": "key_value"}, {"label": "JSON Lines", "value": "jsonl"},
                {"label": "按分隔符拆列", "value": "delimiter"}, {"label": "正则表达式提取", "value": "regex"},
            ]),
            ConfigField("delimiter", "分隔符", default=",", placeholder="分隔符模式使用，如 | 或 \\t"),
            ConfigField("pattern", "提取正则", "textarea", default="", placeholder="建议使用命名分组，例如 (?P<ip>\\S+)"),
            ConfigField("encoding", "字符编码", "select", default="utf-8", options=[
                {"label": "UTF-8", "value": "utf-8"}, {"label": "GBK", "value": "gbk"}, {"label": "Latin-1", "value": "latin1"},
            ]),
            ConfigField("skip_empty", "忽略空行", "boolean", default=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        mode = str(config.get("parse_mode", "auto"))
        delimiter = str(config.get("delimiter", ",")).replace("\\t", "\t").replace("\\n", "\n")
        pattern_text = str(config.get("pattern", "")).strip()
        pattern = re.compile(pattern_text) if pattern_text else None
        if mode == "regex" and pattern is None:
            raise ValueError("正则提取模式需要填写提取正则")
        rows: list[dict[str, Any]] = []
        limit = _preview_source_limit(context)
        with Path(config["path"]).open("r", encoding=str(config.get("encoding", "utf-8")), errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                content = raw_line.rstrip("\r\n")
                if config.get("skip_empty", True) and not content.strip():
                    continue
                selected_mode = mode
                if mode == "auto":
                    stripped = content.lstrip()
                    selected_mode = "jsonl" if stripped.startswith(("{", "[")) else "key_value" if re.search(r"(?:^|\s)[\w.-]+=", content) else "line"
                row: dict[str, Any]
                if selected_mode == "jsonl":
                    try:
                        row = _normalize_json_record(json.loads(content))
                    except json.JSONDecodeError as exc:
                        row = {"内容": content, "解析错误": str(exc)}
                elif selected_mode == "key_value":
                    row = {}
                    try:
                        tokens = shlex.split(content)
                    except ValueError:
                        tokens = content.split()
                    for token in tokens:
                        if "=" in token:
                            key, value = token.split("=", 1)
                            row[key] = value
                    if not row:
                        row["内容"] = content
                    row["原始内容"] = content
                elif selected_mode == "delimiter":
                    if not delimiter:
                        raise ValueError("按分隔符拆列时，分隔符不能为空")
                    row = {f"列{index}": value for index, value in enumerate(content.split(delimiter), 1)}
                elif selected_mode == "regex":
                    match = pattern.search(content) if pattern else None
                    if match is None:
                        row = {"内容": content, "是否匹配": False}
                    else:
                        values = match.groupdict() or {f"分组{index}": value for index, value in enumerate(match.groups(), 1)}
                        row = {**values, "是否匹配": True}
                else:
                    row = {"内容": content}
                rows.append({"行号": line_number, **row})
                if limit is not None and len(rows) >= limit:
                    break
        return _normalized_rows_frame(rows, ["行号", "内容"])


class JsonInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.json", name="JSON / JSONL", kind=PluginKind.INPUT, group="数据输入",
        description="读取JSON数组、嵌套记录或逐行JSON日志", icon="file-text", color="#f97316",
        config_fields=(
            ConfigField("path", "JSON 文件", "file", required=True),
            ConfigField("format", "文件格式", "select", default="auto", options=[
                {"label": "自动判断", "value": "auto"}, {"label": "JSON", "value": "json"}, {"label": "JSON Lines", "value": "jsonl"},
            ]),
            ConfigField("record_path", "记录路径（可选）", default="", placeholder="例如 data.events"),
            ConfigField("encoding", "字符编码", "select", default="utf-8", options=[{"label": "UTF-8", "value": "utf-8"}, {"label": "GBK", "value": "gbk"}]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        path = Path(config["path"])
        encoding = str(config.get("encoding", "utf-8"))
        file_format = str(config.get("format", "auto"))
        if file_format == "auto":
            file_format = "jsonl" if path.suffix.lower() in {".jsonl", ".ndjson"} else "json"
        limit = _preview_source_limit(context)
        rows: list[dict[str, Any]] = []
        if file_format == "jsonl":
            with path.open("r", encoding=encoding, errors="replace") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    rows.append({"行号": line_number, **_normalize_json_record(json.loads(line))})
                    if limit is not None and len(rows) >= limit:
                        break
        else:
            with path.open("r", encoding=encoding, errors="replace") as handle:
                value: Any = json.load(handle)
            record_path = str(config.get("record_path", "")).strip()
            for key in filter(None, record_path.split(".")):
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"JSON记录路径不存在：{record_path}")
                value = value[key]
            values = value if isinstance(value, list) else [value]
            if limit is not None:
                values = values[:limit]
            rows = [_normalize_json_record(item) for item in values]
        return _normalized_rows_frame(rows, ["内容"])


class EvtxInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.evtx", name="Windows EVTX", kind=PluginKind.INPUT, group="数据输入",
        description="解析Windows事件日志，提取事件ID、时间、提供程序、用户及事件数据", icon="file-text", color="#2563eb",
        config_fields=(
            ConfigField("path", "EVTX 文件", "file", required=True),
            ConfigField("event_ids", "常见安全事件（可选）", "event_id_selector", default=[], options=[
                {"label": "4624 登录成功", "value": "4624", "category": "登录"},
                {"label": "4625 登录失败", "value": "4625", "category": "登录"},
                {"label": "4634 用户注销", "value": "4634", "category": "登录"},
                {"label": "4648 显式凭据登录", "value": "4648", "category": "登录"},
                {"label": "4672 特权登录", "value": "4672", "category": "登录"},
                {"label": "4688 创建进程", "value": "4688", "category": "进程"},
                {"label": "4689 进程退出", "value": "4689", "category": "进程"},
                {"label": "4720 创建用户", "value": "4720", "category": "账号"},
                {"label": "4726 删除用户", "value": "4726", "category": "账号"},
                {"label": "4732 添加本地组成员", "value": "4732", "category": "账号"},
                {"label": "4740 账户被锁定", "value": "4740", "category": "账号"},
                {"label": "4768 Kerberos TGT", "value": "4768", "category": "认证"},
                {"label": "4769 Kerberos服务票据", "value": "4769", "category": "认证"},
                {"label": "4776 NTLM身份验证", "value": "4776", "category": "认证"},
                {"label": "1102 清除审计日志", "value": "1102", "category": "高危"},
                {"label": "7045 安装系统服务", "value": "7045", "category": "高危"},
                {"label": "4104 PowerShell脚本块", "value": "4104", "category": "高危"},
            ], help_text="不勾选时读取全部事件；也可以补充比赛题目中的自定义事件ID"),
            ConfigField("providers", "提供程序包含（可选）", default="", placeholder="例如 Security-Auditing"),
            ConfigField("include_xml", "保留原始 XML", "boolean", default=False),
            ConfigField("max_records", "最多读取记录数", "number", default=0, help_text="0 表示完整读取；填写数字会主动限制计算范围"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        wanted_ids = _normalize_event_ids(config.get("event_ids", []))
        provider_filter = str(config.get("providers", "")).strip().lower()
        configured_max = max(0, int(config.get("max_records", 0) or 0))
        preview_limit = _preview_source_limit(context)
        limit = min(configured_max, preview_limit) if configured_max and preview_limit else configured_max or preview_limit
        rows: list[dict[str, Any]] = []
        with Evtx(str(config["path"])) as log:
            for record in log.records():
                try:
                    row = _parse_evtx_xml(record.xml(), bool(config.get("include_xml", False)))
                except (ET.ParseError, ValueError):
                    continue
                if wanted_ids and str(row.get("事件ID", "")) not in wanted_ids:
                    continue
                if provider_filter and provider_filter not in str(row.get("提供程序", "")).lower():
                    continue
                rows.append(row)
                if limit is not None and len(rows) >= limit:
                    break
        return _normalized_rows_frame(rows, ["记录号", "时间", "事件ID", "提供程序", "通道", "计算机", "事件数据"])


class SQLiteInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.sqlite", name="SQLite 数据库", kind=PluginKind.INPUT, group="数据输入",
        description="读取SQLite、DB或浏览器取证数据库中的数据表", icon="database", color="#0f766e",
        config_fields=(
            ConfigField("path", "数据库文件", "file", required=True, placeholder="选择 .db / .sqlite 文件"),
            ConfigField("table", "数据表", required=True, placeholder="例如 urls、cookies、logins"),
            ConfigField("query", "自定义查询（可选）", "textarea", default="", placeholder="仅支持 SELECT / WITH 查询；留空读取整张表"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        query = str(config.get("query", "")).strip().rstrip(";")
        if query and not re.match(r"^(select|with)\b", query, re.IGNORECASE):
            raise ValueError("SQLite自定义查询只允许 SELECT 或 WITH")
        if not query:
            table = str(config.get("table", "")).strip()
            if not table:
                raise ValueError("请填写SQLite数据表名称")
            query = f'SELECT * FROM "{table.replace(chr(34), chr(34) * 2)}"'
        with sqlite3.connect(str(config["path"])) as connection:
            if context.preview and context.variables.get("fast_preview"):
                total = int(pd.read_sql_query(f"SELECT COUNT(*) AS total FROM ({query}) AS count_query", connection).iloc[0]["total"])
                limit = int(context.variables.get("preview_sample_limit", 50_000))
                if total > limit:
                    _mark_database_sample(context, total, limit)
                    query = f"SELECT * FROM ({query}) AS preview_query LIMIT {limit}"
            elif not context.preview and context.variables.get("source_estimates", {}).get(str(context.variables.get("current_node_id", "")), {}).get("large"):
                total = int(pd.read_sql_query(f"SELECT COUNT(*) AS total FROM ({query}) AS count_query", connection).iloc[0]["total"])
                _set_source_estimated_rows(context, total)
                batch_size = max(1, int(context.variables.get("database_batch_size", 50_000)))
                return _frames_from_sql_chunks(pd.read_sql_query(query, connection, chunksize=batch_size), context)
            return pl.from_pandas(pd.read_sql_query(query, connection))


class MySQLInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.mysql", name="MySQL", kind=PluginKind.INPUT, group="数据输入",
        description="连接 MySQL 并选择数据库和数据表", icon="database", color="#f59e0b",
        config_fields=(
            ConfigField("host", "主机", default="127.0.0.1", required=True), ConfigField("port", "端口", "number", default=3306),
            ConfigField("username", "用户名", default="root", required=True), ConfigField("password", "密码", "password", required=True),
            ConfigField("database", "数据库", "mysql_database", required=True), ConfigField("table", "数据表", "mysql_table", required=True),
            ConfigField("query", "高级 SQL（可选）", "textarea", default="", placeholder="留空时读取所选数据表"),
        ) + mysql_advanced_config_fields(ConfigField),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        query = str(config.get("query", "")).strip().rstrip(";")
        if not query:
            query = f"SELECT * FROM {quote_mysql_identifier(config['table'], '数据表')}"
        engine = mysql_sqlalchemy_engine(config, database=str(config["database"]))
        try:
            with engine.connect() as connection:
                if context.preview and context.variables.get("fast_preview"):
                    total = int(pd.read_sql(f"SELECT COUNT(*) AS total FROM ({query}) AS count_query", connection).iloc[0]["total"])
                    limit = int(context.variables.get("preview_sample_limit", 50_000))
                    if total > limit:
                        _mark_database_sample(context, total, limit)
                        query = f"SELECT * FROM ({query}) AS preview_query LIMIT {limit}"
                elif not context.preview and context.variables.get("source_estimates", {}).get(str(context.variables.get("current_node_id", "")), {}).get("large"):
                    total = int(pd.read_sql(f"SELECT COUNT(*) AS total FROM ({query}) AS count_query", connection).iloc[0]["total"])
                    _set_source_estimated_rows(context, total)
                    batch_size = max(1, int(context.variables.get("database_batch_size", 50_000)))
                    return _frames_from_sql_chunks(pd.read_sql(query, connection, chunksize=batch_size), context)
                return pl.from_pandas(pd.read_sql(query, connection))
        finally:
            engine.dispose()


class PcapInputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="input.pcap", name="PCAP", kind=PluginKind.INPUT, group="数据输入",
        description="建立磁盘索引并分页读取 PCAP/PCAPNG 流量", icon="network", color="#6366f1",
        config_fields=(
            ConfigField("path", "流量包路径", "file", required=True),
            ConfigField("display_filter", "协议过滤", "select", default="", options=[
                {"label": "全部协议", "value": ""}, {"label": "TCP", "value": "TCP"}, {"label": "UDP", "value": "UDP"}, {"label": "ICMP", "value": "ICMP"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        from dataworkbench.pcap_index import ensure_pcap_index, load_all_packets, pcap_page

        cache_dir = Path(context.project_dir) / ".cache" / "pcap"
        index_path = ensure_pcap_index(config["path"], cache_dir)
        node_id = str(context.variables.get("current_node_id", ""))
        context.variables.setdefault("pcap_indexes", {})[node_id] = str(index_path)
        protocol = str(config.get("display_filter", "")).strip().upper()
        direct_preview = context.preview and node_id == str(context.variables.get("preview_target_node_id", ""))
        if direct_preview or context.variables.get("direct_pcap_export"):
            page = int(context.variables.get("preview_page", 1)) if direct_preview else 1
            result = pcap_page(index_path, page, context.preview_limit, protocol)
            context.variables.setdefault("row_count_overrides", {})[node_id] = result["total"]
            if direct_preview:
                context.variables.setdefault("pre_paged_nodes", set()).add(node_id)
            return result["frame"]
        return load_all_packets(index_path, protocol)


INPUT_PLUGINS = [
    DemoInputPlugin, DelimitedInputPlugin, TextInputPlugin, SecurityLogInputPlugin, JsonInputPlugin,
    EvtxInputPlugin, SQLiteInputPlugin, MySQLInputPlugin, PcapInputPlugin,
]
