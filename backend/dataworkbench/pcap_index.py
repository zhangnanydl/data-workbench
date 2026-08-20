from __future__ import annotations

import csv
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

import polars as pl


PACKET_COLUMNS = [
    "序号", "时间", "源IP", "目标IP", "协议", "源端口", "目标端口", "长度",
    "会话ID", "方向", "TCP序号", "Payload长度", "PayloadHex", "PayloadASCII",
    "HTTP方法", "HTTP主机", "HTTP路径", "HTTP状态", "DNS查询", "DNS响应", "ICMP类型", "ICMP代码",
]

SQL_COLUMNS = [
    "packet_no", "timestamp", "src_ip", "dst_ip", "protocol", "src_port", "dst_port", "length",
    "session_id", "direction", "tcp_seq", "payload_len", "payload_hex", "payload_ascii",
    "http_method", "http_host", "http_path", "http_status", "dns_query", "dns_answer", "icmp_type", "icmp_code",
]


def _index_path(source: Path, cache_dir: Path) -> Path:
    stat = source.stat()
    key = hashlib.sha256(f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")).hexdigest()[:20]
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"pcap_{key}.sqlite"


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip(".")
    return str(value or "")


def _payload_details(payload: bytes) -> tuple[str, str, str, str, str, str]:
    payload_hex = payload.hex()
    payload_ascii = "".join(chr(value) if 32 <= value < 127 else "." for value in payload)
    method = host = path = status = ""
    if payload:
        text = payload.decode("latin-1", errors="replace")
        lines = text.splitlines()
        if lines:
            parts = lines[0].split(" ")
            if parts[0] in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"}:
                method = parts[0]
                path = parts[1] if len(parts) > 1 else ""
            elif parts[0].startswith("HTTP/"):
                status = parts[1] if len(parts) > 1 else ""
        for line in lines[1:80]:
            if line.lower().startswith("host:"):
                host = line.split(":", 1)[1].strip()
                break
    return payload_hex, payload_ascii, method, host, path, status


def ensure_pcap_index(source_path: str | Path, cache_dir: str | Path, cancel_event: Any = None) -> Path:
    source = Path(source_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"流量包不存在: {source}")
    target = _index_path(source, Path(cache_dir))
    if target.exists():
        with sqlite3.connect(target) as connection:
            complete = connection.execute("SELECT value FROM metadata WHERE key='complete'").fetchone()
            if complete and complete[0] == "1":
                return target

    from scapy.all import DNS, DNSQR, DNSRR, ICMP, IP, IPv6, Raw, TCP, UDP, PcapReader

    temporary = target.with_suffix(".building")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE packets (
              packet_no INTEGER PRIMARY KEY, timestamp TEXT, src_ip TEXT, dst_ip TEXT, protocol TEXT,
              src_port INTEGER, dst_port INTEGER, length INTEGER, session_id TEXT, direction TEXT,
              tcp_seq INTEGER, payload_len INTEGER, payload_hex TEXT, payload_ascii TEXT,
              http_method TEXT, http_host TEXT, http_path TEXT, http_status TEXT,
              dns_query TEXT, dns_answer TEXT, icmp_type INTEGER, icmp_code INTEGER
            );
            CREATE TABLE sessions (
              session_id TEXT PRIMARY KEY, protocol TEXT, endpoint_a TEXT, endpoint_b TEXT,
              packet_count INTEGER, byte_count INTEGER, first_time TEXT, last_time TEXT
            );
            """
        )
        insert_sql = f"INSERT INTO packets ({','.join(SQL_COLUMNS)}) VALUES ({','.join('?' for _ in SQL_COLUMNS)})"
        batch: list[tuple[Any, ...]] = []
        sessions: dict[str, list[Any]] = {}
        with PcapReader(str(source)) as packets:
            for packet_no, packet in enumerate(packets, 1):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("预览加载已停止")
                ip = packet.getlayer(IP) or packet.getlayer(IPv6)
                tcp, udp, icmp = packet.getlayer(TCP), packet.getlayer(UDP), packet.getlayer(ICMP)
                protocol = "TCP" if tcp else "UDP" if udp else "ICMP" if icmp else getattr(packet, "name", "OTHER")
                src_ip, dst_ip = _text(getattr(ip, "src", "")), _text(getattr(ip, "dst", ""))
                transport = tcp or udp
                src_port, dst_port = getattr(transport, "sport", None), getattr(transport, "dport", None)
                endpoint_a, endpoint_b = sorted((f"{src_ip}:{src_port or 0}", f"{dst_ip}:{dst_port or 0}"))
                session_id = f"{protocol}:{endpoint_a}<>{endpoint_b}"
                direction = "A→B" if f"{src_ip}:{src_port or 0}" == endpoint_a else "B→A"
                raw = packet.getlayer(Raw)
                payload = bytes(raw.load) if raw and getattr(raw, "load", None) is not None else b""
                payload_hex, payload_ascii, http_method, http_host, http_path, http_status = _payload_details(payload)
                dns_query = dns_answer = ""
                dns = packet.getlayer(DNS)
                if dns:
                    query = packet.getlayer(DNSQR)
                    dns_query = _text(getattr(query, "qname", "")) if query else ""
                    answers = []
                    for answer_index in range(int(getattr(dns, "ancount", 0) or 0)):
                        answer = dns.an[answer_index] if isinstance(dns.an, (list, tuple)) else dns.an
                        if isinstance(answer, DNSRR):
                            answers.append(_text(getattr(answer, "rdata", "")))
                    dns_answer = ",".join(answers)
                timestamp = str(getattr(packet, "time", ""))
                row = (
                    packet_no, timestamp, src_ip, dst_ip, protocol, src_port, dst_port, len(packet),
                    session_id, direction, getattr(tcp, "seq", None), len(payload), payload_hex, payload_ascii,
                    http_method, http_host, http_path, http_status, dns_query, dns_answer,
                    getattr(icmp, "type", None), getattr(icmp, "code", None),
                )
                batch.append(row)
                session = sessions.setdefault(session_id, [protocol, endpoint_a, endpoint_b, 0, 0, timestamp, timestamp])
                session[3] += 1
                session[4] += len(packet)
                session[6] = timestamp
                if len(batch) >= 1000:
                    connection.executemany(insert_sql, batch)
                    connection.commit()
                    batch.clear()
        if batch:
            connection.executemany(insert_sql, batch)
        connection.executemany(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            [(session_id, *values) for session_id, values in sessions.items()],
        )
        connection.executescript(
            """
            CREATE INDEX idx_packets_session ON packets(session_id, packet_no);
            CREATE INDEX idx_packets_protocol ON packets(protocol);
            CREATE INDEX idx_packets_ips ON packets(src_ip, dst_ip);
            """
        )
        packet_count = connection.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        connection.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("source", str(source)), ("packet_count", str(packet_count)), ("session_count", str(len(sessions))), ("complete", "1"),
        ])
        connection.commit()
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
    finally:
        connection.close()
    if cancel_event is not None and cancel_event.is_set():
        if temporary.exists():
            temporary.unlink()
        raise RuntimeError("预览加载已停止")
    os.replace(temporary, target)
    return target


def _rows_to_frame(rows: list[tuple[Any, ...]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame({column: [] for column in PACKET_COLUMNS})
    return pl.DataFrame(rows, schema=PACKET_COLUMNS, orient="row")


def pcap_page(index_path: str | Path, page: int = 1, page_size: int = 100, protocol: str = "") -> dict[str, Any]:
    page, page_size = max(1, int(page)), min(max(1, int(page_size)), 1000)
    where, params = "", []
    if protocol:
        where, params = " WHERE protocol = ?", [protocol.upper()]
    with sqlite3.connect(index_path) as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM packets{where}", params).fetchone()[0]
        rows = connection.execute(
            f"SELECT {','.join(SQL_COLUMNS)} FROM packets{where} ORDER BY packet_no LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return {"frame": _rows_to_frame(rows), "total": total, "page": page, "pageSize": page_size}


def pcap_sessions(index_path: str | Path, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    page, page_size = max(1, int(page)), min(max(1, int(page_size)), 1000)
    columns = ["会话ID", "协议", "端点A", "端点B", "包数", "字节数", "开始时间", "结束时间"]
    with sqlite3.connect(index_path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        rows = connection.execute(
            "SELECT session_id,protocol,endpoint_a,endpoint_b,packet_count,byte_count,first_time,last_time FROM sessions ORDER BY byte_count DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size),
        ).fetchall()
    frame = pl.DataFrame(rows, schema=columns, orient="row") if rows else pl.DataFrame({column: [] for column in columns})
    return {"frame": frame, "total": total, "page": page, "pageSize": page_size}


def load_all_packets(index_path: str | Path, protocol: str = "") -> pl.DataFrame:
    protocol = protocol.strip().upper()
    where = " WHERE protocol = ?" if protocol else ""
    params = (protocol,) if protocol else ()
    with sqlite3.connect(index_path) as connection:
        rows = connection.execute(f"SELECT {','.join(SQL_COLUMNS)} FROM packets{where} ORDER BY packet_no", params).fetchall()
    return _rows_to_frame(rows)


def export_pcap_index(index_path: str | Path, output_path: str | Path, delimiter: str = ",") -> int:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    count = 0
    with sqlite3.connect(index_path) as connection, temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=(delimiter or ",")[:1])
        writer.writerow(PACKET_COLUMNS)
        cursor = connection.execute(f"SELECT {','.join(SQL_COLUMNS)} FROM packets ORDER BY packet_no")
        while True:
            rows = cursor.fetchmany(5000)
            if not rows:
                break
            writer.writerows(rows)
            count += len(rows)
    os.replace(temporary, output)
    return count
