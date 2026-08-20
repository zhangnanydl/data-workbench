from pathlib import Path

import polars as pl

from dataworkbench.models import ExecutionContext
from dataworkbench.plugins.builtin.advanced_transforms import (
    BatchSpillPlugin,
    CalculatedColumnPlugin,
    ConditionalBranchPlugin,
    DataValidationPlugin,
    InvalidRowRoutingPlugin,
    NumericCalculationPlugin,
    PivotPlugin,
    SetOperationsPlugin,
    TransposePlugin,
    UnpivotPlugin,
    WindowStatisticsPlugin,
)


CONTEXT = ExecutionContext(preview=False)


def test_calculated_column_numeric_calculation_and_condition_branch():
    frame = pl.DataFrame({"姓名": ["张三", "李四"], "班级": ["一班", "二班"], "分数": [80, 60]})
    calculated = CalculatedColumnPlugin().execute([frame], {
        "operation": "concat", "source_field": "班级", "second_field": "姓名", "separator": "-", "output_name": "学生",
    }, CONTEXT)
    assert calculated["学生"].to_list() == ["一班-张三", "二班-李四"]

    numeric = NumericCalculationPlugin().execute([calculated], {
        "source_field": "分数", "operation": "multiply", "operand_mode": "constant", "operand": 1.25, "output_name": "换算分",
    }, CONTEXT)
    assert numeric["换算分"].to_list() == [100.0, 75.0]

    branched = ConditionalBranchPlugin().execute([numeric], {
        "field": "换算分", "operator": "greater_equal", "value": 80, "true_label": "通过", "false_label": "复核",
        "output_name": "结果", "keep": "all",
    }, CONTEXT)
    assert branched["结果"].to_list() == ["通过", "复核"]


def test_pivot_unpivot_and_transpose():
    frame = pl.DataFrame({"班级": ["一班", "一班", "二班"], "科目": ["语文", "数学", "语文"], "分数": [80, 90, 70]})
    pivoted = PivotPlugin().execute([frame], {"index": ["班级"], "on": "科目", "values": "分数", "aggregate": "sum", "fill_value": 0}, CONTEXT)
    assert pivoted.columns == ["班级", "数学", "语文"]
    assert pivoted.filter(pl.col("班级") == "二班")["数学"][0] == 0

    unpivoted = UnpivotPlugin().execute([pivoted], {"index": ["班级"], "values": ["数学", "语文"], "variable_name": "科目", "value_name": "分数"}, CONTEXT)
    assert unpivoted.height == 4

    transposed = TransposePlugin().execute([pl.DataFrame({"名称": ["A", "B"], "值": [1, 2]})], {"header_field": "名称", "header_name": "指标"}, CONTEXT)
    assert transposed.columns == ["指标", "A", "B"]
    assert transposed.row(0) == ("值", 1, 2)


def test_set_operations_and_window_statistics():
    left = pl.DataFrame({"id": [1, 2, 3]})
    right = pl.DataFrame({"id": [3, 4]})
    intersection = SetOperationsPlugin().execute([left, right], {"operation": "intersection", "fields": ["id"]}, CONTEXT)
    assert intersection["id"].to_list() == [3]
    symmetric = SetOperationsPlugin().execute([left, right], {"operation": "symmetric_difference", "fields": ["id"]}, CONTEXT)
    assert set(symmetric["id"].to_list()) == {1, 2, 4}

    frame = pl.DataFrame({"组": ["a", "a", "b"], "顺序": [2, 1, 1], "金额": [20, 10, 7]})
    result = WindowStatisticsPlugin().execute([frame], {
        "partition_by": ["组"], "order_by": "顺序", "value_field": "金额", "operation": "cumulative_sum", "output_name": "累计",
    }, CONTEXT)
    assert result["累计"].to_list() == [30.0, 10.0, 7.0]


def test_data_validation_and_invalid_routing():
    frame = pl.DataFrame({"账号": ["alice", "", "bob"], "分数": [80, 70, -1]})
    validated = DataValidationPlugin().execute([frame], {
        "rules": [
            {"field": "账号", "rule": "not_null", "value": "", "message": "账号不能为空"},
            {"field": "分数", "rule": "min", "value": 0, "message": "分数不能小于0"},
        ], "status_field": "校验通过", "reason_field": "校验问题",
    }, CONTEXT)
    assert validated["校验通过"].to_list() == [True, False, False]
    invalid = InvalidRowRoutingPlugin().execute([validated], {"status_field": "校验通过", "route": "invalid"}, CONTEXT)
    assert invalid.height == 2
    assert set(invalid["校验问题"].to_list()) == {"账号不能为空", "分数不能小于0"}


def test_batch_spill_skips_preview_and_writes_every_row(tmp_path: Path):
    frame = pl.DataFrame({"id": list(range(2500))})
    target = tmp_path / "result.csv"
    plugin = BatchSpillPlugin()
    plugin.execute([frame], {"path": str(target), "format": "csv", "batch_size": 1000}, ExecutionContext(preview=True))
    assert not list(tmp_path.iterdir())

    result = plugin.execute([frame], {"path": str(target), "format": "csv", "batch_size": 1000}, ExecutionContext(preview=False))
    files = sorted(tmp_path.glob("result_*.csv"))
    assert result.height == 2500
    assert len(files) == 3
    assert sum(pl.read_csv(path).height for path in files) == 2500
