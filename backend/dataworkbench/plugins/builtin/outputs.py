from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.mysql_utils import mysql_advanced_config_fields, mysql_sqlalchemy_engine, quote_mysql_identifier
from dataworkbench.plugins.base import DataPlugin


class FileOutputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="output.file", name="Excel / CSV / TXT", kind=PluginKind.OUTPUT, group="数据输出",
        description="导出为 Excel、CSV 或文本文件", icon="file-arrow-down", color="#10b981",
        config_fields=(ConfigField("path", "输出路径", "save_file", required=True), ConfigField("format", "输出格式", "select", default="csv", options=[{"label": "CSV", "value": "csv"}, {"label": "Excel", "value": "xlsx"}, {"label": "TXT", "value": "txt"}]), ConfigField("delimiter", "分隔符", default=","), ConfigField("encoding", "字符编码", default="utf-8")),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview:
            return frame
        path = Path(config["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        output_format = config.get("format", path.suffix.lower().lstrip(".") or "csv")
        temporary = path.with_name(f".{path.stem}.part{path.suffix}")
        try:
            if output_format == "xlsx":
                pd.DataFrame(frame.to_dicts()).to_excel(temporary, index=False)
            else:
                frame.write_csv(temporary, separator=config.get("delimiter", ","))
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return frame


class JsonOutputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="output.json", name="JSON / JSONL 导出", kind=PluginKind.OUTPUT, group="数据输出",
        description="完整导出JSON数组或逐行JSON，适合日志和安全工具交换数据", icon="file-arrow-down", color="#f97316",
        config_fields=(
            ConfigField("path", "输出路径", "save_file", required=True),
            ConfigField("format", "输出格式", "select", default="jsonl", options=[{"label": "JSON Lines（大数据推荐）", "value": "jsonl"}, {"label": "JSON 数组", "value": "json"}]),
            ConfigField("pretty", "JSON美化缩进", "boolean", default=False),
            ConfigField("encoding", "字符编码", "select", default="utf-8", options=[{"label": "UTF-8", "value": "utf-8"}, {"label": "GBK", "value": "gbk"}]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview:
            return frame
        path = Path(config["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.part{path.suffix}")
        encoding = str(config.get("encoding", "utf-8"))
        try:
            with temporary.open("w", encoding=encoding, newline="") as handle:
                if config.get("format", "jsonl") == "jsonl":
                    for row in frame.iter_rows(named=True):
                        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                else:
                    json.dump(frame.to_dicts(), handle, ensure_ascii=False, default=str, indent=2 if config.get("pretty", False) else None)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return frame


class SQLiteOutputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="output.sqlite", name="SQLite 写入", kind=PluginKind.OUTPUT, group="数据输出",
        description="写入本地SQLite数据库，可创建新文件和数据表", icon="database", color="#0f766e",
        config_fields=(
            ConfigField("path", "数据库文件", "save_file", required=True),
            ConfigField("table", "数据表名称", default="result", required=True),
            ConfigField("mode", "表已存在时", "select", default="replace", options=[
                {"label": "覆盖表", "value": "replace"}, {"label": "追加数据", "value": "append"}, {"label": "报错并停止", "value": "fail"},
            ]),
            ConfigField("batch_size", "每批写入行数", "number", default=1000),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview:
            return frame
        path = Path(config["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        table = str(config.get("table", "")).strip()
        if not table:
            raise ValueError("SQLite数据表名称不能为空")
        with sqlite3.connect(str(path)) as connection:
            pd.DataFrame(frame.to_dicts()).to_sql(
                table, connection, if_exists=str(config.get("mode", "replace")), index=False,
                chunksize=max(1, int(config.get("batch_size", 1000) or 1000)), method="multi",
            )
        return frame


class MySQLOutputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="output.mysql", name="MySQL 写入", kind=PluginKind.OUTPUT, group="数据输出",
        description="选择已有库表，或手写名称自动创建后批量写入", icon="database", color="#f97316",
        config_fields=(
            ConfigField("host", "主机", default="127.0.0.1", required=True), ConfigField("port", "端口", "number", default=3306),
            ConfigField("username", "用户名", default="root", required=True), ConfigField("password", "密码", "password", required=True),
            ConfigField("target_mode", "目标配置方式", "select", default="existing", options=[
                {"label": "选择已有数据库和表", "value": "existing"}, {"label": "手写名称并自动创建", "value": "manual"},
            ]),
            ConfigField("database", "已有数据库", "mysql_database"), ConfigField("table", "已有数据表", "mysql_table"),
            ConfigField("database_manual", "新数据库名称", default="ctf_data", placeholder="不存在时自动创建"),
            ConfigField("table_manual", "新数据表名称", default="result", placeholder="不存在时根据字段自动创建"),
            ConfigField("mode", "表已存在时", "select", default="append", options=[{"label": "追加数据", "value": "append"}, {"label": "覆盖表", "value": "replace"}, {"label": "报错并停止", "value": "fail"}]),
            ConfigField("batch_size", "每批写入行数（不是总数）", "number", default=1000,
                        help_text="例如 10000 行会按 1000 行一批连续写入 10 批，最终数据不会截断"),
        ) + mysql_advanced_config_fields(ConfigField),
    )

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors = super().validate(config)
        if config.get("target_mode", "existing") == "manual":
            if not str(config.get("database_manual", "")).strip(): errors.append("新数据库名称不能为空")
            if not str(config.get("table_manual", "")).strip(): errors.append("新数据表名称不能为空")
        else:
            if not str(config.get("database", "")).strip(): errors.append("请选择已有数据库")
            if not str(config.get("table", "")).strip(): errors.append("请选择已有数据表")
        return errors

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview:
            return frame
        target_mode = config.get("target_mode", "existing")
        if target_mode == "manual":
            database, table = str(config["database_manual"]).strip(), str(config["table_manual"]).strip()
            from sqlalchemy import text

            server_engine = mysql_sqlalchemy_engine(config)
            try:
                database_sql = quote_mysql_identifier(database, "数据库名称")
                charset = str(config.get("charset", "utf8mb4"))
                with server_engine.begin() as connection:
                    connection.execute(text(f"CREATE DATABASE IF NOT EXISTS {database_sql} CHARACTER SET {charset}"))
            finally:
                server_engine.dispose()
        else:
            database, table = str(config["database"]).strip(), str(config["table"]).strip()
        quote_mysql_identifier(table, "数据表名称")
        engine = mysql_sqlalchemy_engine(config, database=database)
        try:
            from sqlalchemy import inspect, text

            mode = str(config.get("mode", "append"))
            batch_size = max(1, int(config.get("batch_size", 1000) or 1000))
            table_sql = quote_mysql_identifier(table, "数据表名称")
            callback = context.variables.get("progress_callback")
            cancel_event = context.variables.get("cancel_event")
            node_index = int(context.variables.get("current_node_index", 0))
            node_count = max(1, int(context.variables.get("current_node_count", 1)))
            node_id = str(context.variables.get("current_node_id", ""))
            node_label = str(context.variables.get("current_node_label", "MySQL 写入"))
            batch_count = (frame.height + batch_size - 1) // batch_size
            if callable(callback):
                callback({
                    "status": "running", "phase": "writing",
                    "percent": round(node_index / node_count * 100, 1),
                    "nodeIndex": node_index + 1, "nodeCount": node_count,
                    "currentNodeId": node_id, "currentNode": node_label,
                    "processedRows": 0, "outputRows": 0, "totalRows": frame.height,
                    "batchIndex": 0, "batchCount": batch_count, "batchSize": batch_size,
                    "detail": f"正在连接并准备写入 {frame.height:,} 行，共 {batch_count} 批",
                })
            before_rows = 0
            if mode == "append" and inspect(engine).has_table(table):
                with engine.connect() as connection:
                    before_rows = int(connection.execute(text(f"SELECT COUNT(*) FROM {table_sql}")).scalar_one())

            if frame.is_empty():
                pd.DataFrame(columns=frame.columns).to_sql(table, engine, if_exists=mode, index=False, method="multi")
            else:
                with engine.begin() as connection:
                    for batch_index, offset in enumerate(range(0, frame.height, batch_size), 1):
                        if cancel_event is not None and cancel_event.is_set():
                            raise RuntimeError("任务已由用户停止，当前事务已回滚")
                        batch = frame.slice(offset, batch_size)
                        pd.DataFrame(batch.to_dicts()).to_sql(
                            table, connection, if_exists=mode if offset == 0 else "append",
                            index=False, chunksize=batch_size, method="multi",
                        )
                        if callable(callback):
                            written_rows = min(offset + batch.height, frame.height)
                            callback({
                                "status": "running", "phase": "writing",
                                "percent": round((node_index + written_rows / frame.height) / node_count * 100, 1),
                                "nodeIndex": node_index + 1, "nodeCount": node_count,
                                "currentNodeId": node_id, "currentNode": node_label,
                                "processedRows": written_rows, "outputRows": written_rows,
                                "totalRows": frame.height, "batchSize": batch_size,
                                "batchIndex": batch_index, "batchCount": batch_count,
                                "detail": f"已完成第 {batch_index}/{batch_count} 批，写入 {written_rows:,}/{frame.height:,} 行",
                            })

            with engine.connect() as connection:
                after_rows = int(connection.execute(text(f"SELECT COUNT(*) FROM {table_sql}")).scalar_one())
            expected_rows = before_rows + frame.height if mode == "append" else frame.height
            if after_rows < expected_rows or (mode != "append" and after_rows != expected_rows):
                raise RuntimeError(f"MySQL 完整性校验失败：预计 {expected_rows} 行，实际 {after_rows} 行")
            context.variables.setdefault("output_write_stats", {})[str(context.variables.get("current_node_id", ""))] = {
                "writtenRows": frame.height, "batchSize": batch_size, "batchCount": (frame.height + batch_size - 1) // batch_size,
                "beforeRows": before_rows, "afterRows": after_rows,
            }
        finally:
            engine.dispose()
        return frame


class PcapIndexOutputPlugin(DataPlugin):
    definition = PluginDefinition(
        id="output.pcap_index", name="PCAP 索引完整导出", kind=PluginKind.OUTPUT, group="数据输出",
        description="直接连接 PCAP 节点，从磁盘索引分批导出全部数据包", icon="file-arrow-down", color="#4f46e5",
        config_fields=(
            ConfigField("path", "输出路径", "save_file", required=True),
            ConfigField("delimiter", "分隔符", default=","),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview:
            return frame
        if context.variables.get("direct_parent_plugins") != ["input.pcap"]:
            raise ValueError("PCAP 索引完整导出必须直接连接 PCAP 输入节点")
        parent_indexes = context.variables.get("pcap_indexes", {})
        if not parent_indexes:
            raise ValueError("未找到 PCAP 磁盘索引")
        from dataworkbench.pcap_index import export_pcap_index

        count = export_pcap_index(next(iter(parent_indexes.values())), config["path"], config.get("delimiter", ","))
        node_id = str(context.variables.get("current_node_id", ""))
        context.variables.setdefault("row_count_overrides", {})[node_id] = count
        return frame


OUTPUT_PLUGINS = [FileOutputPlugin, JsonOutputPlugin, SQLiteOutputPlugin, MySQLOutputPlugin, PcapIndexOutputPlugin]
