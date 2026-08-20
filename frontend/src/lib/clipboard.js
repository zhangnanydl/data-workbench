function tsvCell(value) {
  const text = value == null ? "" : String(value);
  return /[\t\r\n"]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function previewRowsToTsv(columns, rows) {
  const header = columns.map((column) => tsvCell(column.label || column.key)).join("\t");
  const body = rows.map((row) => columns.map((column) => tsvCell(row[column.key])).join("\t"));
  return [header, ...body].join("\r\n");
}

export async function copyText(text) {
  const value = String(text ?? "");
  if (globalThis.navigator?.clipboard?.writeText) {
    try {
      await globalThis.navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Desktop WebView and non-secure development origins can deny Clipboard API access.
    }
  }
  if (!globalThis.document) return false;
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}
