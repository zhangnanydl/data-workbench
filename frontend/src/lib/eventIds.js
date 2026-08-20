export function normalizeEventIds(value) {
  const items = Array.isArray(value) ? value : String(value || "").split(/[,，;；\s]+/);
  return [...new Set(items.map((item) => String(item).trim()).filter(Boolean))];
}

export function combineEventIds(commonIds, customText) {
  return [...new Set([...normalizeEventIds(commonIds), ...normalizeEventIds(customText)])];
}
