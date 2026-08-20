import assert from "node:assert/strict";
import test from "node:test";
import { connectionFromNodeDrop } from "../src/lib/connections.js";

test("dropping a source connection on a node body creates a forward edge", () => {
  assert.deepEqual(connectionFromNodeDrop({ nodeId: "source", handleType: "source" }, "target"), {
    source: "source",
    target: "target",
  });
});

test("dragging from a target handle reverses the inferred edge direction", () => {
  assert.deepEqual(connectionFromNodeDrop({ nodeId: "target", handleType: "target" }, "source"), {
    source: "source",
    target: "target",
  });
});

test("node-body drop preserves a named branch output handle", () => {
  assert.deepEqual(connectionFromNodeDrop({ nodeId: "branch", handleType: "source", handleId: "matched" }, "output"), {
    source: "branch",
    target: "output",
    sourceHandle: "matched",
  });
});

test("node-body connection ignores missing targets and self connections", () => {
  assert.equal(connectionFromNodeDrop({ nodeId: "node", handleType: "source" }, "node"), null);
  assert.equal(connectionFromNodeDrop({ nodeId: "node", handleType: "source" }, ""), null);
});
