import { CheckCircle, Database, SpinnerGap, WarningCircle } from "@phosphor-icons/react";

const count = (value) => value == null ? "待评估" : Number(value).toLocaleString();
const bytes = (value = 0) => {
  if (!value) return "未知大小";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Number(value), index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`;
};

export function RunProgress({ progress }) {
  if (!progress) return null;
  const percent = Math.min(100, Math.max(0, Number(progress.percent) || 0));
  const success = progress.status === "success";
  const failed = progress.status === "error";
  return <aside className={`run-progress ${success ? "is-success" : failed ? "is-error" : "is-running"}`} aria-live="polite">
    <header>
      <span>{success ? <CheckCircle weight="fill" size={17} /> : failed ? <WarningCircle size={17} /> : <SpinnerGap className="is-spinning" size={17} />}</span>
      <div><strong>{success ? "全量运行完成" : failed ? "全量运行失败" : progress.currentNode || "正在评估数据量"}</strong><small>{progress.strategy || "后台全量运行"}</small></div>
      <b>{percent.toFixed(percent % 1 ? 1 : 0)}%</b>
    </header>
    <div className="run-progress__track"><i style={{ width: `${percent}%` }} /></div>
    <div className="run-progress__metrics">
      <span><small>数据规模</small><strong>{count(progress.estimatedRows || progress.sourceRows)} 行 · {bytes(progress.estimatedBytes)}</strong></span>
      <span><small>处理进度</small><strong>{count(progress.processedRows)} 条</strong></span>
      <span><small>当前输出</small><strong>{count(progress.finalRows ?? progress.outputRows)} 行</strong></span>
      <span><small>节点</small><strong>{progress.nodeIndex || 0}/{progress.nodeCount || 0}</strong></span>
      <span><small>耗时</small><strong>{Number(progress.elapsedSeconds || 0).toFixed(1)} 秒</strong></span>
    </div>
    <footer><Database size={13} /><span>{success ? "完整性已确认：全部节点完成，导出包含完整结果" : failed ? progress.error || progress.message : "正式运行使用完整数据；快速预览样本不会进入导出"}</span></footer>
  </aside>;
}
