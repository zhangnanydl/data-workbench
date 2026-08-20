import assert from "node:assert/strict";
import test from "node:test";
import { pluginNeedsUpstreamFields, upstreamSchemaKey } from "../src/lib/preview.js";

const pipeline = {
  nodes: [
    { id: "source", pluginId: "input.mysql", config: { table: "users" } },
    { id: "filter", pluginId: "transform.filter", config: { value: "200" } },
  ],
  edges: [{ source: "source", target: "filter" }],
};

test("changing only the selected transform config does not invalidate upstream schema", () => {
  const first = upstreamSchemaKey(pipeline, "filter");
  const changed = structuredClone(pipeline);
  changed.nodes[1].config.value = "404";
  assert.equal(upstreamSchemaKey(changed, "filter"), first);
});

test("changing an upstream source invalidates its cached schema", () => {
  const changed = structuredClone(pipeline);
  changed.nodes[0].config.table = "orders";
  assert.notEqual(upstreamSchemaKey(changed, "filter"), upstreamSchemaKey(pipeline, "filter"));
});

test("upstream columns are requested only for field-aware modules", () => {
  assert.equal(pluginNeedsUpstreamFields({ config_fields: [{ field_type: "columns" }] }), true);
  assert.equal(pluginNeedsUpstreamFields({ config_fields: [{ field_type: "text" }] }), false);
});
