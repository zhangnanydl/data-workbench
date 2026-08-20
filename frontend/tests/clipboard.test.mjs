import assert from "node:assert/strict";
import test from "node:test";
import { previewRowsToTsv } from "../src/lib/clipboard.js";

test("formats visible preview columns as Excel-compatible TSV", () => {
  const columns = [{ key: "name", label: "名称" }, { key: "payload", label: "内容" }];
  const rows = [{ name: "flag", payload: "a\tb" }, { name: "quoted", payload: 'say "hi"' }];
  assert.equal(previewRowsToTsv(columns, rows), '名称\t内容\r\nflag\t"a\tb"\r\nquoted\t"say ""hi"""');
});

test("copies null preview values as empty cells", () => {
  assert.equal(previewRowsToTsv([{ key: "value", label: "值" }], [{ value: null }]), "值\r\n");
});
