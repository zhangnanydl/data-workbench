import csv

import polars as pl
from scapy.all import DNS, DNSQR, Ether, ICMP, IP, Raw, TCP, UDP, wrpcap

from dataworkbench.models import ExecutionContext
from dataworkbench.pcap_index import ensure_pcap_index, export_pcap_index, load_all_packets, pcap_page, pcap_sessions
from dataworkbench.plugins.builtin.ctf import (
    CaesarPlugin,
    FlagScanPlugin,
    HexCodecPlugin,
    HttpExtractPlugin,
    IcmpExtractPlugin,
    MultiBaseCodecPlugin,
    SessionGroupPlugin,
    TcpReassemblePlugin,
    XorPlugin,
)


def make_pcap(path):
    packets = [
        Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / TCP(sport=45000, dport=80, seq=100) / Raw(b"GET /flag.txt HTTP/1.1\r\nHost: ctf.local\r\n\r\n"),
        Ether() / IP(src="10.0.0.1", dst="8.8.8.8") / UDP(sport=53000, dport=53) / DNS(rd=1, qd=DNSQR(qname="flag.ctf.local")),
        Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / ICMP(type=8, code=0) / Raw(b"flag{icmp_hidden}"),
        Ether() / IP(src="10.0.0.1", dst="10.0.0.2") / TCP(sport=45000, dport=80, seq=148) / Raw(b"flag{tcp_stream}"),
    ]
    wrpcap(str(path), packets)


def test_pcap_disk_index_paging_sessions_and_full_export(tmp_path):
    source = tmp_path / "challenge.pcap"
    make_pcap(source)
    index = ensure_pcap_index(source, tmp_path / "cache")

    first_page = pcap_page(index, page=1, page_size=2)
    assert first_page["total"] == 4
    assert first_page["frame"].height == 2
    assert first_page["frame"]["HTTP主机"][0] == "ctf.local"
    assert pcap_page(index, page=2, page_size=2)["frame"]["协议"].to_list() == ["ICMP", "TCP"]
    assert pcap_sessions(index)["total"] == 3

    output = tmp_path / "all_packets.csv"
    assert export_pcap_index(index, output) == 4
    with output.open(encoding="utf-8-sig", newline="") as stream:
        assert len(list(csv.reader(stream))) == 5


def test_protocol_extract_session_group_and_tcp_reassembly(tmp_path):
    source = tmp_path / "challenge.pcap"
    make_pcap(source)
    frame = load_all_packets(ensure_pcap_index(source, tmp_path / "cache"))
    context = ExecutionContext()

    assert HttpExtractPlugin().execute([frame], {}, context).height == 1
    icmp = IcmpExtractPlugin().execute([frame], {}, context)
    assert icmp.height == 1 and "flag{icmp_hidden}" in icmp["PayloadASCII"][0]
    grouped = SessionGroupPlugin().execute([frame], {}, context)
    assert grouped["包数"].max() == 2
    streams = TcpReassemblePlugin().execute([frame], {"max_bytes": 10000}, context)
    assert streams.height == 1
    assert "GET /flag.txt" in streams["PayloadASCII"][0]
    assert "flag{tcp_stream}" in streams["PayloadASCII"][0]


def test_ctf_codecs_bruteforce_and_flag_scan():
    context = ExecutionContext()
    plain = pl.DataFrame({"内容": ["flag{codec_ok}"]})
    hexed = HexCodecPlugin().execute([plain], {"fields": ["内容"], "operation": "encode"}, context)
    assert HexCodecPlugin().execute([hexed], {"fields": ["内容"], "operation": "decode"}, context)["内容"][0] == "flag{codec_ok}"

    for base_name in ("base16", "base32", "base58", "base64", "base85"):
        encoded = MultiBaseCodecPlugin().execute([plain], {"fields": ["内容"], "base": base_name, "operation": "encode"}, context)
        decoded = MultiBaseCodecPlugin().execute([encoded], {"fields": ["内容"], "base": base_name, "operation": "decode"}, context)
        assert decoded["内容"][0] == "flag{codec_ok}"

    cipher = bytes(value ^ 0x2A for value in b"flag{xor_ok}").hex()
    xor = XorPlugin().execute([pl.DataFrame({"密文": [cipher]})], {"fields": ["密文"], "mode": "bruteforce", "input_format": "hex", "top": 5}, context)
    assert "flag{xor_ok}" in xor["密文_XOR结果"][0]
    caesar = CaesarPlugin().execute([pl.DataFrame({"密文": ["iodj{fdhvdu}"]})], {"fields": ["密文"]}, context)
    assert "flag{caesar}" in caesar["密文_凯撒候选"][0]

    scan_frame = pl.DataFrame({"文本": ["nothing", "answer flag{direct}"], "PayloadHex": ["", b"ctf{from_hex}".hex()]})
    result = FlagScanPlugin().execute([scan_frame], {"fields": ["文本", "PayloadHex"], "only_matches": True}, context)
    assert result.height == 1
    assert "flag{direct}" in result["Flag命中"][0]
    assert "ctf{from_hex}" in result["Flag命中"][0]
