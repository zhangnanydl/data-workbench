export function pluginNeedsUpstreamFields(plugin) {
  return Boolean(plugin?.config_fields?.some((field) => ["column", "columns", "validation_rules", "condition_rules", "case_rules"].includes(field.field_type)));
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
    .map(({ source, target, sourceHandle, targetHandle }) => ({ source, target, sourceHandle: sourceHandle || null, targetHandle: targetHandle || null }))
    .sort((left, right) => `${left.source}:${left.sourceHandle}:${left.target}:${left.targetHandle}`.localeCompare(`${right.source}:${right.sourceHandle}:${right.target}:${right.targetHandle}`));
  return JSON.stringify({ targetNodeId, nodes, edges });
}
