from __future__ import annotations

import re
from typing import Any


MYSQL_ADVANCED_FIELDS = (
    "charset", "timezone", "ssl_mode", "connect_timeout", "read_timeout", "write_timeout",
)


def mysql_connect_kwargs(config: dict[str, Any], *, database: str | None = None) -> dict[str, Any]:
    charset = str(config.get("charset", "utf8mb4") or "utf8mb4").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", charset):
        raise ValueError("MySQL 字符集格式无效")
    timezone = str(config.get("timezone", "+08:00") or "").strip()
    if timezone and not re.fullmatch(r"SYSTEM|[+-]\d{2}:\d{2}|[A-Za-z][A-Za-z0-9_+\-/]*", timezone):
        raise ValueError("MySQL 时区格式无效，请使用 +08:00、SYSTEM 或 Asia/Shanghai")
    kwargs: dict[str, Any] = {
        "host": str(config.get("host", "127.0.0.1")),
        "port": int(config.get("port", 3306)),
        "user": str(config.get("username", "")),
        "password": str(config.get("password", "")),
        "charset": charset,
        "connect_timeout": max(1, int(config.get("connect_timeout", 5))),
        "read_timeout": max(1, int(config.get("read_timeout", 30))),
        "write_timeout": max(1, int(config.get("write_timeout", 30))),
    }
    if database:
        kwargs["database"] = database
    if timezone:
        kwargs["init_command"] = f"SET time_zone='{timezone}'"
    ssl_mode = str(config.get("ssl_mode", "disabled") or "disabled")
    if ssl_mode == "disabled":
        kwargs["ssl_disabled"] = True
    elif ssl_mode == "required":
        kwargs["ssl"] = {"check_hostname": False}
    elif ssl_mode != "preferred":
        raise ValueError(f"不支持的 SSL 模式: {ssl_mode}")
    return kwargs


def mysql_sqlalchemy_engine(config: dict[str, Any], *, database: str | None = None):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    connect_args = mysql_connect_kwargs(config, database=None)
    for key in ("host", "port", "user", "password"):
        connect_args.pop(key, None)
    url = URL.create(
        "mysql+pymysql",
        username=str(config.get("username", "")),
        password=str(config.get("password", "")),
        host=str(config.get("host", "127.0.0.1")),
        port=int(config.get("port", 3306)),
        database=database,
    )
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def quote_mysql_identifier(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    if len(text) > 64 or "\0" in text:
        raise ValueError(f"{label}格式无效")
    return f"`{text.replace('`', '``')}`"


def mysql_advanced_config_fields(ConfigField):
    return (
        ConfigField("advanced", "显示连接选项（SSL、时区等）", "boolean", default=True,
                    help_text="默认值适合本机 MySQL；关闭只会收起选项，不会清空配置"),
        ConfigField("charset", "字符集", "select", default="utf8mb4", options=[
            {"label": "utf8mb4（推荐）", "value": "utf8mb4"}, {"label": "utf8", "value": "utf8"},
            {"label": "GBK", "value": "gbk"}, {"label": "latin1", "value": "latin1"},
        ]),
        ConfigField("timezone", "连接时区", "select", default="+08:00", options=[
            {"label": "+08:00（中国标准时间，默认）", "value": "+08:00"},
            {"label": "+00:00（UTC）", "value": "+00:00"},
            {"label": "SYSTEM（跟随 MySQL 服务器）", "value": "SYSTEM"},
            {"label": "Asia/Shanghai（需服务器时区表）", "value": "Asia/Shanghai"},
            {"label": "不主动设置时区", "value": ""},
        ], help_text="建议使用数字偏移；命名时区要求 MySQL 已加载时区表"),
        ConfigField("ssl_mode", "SSL 模式", "select", default="disabled", options=[
            {"label": "忽略/禁用 SSL（本地默认）", "value": "disabled"},
            {"label": "优先使用 SSL", "value": "preferred"},
            {"label": "必须使用 SSL", "value": "required"},
        ], help_text="远程或生产数据库建议选择必须使用 SSL"),
        ConfigField("connect_timeout", "连接超时（秒）", "number", default=5),
        ConfigField("read_timeout", "读取超时（秒）", "number", default=30),
        ConfigField("write_timeout", "写入超时（秒）", "number", default=30),
    )
