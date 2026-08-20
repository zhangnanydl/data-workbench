import assert from "node:assert/strict";
import test from "node:test";
import { formatHexDump } from "../src/lib/payload.js";

test("formats payload bytes as aligned hex and printable ASCII", () => {
  const dump = formatHexDump("666c61677b746573747d00ff");
  assert.match(dump, /^00000000/);
  assert.match(dump, /66 6c 61 67/);
  assert.match(dump, /\|flag\{test\}\.\.\|$/);
});

test("ignores separators and wraps at the requested width", () => {
  const dump = formatHexDump("41:42 43-44", 2);
  assert.deepEqual(dump.split("\n").map((line) => line.slice(-4)), ["|AB|", "|CD|"]);
});
