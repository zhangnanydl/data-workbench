import { CheckCircle, Database, SpinnerGap, WarningCircle } from "@phosphor-icons/react";

const count = (value) => value == null ? "待评估" : Number(value).toLocaleString();
const bytes = (value = 0) => {
  if (!value) return "未知大小";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Number(value), index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`;
};

export function RunProgress({ progress, previewLoading = false, previewLabel = "" }) {
  if (!progress && !previewLoading) return null;
  const previewOnly = !progress && previewLoading;
  const current = progress || {};
  const percent = Math.min(100, Math.max(0, Number(current.percent) || 0));
  const indeterminate = previewOnly || ((current.status === "queued" || current.status === "running") && percent === 0);
  const success = current.status === "success";
  const failed = current.status === "error";
  const title = previewOnly ? `正在加载${previewLabel ? `“${previewLabel}”` : "节点"}数据` : success ? "全量运行完成" : failed ? "全量运行失败" : current.currentNode || "正在评估数据量";
  return <aside className={`run-progress ${previewOnly ? "is-preview" : ""} ${indeterminate ? "is-indeterminate" : ""} ${success ? "is-success" : failed ? "is-error" : "is-running"}`} aria-live="polite" aria-busy={!success && !failed}>
    <header>
      <span>{success ? <CheckCircle weight="fill" size={17} /> : failed ? <WarningCircle size={17} /> : <SpinnerGap className="is-spinning" size={17} />}</span>
      <div><strong>{title}</strong><small>{previewOnly ? "正在读取上游字段和数据，请稍候" : current.strategy || "后台全量运行"}</small></div>
      <b>{indeterminate ? "处理中" : `${percent.toFixed(percent % 1 ? 1 : 0)}%`}</b>
    </header>
    <div className="run-progress__track"><i style={indeterminate ? undefined : { width: `${percent}%` }} /></div>
    {!previewOnly ? <div className="run-progress__metrics">
      <span><small>数据规模</small><strong>{count(current.estimatedRows || current.sourceRows)} 行 · {bytes(current.estimatedBytes)}</strong></span>
      <span><small>处理进度</small><strong>{count(current.processedRows)} 条</strong></span>
      <span><small>当前输出</small><strong>{count(current.finalRows ?? current.outputRows)} 行</strong></span>
      <span><small>节点</small><strong>{current.nodeIndex || 0}/{current.nodeCount || 0}</strong></span>
      <span><small>耗时</small><strong>{Number(current.elapsedSeconds || 0).toFixed(1)} 秒</strong></span>
    </div> : null}
    <footer><Database size={13} /><span>{previewOnly ? "大数据源会分页或抽样预览；运行全部和导出仍覆盖完整数据" : success ? "完整性已确认：全部节点完成，导出包含完整结果" : failed ? current.error || current.message : "正式运行使用完整数据；快速预览样本不会进入导出"}</span></footer>
  </aside>;
}
