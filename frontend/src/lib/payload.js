export function formatHexDump(hexValue, width = 16) {
  const clean = String(hexValue || "").replace(/[^0-9a-f]/gi, "");
  const bytes = clean.match(/.{1,2}/g) || [];
  const lines = [];
  for (let offset = 0; offset < bytes.length; offset += width) {
    const chunk = bytes.slice(offset, offset + width);
    const left = chunk.join(" ").padEnd(width * 3 - 1, " ");
    const ascii = chunk.map((item) => {
      const code = Number.parseInt(item, 16);
      return code >= 32 && code <= 126 ? String.fromCharCode(code) : ".";
    }).join("");
    lines.push(`${offset.toString(16).padStart(8, "0")}  ${left}  |${ascii}|`);
  }
  return lines.join("\n");
}
