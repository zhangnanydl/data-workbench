from __future__ import annotations

import base64
import hashlib
import os
from typing import Any
from urllib.parse import quote, unquote

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


def _fields(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


class FilterPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.filter", name="过滤", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按字段条件筛选数据行", icon="funnel", color="#14b8a6", category="筛选与字段",
        config_fields=(
            ConfigField("field", "字段", "column", required=True),
            ConfigField("operator", "运算符", "select", default="equals", options=[
                {"label": "等于", "value": "equals"}, {"label": "不等于", "value": "not_equals"},
                {"label": "包含", "value": "contains"}, {"label": "大于", "value": "greater"},
                {"label": "大于等于", "value": "greater_equal"}, {"label": "小于", "value": "less"},
                {"label": "小于等于", "value": "less_equal"},
                {"label": "为空", "value": "is_null"}, {"label": "非空", "value": "not_null"},
            ]),
            ConfigField("value", "比较值", default=""),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        field, operator, value = config["field"], config.get("operator", "equals"), config.get("value")
        column = pl.col(field)
        if operator == "equals":
            expression = column.cast(pl.String) == str(value)
        elif operator == "not_equals":
            expression = column.cast(pl.String) != str(value)
        elif operator == "contains":
            expression = column.cast(pl.String).str.contains(str(value), literal=True)
        elif operator == "greater":
            expression = column.cast(pl.Float64, strict=False) > float(value)
        elif operator == "greater_equal":
            expression = column.cast(pl.Float64, strict=False) >= float(value)
        elif operator == "less":
            expression = column.cast(pl.Float64, strict=False) < float(value)
        elif operator == "less_equal":
            expression = column.cast(pl.Float64, strict=False) <= float(value)
        elif operator == "is_null":
            expression = column.is_null()
        elif operator == "not_null":
            expression = column.is_not_null()
        else:
            raise ValueError(f"不支持的过滤运算符: {operator}")
        return frame.filter(expression)


class SelectColumnsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.select_columns", name="选择显示列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="只保留需要查看或导出的字段", icon="columns", color="#3b82f6", category="筛选与字段",
        config_fields=(
            ConfigField("columns", "显示哪些列", "columns", required=True, help_text="字段会从上游数据自动读取"),
            ConfigField("mode", "处理方式", "select", default="keep", options=[{"label": "只保留选中的列", "value": "keep"}, {"label": "隐藏选中的列", "value": "drop"}]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        selected = [field for field in _fields(config.get("columns")) if field in frame.columns]
        if not selected:
            raise ValueError("请至少选择一个字段")
        return frame.select(selected) if config.get("mode", "keep") == "keep" else frame.drop(selected)


class FieldMappingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.mapping", name="字段映射", kind=PluginKind.TRANSFORM, group="数据处理",
        description="重命名字段或映射字段值", icon="text-t", color="#22c55e", category="字段转换",
        config_fields=(
            ConfigField("source_field", "原字段", "column", required=True),
            ConfigField("target_field", "新字段名", required=True),
            ConfigField("value_map", "值替换规则（可选）", "value_map", default=[], help_text="直接填写原值和替换后的值；未配置的内容保持不变"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        import json

        frame = self.require_input(inputs)
        source, target = config["source_field"], config["target_field"]
        mapping = config.get("value_map", {})
        if isinstance(mapping, str):
            mapping = json.loads(mapping or "{}")
        if isinstance(mapping, list):
            mapping = {
                str(rule.get("source_value", "")): str(rule.get("target_value", ""))
                for rule in mapping
                if isinstance(rule, dict) and str(rule.get("source_value", "")) != ""
            }
        if not isinstance(mapping, dict):
            raise ValueError("值替换规则格式无效")
        expression = pl.col(source).cast(pl.String).replace(mapping).alias(target)
        result = frame.with_columns(expression)
        return result.drop(source) if target != source else result


class RenameColumnPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.rename_column", name="重命名列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="为一个字段设置更容易理解的新列名", icon="text-t", color="#16a34a", category="字段转换",
        config_fields=(
            ConfigField("source_field", "原列名", "column", required=True),
            ConfigField("target_field", "新列名", required=True, placeholder="例如：用户手机号"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source, target = str(config["source_field"]), str(config["target_field"]).strip()
        if target in frame.columns and target != source:
            raise ValueError(f"新列名已存在: {target}")
        return frame.rename({source: target})


class SplitColumnPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.split_column", name="分列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="根据分隔符把一个字段拆成多个新列", icon="columns", color="#0d9488", category="字段转换",
        config_fields=(
            ConfigField("source_field", "需要分列的字段", "column", required=True),
            ConfigField("delimiter", "分隔符", required=True, placeholder="例如：, 或 -"),
            ConfigField("output_fields", "拆分后的列名", "column_names", default=["第1列", "第2列"], required=True, help_text="至少设置两列；可继续添加并逐列重命名"),
            ConfigField("keep_source", "保留原列", "boolean", default=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source, delimiter = str(config["source_field"]), str(config["delimiter"])
        output_fields = _fields(config.get("output_fields"))
        if not delimiter:
            raise ValueError("分隔符不能为空")
        if len(output_fields) < 2:
            raise ValueError("分列至少需要设置两个新列名")
        if len(set(output_fields)) != len(output_fields):
            raise ValueError("拆分后的列名不能重复")
        conflicts = [name for name in output_fields if name in frame.columns]
        if conflicts:
            raise ValueError(f"新列名已存在: {', '.join(conflicts)}")
        parts = pl.col(source).cast(pl.String).str.split(delimiter)
        result = frame.with_columns([parts.list.get(index, null_on_oob=True).alias(name) for index, name in enumerate(output_fields)])
        return result if bool(config.get("keep_source", True)) else result.drop(source)


class TypeConvertPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.convert", name="类型转换", kind=PluginKind.TRANSFORM, group="数据处理",
        description="将字段转换为指定的数据类型", icon="arrows-left-right", color="#64748b", category="字段转换",
        config_fields=(ConfigField("field", "字段", "column", required=True), ConfigField("target_type", "目标类型", "select", default="string", options=[{"label": "文本", "value": "string"}, {"label": "整数", "value": "integer"}, {"label": "小数", "value": "float"}, {"label": "日期时间", "value": "datetime"}, {"label": "布尔", "value": "boolean"}]), ConfigField("strict", "严格模式", "boolean", default=False)),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        types = {"string": pl.String, "integer": pl.Int64, "float": pl.Float64, "datetime": pl.Datetime, "boolean": pl.Boolean}
        return frame.with_columns(pl.col(config["field"]).cast(types[config.get("target_type", "string")], strict=bool(config.get("strict", False))))


class MaskPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.mask", name="数据脱敏", kind=PluginKind.TRANSFORM, group="数据处理",
        description="遮盖手机号、身份证等敏感字段", icon="lock", color="#6d5dfc", category="安全与隐私",
        config_fields=(ConfigField("fields", "选择字段", "columns", default="手机号", required=True), ConfigField("keep_start", "保留前几位", "number", default=3), ConfigField("keep_end", "保留后几位", "number", default=4), ConfigField("mask_char", "遮盖字符", default="*")),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        start = max(0, int(config.get("keep_start", 3)))
        end = max(0, int(config.get("keep_end", 4)))
        mask_char = str(config.get("mask_char", "*"))[:1] or "*"

        def mask(value: Any) -> str | None:
            if value is None:
                return None
            text = str(value)
            if len(text) <= start + end:
                return mask_char * len(text)
            suffix = text[-end:] if end > 0 else ""
            return text[:start] + mask_char * (len(text) - start - end) + suffix

        expressions = [pl.col(field).map_elements(mask, return_dtype=pl.String).alias(field) for field in _fields(config.get("fields")) if field in frame.columns]
        return frame.with_columns(expressions)


class GroupAggregatePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.group", name="分组聚合", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按字段分组，并一次完成多项计数、求和、平均等统计", icon="users-three", color="#f59e0b", category="聚合与结构",
        config_fields=(
            ConfigField("group_by", "分组字段", "columns", required=True),
            ConfigField("aggregate_rules", "统计规则", "aggregate_rules", default=[{"operation": "count", "field": "", "output_name": "人数"}], required=True, help_text="可同时添加人数、平均分、总分、最大值等多项指标"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        groups = _fields(config["group_by"])
        rules = config.get("aggregate_rules")
        if not isinstance(rules, list) or not rules:
            rules = [{"operation": config.get("operation", "count"), "field": config.get("aggregate_field", ""), "output_name": config.get("output_name", "数量")}]
        expressions: list[pl.Expr] = []
        output_names: set[str] = set()
        for index, rule in enumerate(rules, start=1):
            operation = str(rule.get("operation", "count"))
            field = str(rule.get("field", "") or "")
            output = str(rule.get("output_name", "") or f"统计{index}").strip()
            if output in output_names or output in groups:
                raise ValueError(f"统计结果列名重复: {output}")
            output_names.add(output)
            if operation == "count":
                expression = pl.len()
            else:
                if not field or field not in frame.columns:
                    raise ValueError(f"统计规则“{output}”需要选择有效字段")
                column = pl.col(field)
                if operation == "count_non_null":
                    expression = column.count()
                elif operation == "count_distinct":
                    expression = column.n_unique()
                elif operation in {"sum", "mean", "median"}:
                    expression = getattr(column.cast(pl.Float64, strict=False), operation)()
                elif operation in {"min", "max", "first", "last"}:
                    expression = getattr(column, operation)()
                else:
                    raise ValueError(f"不支持的聚合方式: {operation}")
            expressions.append(expression.alias(output))
        return frame.group_by(groups, maintain_order=True).agg(expressions)


class MergeInputsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.merge_inputs", name="多路数据合并", kind=PluginKind.TRANSFORM, group="数据处理",
        description="把两个或更多上游节点的数据按行、共同字段或横向列合并", icon="rows", color="#2563eb", category="聚合与结构", accepts_multiple=True,
        config_fields=(
            ConfigField("mode", "合并方式", "select", default="union", options=[
                {"label": "按列名纵向追加（推荐）", "value": "union"},
                {"label": "只保留共同字段后追加", "value": "intersection"},
                {"label": "按行号横向拼接", "value": "horizontal"},
            ]),
            ConfigField("add_source", "增加来源列", "boolean", default=False),
            ConfigField("source_field", "来源列名称", default="数据来源"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        if not inputs:
            raise ValueError("多路数据合并至少需要连接一个上游节点")
        mode = str(config.get("mode", "union"))
        labels = context.variables.get("direct_parent_labels") or [f"输入{index + 1}" for index in range(len(inputs))]
        frames = inputs
        if bool(config.get("add_source", False)):
            source_field = str(config.get("source_field", "数据来源") or "数据来源").strip()
            frames = [frame.with_columns(pl.lit(str(labels[index])).alias(source_field)) for index, frame in enumerate(inputs)]
        # Input preview uses this plugin as an internal pass-through so a named
        # branch handle (for example "matched") is preserved for one parent.
        if len(frames) == 1:
            return frames[0]
        if mode == "union":
            return pl.concat(frames, how="diagonal_relaxed")
        if mode == "intersection":
            common = [column for column in frames[0].columns if all(column in frame.columns for frame in frames[1:])]
            if not common:
                raise ValueError("上游数据没有共同字段")
            return pl.concat([frame.select(common) for frame in frames], how="vertical_relaxed")
        if mode == "horizontal":
            renamed: list[pl.DataFrame] = []
            used: set[str] = set()
            for input_index, frame in enumerate(frames, start=1):
                names: dict[str, str] = {}
                for column in frame.columns:
                    candidate = column
                    suffix = 2
                    while candidate in used:
                        candidate = f"{column}_{input_index}" if suffix == 2 else f"{column}_{input_index}_{suffix}"
                        suffix += 1
                    names[column] = candidate
                    used.add(candidate)
                renamed.append(frame.rename(names))
            return pl.concat(renamed, how="horizontal")
        raise ValueError(f"不支持的合并方式: {mode}")


class DeduplicatePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.deduplicate", name="数据去重", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按一个或多个字段删除重复数据", icon="squares-four", color="#0d9488", category="筛选与字段",
        config_fields=(
            ConfigField("fields", "去重依据字段", "columns", default=[], help_text="不选择字段时比较整行内容"),
            ConfigField("keep", "重复时保留", "select", default="first", options=[
                {"label": "保留第一条", "value": "first"}, {"label": "保留最后一条", "value": "last"}, {"label": "重复项全部删除", "value": "none"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        fields = [field for field in _fields(config.get("fields")) if field in frame.columns]
        return frame.unique(subset=fields or None, keep=str(config.get("keep", "first")), maintain_order=True)


class MergeRowsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.merge_rows", name="合并为一行", kind=PluginKind.TRANSFORM, group="数据处理",
        description="只保留选中的列，将每列全部内容合并为最终一行", icon="rows", color="#8b5cf6", category="聚合与结构",
        config_fields=(
            ConfigField("fields", "需要合并的列", "columns", required=True, help_text="其他列会被删除，最终结果严格只保留一行"),
            ConfigField("separator", "行内容分隔符", default=",", placeholder="例如：, 或换行符"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        selected = [field for field in _fields(config.get("fields")) if field in frame.columns]
        if not selected:
            raise ValueError("请至少选择一个需要合并的列")
        separator = str(config.get("separator", ","))
        return pl.DataFrame({
            field: [separator.join("" if value is None else str(value) for value in frame[field].to_list())]
            for field in selected
        })


class ReplacePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.replace", name="文本检索替换", kind=PluginKind.TRANSFORM, group="数据处理",
        description="替换一个或多个字段中的文字", icon="arrows-left-right", color="#0ea5e9", category="文本处理",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("search", "查找内容", required=True),
            ConfigField("replacement", "替换为", default=""),
            ConfigField("regex", "使用正则表达式", "boolean", default=False),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        expressions = [
            pl.col(field).cast(pl.String).str.replace_all(
                str(config["search"]), str(config.get("replacement", "")), literal=not bool(config.get("regex", False))
            ).alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ]
        return frame.with_columns(expressions)


class TrimPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.trim", name="去除空格", kind=PluginKind.TRANSFORM, group="数据处理",
        description="去除文本开头、结尾或两端的空白字符", icon="text-aa", color="#0891b2", category="文本处理",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("mode", "处理位置", "select", default="both", options=[
                {"label": "两端", "value": "both"}, {"label": "仅开头", "value": "start"}, {"label": "仅结尾", "value": "end"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        mode = config.get("mode", "both")
        method = {"both": "strip_chars", "start": "strip_chars_start", "end": "strip_chars_end"}.get(mode)
        if not method:
            raise ValueError(f"不支持的空格处理方式: {mode}")
        return frame.with_columns([
            getattr(pl.col(field).cast(pl.String).str, method)().alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class ConcatColumnsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.concat_columns", name="合并列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="把多个字段按连接符拼接成一个新字段", icon="rows", color="#0f766e", category="文本处理",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("separator", "连接符", default=""),
            ConfigField("output_name", "新列名", default="合并结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        fields = [field for field in _fields(config.get("fields")) if field in frame.columns]
        if not fields:
            raise ValueError("请至少选择一个字段")
        return frame.with_columns(pl.concat_str(fields, separator=str(config.get("separator", "")), ignore_nulls=True).alias(str(config["output_name"])))


class UppercasePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.uppercase", name="转大写", kind=PluginKind.TRANSFORM, group="数据处理",
        description="将选中字段的英文字母转为大写", icon="text-aa", color="#0284c7", category="文本处理",
        config_fields=(ConfigField("fields", "选择字段", "columns", required=True),),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        return frame.with_columns([
            pl.col(field).cast(pl.String).str.to_uppercase().alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class LowercasePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.lowercase", name="转小写", kind=PluginKind.TRANSFORM, group="数据处理",
        description="将选中字段的英文字母转为小写", icon="text-aa", color="#0369a1", category="文本处理",
        config_fields=(ConfigField("fields", "选择字段", "columns", required=True),),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        return frame.with_columns([
            pl.col(field).cast(pl.String).str.to_lowercase().alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class Base64Plugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.base64", name="Base64 编解码", kind=PluginKind.TRANSFORM, group="数据处理",
        description="对文本字段进行 Base64 编码或解码", icon="text-t", color="#8b5cf6", category="加密与编码",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("operation", "操作", "select", default="encode", options=[
                {"label": "编码", "value": "encode"}, {"label": "解码", "value": "decode"},
            ]),
            ConfigField("encoding", "字符编码", default="utf-8"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        operation, encoding = config.get("operation", "encode"), str(config.get("encoding", "utf-8"))

        def convert(value: Any) -> str | None:
            if value is None:
                return None
            if operation == "encode":
                return base64.b64encode(str(value).encode(encoding)).decode("ascii")
            if operation == "decode":
                try:
                    return base64.b64decode(str(value), validate=True).decode(encoding)
                except Exception as exc:
                    raise ValueError("Base64 内容或字符编码无效") from exc
            raise ValueError(f"不支持的 Base64 操作: {operation}")

        return frame.with_columns([
            pl.col(field).map_elements(convert, return_dtype=pl.String).alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class UrlCodecPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.url_codec", name="URL 编解码", kind=PluginKind.TRANSFORM, group="数据处理",
        description="对网址、查询参数或普通文本进行 URL 编码和解码", icon="network", color="#9333ea", category="加密与编码",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("operation", "操作", "select", default="encode", options=[
                {"label": "编码", "value": "encode"}, {"label": "解码", "value": "decode"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        operation = config.get("operation", "encode")

        def convert(value: Any) -> str | None:
            if value is None:
                return None
            if operation == "encode":
                return quote(str(value), safe="")
            if operation == "decode":
                return unquote(str(value))
            raise ValueError(f"不支持的 URL 操作: {operation}")

        return frame.with_columns([
            pl.col(field).map_elements(convert, return_dtype=pl.String).alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class Md5Plugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.md5", name="MD5 摘要", kind=PluginKind.TRANSFORM, group="数据处理",
        description="生成不可逆的 MD5 摘要，可添加盐值", icon="lock", color="#a855f7", category="加密与编码",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("salt", "盐值（可选）", default="", help_text="盐值会加在原内容前面"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        salt = str(config.get("salt", ""))

        def digest(value: Any) -> str | None:
            return None if value is None else hashlib.md5(f"{salt}{value}".encode("utf-8")).hexdigest()

        return frame.with_columns([
            pl.col(field).map_elements(digest, return_dtype=pl.String).alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


class AesPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.aes", name="AES 对称加密", kind=PluginKind.TRANSFORM, group="数据处理",
        description="使用同一密钥进行 AES-256-GCM 加密或解密", icon="lock", color="#7c3aed", category="加密与编码",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("operation", "操作", "select", default="encrypt", options=[
                {"label": "加密", "value": "encrypt"}, {"label": "解密", "value": "decrypt"},
            ]),
            ConfigField("key", "密钥", "password", required=True, help_text="输入任意口令，内部自动派生 AES-256 密钥"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        frame = self.require_input(inputs)
        operation = config.get("operation", "encrypt")
        cipher = AESGCM(hashlib.sha256(str(config["key"]).encode("utf-8")).digest())

        def convert(value: Any) -> str | None:
            if value is None:
                return None
            if operation == "encrypt":
                nonce = os.urandom(12)
                return base64.b64encode(nonce + cipher.encrypt(nonce, str(value).encode("utf-8"), None)).decode("ascii")
            if operation == "decrypt":
                try:
                    payload = base64.b64decode(str(value), validate=True)
                    return cipher.decrypt(payload[:12], payload[12:], None).decode("utf-8")
                except Exception as exc:
                    raise ValueError("AES 密文或密钥无效") from exc
            raise ValueError(f"不支持的 AES 操作: {operation}")

        return frame.with_columns([
            pl.col(field).map_elements(convert, return_dtype=pl.String).alias(field)
            for field in _fields(config.get("fields")) if field in frame.columns
        ])


TRANSFORM_PLUGINS = [
    FilterPlugin, SelectColumnsPlugin, FieldMappingPlugin, RenameColumnPlugin, SplitColumnPlugin,
    TypeConvertPlugin, MaskPlugin, GroupAggregatePlugin, MergeInputsPlugin, DeduplicatePlugin, MergeRowsPlugin, ReplacePlugin, TrimPlugin,
    ConcatColumnsPlugin, UppercasePlugin, LowercasePlugin, Base64Plugin, UrlCodecPlugin, Md5Plugin, AesPlugin,
]
