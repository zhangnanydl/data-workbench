import polars as pl

from dataworkbench.models import ExecutionContext
from dataworkbench.plugins.builtin.common_transforms import (
    BatchFieldProcessingPlugin,
    CaseWhenPlugin,
    CustomExpressionPlugin,
    DataComparePlugin,
    DataProfilingPlugin,
    DataSamplingPlugin,
    DateTimeCalculationPlugin,
    IntervalGroupingPlugin,
    MultiConditionFilterPlugin,
    RowNumberPlugin,
    TopNPlugin,
)


CONTEXT = ExecutionContext(preview=False)


def test_custom_expression_is_field_aware_and_rejects_unsafe_code():
    frame = pl.DataFrame({"单价": [10.0, 20.0], "购买 数量": [2, 3], "优惠": [1, 5]})
    result = CustomExpressionPlugin().execute([frame], {"expression": "单价 * [购买 数量] - 优惠", "output_name": "金额"}, CONTEXT)
    assert result["金额"].to_list() == [19.0, 55.0]
    try:
        CustomExpressionPlugin().execute([frame], {"expression": "__import__('os').system('dir')", "output_name": "危险"}, CONTEXT)
        assert False, "unsafe expression should fail"
    except ValueError as exc:
        assert "不支持" in str(exc)


def test_multi_filter_and_case_when_rules():
    frame = pl.DataFrame({"地区": ["华东", "华东", "华南"], "金额": [120, 60, 200]})
    filtered = MultiConditionFilterPlugin().execute([frame], {
        "rules": [{"field": "地区", "operator": "equals", "value": "华东"}, {"field": "金额", "operator": "greater_equal", "value": 100}],
        "logic": "all", "mode": "keep",
    }, CONTEXT)
    assert filtered["金额"].to_list() == [120]
    classified = CaseWhenPlugin().execute([frame], {
        "rules": [{"field": "金额", "operator": "greater_equal", "value": 150, "result": "高"}, {"field": "金额", "operator": "greater_equal", "value": 100, "result": "中"}],
        "default_value": "低", "output_name": "等级",
    }, CONTEXT)
    assert classified["等级"].to_list() == ["中", "低", "高"]


def test_datetime_calculation_and_interval_grouping():
    frame = pl.DataFrame({"开始": ["2026-08-20 10:00:00"], "结束": ["2026-08-22 12:00:00"], "分数": [85]})
    dated = DateTimeCalculationPlugin().execute([frame], {
        "source_field": "结束", "second_field": "开始", "operation": "difference_hours", "input_format": "%Y-%m-%d %H:%M:%S", "output_name": "小时差",
    }, CONTEXT)
    assert dated["小时差"][0] == 50
    grouped = IntervalGroupingPlugin().execute([dated], {"source_field": "分数", "boundaries": "60,80,90", "labels": "不及格,及格,良好,优秀", "output_name": "等级"}, CONTEXT)
    assert grouped["等级"][0] == "良好"


def test_data_compare_marks_added_deleted_and_changed():
    old = pl.DataFrame({"id": [1, 2, 3], "名称": ["A", "B", "C"], "金额": [10, 20, 30]})
    new = pl.DataFrame({"id": [1, 2, 4], "名称": ["A", "B", "D"], "金额": [10, 25, 40]})
    result = DataComparePlugin().execute([old, new], {"keys": ["id"], "compare_fields": ["名称", "金额"], "mode": "differences", "status_field": "状态", "suffix": "_新"}, CONTEXT)
    assert dict(zip(result["id"].to_list(), result["状态"].to_list())) == {2: "修改", 3: "缺失", 4: "新增"}


def test_batch_fields_row_number_top_n_and_sampling():
    frame = pl.DataFrame({"组": ["a", "a", "a", "b", "b"], "名称": [" A ", " B ", " C ", " D ", " E "], "分数": [1, 3, 2, 5, 4]})
    cleaned = BatchFieldProcessingPlugin().execute([frame], {"fields": ["名称"], "operation": "trim"}, CONTEXT)
    assert cleaned["名称"].to_list() == ["A", "B", "C", "D", "E"]
    numbered = RowNumberPlugin().execute([cleaned], {"partition_by": ["组"], "order_by": "分数", "direction": "descending", "start": 1, "output_name": "组内行号"}, CONTEXT)
    assert numbered.filter(pl.col("组") == "a")["组内行号"].to_list() == [1, 2, 3]
    top = TopNPlugin().execute([cleaned], {"group_by": ["组"], "order_by": "分数", "direction": "largest", "n": 1}, CONTEXT)
    assert set(top["分数"].to_list()) == {3, 5}
    sample1 = DataSamplingPlugin().execute([frame], {"mode": "count", "count": 3, "seed": 7}, CONTEXT)
    sample2 = DataSamplingPlugin().execute([frame], {"mode": "count", "count": 3, "seed": 7}, CONTEXT)
    assert sample1.equals(sample2) and sample1.height == 3


def test_data_profiling_returns_one_complete_summary_row_per_field():
    frame = pl.DataFrame({"编号": [1, 2, 2], "金额": [10.0, None, 30.0], "名称": ["A", "B", "B"]})
    result = DataProfilingPlugin().execute([frame], {"fields": [], "include_examples": True}, CONTEXT)
    assert result.height == 3
    amount = result.filter(pl.col("字段") == "金额").row(0, named=True)
    assert amount["总行数"] == 3 and amount["空值数"] == 1 and amount["平均值"] == 20.0
