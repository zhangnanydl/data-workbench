import { Fragment, useEffect, useState } from "react";
import { ArrowClockwise, CheckCircle, Database, FolderOpen, Plus, Trash, WarningCircle } from "@phosphor-icons/react";
import { Icon } from "./Icon.jsx";
import { ColumnSelector } from "./ColumnSelector.jsx";
import { bridge } from "../lib/bridge.js";
import { normalizeValueMap } from "../lib/valueMap.js";
import { combineEventIds, normalizeEventIds } from "../lib/eventIds.js";

const MASK_SAMPLE = "13800138000";
const MYSQL_ADVANCED_KEYS = new Set(["charset", "timezone", "ssl_mode", "connect_timeout", "read_timeout", "write_timeout"]);
const AGGREGATE_OPERATIONS = [
  ["count", "行数"], ["count_non_null", "非空计数"], ["count_distinct", "去重计数"],
  ["sum", "求和"], ["mean", "平均值"], ["median", "中位数"], ["max", "最大值"], ["min", "最小值"], ["first", "第一条"], ["last", "最后一条"],
];
const VALIDATION_RULES = [
  ["not_null", "不能为空"], ["numeric", "必须是数值"], ["integer", "必须是整数"],
  ["min", "不小于"], ["max", "不大于"], ["regex", "匹配正则"],
  ["allowed", "属于指定值"], ["unique", "不能重复"],
];
const CONDITION_OPERATIONS = [
  ["equals", "等于"], ["not_equals", "不等于"], ["contains", "包含"], ["not_contains", "不包含"],
  ["greater", "大于"], ["greater_equal", "大于等于"], ["less", "小于"], ["less_equal", "小于等于"],
  ["regex", "匹配正则"], ["is_null", "为空"], ["not_null", "非空"],
];

function maskSample(value, keepStart, keepEnd, maskCharacter) {
  const start = Math.max(0, Number(keepStart) || 0);
  const end = Math.max(0, Number(keepEnd) || 0);
  const character = String(maskCharacter || "*").slice(0, 1) || "*";
  if (value.length <= start + end) return character.repeat(value.length);
  const suffix = end > 0 ? value.slice(-end) : "";
  return value.slice(0, start) + character.repeat(value.length - start - end) + suffix;
}

export function Inspector({ node, plugin, columns, onRename, onConfigChange, onDelete, onPickFile, livePreview, onLivePreviewChange }) {
  const [mysqlDatabases, setMysqlDatabases] = useState([]);
  const [mysqlTables, setMysqlTables] = useState([]);
  const [mysqlLoading, setMysqlLoading] = useState(false);
  const [mysqlMessage, setMysqlMessage] = useState(null);

  useEffect(() => {
    setMysqlDatabases([]);
    setMysqlTables([]);
    setMysqlMessage(null);
  }, [node?.id]);

  if (!node || !plugin) {
    return <aside className="inspector inspector--empty"><span>选择一个模块查看配置</span></aside>;
  }

  const valueFor = (field) => {
    if (field.key === "aggregate_rules" && node.data.config?.aggregate_rules == null && node.data.config?.operation) {
      return [{ operation: node.data.config.operation, field: node.data.config.aggregate_field || "", output_name: node.data.config.output_name || "数量" }];
    }
    return node.data.config?.[field.key] ?? field.default ?? "";
  };
  const mysqlTargetMode = valueFor({ key: "target_mode", default: "existing" });
  const mysqlAdvanced = Boolean(valueFor({ key: "advanced", default: true }));

  const mysqlConfig = () => ({
    host: valueFor({ key: "host", default: "127.0.0.1" }),
    port: valueFor({ key: "port", default: 3306 }),
    username: valueFor({ key: "username", default: "root" }),
    password: valueFor({ key: "password", default: "" }),
    database: valueFor({ key: "database", default: "" }),
    charset: valueFor({ key: "charset", default: "utf8mb4" }),
    timezone: valueFor({ key: "timezone", default: "+08:00" }),
    ssl_mode: valueFor({ key: "ssl_mode", default: "disabled" }),
    connect_timeout: valueFor({ key: "connect_timeout", default: 5 }),
    read_timeout: valueFor({ key: "read_timeout", default: 30 }),
    write_timeout: valueFor({ key: "write_timeout", default: 30 }),
  });

  const showField = (field) => {
    if (["input.mysql", "output.mysql"].includes(plugin.id) && MYSQL_ADVANCED_KEYS.has(field.key) && !mysqlAdvanced) return false;
    if (plugin.id === "output.mysql") {
      if (["database", "table"].includes(field.key)) return mysqlTargetMode === "existing";
      if (["database_manual", "table_manual"].includes(field.key)) return mysqlTargetMode === "manual";
    }
    if (plugin.id === "transform.calculated_column") {
      const operation = valueFor({ key: "operation", default: "copy" });
      if (field.key === "source_field") return operation !== "constant";
      if (["second_field", "separator"].includes(field.key)) return operation === "concat";
      if (field.key === "constant") return operation === "constant";
    }
    if (plugin.id === "transform.numeric_calculation") {
      const operation = valueFor({ key: "operation", default: "add" });
      const operandMode = valueFor({ key: "operand_mode", default: "constant" });
      if (field.key === "operand_mode") return !["abs", "sqrt", "log", "round"].includes(operation);
      if (field.key === "operand") return operation === "round" || (!["abs", "sqrt", "log"].includes(operation) && operandMode === "constant");
      if (field.key === "operand_field") return !["abs", "sqrt", "log", "round"].includes(operation) && operandMode === "field";
    }
    if (plugin.id === "transform.conditional_branch" && field.key === "value") {
      return !["is_null", "not_null"].includes(valueFor({ key: "operator", default: "equals" }));
    }
    if (plugin.id === "transform.window_statistics") {
      const operation = valueFor({ key: "operation", default: "row_number" });
      if (field.key === "value_field") return !["row_number", "rank", "dense_rank"].includes(operation);
      if (field.key === "window_size") return ["moving_mean", "lag", "lead"].includes(operation);
    }
    if (plugin.id === "transform.datetime_calculation") {
      const operation = valueFor({ key: "operation", default: "add_days" });
      if (field.key === "second_field") return ["difference_days", "difference_hours"].includes(operation);
      if (field.key === "amount") return ["add_days", "add_hours"].includes(operation);
      if (field.key === "input_format") return operation !== "from_timestamp";
      if (field.key === "output_format") return operation === "format";
    }
    if (plugin.id === "transform.batch_fields") {
      const operation = valueFor({ key: "operation", default: "trim" });
      if (field.key === "value") return ["fill_null", "replace", "prefix", "suffix"].includes(operation);
      if (field.key === "replacement") return operation === "replace";
    }
    if (plugin.id === "transform.row_number" && field.key === "direction") return Boolean(valueFor({ key: "order_by", default: "" }));
    if (plugin.id === "transform.sampling") {
      const mode = valueFor({ key: "mode", default: "count" });
      if (field.key === "count") return mode !== "fraction";
      if (field.key === "fraction") return mode === "fraction";
      if (field.key === "seed") return ["count", "fraction"].includes(mode);
    }
    return true;
  };

  const loadMysqlDatabases = async () => {
    setMysqlLoading(true);
    setMysqlMessage(null);
    const result = await bridge.listMysqlDatabases(mysqlConfig());
    setMysqlLoading(false);
    setMysqlDatabases(result.items || []);
    setMysqlTables([]);
    setMysqlMessage({ ok: result.ok, text: result.message || result.error });
  };

  const loadMysqlTables = async (database) => {
    onConfigChange("database", database);
    onConfigChange("table", "");
    setMysqlTables([]);
    if (!database) return;
    setMysqlLoading(true);
    const result = await bridge.listMysqlTables({ ...mysqlConfig(), database });
    setMysqlLoading(false);
    setMysqlTables(result.items || []);
    setMysqlMessage({ ok: result.ok, text: result.message || result.error });
  };

  const renderField = (field) => {
    const value = valueFor(field);
    if (field.field_type === "boolean") {
      return <button className={`switch ${value ? "is-on" : ""}`} onClick={() => onConfigChange(field.key, !value)}><span /></button>;
    }
    if (["file", "save_file"].includes(field.field_type)) {
      return (
        <div className="file-field">
          <input value={value} onChange={(event) => onConfigChange(field.key, event.target.value)} placeholder={field.placeholder || "选择路径"} />
          <button onClick={() => onPickFile(field)} aria-label="选择文件"><FolderOpen size={17} /></button>
        </div>
      );
    }
    if (field.field_type === "textarea") {
      return <textarea rows={3} value={value} onChange={(event) => onConfigChange(field.key, event.target.value)} placeholder={field.placeholder} />;
    }
    if (field.field_type === "column_names") {
      const parsed = Array.isArray(value) ? value.map(String) : String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
      const names = parsed.length >= 2 ? parsed : [...parsed, ...Array.from({ length: 2 - parsed.length }, (_, index) => `第${parsed.length + index + 1}列`)];
      const updateName = (index, nextValue) => onConfigChange(field.key, names.map((name, itemIndex) => itemIndex === index ? nextValue : name));
      return <div className="column-name-editor">
        {names.map((name, index) => <div className="column-name-row" key={index}><span>{index + 1}</span><input value={name} onChange={(event) => updateName(index, event.target.value)} placeholder={`第 ${index + 1} 列名称`} aria-label={`拆分后第 ${index + 1} 列名称`} /><button type="button" onClick={() => onConfigChange(field.key, names.filter((_, itemIndex) => itemIndex !== index))} disabled={names.length <= 2} aria-label={`删除第 ${index + 1} 列`}><Trash size={14} /></button></div>)}
        <button className="add-column-name" type="button" onClick={() => onConfigChange(field.key, [...names, `第${names.length + 1}列`])}><Plus size={14} />添加一列</button>
      </div>;
    }
    if (field.field_type === "value_map") {
      const parsedRules = normalizeValueMap(value);
      const rules = parsedRules.length ? parsedRules : [{ source_value: "", target_value: "" }];
      const updateRule = (index, key, nextValue) => onConfigChange(field.key, rules.map((rule, itemIndex) => itemIndex === index ? { ...rule, [key]: nextValue } : rule));
      return <div className="value-map-editor">
        <div className="value-map-head"><span>原值</span><i>→</i><span>替换为</span><b /></div>
        {rules.map((rule, index) => <div className="value-map-row" key={index}>
          <input value={rule.source_value} onChange={(event) => updateRule(index, "source_value", event.target.value)} placeholder="例如 0" aria-label={`映射规则 ${index + 1} 原值`} />
          <i>→</i>
          <input value={rule.target_value} onChange={(event) => updateRule(index, "target_value", event.target.value)} placeholder="例如 失败" aria-label={`映射规则 ${index + 1} 新值`} />
          <button type="button" onClick={() => onConfigChange(field.key, rules.filter((_, itemIndex) => itemIndex !== index))} disabled={rules.length <= 1} aria-label={`删除映射规则 ${index + 1}`}><Trash size={13} /></button>
        </div>)}
        <button className="add-value-map-rule" type="button" onClick={() => onConfigChange(field.key, [...rules, { source_value: "", target_value: "" }])}><Plus size={14} />添加一条替换规则</button>
      </div>;
    }
    if (field.field_type === "event_id_selector") {
      const selected = normalizeEventIds(value);
      const selectedSet = new Set(selected);
      const commonValues = new Set((field.options || []).map((option) => String(option.value)));
      const customValues = selected.filter((eventId) => !commonValues.has(eventId)).join(",");
      const toggleEvent = (eventId) => onConfigChange(field.key, selectedSet.has(eventId) ? selected.filter((item) => item !== eventId) : [...selected, eventId]);
      const categories = [...new Set((field.options || []).map((option) => option.category || "常用"))];
      return <div className="event-id-selector">
        <header><span>已选择 {selected.length} 个事件</span><button type="button" onClick={() => onConfigChange(field.key, [])} disabled={!selected.length}>清空</button></header>
        <div className="event-id-options">
          {categories.map((category) => <section key={category}><strong>{category}</strong>{(field.options || []).filter((option) => (option.category || "常用") === category).map((option) => {
            const eventId = String(option.value);
            return <label className={selectedSet.has(eventId) ? "is-selected" : ""} key={eventId}><input type="checkbox" checked={selectedSet.has(eventId)} onChange={() => toggleEvent(eventId)} /><span>{option.label}</span></label>;
          })}</section>)}
        </div>
        <label className="custom-event-ids"><span>自定义事件ID</span><input value={customValues} onChange={(event) => onConfigChange(field.key, combineEventIds(selected.filter((eventId) => commonValues.has(eventId)), event.target.value))} placeholder="例如 1, 3, 1000" /></label>
      </div>;
    }
    if (field.field_type === "option_selector") {
      const selected = Array.isArray(value) ? value.map(String) : String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
      const selectedSet = new Set(selected);
      const toggleOption = (optionValue) => onConfigChange(field.key, selectedSet.has(optionValue) ? selected.filter((item) => item !== optionValue) : [...selected, optionValue]);
      return <div className="event-id-selector option-selector">
        <header><span>已选择 {selected.length} 项</span><button type="button" onClick={() => onConfigChange(field.key, [])} disabled={!selected.length}>清空</button></header>
        <div className="event-id-options"><section>{(field.options || []).map((option) => {
          const optionValue = String(option.value);
          return <label className={selectedSet.has(optionValue) ? "is-selected" : ""} key={optionValue}><input type="checkbox" checked={selectedSet.has(optionValue)} onChange={() => toggleOption(optionValue)} /><span>{option.label}</span></label>;
        })}</section></div>
      </div>;
    }
    if (field.field_type === "aggregate_rules") {
      const rules = Array.isArray(value) && value.length ? value : [{ operation: "count", field: "", output_name: "人数" }];
      const updateRule = (index, key, nextValue) => onConfigChange(field.key, rules.map((rule, itemIndex) => itemIndex === index ? { ...rule, [key]: nextValue } : rule));
      return <div className="aggregate-rules-editor">
        {rules.map((rule, index) => {
          const needsField = rule.operation !== "count";
          return <section className="aggregate-rule" key={index}>
            <header><strong>统计 {index + 1}</strong><button type="button" onClick={() => onConfigChange(field.key, rules.filter((_, itemIndex) => itemIndex !== index))} disabled={rules.length <= 1} aria-label={`删除统计 ${index + 1}`}><Trash size={13} /></button></header>
            <div className="aggregate-rule-fields">
              <label><span>计算方式</span><select value={rule.operation || "count"} onChange={(event) => updateRule(index, "operation", event.target.value)}>{AGGREGATE_OPERATIONS.map(([operation, label]) => <option value={operation} key={operation}>{label}</option>)}</select></label>
              <label><span>统计字段</span><select value={rule.field || ""} disabled={!needsField || !columns.length} onChange={(event) => updateRule(index, "field", event.target.value)}><option value="">{needsField ? "请选择字段" : "全部行"}</option>{columns.map((column) => <option value={column.key} key={column.key}>{column.label}</option>)}</select></label>
              <label className="aggregate-output-name"><span>结果列名</span><input value={rule.output_name || ""} onChange={(event) => updateRule(index, "output_name", event.target.value)} placeholder="例如：平均分" /></label>
            </div>
          </section>;
        })}
        <button className="add-aggregate-rule" type="button" onClick={() => onConfigChange(field.key, [...rules, { operation: "mean", field: "", output_name: `统计${rules.length + 1}` }])}><Plus size={14} />添加统计项</button>
      </div>;
    }
    if (field.field_type === "validation_rules") {
      const rules = Array.isArray(value) && value.length ? value : [{ field: "", rule: "not_null", value: "", message: "不能为空" }];
      const updateRule = (index, key, nextValue) => onConfigChange(field.key, rules.map((rule, itemIndex) => itemIndex === index ? { ...rule, [key]: nextValue } : rule));
      return <div className="aggregate-rules-editor validation-rules-editor">
        {rules.map((rule, index) => {
          const needsValue = ["min", "max", "regex", "allowed"].includes(rule.rule);
          return <section className="aggregate-rule" key={index}>
            <header><strong>规则 {index + 1}</strong><button type="button" onClick={() => onConfigChange(field.key, rules.filter((_, itemIndex) => itemIndex !== index))} disabled={rules.length <= 1} aria-label={`删除校验规则 ${index + 1}`}><Trash size={13} /></button></header>
            <div className="aggregate-rule-fields">
              <label><span>校验字段</span><select value={rule.field || ""} disabled={!columns.length} onChange={(event) => updateRule(index, "field", event.target.value)}><option value="">{columns.length ? "请选择字段" : "正在读取上游字段…"}</option>{columns.map((column) => <option value={column.key} key={column.key}>{column.label}</option>)}</select></label>
              <label><span>校验方式</span><select value={rule.rule || "not_null"} onChange={(event) => updateRule(index, "rule", event.target.value)}>{VALIDATION_RULES.map(([ruleValue, label]) => <option value={ruleValue} key={ruleValue}>{label}</option>)}</select></label>
              {needsValue ? <label><span>{rule.rule === "allowed" ? "允许值（逗号分隔）" : "规则参数"}</span><input value={rule.value ?? ""} onChange={(event) => updateRule(index, "value", event.target.value)} placeholder={rule.rule === "regex" ? "例如 ^[A-Z]+$" : "请输入"} /></label> : null}
              <label className="aggregate-output-name"><span>失败提示</span><input value={rule.message || ""} onChange={(event) => updateRule(index, "message", event.target.value)} placeholder="例如：手机号格式错误" /></label>
            </div>
          </section>;
        })}
        <button className="add-aggregate-rule" type="button" onClick={() => onConfigChange(field.key, [...rules, { field: "", rule: "not_null", value: "", message: "校验失败" }])}><Plus size={14} />添加校验规则</button>
      </div>;
    }
    if (["condition_rules", "case_rules"].includes(field.field_type)) {
      const isCase = field.field_type === "case_rules";
      const emptyRule = { field: "", operator: "equals", value: "", ...(isCase ? { result: "" } : {}) };
      const rules = Array.isArray(value) && value.length ? value : [emptyRule];
      const updateRule = (index, key, nextValue) => onConfigChange(field.key, rules.map((rule, itemIndex) => itemIndex === index ? { ...rule, [key]: nextValue } : rule));
      return <div className="aggregate-rules-editor condition-rules-editor">
        {rules.map((rule, index) => {
          const needsValue = !["is_null", "not_null"].includes(rule.operator);
          return <section className="aggregate-rule" key={index}>
            <header><strong>{isCase ? `条件 ${index + 1}` : `筛选条件 ${index + 1}`}</strong><button type="button" onClick={() => onConfigChange(field.key, rules.filter((_, itemIndex) => itemIndex !== index))} disabled={rules.length <= 1} aria-label={`删除条件 ${index + 1}`}><Trash size={13} /></button></header>
            <div className="aggregate-rule-fields">
              <label><span>字段</span><select value={rule.field || ""} disabled={!columns.length} onChange={(event) => updateRule(index, "field", event.target.value)}><option value="">{columns.length ? "请选择字段" : "正在读取上游字段…"}</option>{columns.map((column) => <option value={column.key} key={column.key}>{column.label}</option>)}</select></label>
              <label><span>比较方式</span><select value={rule.operator || "equals"} onChange={(event) => updateRule(index, "operator", event.target.value)}>{CONDITION_OPERATIONS.map(([operation, label]) => <option value={operation} key={operation}>{label}</option>)}</select></label>
              {needsValue ? <label><span>比较值</span><input value={rule.value ?? ""} onChange={(event) => updateRule(index, "value", event.target.value)} placeholder="请输入比较值" /></label> : null}
              {isCase ? <label className="aggregate-output-name"><span>满足时结果</span><input value={rule.result ?? ""} onChange={(event) => updateRule(index, "result", event.target.value)} placeholder="例如：高风险" /></label> : null}
            </div>
          </section>;
        })}
        <button className="add-aggregate-rule" type="button" onClick={() => onConfigChange(field.key, [...rules, emptyRule])}><Plus size={14} />{isCase ? "添加条件结果" : "添加筛选条件"}</button>
      </div>;
    }
    if (field.field_type === "select") {
      return <select value={value} onChange={(event) => onConfigChange(field.key, event.target.value)}>{(field.options || []).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>;
    }
    if (field.field_type === "mysql_database") {
      return <select value={value} onChange={(event) => loadMysqlTables(event.target.value)} disabled={!mysqlDatabases.length}><option value="">{mysqlDatabases.length ? "请选择数据库" : "请先连接并读取"}</option>{mysqlDatabases.map((item) => <option key={item} value={item}>{item}</option>)}</select>;
    }
    if (field.field_type === "mysql_table") {
      return <select value={value} onChange={(event) => onConfigChange(field.key, event.target.value)} disabled={!mysqlTables.length}><option value="">{mysqlTables.length ? "请选择数据表" : "选择数据库后自动读取"}</option>{mysqlTables.map((item) => <option key={item} value={item}>{item}</option>)}</select>;
    }
    if (field.field_type === "columns") {
      return <ColumnSelector columns={columns} value={value} onChange={(next) => onConfigChange(field.key, next)} />;
    }
    if (field.field_type === "column") {
      return <select value={value} onChange={(event) => onConfigChange(field.key, event.target.value)} disabled={!columns.length}><option value="">{columns.length ? "请选择字段" : "正在读取上游字段…"}</option>{columns.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}</select>;
    }
    return <input type={field.field_type === "number" ? "number" : field.field_type === "password" ? "password" : "text"} value={value} onChange={(event) => onConfigChange(field.key, field.field_type === "number" ? Number(event.target.value) : event.target.value)} placeholder={field.placeholder} />;
  };

  return (
    <aside className="inspector">
      <div className="inspector__heading">
        <div><span className="eyebrow">模块配置</span><h2><Icon name={plugin.icon} size={18} weight="duotone" />{node.data.label}</h2></div>
        <span className="status-pill"><CheckCircle size={14} weight="fill" />配置有效</span>
      </div>
      <p className="inspector__description">{plugin.description}</p>
      <label className="form-field node-name-field">
        <span>节点名称</span>
        <input
          value={node.data.label || ""}
          onChange={(event) => onRename(event.target.value)}
          onBlur={(event) => { if (!event.target.value.trim()) onRename(plugin.name); }}
          maxLength={40}
          placeholder={plugin.name}
          aria-label="节点名称"
        />
        <small>修改画布上的显示名称，不影响节点功能和已有连线</small>
      </label>
      {plugin.output_ports?.length ? <div className="branch-output-guide">
        <strong>这是一个分支节点</strong>
        <span>从节点右侧对应出口连线，两个数据流会独立处理并完整导出。</span>
        <div>{plugin.output_ports.map((port) => <i style={{ "--port-color": port.color }} key={port.id}><b />{port.label}数据</i>)}</div>
      </div> : null}
      {plugin.config_fields.some((field) => ["column", "columns", "validation_rules", "condition_rules", "case_rules"].includes(field.field_type)) ? <div className="auto-fields-note"><CheckCircle size={14} weight="fill" />已自动读取上游数据的 {columns.length} 个字段</div> : null}
      <div className="form-stack">
        {plugin.config_fields.filter(showField).map((field) => (
          <Fragment key={field.key}>
            {["input.mysql", "output.mysql"].includes(plugin.id) && mysqlTargetMode === "existing" && field.key === "database" ? <div className="mysql-connect-panel"><button onClick={loadMysqlDatabases} disabled={mysqlLoading || !valueFor({ key: "username" }) || !valueFor({ key: "password" })}>{mysqlLoading ? <ArrowClockwise className="is-spinning" size={15} /> : <Database size={15} />}{mysqlLoading ? "正在读取…" : "连接并读取数据库"}</button>{mysqlMessage ? <span className={mysqlMessage.ok ? "is-ok" : "is-error"}>{mysqlMessage.ok ? <CheckCircle size={13} weight="fill" /> : <WarningCircle size={13} />}{mysqlMessage.text}</span> : <small>填写连接信息后读取已有数据库和表</small>}</div> : null}
            {plugin.id === "output.mysql" && mysqlTargetMode === "manual" && field.key === "database_manual" ? <div className="mysql-create-note"><Database size={15} /><span><strong>自动创建模式</strong><small>数据库不存在时创建数据库，表不存在时根据上游字段创建表。</small></span></div> : null}
            {["aggregate_rules", "validation_rules", "condition_rules", "case_rules", "value_map", "event_id_selector", "option_selector"].includes(field.field_type) ? <div className="form-field">
              <span>{field.label}{field.required ? <b>*</b> : null}</span>{renderField(field)}{field.help_text ? <small>{field.help_text}</small> : null}
            </div> : <label className="form-field">
              <span>{field.label}{field.required ? <b>*</b> : null}</span>{renderField(field)}{field.help_text ? <small>{field.help_text}</small> : null}
            </label>}
          </Fragment>
        ))}
      </div>
      {plugin.id === "transform.mask" ? <div className="example-box"><span>示例</span><strong>{MASK_SAMPLE} <i>→</i> {maskSample(MASK_SAMPLE, valueFor({ key: "keep_start", default: 3 }), valueFor({ key: "keep_end", default: 4 }), valueFor({ key: "mask_char", default: "*" }))}</strong></div> : null}
      <div className="preview-toggle"><div><strong>实时预览</strong><span>参数变化后自动刷新样本</span></div><button className={`switch ${livePreview ? "is-on" : ""}`} onClick={() => onLivePreviewChange(!livePreview)}><span /></button></div>
      <section className="node-info">
        <h3>节点信息</h3>
        <dl>
          <div><dt>输出表名</dt><dd>{node.id.replaceAll("-", "_")}</dd></div>
          <div><dt>预计输出</dt><dd>123,876 行</dd></div>
          <div><dt>耗时</dt><dd>0.42 秒</dd></div>
          <div><dt>状态</dt><dd className="success-text"><i />运行成功</dd></div>
        </dl>
      </section>
      <div className="inspector__footer"><button className="danger-link" onClick={onDelete}><Trash size={16} />删除模块</button></div>
    </aside>
  );
}
