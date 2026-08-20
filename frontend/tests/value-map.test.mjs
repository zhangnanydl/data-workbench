import assert from "node:assert/strict";
import test from "node:test";
import { normalizeValueMap, valueMapToObject } from "../src/lib/valueMap.js";

test("converts legacy JSON mappings into editable visual rules", () => {
  assert.deepEqual(normalizeValueMap('{"0":"失败","1":"成功"}'), [
    { source_value: "0", target_value: "失败" },
    { source_value: "1", target_value: "成功" },
  ]);
});

test("visual mapping rules ignore blank source values during execution", () => {
  assert.deepEqual(valueMapToObject([
    { source_value: "GET", target_value: "读取" },
    { source_value: "", target_value: "忽略" },
  ]), { GET: "读取" });
});
