import assert from "node:assert/strict";
import test from "node:test";
import { combineEventIds, normalizeEventIds } from "../src/lib/eventIds.js";

test("normalizes legacy EVTX event ID text and removes duplicates", () => {
  assert.deepEqual(normalizeEventIds("4624, 4625；4688 4624"), ["4624", "4625", "4688"]);
});

test("combines checked common events with custom event IDs", () => {
  assert.deepEqual(combineEventIds(["4624", "4625"], "1102, 7045"), ["4624", "4625", "1102", "7045"]);
});
