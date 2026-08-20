export function pluginNeedsUpstreamFields(plugin) {
  return Boolean(plugin?.config_fields?.some((field) => ["column", "columns"].includes(field.field_type)));
}

export function upstreamSchemaKey(pipeline, targetNodeId) {
  const incoming = pipeline.edges.filter((edge) => edge.target === targetNodeId).map((edge) => edge.source).sort();
  const parents = new Map();
  for (const edge of pipeline.edges) {
    if (!parents.has(edge.target)) parents.set(edge.target, []);
    parents.get(edge.target).push(edge.source);
  }
  const required = new Set(incoming);
  const stack = [...incoming];
  while (stack.length) {
    const current = stack.pop();
    for (const parent of parents.get(current) || []) {
      if (!required.has(parent)) {
        required.add(parent);
        stack.push(parent);
      }
    }
  }
  const nodes = pipeline.nodes
    .filter((node) => required.has(node.id))
    .map(({ id, pluginId, config }) => ({ id, pluginId, config }))
    .sort((left, right) => left.id.localeCompare(right.id));
  const edges = pipeline.edges
    .filter((edge) => required.has(edge.source) && required.has(edge.target))
    .map(({ source, target }) => ({ source, target }))
    .sort((left, right) => `${left.source}:${left.target}`.localeCompare(`${right.source}:${right.target}`));
  return JSON.stringify({ targetNodeId, nodes, edges });
}
