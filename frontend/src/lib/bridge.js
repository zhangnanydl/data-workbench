import { demoRows } from "../data/defaultPipeline.js";
import { valueMapToObject } from "./valueMap.js";

const mysqlAdvancedFields = [
  { key: "advanced", label: "显示连接选项（SSL、时区等）", field_type: "boolean", default: true, help_text: "默认值适合本机 MySQL；关闭只会收起选项，不会清空配置" },
  { key: "charset", label: "字符集", field_type: "select", default: "utf8mb4", options: [{ label: "utf8mb4（推荐）", value: "utf8mb4" }, { label: "utf8", value: "utf8" }, { label: "GBK", value: "gbk" }, { label: "latin1", value: "latin1" }] },
  { key: "timezone", label: "连接时区", field_type: "select", default: "+08:00", options: [{ label: "+08:00（中国标准时间，默认）", value: "+08:00" }, { label: "+00:00（UTC）", value: "+00:00" }, { label: "SYSTEM（跟随 MySQL 服务器）", value: "SYSTEM" }, { label: "Asia/Shanghai（需服务器时区表）", value: "Asia/Shanghai" }, { label: "不主动设置时区", value: "" }], help_text: "建议使用数字偏移；命名时区要求 MySQL 已加载时区表" },
  { key: "ssl_mode", label: "SSL 模式", field_type: "select", default: "disabled", options: [{ label: "忽略/禁用 SSL（本地默认）", value: "disabled" }, { label: "优先使用 SSL", value: "preferred" }, { label: "必须使用 SSL", value: "required" }], help_text: "远程或生产数据库建议选择必须使用 SSL" },
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
  ["transform.sort_rows", "多字段排序", "transform", "数据处理", "按一个或多个字段对全部数据稳定排序", "arrows-left-right", "#2563eb", [{ key: "fields", label: "排序字段（按选择顺序）", field_type: "columns", required: true }, { key: "direction", label: "排序方向", field_type: "select", default: "ascending", options: [{ label: "升序", value: "ascending" }, { label: "降序", value: "descending" }] }, { key: "nulls_last", label: "空值排在最后", field_type: "boolean", default: true }]],
  ["transform.missing_values", "缺失值处理", "transform", "数据处理", "删除含空值的行，或用固定值、前值、后值填充", "squares-four", "#0f766e", [{ key: "fields", label: "处理字段", field_type: "columns", required: true }, { key: "mode", label: "处理方式", field_type: "select", default: "drop", options: [{ label: "删除含空值的行", value: "drop" }, { label: "填写固定值", value: "fixed" }, { label: "使用上一条有效值", value: "forward" }, { label: "使用下一条有效值", value: "backward" }] }, { key: "value", label: "固定值", default: "" }]],
  ["transform.join_inputs", "按键关联两路数据", "transform", "数据处理", "类似 SQL JOIN，按左右键关联两个上游数据表", "rows", "#4f46e5", [{ key: "left_key", label: "第一路关联字段", field_type: "column", required: true }, { key: "right_key", label: "第二路关联字段", field_type: "column", required: true }, { key: "how", label: "关联方式", field_type: "select", default: "left", options: [{ label: "左关联", value: "left" }, { label: "内关联", value: "inner" }, { label: "全关联", value: "full" }, { label: "半关联", value: "semi" }, { label: "反关联", value: "anti" }] }, { key: "suffix", label: "重名字段后缀", default: "_右表" }]],
  ["transform.regex_extract", "正则提取", "transform", "数据处理", "从日志或文本中按正则表达式提取内容", "text-t", "#0891b2", [{ key: "source_field", label: "来源字段", field_type: "column", required: true }, { key: "pattern", label: "正则表达式", required: true }, { key: "group", label: "捕获组序号", field_type: "number", default: 1 }, { key: "output_name", label: "结果列名", default: "提取结果", required: true }, { key: "all_matches", label: "提取全部完整匹配并展开为多行", field_type: "boolean", default: false }]],
  ["transform.json_flatten", "JSON 展平", "transform", "数据处理", "把字段中的 JSON 对象展开成普通列", "columns", "#d97706", [{ key: "source_field", label: "JSON 字段", field_type: "column", required: true }, { key: "prefix", label: "新列前缀", default: "" }, { key: "max_depth", label: "最大展开层级", field_type: "number", default: 4 }, { key: "keep_source", label: "保留原 JSON 字段", field_type: "boolean", default: true }]],
  ["transform.datetime_features", "时间解析与拆分", "transform", "数据处理", "解析时间并生成年月日、小时、星期和时间戳", "history", "#7c3aed", [{ key: "source_field", label: "时间字段", field_type: "column", required: true }, { key: "format", label: "时间格式（可选）", default: "" }, { key: "output_name", label: "解析后时间列", default: "标准时间", required: true }, { key: "parts", label: "需要生成的时间字段", field_type: "option_selector", default: ["年", "月", "日", "小时", "星期", "Unix时间戳"], options: ["年", "月", "日", "小时", "分钟", "秒", "星期", "Unix时间戳"].map(value => ({ label: value, value })) }]],
  ["transform.ioc_extract", "IOC 指标提取", "transform", "数据处理", "从文本提取 IP、URL、域名、邮箱和哈希", "network", "#dc2626", [{ key: "source_field", label: "文本字段", field_type: "column", required: true }, { key: "types", label: "提取类型", field_type: "option_selector", default: ["IP", "URL", "域名", "邮箱", "哈希"], required: true, options: ["IP", "URL", "域名", "邮箱", "哈希"].map(value => ({ label: value, value })) }, { key: "keep_unmatched", label: "保留未发现指标的原始行", field_type: "boolean", default: false }]],
  ["transform.hash_digest", "SHA 哈希摘要", "transform", "数据处理", "生成 SHA-1、SHA-256 或 SHA-512 摘要", "lock", "#9333ea", [{ key: "fields", label: "选择字段", field_type: "columns", required: true }, { key: "algorithm", label: "算法", field_type: "select", default: "sha256", options: [{ label: "SHA-256（推荐）", value: "sha256" }, { label: "SHA-512", value: "sha512" }, { label: "SHA-1", value: "sha1" }] }, { key: "salt", label: "盐值（可选）", default: "" }, { key: "suffix", label: "结果列后缀", default: "_哈希" }]],
  ["transform.calculated_column", "计算列", "transform", "数据处理", "复制、固定值、拼接或文本长度生成新列", "text-t", "#2563eb", [{ key: "operation", label: "计算方式", field_type: "select", default: "copy", options: [{ label: "复制字段", value: "copy" }, { label: "填写固定值", value: "constant" }, { label: "拼接两个字段", value: "concat" }, { label: "文本长度", value: "length" }] }, { key: "source_field", label: "来源字段", field_type: "column" }, { key: "second_field", label: "第二个字段", field_type: "column" }, { key: "constant", label: "固定值", default: "" }, { key: "separator", label: "拼接分隔符", default: "" }, { key: "output_name", label: "新列名称", default: "计算结果", required: true }]],
  ["transform.numeric_calculation", "数值计算", "transform", "数据处理", "执行加减乘除、取整及常用数学运算", "arrows-left-right", "#0ea5e9", [{ key: "source_field", label: "数值字段", field_type: "column", required: true }, { key: "operation", label: "运算", field_type: "select", default: "add", options: [{ label: "加", value: "add" }, { label: "减", value: "subtract" }, { label: "乘", value: "multiply" }, { label: "除", value: "divide" }, { label: "取余", value: "modulo" }, { label: "次方", value: "power" }, { label: "四舍五入", value: "round" }, { label: "绝对值", value: "abs" }, { label: "平方根", value: "sqrt" }, { label: "自然对数", value: "log" }] }, { key: "operand_mode", label: "第二个数来源", field_type: "select", default: "constant", options: [{ label: "固定数值", value: "constant" }, { label: "另一个字段", value: "field" }] }, { key: "operand", label: "固定数值", field_type: "number", default: 0 }, { key: "operand_field", label: "另一个字段", field_type: "column" }, { key: "output_name", label: "结果列名称", default: "数值结果", required: true }]],
  ["transform.conditional_branch", "条件分支", "transform", "数据处理", "按条件拆成满足和不满足两个数据流，也可添加结果标记", "flow", "#8b5cf6", [{ key: "field", label: "判断字段", field_type: "column", required: true }, { key: "operator", label: "判断条件", field_type: "select", default: "equals", options: [{ label: "等于", value: "equals" }, { label: "不等于", value: "not_equals" }, { label: "包含", value: "contains" }, { label: "不包含", value: "not_contains" }, { label: "大于", value: "greater" }, { label: "大于等于", value: "greater_equal" }, { label: "小于", value: "less" }, { label: "小于等于", value: "less_equal" }, { label: "匹配正则", value: "regex" }, { label: "为空", value: "is_null" }, { label: "非空", value: "not_null" }] }, { key: "value", label: "比较值", default: "" }, { key: "true_label", label: "满足条件标记", default: "是" }, { key: "false_label", label: "不满足条件标记", default: "否" }, { key: "output_name", label: "分支列名称", default: "条件分支", required: true }, { key: "keep", label: "旧项目默认出口", field_type: "select", default: "all", options: [{ label: "保留全部并添加标记", value: "all" }, { label: "只保留满足条件", value: "matched" }, { label: "只保留不满足条件", value: "unmatched" }], help_text: "仅用于没有分支标记的旧连线；新流程请使用节点右侧的满足/不满足出口" }]],
  ["transform.pivot", "透视表", "transform", "数据处理", "把字段取值展开成多列并汇总", "columns", "#d97706", [{ key: "index", label: "保留为行的字段", field_type: "columns", required: true }, { key: "on", label: "展开为列的字段", field_type: "column", required: true }, { key: "values", label: "统计值字段", field_type: "column", required: true }, { key: "aggregate", label: "汇总方式", field_type: "select", default: "sum", options: [{ label: "求和", value: "sum" }, { label: "计数", value: "len" }, { label: "平均值", value: "mean" }, { label: "最小值", value: "min" }, { label: "最大值", value: "max" }, { label: "第一条", value: "first" }] }, { key: "fill_value", label: "空结果填充值", default: "" }]],
  ["transform.unpivot", "逆透视", "transform", "数据处理", "把多个字段收拢为字段名和值两列", "rows", "#ea580c", [{ key: "index", label: "保持不变的字段", field_type: "columns", default: [] }, { key: "values", label: "需要收拢的字段", field_type: "columns", required: true }, { key: "variable_name", label: "原字段名列", default: "字段" }, { key: "value_name", label: "原字段值列", default: "值" }]],
  ["transform.transpose", "行列转换", "transform", "数据处理", "交换数据的行和列", "arrows-left-right", "#0d9488", [{ key: "header_field", label: "作为新列名的字段（可选）", field_type: "column" }, { key: "header_name", label: "原字段名列名称", default: "原字段" }]],
  ["transform.set_operations", "集合运算", "transform", "数据处理", "对两个上游执行并集、交集或差集", "squares-four", "#4f46e5", [{ key: "operation", label: "集合运算", field_type: "select", default: "union", options: [{ label: "并集", value: "union" }, { label: "交集", value: "intersection" }, { label: "第一路减第二路", value: "difference" }, { label: "对称差集", value: "symmetric_difference" }] }, { key: "fields", label: "比较字段（留空使用共同字段）", field_type: "columns", default: [] }]],
  ["transform.window_statistics", "窗口统计", "transform", "数据处理", "排名、累计、移动平均及前后记录", "history", "#7c3aed", [{ key: "partition_by", label: "分组字段（可选）", field_type: "columns", default: [] }, { key: "order_by", label: "排序字段", field_type: "column", required: true }, { key: "value_field", label: "统计字段", field_type: "column" }, { key: "operation", label: "统计方式", field_type: "select", default: "row_number", options: [{ label: "组内行号", value: "row_number" }, { label: "排名", value: "rank" }, { label: "密集排名", value: "dense_rank" }, { label: "累计求和", value: "cumulative_sum" }, { label: "移动平均", value: "moving_mean" }, { label: "上一条值", value: "lag" }, { label: "下一条值", value: "lead" }] }, { key: "window_size", label: "移动窗口/偏移行数", field_type: "number", default: 3 }, { key: "output_name", label: "结果列名称", default: "窗口结果", required: true }]],
  ["transform.data_validation", "数据校验", "transform", "数据处理", "使用多条可视化规则校验字段", "check-circle", "#16a34a", [{ key: "rules", label: "校验规则", field_type: "validation_rules", default: [{ field: "", rule: "not_null", value: "", message: "不能为空" }], required: true }, { key: "status_field", label: "校验状态列", default: "校验通过" }, { key: "reason_field", label: "问题原因列", default: "校验问题" }]],
  ["transform.invalid_row_routing", "异常行分流", "transform", "数据处理", "把数据校验结果拆成正常流和异常流，可分别连接不同输出", "funnel", "#dc2626", [{ key: "status_field", label: "校验状态字段", field_type: "column", required: true }, { key: "route", label: "旧项目默认出口", field_type: "select", default: "all", options: [{ label: "全部数据（推荐）", value: "all" }, { label: "仅异常行", value: "invalid" }, { label: "仅正常行", value: "valid" }], help_text: "仅用于没有分支标记的旧连线；新连线请直接使用节点右侧的正常/异常出口" }]],
  ["transform.batch_spill", "分批落盘", "transform", "数据处理", "正式运行时把完整中间结果分批写入文件", "file-arrow-down", "#64748b", [{ key: "path", label: "文件名前缀", field_type: "save_file", required: true }, { key: "format", label: "文件格式", field_type: "select", default: "csv", options: [{ label: "CSV", value: "csv" }, { label: "JSON Lines", value: "jsonl" }, { label: "Parquet", value: "parquet" }] }, { key: "batch_size", label: "每个文件行数", field_type: "number", default: 100000 }]],
  ["transform.custom_expression", "自定义表达式", "transform", "数据处理", "使用安全表达式组合字段生成新列", "text-t", "#2563eb", [{ key: "expression", label: "计算表达式", field_type: "textarea", required: true, placeholder: "例如：[金额] * [数量] - [优惠]", help_text: "支持四则运算和常用函数，不执行任意代码" }, { key: "output_name", label: "结果列名称", default: "表达式结果", required: true }]],
  ["transform.multi_filter", "多条件筛选", "transform", "数据处理", "使用多条条件按且/或关系筛选数据", "funnel", "#14b8a6", [{ key: "rules", label: "筛选条件", field_type: "condition_rules", default: [{ field: "", operator: "equals", value: "" }], required: true }, { key: "logic", label: "条件关系", field_type: "select", default: "all", options: [{ label: "全部满足（且）", value: "all" }, { label: "任一满足（或）", value: "any" }] }, { key: "mode", label: "处理方式", field_type: "select", default: "keep", options: [{ label: "保留满足条件的数据", value: "keep" }, { label: "排除满足条件的数据", value: "drop" }] }]],
  ["transform.case_when", "CASE WHEN 计算列", "transform", "数据处理", "按多条条件依次匹配并生成分类结果", "flow", "#8b5cf6", [{ key: "rules", label: "条件结果", field_type: "case_rules", default: [{ field: "", operator: "equals", value: "", result: "" }], required: true }, { key: "default_value", label: "均不满足时", default: "其他" }, { key: "output_name", label: "结果列名称", default: "分类结果", required: true }]],
  ["transform.datetime_calculation", "日期时间计算", "transform", "数据处理", "日期加减、时间差、格式化与时间戳转换", "history", "#7c3aed", [{ key: "source_field", label: "时间字段", field_type: "column", required: true }, { key: "operation", label: "计算方式", field_type: "select", default: "add_days", options: [{ label: "增加/减少天数", value: "add_days" }, { label: "增加/减少小时", value: "add_hours" }, { label: "与另一字段相差天数", value: "difference_days" }, { label: "与另一字段相差小时", value: "difference_hours" }, { label: "格式化为文本", value: "format" }, { label: "转换为 Unix 时间戳", value: "to_timestamp" }, { label: "Unix 时间戳转时间", value: "from_timestamp" }] }, { key: "second_field", label: "另一个时间字段", field_type: "column" }, { key: "amount", label: "增加量（负数为减少）", field_type: "number", default: 1 }, { key: "input_format", label: "输入格式（可选）", default: "" }, { key: "output_format", label: "输出格式", default: "%Y-%m-%d %H:%M:%S" }, { key: "output_name", label: "结果列名称", default: "时间计算结果", required: true }]],
  ["transform.data_compare", "数据对比", "transform", "数据处理", "比较两个上游并识别新增、缺失和修改", "arrows-left-right", "#4f46e5", [{ key: "keys", label: "唯一标识字段", field_type: "columns", required: true }, { key: "compare_fields", label: "比较内容字段（留空自动选择）", field_type: "columns", default: [] }, { key: "mode", label: "输出范围", field_type: "select", default: "differences", options: [{ label: "只输出差异", value: "differences" }, { label: "输出全部", value: "all" }, { label: "只输出新增", value: "added" }, { label: "只输出缺失", value: "deleted" }, { label: "只输出修改", value: "changed" }] }, { key: "status_field", label: "状态列名称", default: "对比状态" }, { key: "suffix", label: "第二路字段后缀", default: "_新" }]],
  ["transform.batch_fields", "批量字段处理", "transform", "数据处理", "一次对多个字段执行清理、填充或类型转换", "columns", "#0d9488", [{ key: "fields", label: "处理字段", field_type: "columns", required: true }, { key: "operation", label: "处理方式", field_type: "select", default: "trim", options: [{ label: "去除两端空白", value: "trim" }, { label: "转大写", value: "upper" }, { label: "转小写", value: "lower" }, { label: "填充空值", value: "fill_null" }, { label: "文本替换", value: "replace" }, { label: "添加前缀", value: "prefix" }, { label: "添加后缀", value: "suffix" }, { label: "转为文本", value: "string" }, { label: "转为整数", value: "integer" }, { label: "转为小数", value: "float" }] }, { key: "value", label: "参数值", default: "" }, { key: "replacement", label: "替换为", default: "" }]],
  ["transform.row_number", "行号", "transform", "数据处理", "生成全局行号或分组行号", "rows", "#64748b", [{ key: "partition_by", label: "分组字段（可选）", field_type: "columns", default: [] }, { key: "order_by", label: "排序字段（可选）", field_type: "column" }, { key: "direction", label: "排序方向", field_type: "select", default: "ascending", options: [{ label: "升序", value: "ascending" }, { label: "降序", value: "descending" }] }, { key: "start", label: "起始编号", field_type: "number", default: 1 }, { key: "output_name", label: "行号列名称", default: "行号", required: true }]],
  ["transform.top_n", "Top N", "transform", "数据处理", "保留全局或每个分组的前 N 条", "funnel", "#f59e0b", [{ key: "group_by", label: "分组字段（可选）", field_type: "columns", default: [] }, { key: "order_by", label: "排序字段", field_type: "column", required: true }, { key: "direction", label: "保留方向", field_type: "select", default: "largest", options: [{ label: "最大值优先", value: "largest" }, { label: "最小值优先", value: "smallest" }] }, { key: "n", label: "每组保留条数", field_type: "number", default: 10 }]],
  ["transform.sampling", "数据采样", "transform", "数据处理", "固定条数、比例或等间隔抽取样本", "squares-four", "#06b6d4", [{ key: "mode", label: "采样方式", field_type: "select", default: "count", options: [{ label: "随机固定条数", value: "count" }, { label: "随机比例", value: "fraction" }, { label: "等间隔采样", value: "systematic" }, { label: "取前 N 条", value: "head" }] }, { key: "count", label: "样本条数", field_type: "number", default: 1000 }, { key: "fraction", label: "采样比例（0-1）", field_type: "number", default: 0.1 }, { key: "seed", label: "随机种子", field_type: "number", default: 42 }]],
  ["transform.interval_group", "区间分组", "transform", "数据处理", "按数值边界划分自定义区间", "columns", "#ea580c", [{ key: "source_field", label: "数值字段", field_type: "column", required: true }, { key: "boundaries", label: "区间边界", default: "60,80,90", required: true, help_text: "从小到大并用逗号分隔" }, { key: "labels", label: "区间名称（可选）", default: "不及格,及格,良好,优秀" }, { key: "output_name", label: "结果列名称", default: "区间", required: true }]],
  ["transform.data_profiling", "数据剖析", "transform", "数据处理", "统计每列类型、空值率、唯一值及分布", "report", "#16a34a", [{ key: "fields", label: "分析字段（留空分析全部）", field_type: "columns", default: [] }, { key: "include_examples", label: "包含示例值", field_type: "boolean", default: true }]],
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
  ["output.mysql", "MySQL 写入", "output", "数据输出", "选择已有库表或手写名称自动创建", "database", "#f97316", [{ key: "host", label: "主机", default: "127.0.0.1", required: true }, { key: "port", label: "端口", field_type: "number", default: 3306 }, { key: "username", label: "用户名", default: "root", required: true }, { key: "password", label: "密码", field_type: "password", required: true }, { key: "target_mode", label: "目标配置方式", field_type: "select", default: "existing", options: [{ label: "选择已有数据库和表", value: "existing" }, { label: "手写名称并自动创建", value: "manual" }] }, { key: "database", label: "已有数据库", field_type: "mysql_database" }, { key: "table", label: "已有数据表", field_type: "mysql_table" }, { key: "database_manual", label: "新数据库名称", default: "ctf_data", placeholder: "不存在时自动创建" }, { key: "table_manual", label: "新数据表名称", default: "result", placeholder: "不存在时根据字段自动创建" }, { key: "mode", label: "表已存在时", field_type: "select", default: "append", options: [{ label: "追加数据", value: "append" }, { label: "覆盖表", value: "replace" }, { label: "报错并停止", value: "fail" }] }, { key: "batch_size", label: "每批写入行数（不是总数）", field_type: "number", default: 1000, help_text: "例如 10000 行会按 1000 行一批连续写入 10 批，最终数据不会截断" }, ...mysqlAdvancedFields]],
  ["output.pcap_index", "PCAP 索引完整导出", "output", "数据输出", "从磁盘索引分批导出全部数据包", "file-arrow-down", "#4f46e5", [{ key: "path", label: "输出路径", field_type: "save_file", required: true }, { key: "delimiter", label: "分隔符", default: "," }]],
].map(([id, name, kind, group, description, icon, color, config_fields]) => ({
  id, name, kind, group, description, icon, color, config_fields,
  output_ports: id === "transform.invalid_row_routing"
    ? [{ id: "valid", label: "正常", color: "#16a34a" }, { id: "invalid", label: "异常", color: "#dc2626" }]
    : id === "transform.conditional_branch"
      ? [{ id: "matched", label: "满足", color: "#16a34a" }, { id: "unmatched", label: "不满足", color: "#ea580c" }]
      : [],
  category: {
    "transform.filter": "筛选与字段", "transform.select_columns": "筛选与字段",
    "transform.mapping": "字段转换", "transform.rename_column": "字段转换", "transform.split_column": "字段转换", "transform.convert": "字段转换",
    "transform.mask": "安全与隐私", "transform.group": "聚合与结构", "transform.merge_inputs": "聚合与结构", "transform.deduplicate": "筛选与字段", "transform.merge_rows": "聚合与结构",
    "transform.replace": "文本处理", "transform.trim": "文本处理", "transform.concat_columns": "文本处理", "transform.uppercase": "文本处理", "transform.lowercase": "文本处理",
    "transform.base64": "加密与编码", "transform.url_codec": "加密与编码", "transform.md5": "加密与编码", "transform.aes": "加密与编码", "transform.hash_digest": "加密与编码",
    "transform.sort_rows": "筛选与字段", "transform.missing_values": "筛选与字段", "transform.join_inputs": "聚合与结构",
    "transform.regex_extract": "文本处理", "transform.json_flatten": "字段转换", "transform.datetime_features": "字段转换", "transform.ioc_extract": "安全与隐私",
    "transform.calculated_column": "字段计算", "transform.numeric_calculation": "字段计算", "transform.conditional_branch": "流程控制",
    "transform.pivot": "结构转换", "transform.unpivot": "结构转换", "transform.transpose": "结构转换", "transform.set_operations": "多表处理",
    "transform.window_statistics": "聚合统计", "transform.data_validation": "数据质量", "transform.invalid_row_routing": "数据质量", "transform.batch_spill": "流程控制",
    "transform.custom_expression": "字段计算", "transform.multi_filter": "筛选与字段", "transform.case_when": "字段计算", "transform.datetime_calculation": "日期时间",
    "transform.data_compare": "多表处理", "transform.batch_fields": "字段转换", "transform.row_number": "筛选与字段", "transform.top_n": "筛选与字段",
    "transform.sampling": "筛选与字段", "transform.interval_group": "字段计算", "transform.data_profiling": "数据质量",
    "ctf.session_group": "CTF 流量分析", "ctf.tcp_reassemble": "CTF 流量分析",
    "ctf.http_extract": "CTF 协议提取", "ctf.dns_extract": "CTF 协议提取", "ctf.icmp_extract": "CTF 协议提取",
    "ctf.hex_codec": "CTF 编码解码", "ctf.base_codec": "CTF 编码解码",
    "ctf.xor": "CTF 密码爆破", "ctf.caesar": "CTF 密码爆破", "ctf.flag_scan": "CTF 检测",
  }[id] || "",
}));

const desktopApi = () => window.pywebview?.api;
const browserStorageConfig = () => JSON.parse(localStorage.getItem("data-workbench-settings:storage") || '{"mode":"local","mysql":{}}');
const mockRunJobs = new Map();

function mockCondition(row, config = {}) {
  const value = row[config.field];
  const expected = config.value ?? "";
  const text = String(value ?? "");
  const comparison = String(expected);
  if (config.operator === "contains") return text.includes(comparison);
  if (config.operator === "not_contains") return !text.includes(comparison);
  if (config.operator === "not_equals") return text !== comparison;
  if (config.operator === "greater") return Number(value) > Number(expected);
  if (config.operator === "greater_equal") return Number(value) >= Number(expected);
  if (config.operator === "less") return Number(value) < Number(expected);
  if (config.operator === "less_equal") return Number(value) <= Number(expected);
  if (config.operator === "regex") {
    try { return new RegExp(comparison).test(text); } catch { return false; }
  }
  if (config.operator === "is_null") return value == null;
  if (config.operator === "not_null") return value != null;
  return text === comparison;
}

function mockBranchRows(rows, sourceNode, sourceHandle) {
  if (!sourceHandle || sourceNode?.pluginId !== "transform.conditional_branch") return rows;
  const matched = sourceHandle === "matched";
  return rows.filter((row) => mockCondition(row, sourceNode.config || {}) === matched);
}

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
      const branchEdge = pipeline.edges.find((edge) => edge.target === current.id && edge.sourceHandle);
      if (branchEdge) rows = mockBranchRows(rows, pipeline.nodes.find((item) => item.id === branchEdge.source), branchEdge.sourceHandle);
      if (current.pluginId === "transform.filter" && config.field) {
        rows = rows.filter((row) => config.operator !== "equals" || String(row[config.field]) === String(config.value));
      } else if (current.pluginId === "transform.conditional_branch" && config.field) {
        const outputName = config.output_name || "条件分支";
        rows = rows.map((row) => ({ ...row, [outputName]: mockCondition(row, config) ? (config.true_label || "是") : (config.false_label || "否") }));
      } else if (current.pluginId === "transform.select_columns" && Array.isArray(config.columns) && config.columns.length) {
        rows = rows.map((row) => Object.fromEntries(config.columns.filter((field) => Object.hasOwn(row, field)).map((field) => [field, row[field]])));
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
    if (incoming.length === 1 && incoming[0].sourceHandle) {
      const edge = incoming[0];
      const source = pipeline.nodes.find((node) => node.id === edge.source);
      const result = mockPreview(pipeline, edge.source, limit, page);
      const rows = mockBranchRows(result.data.rows, source, edge.sourceHandle);
      const columns = Object.keys(rows[0] || {}).map((key) => ({ key, label: key, type: typeof rows[0]?.[key] === "number" ? "Int64" : "String" }));
      return { ok: true, data: { ...result.data, rows, columns, stats: { ...result.data.stats, rowCount: rows.length, previewCount: rows.length, columnCount: columns.length, nodeId: targetNodeId } } };
    }
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
    if (job.status === "cancelled") return { ok: true, job: { ...job, pipeline: undefined } };
    const nextPercent = Math.min(100, job.percent + 24);
    const nodeIndex = Math.min(job.nodeCount, Math.max(1, Math.ceil(nextPercent / 100 * Math.max(job.nodeCount, 1))));
    Object.assign(job, { percent: nextPercent, nodeIndex, currentNode: `处理节点 ${nodeIndex}`, sourceRows: 128542, processedRows: Math.round(128542 * nextPercent / 100), outputRows: Math.round(123876 * nextPercent / 100), elapsedSeconds: Number((job.elapsedSeconds + 0.6).toFixed(1)) });
    if (nextPercent === 100) Object.assign(job, { status: "success", phase: "complete", complete: true, finalRows: 123876, message: "全量数据处理和导出完成，结果完整", result: mockPreview(job.pipeline, job.pipeline.nodes.at(-1)?.id).data });
    return { ok: true, job: { ...job, pipeline: undefined } };
  },
  async cancelPipelineRun(jobId) {
    if (desktopApi()) return desktopApi().cancel_pipeline_run(jobId);
    const job = mockRunJobs.get(jobId);
    if (!job) return { ok: false, error: "运行任务不存在" };
    Object.assign(job, { status: "cancelled", phase: "cancelled", message: "任务已安全停止" });
    return { ok: true, job: { ...job, pipeline: undefined }, message: "已发送停止请求" };
  },
  async cancelPreview() {
    return desktopApi() ? desktopApi().cancel_preview() : { ok: true, message: "已停止当前加载" };
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
