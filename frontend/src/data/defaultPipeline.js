export const initialNodes = [
  { id: "source-demo", type: "plugin", position: { x: 20, y: 122 }, data: { pluginId: "input.demo", label: "读取示例数据", config: {} } },
  { id: "filter-http", type: "plugin", position: { x: 157, y: 122 }, data: { pluginId: "transform.filter", label: "过滤 HTTP", config: { field: "协议", operator: "equals", value: "HTTP" } } },
  { id: "map-field", type: "plugin", position: { x: 294, y: 122 }, data: { pluginId: "transform.mapping", label: "字段映射", config: { source_field: "请求方法", target_field: "请求方式", value_map: [] } } },
  { id: "mask-phone", type: "plugin", position: { x: 431, y: 122 }, data: { pluginId: "transform.mask", label: "手机号脱敏", config: { fields: "手机号", keep_start: 3, keep_end: 4, mask_char: "*" } } },
  { id: "group-ip", type: "plugin", position: { x: 568, y: 122 }, data: { pluginId: "transform.group", label: "分组聚合", config: { group_by: "IP地址", aggregate_rules: [{ operation: "count", field: "", output_name: "访问次数" }] } } },
  { id: "export-file", type: "plugin", position: { x: 705, y: 122 }, data: { pluginId: "output.file", label: "导出 CSV", config: { path: "处理结果.csv", format: "csv", delimiter: ",", encoding: "utf-8" } } },
];

export const initialEdges = [
  { id: "source-filter", source: "source-demo", target: "filter-http" },
  { id: "filter-map", source: "filter-http", target: "map-field" },
  { id: "map-mask", source: "map-field", target: "mask-phone" },
  { id: "mask-group", source: "mask-phone", target: "group-ip" },
  { id: "group-output", source: "group-ip", target: "export-file" },
].map((edge) => ({ ...edge, type: "smoothstep", animated: false, style: { stroke: "#8390a3", strokeWidth: 1.6 } }));

export const demoRows = [
  { 时间: "2026-08-19 10:15:23", IP地址: "183.232.231.174", 手机号: "13800138000", 请求方法: "GET", 状态码: 200, 路径: "/api/user/login", 协议: "HTTP" },
  { 时间: "2026-08-19 10:15:25", IP地址: "183.232.231.174", 手机号: "13800138000", 请求方法: "GET", 状态码: 200, 路径: "/api/user/info", 协议: "HTTP" },
  { 时间: "2026-08-19 10:15:27", IP地址: "112.25.16.8", 手机号: "18612345678", 请求方法: "POST", 状态码: 200, 路径: "/api/order/create", 协议: "HTTP" },
  { 时间: "2026-08-19 10:15:31", IP地址: "112.25.16.8", 手机号: "18612345678", 请求方法: "GET", 状态码: 200, 路径: "/api/order/list", 协议: "HTTP" },
  { 时间: "2026-08-19 10:15:33", IP地址: "221.196.13.12", 手机号: "15987655678", 请求方法: "GET", 状态码: 404, 路径: "/api/product/123", 协议: "HTTP" },
  { 时间: "2026-08-19 10:15:36", IP地址: "221.196.13.12", 手机号: "15987655678", 请求方法: "GET", 状态码: 200, 路径: "/api/product/list", 协议: "HTTP" },
];
