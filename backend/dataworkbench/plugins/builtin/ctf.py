from __future__ import annotations

import base64
import re
from collections import defaultdict
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


def _fields(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _ascii(data: bytes) -> str:
    return "".join(chr(value) if 32 <= value < 127 else "." for value in data)


class SessionGroupPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.session_group", name="PCAP 会话分组", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 流量分析",
        description="按五元组会话汇总包数、字节数和时间范围", icon="network", color="#2563eb",
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        required = {"会话ID", "协议", "源IP", "目标IP", "源端口", "目标端口", "长度", "时间"}
        if not required.issubset(frame.columns):
            raise ValueError("上游数据不是带会话信息的 PCAP 数据")
        return frame.group_by("会话ID", maintain_order=True).agg(
            pl.col("协议").first(), pl.col("源IP").first(), pl.col("目标IP").first(),
            pl.col("源端口").first(), pl.col("目标端口").first(), pl.len().alias("包数"),
            pl.col("长度").sum().alias("总字节数"), pl.col("Payload长度").sum().alias("Payload字节数"),
            pl.col("时间").min().alias("开始时间"), pl.col("时间").max().alias("结束时间"),
        ).sort("总字节数", descending=True)


class TcpReassemblePlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.tcp_reassemble", name="TCP 流重组", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 流量分析",
        description="按会话、方向和 TCP 序号重组 Payload", icon="flow", color="#1d4ed8",
        config_fields=(ConfigField("max_bytes", "每条流最大字节数", "number", default=5_000_000, help_text="防止异常流占满内存，0 表示不限制"),),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        required = {"会话ID", "方向", "TCP序号", "PayloadHex"}
        if not required.issubset(frame.columns):
            raise ValueError("TCP 流重组需要 PCAP 数据中的会话ID、方向、TCP序号和PayloadHex")
        streams: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
        for row in frame.filter((pl.col("协议") == "TCP") & (pl.col("Payload长度") > 0)).iter_rows(named=True):
            streams[(str(row["会话ID"]), str(row["方向"]))].append((int(row.get("TCP序号") or 0), int(row.get("序号") or 0), str(row.get("PayloadHex") or "")))
        output = []
        max_bytes = max(0, int(config.get("max_bytes", 5_000_000)))
        for (session_id, direction), segments in streams.items():
            payload = bytearray()
            seen_sequences = set()
            for sequence, _, payload_hex in sorted(segments):
                if sequence in seen_sequences:
                    continue
                seen_sequences.add(sequence)
                try:
                    payload.extend(bytes.fromhex(payload_hex))
                except ValueError:
                    continue
                if max_bytes and len(payload) >= max_bytes:
                    del payload[max_bytes:]
                    break
            output.append({
                "会话ID": session_id, "方向": direction, "数据包数": len(segments), "重组字节数": len(payload),
                "PayloadHex": bytes(payload).hex(), "PayloadASCII": _ascii(bytes(payload)),
            })
        return pl.DataFrame(output) if output else pl.DataFrame({"会话ID": [], "方向": [], "数据包数": [], "重组字节数": [], "PayloadHex": [], "PayloadASCII": []})


class HttpExtractPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.http_extract", name="HTTP 数据提取", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 协议提取",
        description="提取 HTTP 方法、Host、路径、状态码和 Payload", icon="network", color="#0ea5e9",
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        columns = [column for column in ["序号", "时间", "会话ID", "源IP", "目标IP", "HTTP方法", "HTTP主机", "HTTP路径", "HTTP状态", "Payload长度", "PayloadHex", "PayloadASCII"] if column in frame.columns]
        if "HTTP方法" in frame.columns:
            return frame.filter((pl.col("HTTP方法") != "") | (pl.col("HTTP状态") != "")).select(columns)
        if "PayloadASCII" not in frame.columns:
            raise ValueError("上游没有可分析的 Payload")
        return frame.filter(pl.col("PayloadASCII").str.contains(r"^(GET|POST|PUT|DELETE|HEAD|HTTP/)")).select(columns)


class DnsExtractPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.dns_extract", name="DNS 数据提取", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 协议提取",
        description="提取 DNS 查询、响应以及通信端点", icon="network", color="#06b6d4",
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if "DNS查询" not in frame.columns:
            raise ValueError("上游没有 DNS 字段")
        columns = [column for column in ["序号", "时间", "会话ID", "源IP", "目标IP", "DNS查询", "DNS响应", "PayloadHex"] if column in frame.columns]
        return frame.filter((pl.col("DNS查询") != "") | (pl.col("DNS响应") != "")).select(columns)


class IcmpExtractPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.icmp_extract", name="ICMP 数据提取", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 协议提取",
        description="提取 ICMP 类型、代码和可能隐藏在载荷中的数据", icon="network", color="#0891b2",
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        if "ICMP类型" not in frame.columns:
            raise ValueError("上游没有 ICMP 字段")
        columns = [column for column in ["序号", "时间", "会话ID", "源IP", "目标IP", "ICMP类型", "ICMP代码", "Payload长度", "PayloadHex", "PayloadASCII"] if column in frame.columns]
        return frame.filter(pl.col("协议") == "ICMP").select(columns)


class HexCodecPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.hex_codec", name="Hex 编解码", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 编码解码",
        description="文本与十六进制数据互相转换", icon="text-t", color="#7c3aed",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("operation", "操作", "select", default="decode", options=[{"label": "Hex解码", "value": "decode"}, {"label": "Hex编码", "value": "encode"}]),
            ConfigField("encoding", "文本编码", default="utf-8"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame, operation, encoding = self.require_input(inputs), config.get("operation", "decode"), str(config.get("encoding", "utf-8"))
        def convert(value: Any) -> str | None:
            if value is None:
                return None
            if operation == "encode":
                return str(value).encode(encoding).hex()
            try:
                return bytes.fromhex(re.sub(r"\s+", "", str(value))).decode(encoding, errors="replace")
            except ValueError as exc:
                raise ValueError("Hex 内容无效") from exc
        return frame.with_columns([pl.col(field).map_elements(convert, return_dtype=pl.String).alias(field) for field in _fields(config.get("fields")) if field in frame.columns])


_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = bytearray()
    while number:
        number, remainder = divmod(number, 58)
        encoded.append(_BASE58_ALPHABET[remainder])
    leading = len(data) - len(data.lstrip(b"\0"))
    return (b"1" * leading + bytes(reversed(encoded or b"1"))).decode("ascii")


def _base58_decode(text: str) -> bytes:
    number = 0
    for character in text.encode("ascii"):
        number = number * 58 + _BASE58_ALPHABET.index(character)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + raw


class MultiBaseCodecPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.base_codec", name="多种 Base 编解码", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 编码解码",
        description="支持 Base16、Base32、Base58、Base64 和 Base85", icon="text-t", color="#8b5cf6",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("base", "编码类型", "select", default="base64", options=[{"label": name.upper(), "value": name} for name in ["base16", "base32", "base58", "base64", "base85"]]),
            ConfigField("operation", "操作", "select", default="decode", options=[{"label": "解码", "value": "decode"}, {"label": "编码", "value": "encode"}]),
            ConfigField("encoding", "文本编码", default="utf-8"),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        base_name, operation, encoding = config.get("base", "base64"), config.get("operation", "decode"), str(config.get("encoding", "utf-8"))
        codecs = {"base16": (base64.b16encode, base64.b16decode), "base32": (base64.b32encode, base64.b32decode), "base64": (base64.b64encode, base64.b64decode), "base85": (base64.b85encode, base64.b85decode)}
        def convert(value: Any) -> str | None:
            if value is None:
                return None
            try:
                if base_name == "base58":
                    return _base58_encode(str(value).encode(encoding)) if operation == "encode" else _base58_decode(str(value)).decode(encoding, errors="replace")
                encoder, decoder = codecs[base_name]
                return encoder(str(value).encode(encoding)).decode("ascii") if operation == "encode" else decoder(str(value).encode("ascii")).decode(encoding, errors="replace")
            except Exception as exc:
                raise ValueError(f"{base_name.upper()} 内容无效") from exc
        return frame.with_columns([pl.col(field).map_elements(convert, return_dtype=pl.String).alias(field) for field in _fields(config.get("fields")) if field in frame.columns])


def _score_plaintext(data: bytes) -> float:
    if not data:
        return -1
    printable = sum(32 <= value < 127 or value in (9, 10, 13) for value in data) / len(data)
    text = data.decode("latin-1", errors="ignore").lower()
    common = sum(text.count(token) for token in (" the ", "flag", "ctf", "http", "pass", "key", "{", "}"))
    return printable * 100 + common * 8


class XorPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.xor", name="XOR 解密与爆破", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 密码爆破",
        description="使用指定密钥 XOR，或爆破单字节密钥并按可读性排序", icon="lock", color="#dc2626",
        config_fields=(
            ConfigField("fields", "选择字段", "columns", required=True),
            ConfigField("mode", "模式", "select", default="bruteforce", options=[{"label": "单字节爆破", "value": "bruteforce"}, {"label": "指定密钥", "value": "apply"}]),
            ConfigField("key", "密钥", default="", help_text="支持普通文本或 0x2a 形式"),
            ConfigField("input_format", "输入格式", "select", default="text", options=[{"label": "文本", "value": "text"}, {"label": "Hex", "value": "hex"}, {"label": "Base64", "value": "base64"}]),
            ConfigField("top", "保留候选数", "number", default=5),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame, mode = self.require_input(inputs), config.get("mode", "bruteforce")
        def source_bytes(value: Any) -> bytes:
            text = str(value)
            if config.get("input_format") == "hex": return bytes.fromhex(re.sub(r"\s+", "", text))
            if config.get("input_format") == "base64": return base64.b64decode(text)
            return text.encode("latin-1", errors="replace")
        def convert(value: Any) -> str | None:
            if value is None: return None
            data = source_bytes(value)
            if mode == "apply":
                key_text = str(config.get("key", ""))
                if not key_text: raise ValueError("指定密钥模式需要填写密钥")
                key = bytes([int(key_text, 16)]) if key_text.lower().startswith("0x") else key_text.encode("utf-8")
                return bytes(value ^ key[index % len(key)] for index, value in enumerate(data)).decode("utf-8", errors="replace")
            candidates = []
            for key in range(256):
                decoded = bytes(value ^ key for value in data)
                candidates.append((_score_plaintext(decoded), key, decoded.decode("utf-8", errors="replace")))
            return "\n".join(f"0x{key:02x} | {text}" for _, key, text in sorted(candidates, reverse=True)[:max(1, int(config.get('top', 5)))])
        expressions = [pl.col(field).map_elements(convert, return_dtype=pl.String).alias(f"{field}_XOR结果") for field in _fields(config.get("fields")) if field in frame.columns]
        return frame.with_columns(expressions)


class CaesarPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.caesar", name="凯撒密码爆破", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 密码爆破",
        description="尝试全部 26 种字母位移并输出候选结果", icon="text-aa", color="#ea580c",
        config_fields=(ConfigField("fields", "选择字段", "columns", required=True),),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        def candidates(value: Any) -> str | None:
            if value is None: return None
            text = str(value)
            rows = []
            for shift in range(26):
                decoded = "".join(chr((ord(char) - base - shift) % 26 + base) if (base := 65 if char.isupper() else 97 if char.islower() else 0) else char for char in text)
                rows.append(f"{shift:02d} | {decoded}")
            return "\n".join(rows)
        return frame.with_columns([pl.col(field).map_elements(candidates, return_dtype=pl.String).alias(f"{field}_凯撒候选") for field in _fields(config.get("fields")) if field in frame.columns])


class FlagScanPlugin(DataPlugin):
    definition = PluginDefinition(
        id="ctf.flag_scan", name="Flag 自动扫描", kind=PluginKind.TRANSFORM, group="数据处理", category="CTF 检测",
        description="在文本、Payload、Hex解码结果中扫描疑似 Flag", icon="funnel", color="#16a34a",
        config_fields=(
            ConfigField("fields", "扫描字段", "columns", required=True),
            ConfigField("pattern", "Flag 正则", default=r"[A-Za-z0-9_]{0,24}\{[^{}\r\n]{1,200}\}"),
            ConfigField("only_matches", "只保留命中行", "boolean", default=True),
        ),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        pattern = re.compile(str(config.get("pattern") or self.definition.config_fields[1].default), re.IGNORECASE)
        fields = [field for field in _fields(config.get("fields")) if field in frame.columns]
        def scan(row: dict[str, Any]) -> dict[str, Any]:
            matches = []
            for field in fields:
                text = str(row.get(field) or "")
                matches.extend(match.group(0) for match in pattern.finditer(text))
                if field.lower().endswith("hex"):
                    try:
                        decoded = bytes.fromhex(text).decode("utf-8", errors="ignore")
                        matches.extend(match.group(0) for match in pattern.finditer(decoded))
                    except ValueError:
                        pass
            unique = list(dict.fromkeys(matches))
            return {**row, "Flag命中": "\n".join(unique), "Flag数量": len(unique)}
        rows = [scan(row) for row in frame.iter_rows(named=True)]
        result = pl.DataFrame(rows) if rows else frame.with_columns(pl.lit("").alias("Flag命中"), pl.lit(0).alias("Flag数量"))
        return result.filter(pl.col("Flag数量") > 0) if bool(config.get("only_matches", True)) else result


CTF_PLUGINS = [
    SessionGroupPlugin, TcpReassemblePlugin, HttpExtractPlugin, DnsExtractPlugin, IcmpExtractPlugin,
    HexCodecPlugin, MultiBaseCodecPlugin, XorPlugin, CaesarPlugin, FlagScanPlugin,
]
