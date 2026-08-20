from dataworkbench.engine import PipelineEngine
from dataworkbench.bridge import DesktopBridge
from dataworkbench.mysql_utils import mysql_connect_kwargs, quote_mysql_identifier
from dataworkbench.models import ExecutionContext
from dataworkbench.plugins.builtin.inputs import JsonInputPlugin, SQLiteInputPlugin, SecurityLogInputPlugin, _normalize_event_ids, _parse_evtx_xml
from dataworkbench.plugins.builtin.outputs import FileOutputPlugin, JsonOutputPlugin, SQLiteOutputPlugin
import hashlib
import json
import sys
import time
import pandas as pd
import polars as pl
import webview


def demo_pipeline():
    return {
        "nodes": [
            {"id": "source", "pluginId": "input.demo", "config": {}},
            {"id": "filter", "pluginId": "transform.filter", "config": {"field": "协议", "operator": "equals", "value": "HTTP"}},
            {"id": "mask", "pluginId": "transform.mask", "config": {"fields": "手机号", "keep_start": 3, "keep_end": 4, "mask_char": "*"}},
        ],
        "edges": [
            {"id": "e1", "source": "source", "target": "filter"},
            {"id": "e2", "source": "filter", "target": "mask"},
        ],
    }


def test_registry_contains_all_plugin_kinds():
    definitions = PipelineEngine().registry.list_definitions()
    assert {item["kind"] for item in definitions} == {"input", "transform", "output"}


def test_registry_contains_security_exam_file_plugins():
    plugin_ids = {item["id"] for item in PipelineEngine().registry.list_definitions()}
    assert {"input.log", "input.evtx", "input.json", "input.sqlite", "output.json", "output.sqlite"} <= plugin_ids


def test_log_input_does_not_truncate_computation_to_preview_page(tmp_path):
    log_path = tmp_path / "auth.log"
    log_path.write_text('time=10:00 user=alice action="login ok"\ntime=10:01 user=bob action=failed\n', encoding="utf-8")
    result = SecurityLogInputPlugin().execute([], {"path": str(log_path), "parse_mode": "key_value", "encoding": "utf-8"}, ExecutionContext(preview=True, preview_limit=1))
    assert result.height == 2
    assert result.row(0, named=True)["user"] == "alice"
    assert result.row(0, named=True)["action"] == "login ok"


def test_ten_thousand_rows_are_fully_processed_paged_and_exported(tmp_path):
    source_path = tmp_path / "source.csv"
    output_path = tmp_path / "filtered.csv"
    pl.DataFrame({
        "序号": range(1, 10_001),
        "类别": ["保留" if value % 10 == 0 else "忽略" for value in range(1, 10_001)],
    }).write_csv(source_path)
    pipeline = {
        "nodes": [
            {"id": "source", "pluginId": "input.csv", "config": {"path": str(source_path), "delimiter": ",", "encoding": "utf8"}},
            {"id": "filter", "pluginId": "transform.filter", "config": {"field": "类别", "operator": "equals", "value": "保留"}},
            {"id": "output", "pluginId": "output.file", "config": {"path": str(output_path), "format": "csv", "delimiter": ","}},
        ],
        "edges": [
            {"id": "e1", "source": "source", "target": "filter"},
            {"id": "e2", "source": "filter", "target": "output"},
        ],
    }
    bridge = DesktopBridge(tmp_path)

    first_page = bridge.preview_pipeline(pipeline, "output", 100, 1)
    second_page = bridge.preview_pipeline(pipeline, "output", 100, 2)
    assert first_page["ok"] is True
    assert first_page["data"]["stats"]["rowCount"] == 1_000
    assert len(first_page["data"]["rows"]) == 100
    assert first_page["data"]["rows"][0]["序号"] == 10
    assert second_page["data"]["rows"][0]["序号"] == 1_010
    assert not output_path.exists(), "实时预览不应提前写出文件"

    completed = bridge.run_pipeline(pipeline)
    assert completed["ok"] is True
    assert completed["data"]["stats"]["rowCount"] == 1_000
    exported = pl.read_csv(output_path)
    assert exported.height == 1_000
    assert exported["序号"].to_list()[-1] == 10_000


def test_large_csv_uses_fast_preview_sample_but_full_run_remains_complete(tmp_path):
    source_path = tmp_path / "large.csv"
    output_path = tmp_path / "large-result.csv"
    row_count = 260_000
    pl.DataFrame({"序号": range(1, row_count + 1), "类别": ["保留"] * row_count}).write_csv(source_path)
    pipeline = {
        "nodes": [
            {"id": "source", "pluginId": "input.csv", "config": {"path": str(source_path), "delimiter": ",", "encoding": "utf8"}},
            {"id": "filter", "pluginId": "transform.filter", "config": {"field": "类别", "operator": "equals", "value": "保留"}},
            {"id": "output", "pluginId": "output.file", "config": {"path": str(output_path), "format": "csv"}},
        ],
        "edges": [{"id": "e1", "source": "source", "target": "filter"}, {"id": "e2", "source": "filter", "target": "output"}],
    }
    bridge = DesktopBridge(tmp_path)
    assessment = bridge.assess_pipeline(pipeline)
    preview = bridge.preview_pipeline(pipeline, "output", 100, 1)
    assert assessment["data"]["largeData"] is True
    assert assessment["data"]["estimatedRows"] >= 250_000
    assert preview["data"]["stats"]["sampled"] is True
    assert preview["data"]["stats"]["rowCount"] == 50_000
    assert preview["data"]["stats"]["estimatedRowCount"] >= 250_000
    assert not output_path.exists()

    progress_events = []
    PipelineEngine().execute(
        pipeline, preview=False, target_node_id="filter", project_dir=tmp_path,
        execution_variables={"source_estimates": assessment["data"]["sources"]},
        progress_callback=progress_events.append,
    )
    reading_events = [event for event in progress_events if event.get("phase") == "reading"]
    assert reading_events
    assert reading_events[0]["sourceRows"] > 0
    assert 0 < reading_events[0]["percent"] < 100

    started = bridge.start_pipeline_run(pipeline)
    assert started["ok"] is True
    deadline = time.monotonic() + 15
    job = started["job"]
    while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.05)
        job = bridge.get_pipeline_run(job["jobId"])["job"]
    assert job["status"] == "success"
    assert job["percent"] == 100
    assert job["complete"] is True
    assert job["finalRows"] == row_count
    assert pl.read_csv(output_path).height == row_count
    bridge.close()


def test_json_input_supports_nested_record_path(tmp_path):
    source = tmp_path / "events.json"
    source.write_text(json.dumps({"data": {"events": [{"id": 1, "meta": {"ip": "127.0.0.1"}}, {"id": 2}]}}), encoding="utf-8")
    result = JsonInputPlugin().execute([], {"path": str(source), "format": "json", "record_path": "data.events", "encoding": "utf-8"}, ExecutionContext())
    assert result.height == 2
    assert result.row(0, named=True)["meta"] == '{"ip": "127.0.0.1"}'


def test_evtx_xml_parser_extracts_security_fields():
    xml = '''<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="Microsoft-Windows-Security-Auditing"/><EventID>4624</EventID><Level>0</Level><TimeCreated SystemTime="2026-08-20T01:02:03Z"/><EventRecordID>88</EventRecordID><Execution ProcessID="4" ThreadID="9"/><Channel>Security</Channel><Computer>ctf-pc</Computer><Security UserID="S-1-5-18"/></System><EventData><Data Name="TargetUserName">admin</Data><Data Name="IpAddress">10.0.0.8</Data></EventData></Event>'''
    result = _parse_evtx_xml(xml)
    assert result["事件ID"] == "4624"
    assert result["数据_TargetUserName"] == "admin"
    assert result["数据_IpAddress"] == "10.0.0.8"


def test_evtx_event_id_filter_accepts_checklist_and_legacy_text():
    assert _normalize_event_ids(["4624", "4625", "4624"]) == {"4624", "4625"}
    assert _normalize_event_ids("4624,4625；4688 1102") == {"4624", "4625", "4688", "1102"}


def test_json_and_sqlite_outputs_are_complete_and_readable(tmp_path):
    frame = pl.DataFrame({"序号": [1, 2, 3], "内容": ["alpha", "flag{ok}", "omega"]})
    json_path = tmp_path / "result.jsonl"
    JsonOutputPlugin().execute([frame], {"path": str(json_path), "format": "jsonl", "encoding": "utf-8"}, ExecutionContext(preview=False))
    assert [json.loads(line)["内容"] for line in json_path.read_text(encoding="utf-8").splitlines()] == ["alpha", "flag{ok}", "omega"]

    sqlite_path = tmp_path / "result.sqlite"
    SQLiteOutputPlugin().execute([frame], {"path": str(sqlite_path), "table": "evidence", "mode": "replace", "batch_size": 2}, ExecutionContext(preview=False))
    loaded = SQLiteInputPlugin().execute([], {"path": str(sqlite_path), "table": "evidence", "query": ""}, ExecutionContext(preview=False))
    assert loaded.to_dicts() == frame.to_dicts()

    progress_events = []
    chunked = SQLiteInputPlugin().execute([], {"path": str(sqlite_path), "table": "evidence", "query": ""}, ExecutionContext(
        preview=False,
        variables={
            "current_node_id": "sqlite", "current_node_index": 0, "current_node_count": 1,
            "current_node_label": "SQLite 数据库", "source_estimates": {"sqlite": {"large": True}},
            "database_batch_size": 2, "progress_callback": progress_events.append,
        },
    ))
    assert chunked.to_dicts() == frame.to_dicts()
    assert [event["sourceRows"] for event in progress_events] == [2, 3]
    assert progress_events[-1]["estimatedRows"] == 3


def test_pipeline_preview_masks_phone_number():
    result = PipelineEngine().execute(demo_pipeline(), target_node_id="mask")
    assert result["rows"][0]["手机号"] == "138****8000"
    assert result["stats"]["pluginId"] == "transform.mask"


def test_mask_with_zero_suffix_does_not_repeat_original_value():
    pipeline = demo_pipeline()
    mask = next(node for node in pipeline["nodes"] if node["id"] == "mask")
    mask["config"]["keep_end"] = 0
    result = PipelineEngine().execute(pipeline, target_node_id="mask")
    assert result["rows"][0]["手机号"] == "138********"


def test_mask_with_zero_prefix_and_suffix_masks_every_character():
    pipeline = demo_pipeline()
    mask = next(node for node in pipeline["nodes"] if node["id"] == "mask")
    mask["config"].update({"keep_start": 0, "keep_end": 0})
    result = PipelineEngine().execute(pipeline, target_node_id="mask")
    assert result["rows"][0]["手机号"] == "***********"


def pipeline_with_transforms(*transforms):
    nodes = [{"id": "source", "pluginId": "input.demo", "config": {}}]
    edges = []
    previous = "source"
    for index, (plugin_id, config) in enumerate(transforms):
        node_id = f"step-{index}"
        nodes.append({"id": node_id, "pluginId": plugin_id, "config": config})
        edges.append({"id": f"edge-{index}", "source": previous, "target": node_id})
        previous = node_id
    return {"nodes": nodes, "edges": edges}, previous


def test_filter_supports_less_and_less_equal():
    less_pipeline, less_target = pipeline_with_transforms(("transform.filter", {"field": "状态码", "operator": "less", "value": 404}))
    equal_pipeline, equal_target = pipeline_with_transforms(("transform.filter", {"field": "状态码", "operator": "less_equal", "value": 200}))
    assert PipelineEngine().execute(less_pipeline, target_node_id=less_target)["stats"]["rowCount"] == 5
    assert PipelineEngine().execute(equal_pipeline, target_node_id=equal_target)["stats"]["rowCount"] == 5


def test_text_replace_uppercase_and_lowercase():
    pipeline, target = pipeline_with_transforms(
        ("transform.replace", {"fields": ["路径"], "search": "/api/", "replacement": "/API/"}),
        ("transform.uppercase", {"fields": ["请求方法"]}),
        ("transform.lowercase", {"fields": ["协议"]}),
    )
    row = PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]
    assert row["路径"].startswith("/API/")
    assert row["请求方法"] == "GET"
    assert row["协议"] == "http"


def test_field_mapping_accepts_friendly_rules_and_legacy_json():
    friendly_pipeline, friendly_target = pipeline_with_transforms(("transform.mapping", {
        "source_field": "请求方法", "target_field": "操作", "value_map": [
            {"source_value": "GET", "target_value": "读取"},
            {"source_value": "POST", "target_value": "提交"},
            {"source_value": "", "target_value": "忽略"},
        ],
    }))
    legacy_pipeline, legacy_target = pipeline_with_transforms(("transform.mapping", {
        "source_field": "请求方法", "target_field": "操作", "value_map": '{"GET":"读取"}',
    }))
    assert PipelineEngine().execute(friendly_pipeline, target_node_id=friendly_target)["rows"][0]["操作"] == "读取"
    assert PipelineEngine().execute(friendly_pipeline, target_node_id=friendly_target)["rows"][2]["操作"] == "提交"
    assert PipelineEngine().execute(legacy_pipeline, target_node_id=legacy_target)["rows"][0]["操作"] == "读取"


def test_rename_and_split_columns():
    pipeline, target = pipeline_with_transforms(
        ("transform.rename_column", {"source_field": "路径", "target_field": "请求路径"}),
        ("transform.split_column", {"source_field": "请求路径", "delimiter": "/", "output_fields": ["空白", "模块", "资源", "动作"], "keep_source": True}),
    )
    row = PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]
    assert row["请求路径"] == "/api/user/login"
    assert row["模块"] == "api"
    assert row["资源"] == "user"
    assert row["动作"] == "login"


def test_split_column_requires_two_or_more_named_columns():
    pipeline, target = pipeline_with_transforms(
        ("transform.split_column", {"source_field": "路径", "delimiter": "/", "output_fields": ["唯一列"], "keep_source": True}),
    )
    try:
        PipelineEngine().execute(pipeline, target_node_id=target)
    except ValueError as exc:
        assert "至少需要设置两个" in str(exc)
    else:
        raise AssertionError("单个输出列应当被拒绝")


def test_merge_rows_keeps_only_selected_columns_and_returns_exactly_one_row():
    pipeline, target = pipeline_with_transforms(
        ("transform.merge_rows", {"fields": ["IP地址", "请求方法"], "separator": " | "}),
    )
    result = PipelineEngine().execute(pipeline, target_node_id=target)
    assert result["stats"]["rowCount"] == 1
    assert [column["key"] for column in result["columns"]] == ["IP地址", "请求方法"]
    row = result["rows"][0]
    assert row["IP地址"].count(" | ") == 5
    assert row["请求方法"].count(" | ") == 5
    assert "13800138000" not in str(row)


def test_url_codec_round_trip():
    pipeline, target = pipeline_with_transforms(
        ("transform.url_codec", {"fields": ["路径"], "operation": "encode"}),
        ("transform.url_codec", {"fields": ["路径"], "operation": "decode"}),
    )
    assert PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]["路径"] == "/api/user/login"


def test_trim_and_concat_columns():
    pipeline, target = pipeline_with_transforms(
        ("transform.replace", {"fields": ["协议"], "search": "HTTP", "replacement": "  HTTP  "}),
        ("transform.trim", {"fields": ["协议"], "mode": "both"}),
        ("transform.concat_columns", {"fields": ["请求方法", "协议"], "separator": "-", "output_name": "请求描述"}),
    )
    row = PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]
    assert row["协议"] == "HTTP"
    assert row["请求描述"] == "GET-HTTP"


def test_base64_encode_and_decode_round_trip():
    pipeline, target = pipeline_with_transforms(
        ("transform.base64", {"fields": ["手机号"], "operation": "encode", "encoding": "utf-8"}),
        ("transform.base64", {"fields": ["手机号"], "operation": "decode", "encoding": "utf-8"}),
    )
    assert PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]["手机号"] == "13800138000"


def test_md5_digest_matches_standard_result():
    pipeline, target = pipeline_with_transforms(("transform.md5", {"fields": ["手机号"], "salt": ""}))
    result = PipelineEngine().execute(pipeline, target_node_id=target)
    assert result["rows"][0]["手机号"] == hashlib.md5(b"13800138000").hexdigest()


def test_aes_encrypt_and_decrypt_round_trip():
    pipeline, target = pipeline_with_transforms(
        ("transform.aes", {"fields": ["手机号"], "operation": "encrypt", "key": "test-key"}),
        ("transform.aes", {"fields": ["手机号"], "operation": "decrypt", "key": "test-key"}),
    )
    assert PipelineEngine().execute(pipeline, target_node_id=target)["rows"][0]["手机号"] == "13800138000"


def test_transform_plugins_expose_secondary_categories():
    transforms = [item for item in PipelineEngine().registry.list_definitions() if item["kind"] == "transform"]
    assert {item["category"] for item in transforms} >= {"筛选与字段", "文本处理", "字段转换", "聚合与结构", "安全与隐私", "加密与编码"}


def test_preview_cache_is_bounded_during_frequent_config_changes():
    engine = PipelineEngine()
    for value in range(80):
        pipeline, target = pipeline_with_transforms(("transform.filter", {"field": "状态码", "operator": "greater_equal", "value": value}))
        engine.execute(pipeline, target_node_id=target)
    assert len(engine._cache) <= 64


def test_cycle_is_rejected():
    pipeline = demo_pipeline()
    pipeline["edges"].append({"id": "cycle", "source": "mask", "target": "source"})
    errors = PipelineEngine().validate(pipeline)
    assert any("循环" in error for error in errors)


def test_select_columns_keeps_requested_fields():
    pipeline = demo_pipeline()
    pipeline["nodes"].append({"id": "select", "pluginId": "transform.select_columns", "config": {"columns": ["IP地址", "手机号"], "mode": "keep"}})
    pipeline["edges"].append({"id": "e3", "source": "mask", "target": "select"})
    result = PipelineEngine().execute(pipeline, target_node_id="select")
    assert [column["key"] for column in result["columns"]] == ["IP地址", "手机号"]


def test_merge_inputs_combines_multiple_upstreams_and_tracks_source():
    plugin = PipelineEngine().registry.get("transform.merge_inputs")
    result = plugin.execute(
        [pl.DataFrame({"姓名": ["小明"], "分数": [80]}), pl.DataFrame({"姓名": ["小红"], "城市": ["上海"]})],
        {"mode": "union", "add_source": True, "source_field": "来源"},
        ExecutionContext(variables={"direct_parent_labels": ["一班", "二班"]}),
    )
    assert result.height == 2
    assert result.columns == ["姓名", "分数", "来源", "城市"]
    assert result["来源"].to_list() == ["一班", "二班"]


def test_deduplicate_supports_selected_fields_and_keep_policy():
    plugin = PipelineEngine().registry.get("transform.deduplicate")
    frame = pl.DataFrame({"用户": ["A", "A", "B"], "分数": [80, 90, 70]})
    first = plugin.execute([frame], {"fields": ["用户"], "keep": "first"}, ExecutionContext())
    unique_only = plugin.execute([frame], {"fields": ["用户"], "keep": "none"}, ExecutionContext())
    assert first.to_dicts() == [{"用户": "A", "分数": 80}, {"用户": "B", "分数": 70}]
    assert unique_only.to_dicts() == [{"用户": "B", "分数": 70}]


def test_group_aggregate_runs_multiple_statistics_in_one_node():
    plugin = PipelineEngine().registry.get("transform.group")
    frame = pl.DataFrame({"性别": ["男", "女", "男", "女"], "分数": [80, 90, 100, 70]})
    result = plugin.execute([frame], {"group_by": ["性别"], "aggregate_rules": [
        {"operation": "count", "field": "", "output_name": "人数"},
        {"operation": "mean", "field": "分数", "output_name": "平均分"},
        {"operation": "max", "field": "分数", "output_name": "最高分"},
    ]}, ExecutionContext())
    assert result.to_dicts() == [
        {"性别": "男", "人数": 2, "平均分": 90.0, "最高分": 100},
        {"性别": "女", "人数": 2, "平均分": 80.0, "最高分": 90},
    ]


def test_multi_input_preview_combines_all_direct_parents(tmp_path):
    pipeline = {"nodes": [
        {"id": "source-a", "pluginId": "input.demo", "label": "来源A", "config": {}},
        {"id": "source-b", "pluginId": "input.demo", "label": "来源B", "config": {}},
        {"id": "merge", "pluginId": "transform.merge_inputs", "config": {"mode": "union"}},
    ], "edges": [
        {"id": "e1", "source": "source-a", "target": "merge"},
        {"id": "e2", "source": "source-b", "target": "merge"},
    ]}
    preview = DesktopBridge(tmp_path).preview_node_input(pipeline, "merge")
    assert preview["ok"] is True
    assert preview["data"]["stats"]["rowCount"] == 12
    assert "数据来源" in [column["key"] for column in preview["data"]["columns"]]


def test_incomplete_downstream_node_does_not_block_upstream_preview():
    pipeline = demo_pipeline()
    pipeline["nodes"].append({"id": "incomplete", "pluginId": "transform.select_columns", "config": {}})
    pipeline["edges"].append({"id": "e3", "source": "mask", "target": "incomplete"})
    result = PipelineEngine().execute(pipeline, target_node_id="mask")
    assert result["stats"]["nodeId"] == "mask"


def test_bridge_reads_upstream_columns_for_incomplete_config(tmp_path):
    pipeline = demo_pipeline()
    pipeline["nodes"].append({"id": "select", "pluginId": "transform.select_columns", "config": {}})
    pipeline["edges"].append({"id": "e3", "source": "mask", "target": "select"})
    result = DesktopBridge(tmp_path).preview_node_input(pipeline, "select")
    assert result["ok"] is True
    assert "手机号" in [column["key"] for column in result["data"]["columns"]]


def test_input_preview_is_before_selected_transform(tmp_path):
    bridge = DesktopBridge(tmp_path)
    input_result = bridge.preview_node_input(demo_pipeline(), "mask")
    output_result = bridge.preview_pipeline(demo_pipeline(), "mask")
    assert input_result["data"]["rows"][0]["手机号"] == "13800138000"
    assert output_result["data"]["rows"][0]["手机号"] == "138****8000"


def test_project_round_trip(tmp_path):
    bridge = DesktopBridge(tmp_path)
    saved = bridge.save_project(demo_pipeline(), "测试项目")
    assert saved["ok"] is True
    listed = bridge.list_projects()
    assert listed[0]["name"] == "测试项目"
    loaded = bridge.load_project(saved["path"])
    assert loaded["data"]["nodes"][0]["pluginId"] == "input.demo"


def test_storage_config_defaults_to_local_and_persists(tmp_path, monkeypatch):
    bridge = DesktopBridge(tmp_path)
    assert bridge.get_storage_config()["mode"] == "local"
    assert bridge.configure_storage({"mode": "local"})["ok"] is True
    assert json.loads((tmp_path / "storage.json").read_text(encoding="utf-8"))["mode"] == "local"

    monkeypatch.setattr(bridge, "test_storage_connection", lambda config: {"ok": True, "message": "连接成功"})
    result = bridge.configure_storage({"mode": "mysql", "mysql": {"host": "db.local", "username": "ctf", "password": "secret", "database": "workbench", "table": "projects"}})
    assert result["ok"] is True
    saved = bridge.get_storage_config()
    assert saved["mode"] == "mysql"
    assert saved["mysql"]["host"] == "db.local"
    assert saved["mysql"]["charset"] == "utf8mb4"


def test_initialize_mysql_storage_creates_schema_and_saves_config(tmp_path, monkeypatch):
    bridge = DesktopBridge(tmp_path)
    initialized = {"database": "workbench", "projectTable": "projects", "metaTable": "projects_meta", "schemaVersion": 1}
    monkeypatch.setattr(bridge, "_prepare_mysql_storage", lambda config: initialized)
    result = bridge.initialize_storage({"mode": "mysql", "mysql": {"host": "db.local", "username": "ctf", "password": "secret", "database": "workbench", "table": "projects"}})
    assert result["ok"] is True
    assert result["details"] == initialized
    assert bridge.get_storage_config()["mode"] == "mysql"
    assert "项目表 projects" in result["message"]


def test_mysql_storage_initializer_creates_database_tables_metadata_and_index(tmp_path, monkeypatch):
    statements = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            statements.append((sql, params))

        def fetchone(self):
            return (0,)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            statements.append(("COMMIT", None))

        def close(self):
            pass

    class FakePyMysql:
        @staticmethod
        def connect(**kwargs):
            return FakeConnection()

    monkeypatch.setitem(sys.modules, "pymysql", FakePyMysql)
    details = DesktopBridge(tmp_path)._prepare_mysql_storage({
        "host": "127.0.0.1", "port": 3306, "username": "root", "password": "root",
        "database": "dataworkbench", "table": "projects", "charset": "utf8mb4",
        "timezone": "+08:00", "ssl_mode": "disabled", "connect_timeout": 5,
        "read_timeout": 30, "write_timeout": 30,
    })
    sql = "\n".join(statement for statement, _ in statements)
    assert "CREATE DATABASE IF NOT EXISTS `dataworkbench`" in sql
    assert "CREATE TABLE IF NOT EXISTS `projects`" in sql
    assert "CREATE TABLE IF NOT EXISTS `projects_meta`" in sql
    assert "CREATE INDEX `idx_updated_at`" in sql
    assert any(params == ("schema_version", "1") for _, params in statements)
    assert details == {"database": "dataworkbench", "projectTable": "projects", "metaTable": "projects_meta", "schemaVersion": 1}


def test_file_dialog_uses_current_pywebview_types(tmp_path):
    class FakeWindow:
        def __init__(self):
            self.calls = []

        def create_file_dialog(self, dialog_type, **kwargs):
            self.calls.append((dialog_type, kwargs))
            return (r"D:\data\sample.xlsx",)

    bridge = DesktopBridge(tmp_path)
    fake_window = FakeWindow()
    bridge.attach_window(fake_window)
    opened = bridge.pick_file(["xlsx", "csv"])
    saved = bridge.pick_save_file("csv")
    assert opened["path"] == r"D:\data\sample.xlsx"
    assert saved["path"] == r"D:\data\sample.xlsx"
    assert fake_window.calls[0][0] == webview.FileDialog.OPEN
    assert fake_window.calls[1][0] == webview.FileDialog.SAVE


def test_mysql_input_exposes_simple_cascading_fields():
    mysql = next(item for item in PipelineEngine().registry.list_definitions() if item["id"] == "input.mysql")
    fields = {field["key"]: field for field in mysql["config_fields"]}
    assert fields["username"]["required"] is True
    assert fields["password"]["field_type"] == "password"
    assert fields["database"]["field_type"] == "mysql_database"
    assert fields["table"]["field_type"] == "mysql_table"
    assert fields["ssl_mode"]["default"] == "disabled"
    assert fields["charset"]["default"] == "utf8mb4"
    assert fields["timezone"]["default"] == "+08:00"


def test_mysql_output_supports_existing_or_auto_create_modes():
    engine = PipelineEngine()
    mysql = next(item for item in engine.registry.list_definitions() if item["id"] == "output.mysql")
    fields = {field["key"]: field for field in mysql["config_fields"]}
    assert fields["target_mode"]["options"][0]["value"] == "existing"
    assert fields["database"]["field_type"] == "mysql_database"
    assert fields["table"]["field_type"] == "mysql_table"
    assert fields["database_manual"]["default"] == "ctf_data"
    assert fields["table_manual"]["default"] == "result"

    plugin = engine.registry.get("output.mysql")
    common = {"host": "127.0.0.1", "username": "root", "password": "root"}
    assert "请选择已有数据库" in plugin.validate({**common, "target_mode": "existing"})
    assert plugin.validate({**common, "target_mode": "manual", "database_manual": "ctf", "table_manual": "flags"}) == []


def test_mysql_connection_options_are_validated_and_forwarded():
    config = {"host": "localhost", "port": 3307, "username": "root", "password": "root", "charset": "gbk", "timezone": "+08:00", "ssl_mode": "disabled", "connect_timeout": 7, "read_timeout": 9, "write_timeout": 11}
    kwargs = mysql_connect_kwargs(config, database="ctf")
    assert kwargs["database"] == "ctf"
    assert kwargs["charset"] == "gbk"
    assert kwargs["ssl_disabled"] is True
    assert kwargs["init_command"] == "SET time_zone='+08:00'"
    assert (kwargs["connect_timeout"], kwargs["read_timeout"], kwargs["write_timeout"]) == (7, 9, 11)
    assert quote_mysql_identifier("ctf`result", "表") == "`ctf``result`"


def test_excel_output_does_not_require_optional_pyarrow(tmp_path):
    output = tmp_path / "result.xlsx"
    FileOutputPlugin().execute([pl.DataFrame({"flag": ["flag{xlsx}"], "score": [100]})], {"path": str(output), "format": "xlsx"}, ExecutionContext(preview=False))
    frame = pd.read_excel(output)
    assert frame.to_dict("records") == [{"flag": "flag{xlsx}", "score": 100}]


def test_desktop_worker_executes_preview_out_of_process(tmp_path):
    bridge = DesktopBridge(tmp_path, use_worker=True)
    try:
        bridge.warm_worker()
        result = bridge.preview_pipeline(demo_pipeline(), "mask", 20)
        assert result["ok"] is True
        assert result["data"]["rows"][0]["手机号"] == "138****8000"
    finally:
        bridge.close()
