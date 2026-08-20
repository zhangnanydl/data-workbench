export function normalizeValueMap(value) {
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value || "{}");
    } catch {
      return [];
    }
  }
  if (Array.isArray(parsed)) {
    return parsed
      .filter((rule) => rule && typeof rule === "object")
      .map((rule) => ({ source_value: String(rule.source_value ?? ""), target_value: String(rule.target_value ?? "") }));
  }
  if (parsed && typeof parsed === "object") {
    return Object.entries(parsed).map(([source_value, target_value]) => ({ source_value, target_value: String(target_value ?? "") }));
  }
  return [];
}

export function valueMapToObject(value) {
  return Object.fromEntries(normalizeValueMap(value).filter((rule) => rule.source_value !== "").map((rule) => [rule.source_value, rule.target_value]));
}
