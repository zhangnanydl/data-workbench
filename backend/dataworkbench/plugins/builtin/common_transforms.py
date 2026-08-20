from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin
from dataworkbench.plugins.builtin.advanced_transforms import CONDITION_OPTIONS, _condition, _fields, _require_columns


class _SafeExpressionCompiler:
    _binary = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    }
    _compare = {
        ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
    }

    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.aliases: dict[str, str] = {}

    def compile(self, source: str) -> pl.Expr:
        def replace(match: re.Match[str]) -> str:
            alias = f"__dw_field_{len(self.aliases)}"
            self.aliases[alias] = match.group(1)
            return alias

        prepared = re.sub(r"\[([^\[\]]+)\]", replace, source)
        try:
            tree = ast.parse(prepared, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"表达式语法错误: {exc.msg}") from exc
        return self._node(tree.body)

    def _node(self, node: ast.AST) -> pl.Expr:
        if isinstance(node, ast.Constant):
            return pl.lit(node.value)
        if isinstance(node, ast.Name):
            field = self.aliases.get(node.id, node.id)
            if field not in self.frame.columns:
                raise ValueError(f"表达式字段不存在: {field}；含空格字段请写成 [字段名]")
            return pl.col(field)
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary:
            return self._binary[type(node.op)](self._node(node.left), self._node(node.right))
        if isinstance(node, ast.UnaryOp):
            value = self._node(node.operand)
            if isinstance(node.op, ast.USub): return -value
            if isinstance(node.op, ast.UAdd): return value
            if isinstance(node.op, ast.Not): return ~value.cast(pl.Boolean, strict=False)
        if isinstance(node, ast.BoolOp):
            values = [self._node(value).cast(pl.Boolean, strict=False) for value in node.values]
            return pl.all_horizontal(values) if isinstance(node.op, ast.And) else pl.any_horizontal(values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in self._compare:
            return self._compare[type(node.ops[0])](self._node(node.left), self._node(node.comparators[0]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name, args = node.func.id, [self._node(item) for item in node.args]
            if name == "abs" and len(args) == 1: return args[0].abs()
            if name == "round" and len(args) in {1, 2}:
                digits = 0 if len(node.args) == 1 else int(ast.literal_eval(node.args[1]))
                return args[0].round(digits)
            if name == "sqrt" and len(args) == 1: return args[0].cast(pl.Float64, strict=False).sqrt()
            if name == "log" and len(args) == 1: return args[0].cast(pl.Float64, strict=False).log()
            if name == "length" and len(args) == 1: return args[0].cast(pl.String).str.len_chars()
            if name == "upper" and len(args) == 1: return args[0].cast(pl.String).str.to_uppercase()
            if name == "lower" and len(args) == 1: return args[0].cast(pl.String).str.to_lowercase()
            if name == "coalesce" and args: return pl.coalesce(args)
            raise ValueError(f"不支持的表达式函数: {name}")
        raise ValueError("表达式包含不支持的语法；仅允许字段、常量、四则运算、比较和常用函数")


class CustomExpressionPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.custom_expression", name="自定义表达式", kind=PluginKind.TRANSFORM, group="数据处理",
        description="使用安全表达式组合字段生成新列，不执行任意代码", icon="text-t", color="#2563eb", category="字段计算",
        config_fields=(
            ConfigField("expression", "计算表达式", "textarea", required=True, placeholder="例如：[金额] * [数量] - [优惠]", help_text="支持 + - * / // % **、比较，以及 abs、round、sqrt、log、length、upper、lower、coalesce 函数"),
            ConfigField("output_name", "结果列名称", default="表达式结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); expression = str(config.get("expression", "")).strip()
        if not expression: raise ValueError("计算表达式不能为空")
        return frame.with_columns(_SafeExpressionCompiler(frame).compile(expression).alias(str(config.get("output_name", "表达式结果") or "表达式结果")))


class MultiConditionFilterPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.multi_filter", name="多条件筛选", kind=PluginKind.TRANSFORM, group="数据处理",
        description="使用多条可视化条件按全部满足或任一满足筛选数据", icon="funnel", color="#14b8a6", category="筛选与字段",
        config_fields=(
            ConfigField("rules", "筛选条件", "condition_rules", default=[{"field": "", "operator": "equals", "value": ""}], required=True),
            ConfigField("logic", "条件关系", "select", default="all", options=[{"label": "全部满足（且）", "value": "all"}, {"label": "任一满足（或）", "value": "any"}]),
            ConfigField("mode", "处理方式", "select", default="keep", options=[{"label": "保留满足条件的数据", "value": "keep"}, {"label": "排除满足条件的数据", "value": "drop"}]),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); rules = config.get("rules")
        if not isinstance(rules, list) or not rules: raise ValueError("请至少添加一条筛选条件")
        conditions = []
        for index, rule in enumerate(rules, 1):
            field = str(rule.get("field", "")); _require_columns(frame, [field], f"第 {index} 条条件字段")
            conditions.append(_condition(field, str(rule.get("operator", "equals")), rule.get("value", "")).fill_null(False))
        combined = pl.all_horizontal(conditions) if str(config.get("logic", "all")) == "all" else pl.any_horizontal(conditions)
        return frame.filter(~combined if str(config.get("mode", "keep")) == "drop" else combined)


class CaseWhenPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.case_when", name="CASE WHEN 计算列", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按多条条件依次匹配结果并生成分类字段", icon="flow", color="#8b5cf6", category="字段计算",
        config_fields=(
            ConfigField("rules", "条件结果", "case_rules", default=[{"field": "", "operator": "equals", "value": "", "result": ""}], required=True),
            ConfigField("default_value", "均不满足时", default="其他"), ConfigField("output_name", "结果列名称", default="分类结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); rules = config.get("rules")
        if not isinstance(rules, list) or not rules: raise ValueError("请至少添加一条 CASE WHEN 规则")
        expression = None
        for index, rule in enumerate(rules, 1):
            field = str(rule.get("field", "")); _require_columns(frame, [field], f"第 {index} 条规则字段")
            condition = _condition(field, str(rule.get("operator", "equals")), rule.get("value", "")).fill_null(False)
            result = pl.lit(rule.get("result", ""))
            expression = pl.when(condition).then(result) if expression is None else expression.when(condition).then(result)
        return frame.with_columns(expression.otherwise(pl.lit(config.get("default_value", "其他"))).alias(str(config.get("output_name", "分类结果"))))


def _datetime_expr(frame: pl.DataFrame, field: str, fmt: str = "") -> pl.Expr:
    _require_columns(frame, [field])
    if frame.schema[field].is_temporal(): return pl.col(field)
    return pl.col(field).cast(pl.String).str.to_datetime(format=fmt or None, strict=False)


class DateTimeCalculationPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.datetime_calculation", name="日期时间计算", kind=PluginKind.TRANSFORM, group="数据处理",
        description="日期加减、计算时间差、格式化时间或转换 Unix 时间戳", icon="history", color="#7c3aed", category="日期时间",
        config_fields=(
            ConfigField("source_field", "时间字段", "column", required=True), ConfigField("operation", "计算方式", "select", default="add_days", options=[
                {"label": "增加/减少天数", "value": "add_days"}, {"label": "增加/减少小时", "value": "add_hours"},
                {"label": "与另一字段相差天数", "value": "difference_days"}, {"label": "与另一字段相差小时", "value": "difference_hours"},
                {"label": "格式化为文本", "value": "format"}, {"label": "转换为 Unix 时间戳", "value": "to_timestamp"},
                {"label": "Unix 时间戳转时间", "value": "from_timestamp"},
            ]),
            ConfigField("second_field", "另一个时间字段", "column"), ConfigField("amount", "增加量（负数为减少）", "number", default=1),
            ConfigField("input_format", "输入格式（可选）", default="", placeholder="例如 %Y-%m-%d %H:%M:%S"),
            ConfigField("output_format", "输出格式", default="%Y-%m-%d %H:%M:%S"), ConfigField("output_name", "结果列名称", default="时间计算结果", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); source = str(config.get("source_field", "")); operation = str(config.get("operation", "add_days"))
        if operation == "from_timestamp":
            _require_columns(frame, [source]); expression = pl.from_epoch(pl.col(source).cast(pl.Int64, strict=False), time_unit="s")
        else:
            parsed = _datetime_expr(frame, source, str(config.get("input_format", "")))
            amount = int(config.get("amount", 1) or 0)
            if operation == "add_days": expression = parsed + pl.duration(days=amount)
            elif operation == "add_hours": expression = parsed + pl.duration(hours=amount)
            elif operation in {"difference_days", "difference_hours"}:
                second = _datetime_expr(frame, str(config.get("second_field", "")), str(config.get("input_format", "")))
                duration = parsed - second
                expression = duration.dt.total_days() if operation == "difference_days" else duration.dt.total_hours()
            elif operation == "format": expression = parsed.dt.strftime(str(config.get("output_format", "%Y-%m-%d %H:%M:%S")))
            elif operation == "to_timestamp": expression = parsed.dt.epoch("s")
            else: raise ValueError(f"不支持的日期时间计算: {operation}")
        return frame.with_columns(expression.alias(str(config.get("output_name", "时间计算结果"))))


class DataComparePlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.data_compare", name="数据对比", kind=PluginKind.TRANSFORM, group="数据处理", accepts_multiple=True,
        description="按主键比较两个上游数据，识别新增、缺失、修改和未变化记录", icon="arrows-left-right", color="#4f46e5", category="多表处理",
        config_fields=(
            ConfigField("keys", "唯一标识字段", "columns", required=True), ConfigField("compare_fields", "比较内容字段（留空自动选择）", "columns", default=[]),
            ConfigField("mode", "输出范围", "select", default="differences", options=[{"label": "只输出差异", "value": "differences"}, {"label": "输出全部", "value": "all"}, {"label": "只输出新增", "value": "added"}, {"label": "只输出缺失", "value": "deleted"}, {"label": "只输出修改", "value": "changed"}]),
            ConfigField("status_field", "状态列名称", default="对比状态"), ConfigField("suffix", "第二路字段后缀", default="_新"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        if len(inputs) != 2: raise ValueError("数据对比必须连接且只能连接两个上游节点")
        left, right = inputs; keys = _fields(config.get("keys")); _require_columns(left, keys, "第一路主键"); _require_columns(right, keys, "第二路主键")
        if not keys: raise ValueError("请至少选择一个唯一标识字段")
        fields = _fields(config.get("compare_fields")) or [field for field in left.columns if field in right.columns and field not in keys]
        _require_columns(left, fields, "第一路比较字段"); _require_columns(right, fields, "第二路比较字段")
        suffix = str(config.get("suffix", "_新") or "_新"); left_marker, right_marker = "__dw_left__", "__dw_right__"
        joined = left.with_columns(pl.lit(True).alias(left_marker)).join(right.with_columns(pl.lit(True).alias(right_marker)), on=keys, how="full", suffix=suffix, coalesce=True, nulls_equal=True)
        changed = pl.any_horizontal([pl.col(field).ne_missing(pl.col(f"{field}{suffix}")) for field in fields]) if fields else pl.lit(False)
        status = (pl.when(pl.col(left_marker).is_null()).then(pl.lit("新增"))
                  .when(pl.col(right_marker).is_null()).then(pl.lit("缺失"))
                  .when(changed).then(pl.lit("修改")).otherwise(pl.lit("未变化")))
        status_field = str(config.get("status_field", "对比状态")); result = joined.with_columns(status.alias(status_field)).drop(left_marker, right_marker)
        mode = str(config.get("mode", "differences"))
        if mode == "all": return result
        if mode == "differences": return result.filter(pl.col(status_field) != "未变化")
        return result.filter(pl.col(status_field) == {"added": "新增", "deleted": "缺失", "changed": "修改"}[mode])


class BatchFieldProcessingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.batch_fields", name="批量字段处理", kind=PluginKind.TRANSFORM, group="数据处理",
        description="一次对多个字段执行清理、填充、替换、前后缀或类型转换", icon="columns", color="#0d9488", category="字段转换",
        config_fields=(
            ConfigField("fields", "处理字段", "columns", required=True), ConfigField("operation", "处理方式", "select", default="trim", options=[
                {"label": "去除两端空白", "value": "trim"}, {"label": "转大写", "value": "upper"}, {"label": "转小写", "value": "lower"},
                {"label": "填充空值", "value": "fill_null"}, {"label": "文本替换", "value": "replace"},
                {"label": "添加前缀", "value": "prefix"}, {"label": "添加后缀", "value": "suffix"},
                {"label": "转为文本", "value": "string"}, {"label": "转为整数", "value": "integer"}, {"label": "转为小数", "value": "float"},
            ]), ConfigField("value", "参数值", default=""), ConfigField("replacement", "替换为", default=""),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); fields = _fields(config.get("fields")); _require_columns(frame, fields)
        if not fields: raise ValueError("请至少选择一个处理字段")
        operation, value = str(config.get("operation", "trim")), config.get("value", ""); expressions = []
        for field in fields:
            column = pl.col(field)
            if operation == "trim": expression = column.cast(pl.String).str.strip_chars()
            elif operation == "upper": expression = column.cast(pl.String).str.to_uppercase()
            elif operation == "lower": expression = column.cast(pl.String).str.to_lowercase()
            elif operation == "fill_null": expression = column.fill_null(pl.lit(value).cast(frame.schema[field], strict=False))
            elif operation == "replace": expression = column.cast(pl.String).str.replace_all(str(value), str(config.get("replacement", "")), literal=True)
            elif operation == "prefix": expression = pl.lit(str(value)) + column.cast(pl.String)
            elif operation == "suffix": expression = column.cast(pl.String) + pl.lit(str(value))
            elif operation == "string": expression = column.cast(pl.String, strict=False)
            elif operation == "integer": expression = column.cast(pl.Int64, strict=False)
            elif operation == "float": expression = column.cast(pl.Float64, strict=False)
            else: raise ValueError(f"不支持的批量字段处理: {operation}")
            expressions.append(expression.alias(field))
        return frame.with_columns(expressions)


class RowNumberPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.row_number", name="行号", kind=PluginKind.TRANSFORM, group="数据处理",
        description="生成全局行号或分组行号，可按字段排序后编号", icon="rows", color="#64748b", category="筛选与字段",
        config_fields=(
            ConfigField("partition_by", "分组字段（可选）", "columns", default=[]), ConfigField("order_by", "排序字段（可选）", "column"),
            ConfigField("direction", "排序方向", "select", default="ascending", options=[{"label": "升序", "value": "ascending"}, {"label": "降序", "value": "descending"}]),
            ConfigField("start", "起始编号", "number", default=1), ConfigField("output_name", "行号列名称", default="行号", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); groups = _fields(config.get("partition_by")); order_by = str(config.get("order_by", "") or ""); _require_columns(frame, groups)
        if order_by: _require_columns(frame, [order_by]); frame = frame.sort([*groups, order_by], descending=str(config.get("direction", "ascending")) == "descending", maintain_order=True)
        start = int(config.get("start", 1) or 1); expression = pl.int_range(start, start + pl.len())
        if groups: expression = expression.over(groups)
        return frame.with_columns(expression.alias(str(config.get("output_name", "行号"))))


class TopNPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.top_n", name="Top N", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按排序字段保留全局或每个分组的前 N 条记录", icon="funnel", color="#f59e0b", category="筛选与字段",
        config_fields=(
            ConfigField("group_by", "分组字段（可选）", "columns", default=[]), ConfigField("order_by", "排序字段", "column", required=True),
            ConfigField("direction", "保留方向", "select", default="largest", options=[{"label": "最大值优先", "value": "largest"}, {"label": "最小值优先", "value": "smallest"}]),
            ConfigField("n", "每组保留条数", "number", default=10),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); groups = _fields(config.get("group_by")); order = str(config.get("order_by", "")); _require_columns(frame, [*groups, order])
        n = max(1, int(config.get("n", 10) or 10)); result = frame.sort([*groups, order], descending=str(config.get("direction", "largest")) == "largest", maintain_order=True)
        if not groups: return result.head(n)
        marker = "__dw_top_n__"; return result.with_columns(pl.int_range(0, pl.len()).over(groups).alias(marker)).filter(pl.col(marker) < n).drop(marker)


class DataSamplingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.sampling", name="数据采样", kind=PluginKind.TRANSFORM, group="数据处理",
        description="按固定条数、比例或等间隔抽取可复现的数据样本", icon="squares-four", color="#06b6d4", category="筛选与字段",
        config_fields=(
            ConfigField("mode", "采样方式", "select", default="count", options=[{"label": "随机固定条数", "value": "count"}, {"label": "随机比例", "value": "fraction"}, {"label": "等间隔采样", "value": "systematic"}, {"label": "取前 N 条", "value": "head"}]),
            ConfigField("count", "样本条数", "number", default=1000), ConfigField("fraction", "采样比例（0-1）", "number", default=0.1), ConfigField("seed", "随机种子", "number", default=42),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); mode = str(config.get("mode", "count")); count = max(0, int(config.get("count", 1000) or 0)); seed = int(config.get("seed", 42) or 42)
        if mode == "head": return frame.head(count)
        if mode == "fraction": return frame.sample(fraction=min(1.0, max(0.0, float(config.get("fraction", 0.1) or 0))), seed=seed, shuffle=True)
        if mode == "count": return frame.sample(n=min(count, frame.height), seed=seed, shuffle=True)
        if mode == "systematic":
            if count <= 0 or frame.is_empty(): return frame.head(0)
            step = max(1, math.ceil(frame.height / count)); return frame.gather_every(step).head(count)
        raise ValueError(f"不支持的采样方式: {mode}")


class IntervalGroupingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.interval_group", name="区间分组", kind=PluginKind.TRANSFORM, group="数据处理",
        description="根据数值边界把年龄、金额、分数等划分为多个区间", icon="columns", color="#ea580c", category="字段计算",
        config_fields=(
            ConfigField("source_field", "数值字段", "column", required=True), ConfigField("boundaries", "区间边界", required=True, default="60,80,90", help_text="从小到大填写并用逗号分隔"),
            ConfigField("labels", "区间名称（可选）", default="不及格,及格,良好,优秀", help_text="名称数量应比边界多 1 个"), ConfigField("output_name", "结果列名称", default="区间", required=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); field = str(config.get("source_field", "")); _require_columns(frame, [field])
        try: boundaries = [float(item.strip()) for item in str(config.get("boundaries", "")).split(",") if item.strip()]
        except ValueError as exc: raise ValueError("区间边界必须是用逗号分隔的数值") from exc
        if not boundaries or boundaries != sorted(set(boundaries)): raise ValueError("区间边界必须从小到大且不能重复")
        labels = [item.strip() for item in str(config.get("labels", "")).split(",") if item.strip()]
        if not labels: labels = [f"小于 {boundaries[0]:g}", *[f"{boundaries[index - 1]:g}–{boundaries[index]:g}" for index in range(1, len(boundaries))], f"大于等于 {boundaries[-1]:g}"]
        if len(labels) != len(boundaries) + 1: raise ValueError(f"需要填写 {len(boundaries) + 1} 个区间名称")
        column = pl.col(field).cast(pl.Float64, strict=False); expression = pl.when(column < boundaries[0]).then(pl.lit(labels[0]))
        for index in range(1, len(boundaries)): expression = expression.when(column < boundaries[index]).then(pl.lit(labels[index]))
        expression = expression.otherwise(pl.when(column.is_null()).then(pl.lit(None, dtype=pl.String)).otherwise(pl.lit(labels[-1])))
        return frame.with_columns(expression.alias(str(config.get("output_name", "区间"))))


class DataProfilingPlugin(DataPlugin):
    definition = PluginDefinition(
        id="transform.data_profiling", name="数据剖析", kind=PluginKind.TRANSFORM, group="数据处理",
        description="输出每个字段的数据类型、空值率、唯一值及常用统计指标", icon="report", color="#16a34a", category="数据质量",
        config_fields=(ConfigField("fields", "分析字段（留空分析全部）", "columns", default=[]), ConfigField("include_examples", "包含示例值", "boolean", default=True)),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs); fields = _fields(config.get("fields")) or frame.columns; _require_columns(frame, fields)
        rows = []
        for field in fields:
            series, dtype = frame[field], frame.schema[field]; non_null = series.drop_nulls(); numeric = dtype.is_numeric()
            rows.append({
                "字段": field, "类型": str(dtype), "总行数": frame.height, "非空数": non_null.len(), "空值数": series.null_count(),
                "空值率": round(series.null_count() / frame.height * 100, 4) if frame.height else 0.0, "唯一值数": series.n_unique(),
                "最小值": str(non_null.min()) if non_null.len() else None, "最大值": str(non_null.max()) if non_null.len() else None,
                "平均值": float(non_null.mean()) if numeric and non_null.len() else None,
                "示例值": "、".join(str(value) for value in non_null.unique(maintain_order=True).head(3).to_list()) if bool(config.get("include_examples", True)) else None,
            })
        return pl.DataFrame(rows, infer_schema_length=None)


COMMON_TRANSFORM_PLUGINS = [
    CustomExpressionPlugin, MultiConditionFilterPlugin, CaseWhenPlugin, DateTimeCalculationPlugin,
    DataComparePlugin, BatchFieldProcessingPlugin, RowNumberPlugin, TopNPlugin,
    DataSamplingPlugin, IntervalGroupingPlugin, DataProfilingPlugin,
]
