from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


def _fields(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _require_columns(frame: pl.DataFrame, fields: list[str], label: str = "字段") -> list[str]:
    missing = [field for field in fields if field not in frame.columns]
    if missing:
        raise ValueError(f"{label}不存在: {', '.join(missing)}")
    return fields


def _condition(field: str, operator: str, value: Any) -> pl.Expr:
    column = pl.col(field)
    if operator == "is_null":
        return column.is_null()
    if operator == "not_null":
        return column.is_not_null()
    if operator in {"contains", "not_contains", "regex"}:
        expression = column.cast(pl.String).str.contains(str(value or ""), literal=operator != "regex")
        return ~expression if operator == "not_contains" else expression
    if operator in {"greater", "greater_equal", "less", "less_equal"}:
        left, right = column.cast(pl.Float64, strict=False), pl.lit(value).cast(pl.Float64, strict=False)
        return {"greater": left > right, "greater_equal": left >= right, "less": left < right, "less_equal": left <= right}[operator]
    if operator == "not_equals":
        return column.cast(pl.String) != str(value)
    return column.cast(pl.String) == str(value)


CONDITION_OPTIONS = [
    {"label": "等于", "value": "equals"}, {"label": "不等于", "value": "not_equals"},
    {"label": "包含", "value": "contains"}, {"label": "不包含", "value": "not_contains"},
    {"label": "大于", "value": "greater"}, {"label": "大于等于", "value": "greater_equal"},
    {"label": "小于", "value": "less"}, {"label": "小于等于", "value": "less_equal"},
    {"label": "匹配正则", "value": "regex"}, {"label": "为空", "value": "is_null"},
    {"label": "非空", "value": "not_null"},
]


class CalculatedColumnPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.calculated_column", name="计算列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="复制字段、填写固定值、拼接字段或计算文本长度并生成新列", icon="text-t", color="#2563eb", category="字段计算",
        config_fields=(
            ConfigField("operation", "计算方式", "select", default="copy", options=[
                {"label": "复制字段", "value": "copy"}, {"label": "填写固定值", "value": "constant"},
                {"label": "拼接两个字段", "value": "concat"}, {"label": "文本长度", "value": "length"},
            ]),
            ConfigField("source_field", "来源字段", "column"), ConfigField("second_field", "第二个字段", "column"),
            ConfigField("constant", "固定值", default=""), ConfigField("separator", "拼接分隔符", default=""),
            ConfigField("output_name", "新列名称", default="计算结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        operation, output = str(config.get("operation", "copy")), str(config.get("output_name", "计算结果")).strip()
        if not output:
            raise ValueError("新列名称不能为空")
        if operation == "constant":
            expression = pl.lit(config.get("constant", ""))
        else:
            source = str(config.get("source_field", ""))
            _require_columns(frame, [source], "来源字段")
            if operation == "copy":
                expression = pl.col(source)
            elif operation == "length":
                expression = pl.col(source).cast(pl.String).str.len_chars()
            elif operation == "concat":
                second = str(config.get("second_field", ""))
                _require_columns(frame, [second], "第二个字段")
                expression = pl.concat_str([pl.col(source), pl.col(second)], separator=str(config.get("separator", "")), ignore_nulls=False)
            else:
                raise ValueError(f"不支持的计算列方式: {operation}")
        return frame.with_columns(expression.alias(output))


class NumericCalculationPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.numeric_calculation", name="数值计算", kind=PluginKind.TRANSFORM, group="数据处理",
        description="对数值字段执行加减乘除、取整、绝对值、平方根或对数", icon="arrows-left-right", color="#0ea5e9", category="字段计算",
        config_fields=(
            ConfigField("source_field", "数值字段", "column", required=True),
            ConfigField("operation", "运算", "select", default="add", options=[
                {"label": "加", "value": "add"}, {"label": "减", "value": "subtract"}, {"label": "乘", "value": "multiply"},
                {"label": "除", "value": "divide"}, {"label": "取余", "value": "modulo"}, {"label": "次方", "value": "power"},
                {"label": "四舍五入", "value": "round"}, {"label": "绝对值", "value": "abs"},
                {"label": "平方根", "value": "sqrt"}, {"label": "自然对数", "value": "log"},
            ]),
            ConfigField("operand_mode", "第二个数来源", "select", default="constant", options=[
                {"label": "固定数值", "value": "constant"}, {"label": "另一个字段", "value": "field"},
            ]),
            ConfigField("operand", "固定数值", "number", default=0), ConfigField("operand_field", "另一个字段", "column"),
            ConfigField("output_name", "结果列名称", default="数值结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        source, operation = str(config.get("source_field", "")), str(config.get("operation", "add"))
        _require_columns(frame, [source])
        left = pl.col(source).cast(pl.Float64, strict=False)
        if str(config.get("operand_mode", "constant")) == "field":
            operand_field = str(config.get("operand_field", ""))
            _require_columns(frame, [operand_field], "运算字段")
            right = pl.col(operand_field).cast(pl.Float64, strict=False)
        else:
            right = pl.lit(config.get("operand", 0)).cast(pl.Float64, strict=False)
        if operation == "divide":
            expression = pl.when(right == 0).then(None).otherwise(left / right)
        elif operation == "round":
            digits = max(0, int(float(config.get("operand", 0) or 0)))
            expression = left.round(digits)
        elif operation == "abs": expression = left.abs()
        elif operation == "sqrt": expression = left.sqrt()
        elif operation == "log": expression = left.log()
        elif operation == "add": expression = left + right
        elif operation == "subtract": expression = left - right
        elif operation == "multiply": expression = left * right
        elif operation == "modulo": expression = left % right
        elif operation == "power": expression = left.pow(right)
        else: raise ValueError(f"不支持的数值运算: {operation}")
        return frame.with_columns(expression.alias(str(config.get("output_name", "数值结果") or "数值结果")))


class ConditionalBranchPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.conditional_branch", name="条件分支", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按条件标记不同分支，并可只保留满足或不满足条件的数据", icon="flow", color="#8b5cf6", category="流程控制",
        config_fields=(
            ConfigField("field", "判断字段", "column", required=True), ConfigField("operator", "判断条件", "select", default="equals", options=CONDITION_OPTIONS),
            ConfigField("value", "比较值", default=""), ConfigField("true_label", "满足条件标记", default="是"),
            ConfigField("false_label", "不满足条件标记", default="否"), ConfigField("output_name", "分支列名称", default="条件分支", required=True),
            ConfigField("keep", "输出范围", "select", default="all", options=[
                {"label": "保留全部并添加标记", "value": "all"}, {"label": "只保留满足条件", "value": "matched"},
                {"label": "只保留不满足条件", "value": "unmatched"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        field = str(config.get("field", "")); _require_columns(frame, [field])
        condition = _condition(field, str(config.get("operator", "equals")), config.get("value", "")).fill_null(False)
        result = frame.with_columns(pl.when(condition).then(pl.lit(str(config.get("true_label", "是")))).otherwise(pl.lit(str(config.get("false_label", "否")))).alias(str(config.get("output_name", "条件分支"))))
        keep = str(config.get("keep", "all"))
        return result.filter(condition if keep == "matched" else ~condition) if keep != "all" else result


class PivotPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.pivot", name="透视表", kind=PluginKind.TRANSFORM, group="数据处理",
        description="把一个字段的不同取值展开为多列并进行汇总", icon="columns", color="#d97706", category="结构转换",
        config_fields=(
            ConfigField("index", "保留为行的字段", "columns", required=True), ConfigField("on", "展开为列的字段", "column", required=True),
            ConfigField("values", "统计值字段", "column", required=True), ConfigField("aggregate", "汇总方式", "select", default="sum", options=[
                {"label": "求和", "value": "sum"}, {"label": "计数", "value": "len"}, {"label": "平均值", "value": "mean"},
                {"label": "最小值", "value": "min"}, {"label": "最大值", "value": "max"}, {"label": "第一条", "value": "first"},
            ]), ConfigField("fill_value", "空结果填充值", default=""),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        index, on, values = _fields(config.get("index")), str(config.get("on", "")), str(config.get("values", ""))
        _require_columns(frame, [*index, on, values])
        result = frame.pivot(on=on, index=index, values=values, aggregate_function=str(config.get("aggregate", "sum")), maintain_order=True, sort_columns=True)
        fill = config.get("fill_value", "")
        if fill == "":
            return result
        return result.with_columns(
            pl.col(field).fill_null(pl.lit(fill).cast(dtype, strict=False)).alias(field)
            for field, dtype in result.schema.items() if field not in index
        )


class UnpivotPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.unpivot", name="逆透视", kind=PluginKind.TRANSFORM, group="数据处理",
        description="把多个宽表字段收拢为字段名和值两列", icon="rows", color="#ea580c", category="结构转换",
        config_fields=(
            ConfigField("index", "保持不变的字段", "columns", default=[]), ConfigField("values", "需要收拢的字段", "columns", required=True),
            ConfigField("variable_name", "原字段名列", default="字段"), ConfigField("value_name", "原字段值列", default="值"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        index, values = _fields(config.get("index")), _fields(config.get("values")); _require_columns(frame, [*index, *values])
        if not values: raise ValueError("请至少选择一个需要逆透视的字段")
        return frame.unpivot(on=values, index=index, variable_name=str(config.get("variable_name", "字段")), value_name=str(config.get("value_name", "值")))


class TransposePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.transpose", name="行列转换", kind=PluginKind.TRANSFORM, group="数据处理",
        description="交换数据的行和列，可使用某一列内容作为新的列名", icon="arrows-left-right", color="#0d9488", category="结构转换",
        config_fields=(
            ConfigField("header_field", "作为新列名的字段（可选）", "column"), ConfigField("header_name", "原字段名列名称", default="原字段"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        header_field = str(config.get("header_field", "") or "")
        if header_field:
            _require_columns(frame, [header_field])
            names = [str(value) if value is not None else f"第{index + 1}列" for index, value in enumerate(frame[header_field].to_list())]
            if len(names) != len(set(names)): raise ValueError("作为新列名的字段包含重复值，请先去重或更换字段")
            frame = frame.drop(header_field)
        else:
            names = [f"第{index + 1}列" for index in range(frame.height)]
        return frame.transpose(include_header=True, header_name=str(config.get("header_name", "原字段") or "原字段"), column_names=names)


class SetOperationsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.set_operations", name="集合运算", kind=PluginKind.TRANSFORM, group="数据处理", accepts_multiple=True,
        description="对两个上游数据执行并集、交集、差集或对称差集", icon="squares-four", color="#4f46e5", category="多表处理",
        config_fields=(
            ConfigField("operation", "集合运算", "select", default="union", options=[
                {"label": "并集", "value": "union"}, {"label": "交集", "value": "intersection"},
                {"label": "第一路减第二路", "value": "difference"}, {"label": "对称差集", "value": "symmetric_difference"},
            ]), ConfigField("fields", "比较字段（留空使用共同字段）", "columns", default=[]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        if len(inputs) != 2: raise ValueError("集合运算必须连接且只能连接两个上游节点")
        left, right = inputs
        fields = _fields(config.get("fields")) or [field for field in left.columns if field in right.columns]
        _require_columns(left, fields, "第一路比较字段"); _require_columns(right, fields, "第二路比较字段")
        if not fields: raise ValueError("两个上游没有可比较的共同字段")
        left_set, right_set = left.select(fields).unique(maintain_order=True), right.select(fields).unique(maintain_order=True)
        operation = str(config.get("operation", "union"))
        if operation == "union": return pl.concat([left_set, right_set], how="vertical_relaxed").unique(maintain_order=True)
        if operation == "intersection": return left_set.join(right_set, on=fields, how="semi", nulls_equal=True)
        if operation == "difference": return left_set.join(right_set, on=fields, how="anti", nulls_equal=True)
        if operation == "symmetric_difference":
            return pl.concat([left_set.join(right_set, on=fields, how="anti", nulls_equal=True), right_set.join(left_set, on=fields, how="anti", nulls_equal=True)], how="vertical_relaxed")
        raise ValueError(f"不支持的集合运算: {operation}")


class WindowStatisticsPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.window_statistics", name="窗口统计", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按分组和顺序计算排名、累计值、移动平均、前后记录", icon="history", color="#7c3aed", category="聚合统计",
        config_fields=(
            ConfigField("partition_by", "分组字段（可选）", "columns", default=[]), ConfigField("order_by", "排序字段", "column", required=True),
            ConfigField("value_field", "统计字段", "column"), ConfigField("operation", "统计方式", "select", default="row_number", options=[
                {"label": "组内行号", "value": "row_number"}, {"label": "排名", "value": "rank"}, {"label": "密集排名", "value": "dense_rank"},
                {"label": "累计求和", "value": "cumulative_sum"}, {"label": "移动平均", "value": "moving_mean"},
                {"label": "上一条值", "value": "lag"}, {"label": "下一条值", "value": "lead"},
            ]), ConfigField("window_size", "移动窗口/偏移行数", "number", default=3), ConfigField("output_name", "结果列名称", default="窗口结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        groups, order, value = _fields(config.get("partition_by")), str(config.get("order_by", "")), str(config.get("value_field", ""))
        _require_columns(frame, [*groups, order]); operation = str(config.get("operation", "row_number"))
        if operation not in {"row_number", "rank", "dense_rank"}: _require_columns(frame, [value], "统计字段")
        row_id = "__dw_original_row__"
        while row_id in frame.columns: row_id += "_"
        sorted_frame = frame.with_row_index(row_id).sort([*groups, order], maintain_order=True)
        base = pl.col(value).cast(pl.Float64, strict=False) if value else pl.col(order)
        size = max(1, int(config.get("window_size", 3) or 3))
        if operation == "row_number": expression = pl.int_range(1, pl.len() + 1)
        elif operation == "rank": expression = pl.col(order).rank("ordinal")
        elif operation == "dense_rank": expression = pl.col(order).rank("dense")
        elif operation == "cumulative_sum": expression = base.cum_sum()
        elif operation == "moving_mean": expression = base.rolling_mean(window_size=size, min_samples=1)
        elif operation == "lag": expression = pl.col(value).shift(size)
        elif operation == "lead": expression = pl.col(value).shift(-size)
        else: raise ValueError(f"不支持的窗口统计: {operation}")
        if groups: expression = expression.over(groups)
        return sorted_frame.with_columns(expression.alias(str(config.get("output_name", "窗口结果")))).sort(row_id).drop(row_id)


class DataValidationPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.data_validation", name="数据校验", kind=PluginKind.TRANSFORM, group="数据处理",
        description="使用多条可视化规则校验字段并标记问题原因", icon="check-circle", color="#16a34a", category="数据质量",
        config_fields=(
            ConfigField("rules", "校验规则", "validation_rules", default=[{"field": "", "rule": "not_null", "value": "", "message": "不能为空"}], required=True),
            ConfigField("status_field", "校验状态列", default="校验通过"), ConfigField("reason_field", "问题原因列", default="校验问题"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); rules = config.get("rules")
        if not isinstance(rules, list) or not rules: raise ValueError("请至少添加一条校验规则")
        failures: list[pl.Expr] = []
        for index, rule in enumerate(rules, 1):
            field = str(rule.get("field", "")); _require_columns(frame, [field], f"第 {index} 条规则字段")
            rule_type, value = str(rule.get("rule", "not_null")), rule.get("value", "")
            column = pl.col(field)
            if rule_type == "not_null": valid = column.is_not_null() & (column.cast(pl.String) != "")
            elif rule_type == "numeric": valid = column.cast(pl.Float64, strict=False).is_not_null()
            elif rule_type == "integer": valid = column.cast(pl.Int64, strict=False).is_not_null()
            elif rule_type == "min": valid = column.cast(pl.Float64, strict=False) >= pl.lit(value).cast(pl.Float64, strict=False)
            elif rule_type == "max": valid = column.cast(pl.Float64, strict=False) <= pl.lit(value).cast(pl.Float64, strict=False)
            elif rule_type == "regex":
                try: re.compile(str(value))
                except re.error as exc: raise ValueError(f"第 {index} 条规则正则无效: {exc}") from exc
                valid = column.cast(pl.String).str.contains(str(value))
            elif rule_type == "allowed": valid = column.cast(pl.String).is_in([item.strip() for item in str(value).split(",")])
            elif rule_type == "unique": valid = ~column.is_duplicated()
            else: raise ValueError(f"第 {index} 条规则类型不支持: {rule_type}")
            message = str(rule.get("message", "") or f"{field}校验失败")
            failures.append(pl.when(valid.fill_null(False)).then(pl.lit(None, dtype=pl.String)).otherwise(pl.lit(message)))
        reason_field, status_field = str(config.get("reason_field", "校验问题")), str(config.get("status_field", "校验通过"))
        reasons = pl.concat_list(failures).list.drop_nulls().list.join("；")
        return frame.with_columns(reasons.alias(reason_field)).with_columns((pl.col(reason_field) == "").alias(status_field))


class InvalidRowRoutingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.invalid_row_routing", name="异常行分流", kind=PluginKind.TRANSFORM, group="数据处理",
        description="根据数据校验状态保留正常行或异常行", icon="funnel", color="#dc2626", category="数据质量",
        config_fields=(
            ConfigField("status_field", "校验状态字段", "column", required=True), ConfigField("route", "输出数据", "select", default="invalid", options=[
                {"label": "仅异常行", "value": "invalid"}, {"label": "仅正常行", "value": "valid"}, {"label": "全部数据", "value": "all"},
            ]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); field = str(config.get("status_field", "")); _require_columns(frame, [field])
        route = str(config.get("route", "invalid"))
        if route == "all": return frame
        valid = pl.col(field).cast(pl.Boolean, strict=False).fill_null(False)
        return frame.filter(valid if route == "valid" else ~valid)


class BatchSpillPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.batch_spill", name="分批落盘", kind=PluginKind.TRANSFORM, group="数据处理",
        description="正式运行时把完整中间结果分批写入多个文件，并继续向下游传递数据", icon="file-arrow-down", color="#64748b", category="流程控制",
        config_fields=(
            ConfigField("path", "文件名前缀", "save_file", required=True, placeholder="例如 D:\\data\\result.csv"),
            ConfigField("format", "文件格式", "select", default="csv", options=[
                {"label": "CSV", "value": "csv"}, {"label": "JSON Lines", "value": "jsonl"}, {"label": "Parquet", "value": "parquet"},
            ]), ConfigField("batch_size", "每个文件行数", "number", default=100000),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if context.preview: return frame
        requested = Path(str(config.get("path", "")))
        if not requested.name: raise ValueError("请选择分批落盘的文件名前缀")
        output_format = str(config.get("format", "csv")); extension = {"csv": ".csv", "jsonl": ".jsonl", "parquet": ".parquet"}.get(output_format)
        if extension is None: raise ValueError(f"不支持的落盘格式: {output_format}")
        requested.parent.mkdir(parents=True, exist_ok=True); stem = requested.stem or "batch"; batch_size = max(1, int(config.get("batch_size", 100000) or 100000))
        count = max(1, math.ceil(frame.height / batch_size)); paths: list[str] = []
        for batch_index in range(count):
            target = requested.parent / f"{stem}_{batch_index + 1:05d}{extension}"; temporary = target.with_name(f".{target.name}.part")
            batch = frame.slice(batch_index * batch_size, batch_size)
            try:
                if output_format == "csv": batch.write_csv(temporary)
                elif output_format == "jsonl":
                    with temporary.open("w", encoding="utf-8", newline="") as handle:
                        for row in batch.iter_rows(named=True): handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                else: batch.write_parquet(temporary)
                os.replace(temporary, target); paths.append(str(target))
            except Exception:
                temporary.unlink(missing_ok=True); raise
        context.variables.setdefault("batch_spill_stats", {})[str(context.variables.get("current_node_id", ""))] = {"files": paths, "rows": frame.height, "batchSize": batch_size}
        return frame


ADVANCED_TRANSFORM_PLUGINS = [
    CalculatedColumnPlugin, NumericCalculationPlugin, ConditionalBranchPlugin,
    PivotPlugin, UnpivotPlugin, TransposePlugin, SetOperationsPlugin,
    WindowStatisticsPlugin, DataValidationPlugin, InvalidRowRoutingPlugin, BatchSpillPlugin,
]
