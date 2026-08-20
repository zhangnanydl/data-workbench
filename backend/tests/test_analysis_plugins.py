import hashlib

import polars as pl

from dataworkbench.models import ExecutionContext
from dataworkbench.plugins.builtin.analysis import (
    DateTimeFeaturesPlugin,
    HashDigestPlugin,
    IocExtractPlugin,
    JoinInputsPlugin,
    JsonFlattenPlugin,
    MissingValuesPlugin,
    RegexExtractPlugin,
    SortRowsPlugin,
)


CONTEXT = ExecutionContext(preview=False)


def test_sort_rows_and_missing_value_strategies():
    frame = pl.DataFrame({"group": ["b", "a", "a"], "score": [2, None, 3]})
    sorted_frame = SortRowsPlugin().execute([frame], {"fields": ["group", "score"], "direction": "ascending", "nulls_last": True}, CONTEXT)
    assert sorted_frame["group"].to_list() == ["a", "a", "b"]
    assert sorted_frame["score"].to_list() == [3, None, 2]

    filled = MissingValuesPlugin().execute([frame], {"fields": ["score"], "mode": "fixed", "value": "0"}, CONTEXT)
    assert filled["score"].to_list() == [2, 0, 3]
    dropped = MissingValuesPlugin().execute([frame], {"fields": ["score"], "mode": "drop"}, CONTEXT)
    assert dropped.height == 2


def test_join_inputs_supports_relational_key_join():
    left = pl.DataFrame({"user_id": [1, 2, 3], "event": ["login", "scan", "logout"]})
    right = pl.DataFrame({"id": [1, 3], "risk": ["low", "high"]})
    result = JoinInputsPlugin().execute([left, right], {"left_key": "user_id", "right_key": "id", "how": "left", "suffix": "_资产"}, CONTEXT)
    assert result.height == 3
    assert result["risk"].to_list() == ["low", None, "high"]


def test_regex_json_and_datetime_extraction():
    logs = pl.DataFrame({"message": ["user=alice src=10.0.0.8", "user=bob src=10.0.0.9"]})
    extracted = RegexExtractPlugin().execute([logs], {"source_field": "message", "pattern": r"user=(\w+)", "group": 1, "output_name": "user"}, CONTEXT)
    assert extracted["user"].to_list() == ["alice", "bob"]

    nested = pl.DataFrame({"id": [1], "detail": ['{"user":{"name":"alice","admin":true},"tags":["ctf","web"]}']})
    flattened = JsonFlattenPlugin().execute([nested], {"source_field": "detail", "prefix": "详情_", "max_depth": 4, "keep_source": False}, CONTEXT)
    assert flattened["详情_user.name"][0] == "alice"
    assert flattened["详情_user.admin"][0] is True
    assert flattened["详情_tags"][0] == '["ctf", "web"]'

    times = pl.DataFrame({"time": ["2026-08-20 13:14:15"]})
    dated = DateTimeFeaturesPlugin().execute([times], {"source_field": "time", "format": "%Y-%m-%d %H:%M:%S", "output_name": "标准时间", "parts": ["年", "月", "日", "小时", "星期", "Unix时间戳"]}, CONTEXT)
    assert dated.select("年", "月", "日", "小时").row(0) == (2026, 8, 20, 13)
    assert dated["Unix时间戳"][0] > 1_700_000_000


def test_ioc_extraction_validates_ips_and_expands_matches():
    frame = pl.DataFrame({"message": ["访问 https://evil.example/a，回连 10.0.0.8，hash d41d8cd98f00b204e9800998ecf8427e", "invalid 999.1.1.1"]})
    result = IocExtractPlugin().execute([frame], {"source_field": "message", "types": ["IP", "URL", "域名", "哈希"], "keep_unmatched": False}, CONTEXT)
    pairs = set(zip(result["IOC类型"].to_list(), result["IOC值"].to_list()))
    assert ("IP", "10.0.0.8") in pairs
    assert ("URL", "https://evil.example/a") in pairs
    assert ("域名", "evil.example") in pairs
    assert ("哈希", "d41d8cd98f00b204e9800998ecf8427e") in pairs
    assert all(value != "999.1.1.1" for value in result["IOC值"])


def test_sha_digest_can_preserve_source_and_write_new_column():
    frame = pl.DataFrame({"value": ["flag"]})
    result = HashDigestPlugin().execute([frame], {"fields": ["value"], "algorithm": "sha256", "salt": "ctf:", "suffix": "_sha"}, CONTEXT)
    assert result["value"][0] == "flag"
    assert result["value_sha"][0] == hashlib.sha256(b"ctf:flag").hexdigest()
