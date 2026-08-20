import assert from "node:assert/strict";
import test from "node:test";
import { createAutomaticProject, createPluginNode } from "../src/lib/projects.js";

test("dropping the first module can create a configured node and automatic project", () => {
  const plugin = { id: "input.csv", name: "Excel / CSV", config_fields: [{ key: "path", default: "" }, { key: "delimiter", default: "," }] };
  const now = new Date(2026, 7, 19, 9, 5, 7).getTime();
  const node = createPluginNode(plugin, { x: 120, y: 80 }, now);
  const project = createAutomaticProject(node, now);
  assert.equal(node.data.config.delimiter, ",");
  assert.equal(project.name, "自动项目_20260819_090507");
  assert.equal(project.pipeline.nodes[0].id, node.id);
});
