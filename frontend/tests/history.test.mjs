import assert from "node:assert/strict";
import test from "node:test";
import { appendCanvasHistory, createCanvasSnapshot } from "../src/lib/history.js";

test("canvas snapshots preserve the state before later config and position changes", () => {
  const nodes = [{ id: "a", position: { x: 10, y: 20 }, data: { config: { fields: ["IP"] } } }];
  const snapshot = createCanvasSnapshot(nodes, [], "a");
  nodes[0].position.x = 999;
  nodes[0].data.config.fields.push("端口");
  assert.deepEqual(snapshot.nodes[0].position, { x: 10, y: 20 });
  assert.deepEqual(snapshot.nodes[0].data.config.fields, ["IP"]);
});

test("history ignores duplicate snapshots and keeps its configured limit", () => {
  let history = [];
  for (let index = 0; index < 5; index += 1) {
    history = appendCanvasHistory(history, createCanvasSnapshot([{ id: "a", position: { x: index, y: 0 }, data: { config: {} } }], []), 3);
  }
  history = appendCanvasHistory(history, createCanvasSnapshot([{ id: "a", position: { x: 4, y: 0 }, data: { config: {} } }], []), 3);
  assert.equal(history.length, 3);
  assert.deepEqual(history.map((item) => item.nodes[0].position.x), [2, 3, 4]);
});
