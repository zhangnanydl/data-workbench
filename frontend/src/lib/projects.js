function compactTimestamp(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

export function createPluginNode(plugin, position, now = Date.now()) {
  const config = Object.fromEntries((plugin.config_fields || []).map((field) => [field.key, field.default ?? ""]));
  return {
    id: `${plugin.id.replaceAll(".", "-")}-${now}`,
    type: "plugin",
    position,
    data: { pluginId: plugin.id, plugin, label: plugin.name, config },
  };
}

export function createAutomaticProject(node, now = Date.now()) {
  const name = `自动项目_${compactTimestamp(new Date(now))}`;
  return {
    id: `project-${now}`,
    name,
    meta: "刚刚自动创建",
    pipeline: {
      version: 1,
      name,
      nodes: [{ id: node.id, pluginId: node.data.pluginId, label: node.data.label, config: node.data.config, position: node.position }],
      edges: [],
    },
  };
}
