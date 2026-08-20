import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { CheckCircle } from "@phosphor-icons/react";
import { Icon } from "./Icon.jsx";

export const PluginNode = memo(function PluginNode({ data, selected }) {
  const plugin = data.plugin;
  const isInput = plugin?.kind === "input";
  const isOutput = plugin?.kind === "output";
  return (
    <div className={`plugin-node ${selected ? "is-selected" : ""}`} style={{ "--node-color": plugin?.color || "#6d5dfc" }}>
      {isInput ? null : <Handle type="target" position={Position.Left} className="node-handle" />}
      <div className="plugin-node__top">
        <span className="plugin-node__icon"><Icon name={plugin?.icon} size={17} weight="duotone" /></span>
        <CheckCircle size={16} weight="fill" className="plugin-node__status" />
      </div>
      <strong>{data.label || plugin?.name || "未命名模块"}</strong>
      <span className="plugin-node__caption">{data.statusText || (isOutput ? "等待写入" : isInput ? "128,542 行" : "123,876 行")}</span>
      {isOutput ? null : <Handle type="source" position={Position.Right} className="node-handle" />}
    </div>
  );
});
