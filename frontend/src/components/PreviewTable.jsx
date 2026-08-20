import { useEffect, useMemo, useState } from "react";
import { ArrowClockwise, Check, CheckCircle, Copy, Eye, WarningCircle, X } from "@phosphor-icons/react";
import { ColumnSelector } from "./ColumnSelector.jsx";
import { formatHexDump } from "../lib/payload.js";
import { copyText, previewRowsToTsv } from "../lib/clipboard.js";

export function PreviewTable({ preview, loading, error, onRefresh, page = 1, pageSize = 100, onPageChange, onPageSizeChange, pcapMode = null, onPcapModeChange, previewMode = "output", onPreviewModeChange }) {
  const columns = preview?.columns || [];
  const signature = columns.map((column) => column.key).join("|");
  const [visibleKeys, setVisibleKeys] = useState([]);
  useEffect(() => setVisibleKeys(columns.map((column) => column.key)), [signature]);
  const visibleColumns = useMemo(() => columns.filter((column) => visibleKeys.includes(column.key)), [columns, visibleKeys]);
  const rows = preview?.rows || [];
  const stats = preview?.stats || {};
  const rowCount = Number(stats.rowCount || 0);
  const estimatedRowCount = stats.estimatedRowCount == null ? null : Number(stats.estimatedRowCount);
  const pageCount = rowCount ? Math.ceil(rowCount / pageSize) : 0;
  const hasPreview = Boolean(preview);
  const [selectedRow, setSelectedRow] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  useEffect(() => setSelectedRow(null), [page, signature]);
  const hasPayload = columns.some((column) => ["PayloadHex", "PayloadASCII", "重组Hex", "重组ASCII"].includes(column.key));
  const rowPayload = (row) => row?.PayloadHex || row?.重组Hex || "";
  const rowAscii = (row) => row?.PayloadASCII || row?.重组ASCII || "";
  const copyValue = async (value, feedback = "已复制") => {
    const copied = await copyText(value);
    setCopyFeedback(copied ? feedback : "复制失败");
    globalThis.setTimeout(() => setCopyFeedback(""), 1600);
  };
  const copyPage = () => copyValue(previewRowsToTsv(visibleColumns, rows), `已复制当前 ${rows.length} 行`);
  return (
    <section className="preview-panel">
      <div className="preview-tabs">
        {pcapMode ? <><button className={pcapMode === "packets" ? "is-active" : ""} onClick={() => onPcapModeChange?.("packets")}>数据包</button><button className={pcapMode === "sessions" ? "is-active" : ""} onClick={() => onPcapModeChange?.("sessions")}>会话</button></> : <><button className={previewMode === "input" ? "is-active" : ""} onClick={() => onPreviewModeChange?.("input")}>输入数据</button><button className={previewMode === "output" ? "is-active" : ""} onClick={() => onPreviewModeChange?.("output")}>实时数据</button></>}
        <div className="preview-summary">
          {error ? <span className="preview-error"><WarningCircle size={15} />{error}</span> : hasPreview ? <><span>{stats.sampled ? "快速样本" : "实时预览"}</span><span>{stats.sampled ? `样本结果 ${rowCount.toLocaleString()} 行${estimatedRowCount != null ? ` · 预计全量 ${estimatedRowCount.toLocaleString()} 行` : ""}` : `完整结果 ${rowCount.toLocaleString()} 行`}</span><CheckCircle size={16} weight="fill" /></> : <span>等待选择节点</span>}
          <ColumnSelector compact columns={columns} value={visibleKeys} onChange={setVisibleKeys} />
          <button className="copy-page-button" onClick={copyPage} disabled={!rows.length} title="按当前显示列复制，可直接粘贴到 Excel"><Copy size={15} />复制当前页</button>
          <button className="refresh-button" onClick={onRefresh} disabled={loading || !hasPreview}><ArrowClockwise size={15} className={loading ? "is-spinning" : ""} />刷新</button>
        </div>
      </div>
      <div className="table-meta"><Eye size={13} />{stats.paged ? `第 ${page} 页，当前 ${rows.length} 行（${stats.sampled ? "快速样本，正式运行仍处理全量" : "基于完整数据处理"}）` : `显示 ${rows.length || 0} 行`} · 当前显示 {visibleColumns.length}/{columns.length} 列 · 点击单元格复制{hasPayload ? " · 点击行空白处查看 Payload" : ""}{copyFeedback ? <span className="copy-feedback"><Check size={12} />{copyFeedback}</span> : null}</div>
      <div className="table-scroll">
        <table>
          <thead><tr><th className="row-number">#</th>{visibleColumns.map((column) => <th key={column.key}><span>{column.label}</span><small>{column.type}</small></th>)}</tr></thead>
          <tbody>
            {rows.map((row, index) => <tr className={rowPayload(row) ? "payload-row" : ""} onClick={() => rowPayload(row) && setSelectedRow(row)} key={index}><td className="row-number">{stats.paged ? (page - 1) * pageSize + index + 1 : index + 1}</td>{visibleColumns.map((column) => <td className={`copyable-cell ${column.key.includes("手机") ? "is-changed" : ""}`} key={column.key} tabIndex={0} title={`${String(row[column.key] ?? "")}（点击复制）`} onClick={(event) => { event.stopPropagation(); copyValue(row[column.key], `已复制：${column.label}`); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); copyValue(row[column.key], `已复制：${column.label}`); } }}>{String(row[column.key] ?? "—")}</td>)}</tr>)}
            {!rows.length && !loading ? <tr><td className="empty-table" colSpan={visibleColumns.length + 1}>连接并选择一个节点后查看实时结果</td></tr> : null}
          </tbody>
        </table>
      </div>
      <footer className="table-footer"><span>{stats.sampled ? `样本共 ${rowCount.toLocaleString()} 行${estimatedRowCount != null ? `，预计全量 ${estimatedRowCount.toLocaleString()} 行` : ""}` : `共 ${rowCount.toLocaleString()} 行`}</span><div><button disabled={!stats.paged || page <= 1 || loading} onClick={() => onPageChange?.(page - 1)}>‹</button><span>{pageCount ? `${page} / ${pageCount.toLocaleString()}` : "0 / 0"}</span><button disabled={!stats.paged || page >= pageCount || loading} onClick={() => onPageChange?.(page + 1)}>›</button><select value={pageSize} disabled={!stats.paged || !hasPreview} onChange={(event) => onPageSizeChange?.(Number(event.target.value))}><option value="50">50 行/页</option><option value="100">100 行/页</option><option value="250">250 行/页</option><option value="500">500 行/页</option></select></div></footer>
      {selectedRow ? <div className="payload-backdrop" onClick={() => setSelectedRow(null)}><div className="payload-viewer" onClick={(event) => event.stopPropagation()}><header><div><strong>Payload 查看器</strong><span>{selectedRow.会话ID || "数据包载荷"} · {Number((rowPayload(selectedRow).length || 0) / 2).toLocaleString()} 字节</span></div><button onClick={() => setSelectedRow(null)}><X size={18} /></button></header><div className="payload-tabs"><span>Hex / ASCII</span><div><button onClick={() => copyValue(rowPayload(selectedRow), "已复制 Hex")}><Copy size={13} />复制 Hex</button><button onClick={() => copyValue(rowAscii(selectedRow), "已复制文本")}><Copy size={13} />复制文本</button></div></div><pre>{formatHexDump(rowPayload(selectedRow)) || rowAscii(selectedRow) || "空 Payload"}</pre><div className="payload-plain"><strong>纯文本</strong><pre>{rowAscii(selectedRow) || "—"}</pre></div></div></div> : null}
    </section>
  );
}
