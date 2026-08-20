import assert from "node:assert/strict";
import test from "node:test";
import { layoutPipelineNodes } from "../src/lib/layout.js";

const node = (id) => ({ id, position: { x: 0, y: 0 } });

test("sequential pipeline nodes keep generous horizontal spacing", () => {
  const result = layoutPipelineNodes(
    [node("a"), node("b"), node("c")],
    [{ source: "a", target: "b" }, { source: "b", target: "c" }],
  );
  assert.ok(result[1].position.x - result[0].position.x >= 200);
  assert.ok(result[2].position.x - result[1].position.x >= 200);
});

test("branch nodes are separated vertically within the same layer", () => {
  const result = layoutPipelineNodes(
    [node("source"), node("left"), node("right")],
    [{ source: "source", target: "left" }, { source: "source", target: "right" }],
  );
  assert.equal(result[1].position.x, result[2].position.x);
  assert.ok(Math.abs(result[1].position.y - result[2].position.y) >= 150);
});
