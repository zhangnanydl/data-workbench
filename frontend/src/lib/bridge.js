import { demoRows } from "../data/defaultPipeline.js";
import { valueMapToObject } from "./valueMap.js";

const mysqlAdvancedFields = [
  { key: "advanced", label: "高级连接参数", field_type: "boolean", default: false },
  { key: "charset", label: "字符集", field_type: "select", default: "utf8mb4", options: [{ label: "utf8mb4（推荐）", value: "utf8mb4" }, { label: "utf8", value: "utf8" }, { label: "GBK", value: "gbk" }, { label: "latin1", value: "latin1" }] },
  { key: "timezone", label: "连接时区", default: "+08:00", placeholder: "例如：+08:00 或 Asia/Shanghai" },
  { key: "ssl_mode", label: "SSL 模式", field_type: "select", default: "disabled", options: [{ label: "禁用 SSL（本地推荐）", value: "disabled" }, { label: "优先使用 SSL", value: "preferred" }, { label: "必须使用 SSL", value: "required" }] },
  { key: "connect_timeout", label: "连接超时（秒）", field_type: "number", default: 5 },
  { key: "read_timeout", label: "读取超时（秒）", field_type: "number", default: 30 },
  { key: "write_timeout", label: "写入超时（秒）", field_type: "number", default: 30 },
];

const evtxEventOptions = [
  ["4624", "4624 登录成功", "登录"], ["4625", "4625 登录失败", "登录"], ["4634", "4634 用户注销", "登录"],
  ["4648", "4648 显式凭据登录", "登录"], ["4672", "4672 特权登录", "登录"], ["4688", "4688 创建进程", "进程"],
  ["4689", "4689 进程退出", "进程"], ["4720", "4720 创建用户", "账号"], ["4726", "4726 删除用户", "账号"],
  ["4732", "4732 添加本地组成员", "账号"], ["4740", "4740 账户被锁定", "账号"], ["4768", "4768 Kerberos TGT", "认证"],
  ["4769", "4769 Kerberos服务票据", "认证"], ["4776", "4776 NTLM身份验证", "认证"], ["1102", "1102 清除审计日志", "高危"],
  ["7045", "7045 安装系统服务", "高危"], ["4104", "4104 PowerShell脚本块", "高危"],
].map(([value, label, category]) => ({ value, label, category }));

export const fallbackPlugins = [
  ["input.demo", "示例数据", "input", "数据输入", "内置访问日志样本", "database", "#3b82f6", []],
  ["input.csv", "Excel / CSV", "input", "数据输入", "读取表格文件", "file-csv", "#10b981", [{ key: "path", label: "文件路径", field_type: "file", required: true, default: "" }, { key: "delimiter", label: "CSV 分隔符", default: "," }]],
  ["input.text", "TXT", "input", "数据输入", "读取文本文件", "file-text", "#14b8a6", [{ key: "path", label: "文件路径", field_type: "file", required: true, default: "" }, { key: "delimiter", label: "分隔符", default: "" }]],
  ["input.log", "安全日志 LOG", "input", "数据输入", "自动、键值对、JSONL、分隔符和正则解析日志", "file-text", "#ef4444", [{ key: "path", label: "日志文件", field_type: "file", required: true, default: "" }, { key: "parse_mode", label: "解析方式", field_type: "select", default: "auto", options: [{ label: "自动识别（推荐）", value: "auto" }, { label: "每行一条", value: "line" }, { label: "键值对 key=value", value: "key_value" }, { label: "JSON Lines", value: "jsonl" }, { label: "按分隔符拆列", value: "delimiter" }, { label: "正则表达式提取", value: "regex" }] }, { key: "delimiter", label: "分隔符", default: "," }, { key: "pattern", label: "提取正则", field_type: "textarea", default: "" }, { key: "encoding", label: "字符编码", field_type: "select", default: "utf-8", options: [{ label: "UTF-8", value: "utf-8" }, { label: "GBK", value: "gbk" }, { label: "Latin-1", value: "latin1" }] }, { key: "skip_empty", label: "忽略空行", field_type: "boolean", default: true }]],
  ["input.evtx", "Windows EVTX", "input", "数据输入", "解析Windows事件日志及事件数据", "file-text", "#2563eb", [{ key: "path", label: "EVTX 文件", field_type: "file", required: true, default: "" }, { key: "event_ids", label: "常见安全事件（可选）", field_type: "event_id_selector", default: [], options: evtxEventOptions, help_text: "不勾选时读取全部事件；也可以补充自定义事件ID" }, { key: "providers", label: "提供程序包含（可选）", default: "" }, { key: "include_xml", label: "保留原始 XML", field_type: "boolean", default: false }, { key: "max_records", label: "最多读取记录数", field_type: "number", default: 0 }]],
  ["input.json", "JSON / JSONL", "input", "数据输入", "读取JSON数组、嵌套记录或逐行JSON日志", "file-text", "#f97316", [{ key: "path", label: "JSON 文件", field_type: "file", required: true, default: "" }, { key: "format", label: "文件格式", field_type: "select", default: "auto", options: [{ label: "自动判断", value: "auto" }, { label: "JSON", value: "json" }, { label: "JSON Lines", value: "jsonl" }] }, { key: "record_path", label: "记录路径（可选）", default: "", placeholder: "例如 data.events" }, { key: "encoding", label: "字符编码", field_type: "select", default: "utf-8", options: [{ label: "UTF-8", value: "utf-8" }, { label: "GBK", value: "gbk" }] }]],
  ["input.sqlite", "SQLite 数据库", "input", "数据输入", "读取SQLite或浏览器取证数据库", "database", "#0f766e", [{ key: "path", label: "数据库文件", field_type: "file", required: true, default: "" }, { key: "table", label: "数据表", required: true, default: "" }, { key: "query", label: "自定义查询（可选）", field_type: "textarea", default: "" }]],
  ["input.pcap", "PCAP", "input", "数据输入", "解析网络流量包", "network", "#6366f1", [{ key: "path", label: "流量包路径", field_type: "file", required: true, default: "" }, { key: "display_filter", label: "协议过滤", default: "" }]],
  ["input.mysql", "MySQL", "input", "数据输入", "连接 MySQL 并选择数据库和数据表", "database", "#f59e0b", [{ key: "host", label: "主机", default: "127.0.0.1", required: true }, { key: "port", label: "端口", field_type: "number", default: 3306 }, { key: "username", label: "用户名", default: "root", required: true }, { key: "password", label: "密码", field_type: "password", required: true }, { key: "database", label: "数据库", field_type: "mysql_database", required: true }, { key: "table", label: "数据表", field_type: "mysql_table", required: true }, { key: "query", label: "高级 SQL（可选）", field_type: "textarea", default: "", placeholder: "留空时读取所选数据表" }, ...mysqlAdvancedFields]],
  ["transform.filter", "过滤", "transform", "数据处理", "按条件筛选数据", "funnel", "#14b8a6", [{ key: "field", label: "字段", field_type: "column", required: true }, { key: "operator", label: "运算符", field_type: "select", default: "equals", options: [{ label: "等于", value: "equals" }, { label: "不等于", value: "not_equals" }, { label: "包含", value: "contains" }, { label: "大于", value: "greater" }, { label: "大于等于", value: "greater_equal" }, { label: "小于", value: "less" }, { label: "小于等于", value: "less_equal" }, { label: "为空", value: "is_null" }, { label: "非空", value: "not_null" }] }, { key: "value", label: "比较值", default: "" }]],
  ["transform.select_columns", "选择显示列", "transform", "数据处理", "只保留需要查看或导出的字段", "columns", "#3b82f6", [{ key: "columns", label: "显示哪些列", field_type: "columns", required: true, help_text: "字段会从上游数据自动读取" }, { key: "mode", label: "处理方式", field_type: "select", default: "keep", options: [{ label: "只保留选中的列", value: "keep" }, { label: "隐藏选中的列", value: "drop" }] }]],
  ["transform.mapping", "字段映射", "transform", "数据处理", "重命名或替换字段值", "text-t", "#22c55e", [{ key: "source_field", label: "原字段", field_type: "column", required: true }, { key: "target_field", label: "新字段名", required: true }, { key: "value_map", label: "值替换规则（可选）", field_type: "value_map", default: [], help_text: "直接填写原值和替换后的值；未配置的内容保持不变" }]],
  ["transform.rename_column", "重命名列", "transform", "数据处理", "为一个字段设置新的列名", "text-t", "#16a34a", [{ key: "source_field", label: "原列名", field_type: "column", required: true }, { key: "target_field", label: "新列名", required: true, placeholder: "例如：用户手机号" }]],
  ["transform.split_column", "分列", "transform", "数据处理", "根据分隔符把一个字段拆成两列或多列", "columns", "#0d9488", [{ key: "source_field", label: "需要分列的字段", field_type: "column", required: true }, { key: "delimiter", label: "分隔符", required: true, placeholder: "例如：, 或 -" }, { key: "output_fields", label: "拆分后的列名", field_type: "column_names", default: ["第1列", "第2列"], required: true, help_text: "至少设置两列；可继续添加并逐列重命名" }, { key: "keep_source", label: "保留原列", field_type: "boolean", default: true }]],
  ["transform.convert", "类型转换", "transform", "数据处理", "转换字段数据类型", "arrows-left-right", "#64748b", [{ key: "field", label: "字段", field_type: "column", required: true }, { key: "target_type", label: "目标类型", field_type: "select", default: "string", options: [{ label: "文本", value: "string" }, { label: "整数", value: "integer" }, { label: "小数", value: "float" }] }]],
  ["transform.mask", "数据脱敏", "transform", "数据处理", "遮盖敏感字段", "lock", "#6d5dfc", [{ key: "fields", label: "选择字段", field_type: "columns", default: "手机号" }, { key: "keep_start", label: "保留前几位", field_type: "number", default: 3 }, { key: "keep_end", label: "保留后几位", field_type: "number", default: 4 }, { key: "mask_char", label: "遮盖字符", default: "*" }]],
  ["transform.group", "分组聚合", "transform", "数据处理", "按字段分组，并一次完成多项计数、求和、平均等统计", "users-three", "#f59e0b", [{ key: "group_by", label: "分组字段", field_type: "columns", required: true }, { key: "aggregate_rules", label: "统计规则", field_type: "aggregate_rules", default: [{ operation: "count", field: "", output_name: "人数" }], required: true, help_text: "可同时添加人数、平均分、总分、最大值等多项指标" }]],
  ["transform.merge_inputs", "多路数据合并", "transform", "数据处理", "把两个或更多上游节点的数据进行合并", "rows", "#2563eb", [{ key: "mode", label: "合并方式", field_type: "select", default: "union", options: [{ label: "按列名纵向追加（推荐）", value: "union" }, { label: "只保留共同字段后追加", value: "intersection" }, { label: "按行号横向拼接", value: "horizontal" }] }, { key: "add_source", label: "增加来源列", field_type: "boolean", default: false }, { key: "source_field", label: "来源列名称", default: "数据来源" }]],
  ["transform.deduplicate", "数据去重", "transform", "数据处理", "按一个或多个字段删除重复数据", "squares-four", "#0d9488", [{ key: "fields", label: "去重依据字段", field_type: "columns", default: [], help_text: "不选择字段时比较整行内容" }, { key: "keep", label: "重复时保留", field_type: "select", default: "first", options: [{ label: "保留第一条", value: "first" }, { label: "保留最后一条", value: "last" }, { label: "重复项全部删除", value: "none" }] }]],
  ["transform.merge_rows", "合并为一行", "transform", "数据处理", "只保留选中列并把每列全部内容合并成一行", "rows", "#8b5cf6", [{ key: "fields", label: "需要合并的列", field_type: "columns", required: true, help_text: "其他列会被删除，最终结果严格只保留一行" }, { key: "separator", label: "行内容分隔符", default: ",", placeholder: "例如：, 或换行符" }]],
  ["transform.replace", "文本检索替换", "transform", "数据处理", "替换一个或多个字段中的文字", "arrows-left-right", "#0ea5e9", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "search", label: "查找内容", required: true }, { key: "replacement", label: "替换为", default: "" }, { key: "regex", label: "使用正则表达式", field_type: "boolean", default: false }]],
  ["transform.trim", "去除空格", "transform", "数据处理", "去除文本开头、结尾或两端的空白字符", "text-aa", "#0891b2", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "mode", label: "处理位置", field_type: "select", default: "both", options: [{ label: "两端", value: "both" }, { label: "仅开头", value: "start" }, { label: "仅结尾", value: "end" }] }]],
  ["transform.concat_columns", "合并列", "transform", "数据处理", "把多个字段拼接成一个新字段", "rows", "#0f766e", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "separator", label: "连接符", default: "" }, { key: "output_name", label: "新列名", default: "合并结果", required: true }]],
  ["transform.uppercase", "转大写", "transform", "数据处理", "将选中字段的英文字母转为大写", "text-aa", "#0284c7", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }]],
  ["transform.lowercase", "转小写", "transform", "数据处理", "将选中字段的英文字母转为小写", "text-aa", "#0369a1", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }]],
  ["transform.base64", "Base64 编解码", "transform", "数据处理", "对文本字段进行 Base64 编码或解码", "text-t", "#8b5cf6", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "operation", label: "操作", field_type: "select", default: "encode", options: [{ label: "编码", value: "encode" }, { label: "解码", value: "decode" }] }, { key: "encoding", label: "字符编码", default: "utf-8" }]],
  ["transform.url_codec", "URL 编解码", "transform", "数据处理", "对网址和查询参数进行 URL 编码或解码", "network", "#9333ea", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "operation", label: "操作", field_type: "select", default: "encode", options: [{ label: "编码", value: "encode" }, { label: "解码", value: "decode" }] }]],
  ["transform.md5", "MD5 摘要", "transform", "数据处理", "生成不可逆的 MD5 摘要", "lock", "#a855f7", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "salt", label: "盐值（可选）", default: "" }]],
  ["transform.aes", "AES 对称加密", "transform", "数据处理", "使用同一密钥进行 AES-256-GCM 加密或解密", "lock", "#7c3aed", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "operation", label: "操作", field_type: "select", default: "encrypt", options: [{ label: "加密", value: "encrypt" }, { label: "解密", value: "decrypt" }] }, { key: "key", label: "密钥", field_type: "password", required: true }]],
  ["ctf.session_group", "PCAP 会话分组", "transform", "数据处理", "按五元组汇总流量会话", "network", "#2563eb", []],
  ["ctf.tcp_reassemble", "TCP 流重组", "transform", "数据处理", "按会话和TCP序号重组Payload", "flow", "#1d4ed8", [{ key: "max_bytes", label: "每条流最大字节数", field_type: "number", default: 5000000 }]],
  ["ctf.http_extract", "HTTP 数据提取", "transform", "数据处理", "提取HTTP方法、Host、路径和Payload", "network", "#0ea5e9", []],
  ["ctf.dns_extract", "DNS 数据提取", "transform", "数据处理", "提取DNS查询和响应", "network", "#06b6d4", []],
  ["ctf.icmp_extract", "ICMP 数据提取", "transform", "数据处理", "提取ICMP类型和隐藏载荷", "network", "#0891b2", []],
  ["ctf.hex_codec", "Hex 编解码", "transform", "数据处理", "文本与十六进制互相转换", "text-t", "#7c3aed", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "operation", label: "操作", field_type: "select", default: "decode", options: [{ label: "Hex解码", value: "decode" }, { label: "Hex编码", value: "encode" }] }, { key: "encoding", label: "文本编码", default: "utf-8" }]],
  ["ctf.base_codec", "多种 Base 编解码", "transform", "数据处理", "支持Base16、32、58、64、85", "text-t", "#8b5cf6", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "base", label: "编码类型", field_type: "select", default: "base64", options: ["base16", "base32", "base58", "base64", "base85"].map(value => ({ label: value.toUpperCase(), value })) }, { key: "operation", label: "操作", field_type: "select", default: "decode", options: [{ label: "解码", value: "decode" }, { label: "编码", value: "encode" }] }]],
  ["ctf.xor", "XOR 解密与爆破", "transform", "数据处理", "指定密钥XOR或爆破单字节密钥", "lock", "#dc2626", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "mode", label: "模式", field_type: "select", default: "bruteforce", options: [{ label: "单字节爆破", value: "bruteforce" }, { label: "指定密钥", value: "apply" }] }, { key: "key", label: "密钥", default: "" }, { key: "input_format", label: "输入格式", field_type: "select", default: "text", options: [{ label: "文本", value: "text" }, { label: "Hex", value: "hex" }, { label: "Base64", value: "base64" }] }, { key: "top", label: "保留候选数", field_type: "number", default: 5 }]],
  ["ctf.caesar", "凯撒密码爆破", "transform", "数据处理", "尝试全部26种字母位移", "text-aa", "#ea580c", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }]],
  ["ctf.flag_scan", "Flag 自动扫描", "transform", "数据处理", "扫描文本和Hex中的疑似Flag", "funnel", "#16a34a", [{ key: "fields", label: "扫描字段", field_type: "columns", required: true }, { key: "pattern", label: "Flag 正则", default: "[A-Za-z0-9_]{0,24}\\{[^{}\\r\\n]{1,200}\\}" }, { key: "only_matches", label: "只保留命中行", field_type: "boolean", default: true }]],
  ["output.file", "Excel / CSV / TXT", "output", "数据输出", "导出到本地文件", "file-arrow-down", "#10b981", [{ key: "path", label: "输出路径", field_type: "save_file", required: true }, { key: "format", label: "输出格式", field_type: "select", default: "csv", options: [{ label: "CSV", value: "csv" }, { label: "Excel", value: "xlsx" }, { label: "TXT", value: "txt" }] }]],
  ["output.json", "JSON / JSONL 导出", "output", "数据输出", "完整导出JSON数组或逐行JSON", "file-arrow-down", "#f97316", [{ key: "path", label: "输出路径", field_type: "save_file", required: true }, { key: "format", label: "输出格式", field_type: "select", default: "jsonl", options: [{ label: "JSON Lines（大数据推荐）", value: "jsonl" }, { label: "JSON 数组", value: "json" }] }, { key: "pretty", label: "JSON美化缩进", field_type: "boolean", default: false }, { key: "encoding", label: "字符编码", default: "utf-8" }]],
  ["output.sqlite", "SQLite 写入", "output", "数据输出", "写入本地SQLite数据库并自动创建表", "database", "#0f766e", [{ key: "path", label: "数据库文件", field_type: "save_file", required: true }, { key: "table", label: "数据表名称", default: "result", required: true }, { key: "mode", label: "表已存在时", field_type: "select", default: "replace", options: [{ label: "覆盖表", value: "replace" }, { label: "追加数据", value: "append" }, { label: "报错并停止", value: "fail" }] }, { key: "batch_size", label: "每批写入行数", field_type: "number", default: 1000 }]],
  ["output.mysql", "MySQL 写入", "output", "数据输出", "选择已有库表或手写名称自动创建", "database", "#f97316", [{ key: "host", label: "主机", default: "127.0.0.1", required: true }, { key: "port", label: "端口", field_type: "number", default: 3306 }, { key: "username", label: "用户名", default: "root", required: true }, { key: "password", label: "密码", field_type: "password", required: true }, { key: "target_mode", label: "目标配置方式", field_type: "select", default: "existing", options: [{ label: "选择已有数据库和表", value: "existing" }, { label: "手写名称并自动创建", value: "manual" }] }, { key: "database", label: "已有数据库", field_type: "mysql_database" }, { key: "table", label: "已有数据表", field_type: "mysql_table" }, { key: "database_manual", label: "新数据库名称", default: "ctf_data", placeholder: "不存在时自动创建" }, { key: "table_manual", label: "新数据表名称", default: "result", placeholder: "不存在时根据字段自动创建" }, { key: "mode", label: "表已存在时", field_type: "select", default: "append", options: [{ label: "追加数据", value: "append" }, { label: "覆盖表", value: "replace" }, { label: "报错并停止", value: "fail" }] }, { key: "batch_size", label: "每批写入行数", field_type: "number", default: 1000 }, ...mysqlAdvancedFields]],
  ["output.pcap_index", "PCAP 索引完整导出", "output", "数据输出", "从磁盘索引分批导出全部数据包", "file-arrow-down", "#4f46e5", [{ key: "path", label: "输出路径", field_type: "save_file", required: true }, { key: "delimiter", label: "分隔符", default: "," }]],
].map(([id, name, kind, group, description, icon, color, config_fields]) => ({
  id, name, kind, group, description, icon, color, config_fields,
  category: {
    "transform.filter": "筛选与字段", "transform.select_columns": "筛选与字段",
    "transform.mapping": "字段转换", "transform.rename_column": "字段转换", "transform.split_column": "字段转换", "transform.convert": "字段转换",
    "transform.mask": "安全与隐私", "transform.group": "聚合与结构", "transform.merge_inputs": "聚合与结构", "transform.deduplicate": "筛选与字段", "transform.merge_rows": "聚合与结构",
    "transform.replace": "文本处理", "transform.trim": "文本处理", "transform.concat_columns": "文本处理", "transform.uppercase": "文本处理", "transform.lowercase": "文本处理",
    "transform.base64": "加密与编码", "transform.url_codec": "加密与编码", "transform.md5": "加密与编码", "transform.aes": "加密与编码",
    "ctf.session_group": "CTF 流量分析", "ctf.tcp_reassemble": "CTF 流量分析",
    "ctf.http_extract": "CTF 协议提取", "ctf.dns_extract": "CTF 协议提取", "ctf.icmp_extract": "CTF 协议提取",
    "ctf.hex_codec": "CTF 编码解码", "ctf.base_codec": "CTF 编码解码",
    "ctf.xor": "CTF 密码爆破", "ctf.caesar": "CTF 密码爆破", "ctf.flag_scan": "CTF 检测",
  }[id] || "",
}));

const desktopApi = () => window.pywebview?.api;
const browserStorageConfig = () => JSON.parse(localStorage.getItem("data-workbench-settings:storage") || '{"mode":"local","mysql":{}}');
const mockRunJobs = new Map();

function mockPreview(pipeline, targetNodeId, limit = 100, page = 1) {
  const node = pipeline.nodes.find((item) => item.id === targetNodeId);
  let rows = demoRows.map((row) => ({ ...row }));
  if (node?.pluginId === "input.pcap") {
    rows = [
      { 序号: 1, 时间: "2026-08-19 10:21:04.120", 源IP: "10.10.1.15", 目标IP: "10.10.1.80", 协议: "TCP", 源端口: 51422, 目标端口: 80, 长度: 104, 会话ID: "tcp:10.10.1.15:51422-10.10.1.80:80", Payload长度: 48, PayloadHex: "474554202f666c61672e74787420485454502f312e310d0a486f73743a206374662e6c6f63616c0d0a0d0a", PayloadASCII: "GET /flag.txt HTTP/1.1\r\nHost: ctf.local\r\n\r\n", HTTP方法: "GET", HTTP主机: "ctf.local", HTTP路径: "/flag.txt" },
      { 序号: 2, 时间: "2026-08-19 10:21:04.131", 源IP: "10.10.1.80", 目标IP: "10.10.1.15", 协议: "TCP", 源端口: 80, 目标端口: 51422, 长度: 91, 会话ID: "tcp:10.10.1.15:51422-10.10.1.80:80", Payload长度: 35, PayloadHex: "485454502f312e3120323030204f4b0d0a0d0a666c61677b706361705f64656d6f7d", PayloadASCII: "HTTP/1.1 200 OK\r\n\r\nflag{pcap_demo}", HTTP状态: "200" },
    ];
  }
  if (node?.pluginId !== "input.pcap") {
    for (const current of pipeline.nodes) {
      const config = current.config || {};
      if (current.pluginId === "transform.filter" && config.field) {
        rows = rows.filter((row) => config.operator !== "equals" || String(row[config.field]) === String(config.value));
      } else if (current.pluginId === "transform.mapping" && config.source_field && config.target_field) {
        const valueMap = valueMapToObject(config.value_map);
        rows = rows.map((row) => { const original = row[config.source_field]; const mapped = Object.hasOwn(valueMap, String(original)) ? valueMap[String(original)] : original; const next = { ...row, [config.target_field]: mapped }; if (config.target_field !== config.source_field) delete next[config.source_field]; return next; });
      } else if (current.pluginId === "transform.mask") {
        const fields = Array.isArray(config.fields) ? config.fields : String(config.fields || "").split(",").filter(Boolean);
        const start = Math.max(0, Number(config.keep_start) || 0), end = Math.max(0, Number(config.keep_end) || 0), character = String(config.mask_char || "*")[0];
        rows = rows.map((row) => ({ ...row, ...Object.fromEntries(fields.map((field) => { const text = String(row[field] ?? ""); return [field, text.slice(0, start) + character.repeat(Math.max(0, text.length - start - end)) + (end ? text.slice(-end) : "")]; })) }));
      } else if (current.pluginId === "transform.deduplicate") {
        const fields = Array.isArray(config.fields) && config.fields.length ? config.fields : Object.keys(rows[0] || {});
        const seen = new Set(); rows = rows.filter((row) => { const key = JSON.stringify(fields.map((field) => row[field])); if (seen.has(key)) return false; seen.add(key); return true; });
      } else if (current.pluginId === "transform.group") {
        const groups = Array.isArray(config.group_by) ? config.group_by : String(config.group_by || "").split(",").filter(Boolean);
        const rules = Array.isArray(config.aggregate_rules) ? config.aggregate_rules : [{ operation: config.operation || "count", field: config.aggregate_field || "", output_name: config.output_name || "数量" }];
        const grouped = new Map();
        for (const row of rows) { const key = JSON.stringify(groups.map((field) => row[field])); if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(row); }
        rows = [...grouped.entries()].map(([key, items]) => ({ ...Object.fromEntries(groups.map((field, index) => [field, JSON.parse(key)[index]])), ...Object.fromEntries(rules.map((rule, index) => { const values = items.map((item) => Number(item[rule.field])).filter(Number.isFinite); const result = rule.operation === "mean" ? values.reduce((sum, value) => sum + value, 0) / (values.length || 1) : rule.operation === "sum" ? values.reduce((sum, value) => sum + value, 0) : items.length; return [rule.output_name || `统计${index + 1}`, result]; })) }));
      }
      if (current.id === targetNodeId) break;
    }
  }
  const rowCount = rows.length;
  rows = rows.slice((Math.max(page, 1) - 1) * limit, Math.max(page, 1) * limit);
  const columns = Object.keys(rows[0] || {}).map((key) => ({ key, label: key, type: typeof rows[0]?.[key] === "number" ? "Int64" : "String" }));
  return { ok: true, data: { columns, rows, stats: { rowCount, previewCount: rows.length, columnCount: columns.length, nodeId: targetNodeId, pluginId: node?.pluginId, preview: true, paged: true, page, pageSize: limit } } };
}

export const bridge = {
  async listPlugins() {
    return desktopApi() ? desktopApi().list_plugins() : fallbackPlugins;
  },
  async previewPipeline(pipeline, targetNodeId, limit = 100, page = 1) {
    return desktopApi() ? desktopApi().preview_pipeline(pipeline, targetNodeId, limit, page) : mockPreview(pipeline, targetNodeId, limit, page);
  },
  async previewNodeInput(pipeline, targetNodeId, limit = 100, page = 1) {
    if (desktopApi()) return desktopApi().preview_node_input(pipeline, targetNodeId, limit, page);
    const incoming = pipeline.edges.filter((edge) => edge.target === targetNodeId);
    if (incoming.length > 1) {
      const rows = incoming.flatMap((edge) => {
        const source = pipeline.nodes.find((node) => node.id === edge.source);
        return mockPreview(pipeline, edge.source).data.rows.map((row) => ({ ...row, 数据来源: source?.label || source?.pluginId || edge.source }));
      });
      const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
      return { ok: true, data: { rows, columns: keys.map((key) => ({ key, label: key, type: "String" })), stats: { rowCount: rows.length, previewCount: rows.length, columnCount: keys.length, nodeId: targetNodeId, preview: true } } };
    }
    return mockPreview(pipeline, incoming[0]?.source || targetNodeId, limit, page);
  },
  async pcapPage(path, page = 1, pageSize = 100, protocol = "") {
    if (desktopApi()) return desktopApi().pcap_page(path, page, pageSize, protocol);
    const result = mockPreview({ nodes: [{ id: "pcap", pluginId: "input.pcap" }], edges: [] }, "pcap");
    result.data.stats = { ...result.data.stats, rowCount: 128542, page, pageSize, paged: true, protocol, path };
    return result;
  },
  async pcapSessions(path, page = 1, pageSize = 100) {
    if (desktopApi()) return desktopApi().pcap_sessions(path, page, pageSize);
    const rows = [{ 会话ID: "tcp:10.10.1.15:51422-10.10.1.80:80", 协议: "TCP", 端点A: "10.10.1.15:51422", 端点B: "10.10.1.80:80", 数据包数: 2, 总字节数: 195, Payload字节数: 83 }];
    const columns = Object.keys(rows[0]).map((key) => ({ key, label: key, type: typeof rows[0][key] === "number" ? "Int64" : "String" }));
    return { ok: true, data: { rows, columns, stats: { rowCount: 924, page, pageSize, paged: true, previewCount: rows.length, columnCount: columns.length, path } } };
  },
  async runPipeline(pipeline) {
    if (desktopApi()) return desktopApi().run_pipeline(pipeline);
    await new Promise((resolve) => setTimeout(resolve, 850));
    return { ok: true, data: mockPreview(pipeline, pipeline.nodes.at(-1)?.id).data, message: "流程运行完成" };
  },
  async assessPipeline(pipeline) {
    if (desktopApi()) return desktopApi().assess_pipeline(pipeline);
    const nodeCount = pipeline.nodes.length;
    return { ok: true, data: { estimatedRows: 128542, estimatedBytes: 18_400_000, nodeCount, sourceCount: pipeline.nodes.filter((node) => node.pluginId.startsWith("input.")).length, largeData: false, fastPreview: false, strategy: "完整预览 + 后台全量运行" } };
  },
  async startPipelineRun(pipeline) {
    if (desktopApi()) return desktopApi().start_pipeline_run(pipeline);
    const jobId = `mock-${Date.now()}`;
    mockRunJobs.set(jobId, { jobId, status: "running", phase: "executing", percent: 0, createdAt: new Date().toISOString(), elapsedSeconds: 0, estimatedRows: 128542, estimatedBytes: 18_400_000, nodeCount: pipeline.nodes.length, strategy: "完整预览 + 后台全量运行", largeData: false, complete: false, pipeline });
    return { ok: true, job: mockRunJobs.get(jobId), message: "全量任务已启动" };
  },
  async getPipelineRun(jobId) {
    if (desktopApi()) return desktopApi().get_pipeline_run(jobId);
    const job = mockRunJobs.get(jobId);
    if (!job) return { ok: false, error: "运行任务不存在" };
    const nextPercent = Math.min(100, job.percent + 24);
    const nodeIndex = Math.min(job.nodeCount, Math.max(1, Math.ceil(nextPercent / 100 * Math.max(job.nodeCount, 1))));
    Object.assign(job, { percent: nextPercent, nodeIndex, currentNode: `处理节点 ${nodeIndex}`, sourceRows: 128542, processedRows: Math.round(128542 * nextPercent / 100), outputRows: Math.round(123876 * nextPercent / 100), elapsedSeconds: Number((job.elapsedSeconds + 0.6).toFixed(1)) });
    if (nextPercent === 100) Object.assign(job, { status: "success", phase: "complete", complete: true, finalRows: 123876, message: "全量数据处理和导出完成，结果完整", result: mockPreview(job.pipeline, job.pipeline.nodes.at(-1)?.id).data });
    return { ok: true, job: { ...job, pipeline: undefined } };
  },
  async saveProject(pipeline, name) {
    if (desktopApi()) return desktopApi().save_project(pipeline, name);
    const path = `${browserStorageConfig().mode === "mysql" ? "data-workbench-db" : "data-workbench"}:${name}`;
    localStorage.setItem(path, JSON.stringify(pipeline));
    return { ok: true, path, message: `已保存 ${name}` };
  },
  async listProjects() {
    if (desktopApi()) return desktopApi().list_projects();
    const prefix = browserStorageConfig().mode === "mysql" ? "data-workbench-db:" : "data-workbench:";
    return Object.keys(localStorage).filter((key) => key.startsWith(prefix)).map((key) => ({ name: key.slice(prefix.length), path: key }));
  },
  async loadProject(path) {
    if (desktopApi()) return desktopApi().load_project(path);
    const data = localStorage.getItem(path);
    return data ? { ok: true, data: JSON.parse(data) } : { ok: false, error: "未找到项目" };
  },
  async getStorageConfig() {
    return desktopApi() ? desktopApi().get_storage_config() : browserStorageConfig();
  },
  async testStorageConnection(config) {
    if (desktopApi()) return desktopApi().test_storage_connection(config);
    return { ok: true, message: config.mode === "mysql" ? "开发模式：MySQL 配置格式有效" : "本地项目目录可用" };
  },
  async initializeStorage(config) {
    if (desktopApi()) return desktopApi().initialize_storage(config);
    localStorage.setItem("data-workbench-settings:storage", JSON.stringify(config));
    const database = config.mysql?.database || "dataworkbench";
    const table = config.mysql?.table || "projects";
    return { ok: true, config, details: { database, projectTable: table, metaTable: `${table}_meta`, schemaVersion: 1 }, message: config.mode === "mysql" ? `开发模式：已模拟初始化 ${database}.${table}` : "本地存储初始化完成并已保存配置" };
  },
  async configureStorage(config) {
    if (desktopApi()) return desktopApi().configure_storage(config);
    localStorage.setItem("data-workbench-settings:storage", JSON.stringify(config));
    return { ok: true, config, message: "存储模式已保存" };
  },
  async listMysqlDatabases(config) {
    return desktopApi() ? desktopApi().list_mysql_databases(config) : { ok: true, items: ["information_schema", "safetool", "test"], message: "已读取 3 个数据库" };
  },
  async listMysqlTables(config) {
    const mock = config.database === "safetool" ? ["access_logs", "orders", "users"] : ["sample_data"];
    return desktopApi() ? desktopApi().list_mysql_tables(config) : { ok: true, items: mock, message: `已读取 ${mock.length} 张表` };
  },
  async pickFile() {
    return desktopApi() ? desktopApi().pick_file(["csv", "xlsx", "xls", "txt", "log", "out", "trace", "evtx", "json", "jsonl", "ndjson", "db", "sqlite", "sqlite3", "pcap", "pcapng"]) : { ok: true, path: "D:\\data\\sample.csv" };
  },
  async pickSaveFile(extension = "csv") {
    return desktopApi() ? desktopApi().pick_save_file(extension) : { ok: true, path: `D:\\output\\处理结果.${extension}` };
  },
};
