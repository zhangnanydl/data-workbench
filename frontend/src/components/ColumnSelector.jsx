import { useMemo, useState } from "react";
import { CaretDown, Check, Columns, MagnifyingGlass } from "@phosphor-icons/react";

function normalize(value) {
  if (Array.isArray(value)) return value;
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

export function ColumnSelector({ columns, value, onChange, compact = false }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = normalize(value);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filtered = columns.filter((column) => column.label.toLowerCase().includes(query.toLowerCase()));

  const toggle = (key) => {
    const next = selectedSet.has(key) ? selected.filter((item) => item !== key) : [...selected, key];
    onChange(next);
  };

  return (
    <div className={`column-selector ${compact ? "is-compact" : ""}`}>
      <button type="button" className="column-selector__trigger" onClick={() => setOpen((current) => !current)}>
        <Columns size={15} />
        <span>{selected.length ? `已选择 ${selected.length} 列` : columns.length ? "请选择字段" : "等待上游字段"}</span>
        <CaretDown size={13} />
      </button>
      {open ? (
        <div className="column-selector__menu">
          <label><MagnifyingGlass size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索字段" /></label>
          <div className="column-selector__actions"><button type="button" onClick={() => onChange(columns.map((column) => column.key))}>全选</button><button type="button" onClick={() => onChange([])}>清空</button></div>
          <div className="column-selector__list">
            {filtered.map((column) => (
              <button type="button" key={column.key} className={selectedSet.has(column.key) ? "is-selected" : ""} onClick={() => toggle(column.key)}>
                <i>{selectedSet.has(column.key) ? <Check size={12} weight="bold" /> : null}</i>
                <span>{column.label}</span>
                <small>{column.type}</small>
              </button>
            ))}
            {!filtered.length ? <div className="column-selector__empty">{columns.length ? "没有匹配的字段" : "请先连接并配置上游数据源"}</div> : null}
          </div>
          <button type="button" className="column-selector__done" onClick={() => setOpen(false)}>完成</button>
        </div>
      ) : null}
    </div>
  );
}
