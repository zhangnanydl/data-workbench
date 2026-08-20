import { memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { CaretDown, DotsSixVertical, MagnifyingGlass, X } from "@phosphor-icons/react";
import { Icon } from "./Icon.jsx";

const groupOrder = ["数据输入", "数据处理", "数据输出", "扩展模块"];
const categoryOrder = ["筛选与清洗", "字段与结构", "聚合与分析", "文本与编码", "安全与流量"];
const defaultExpandedCategories = new Set(["筛选与清洗"]);
const scopeOptions = [
  ["all", "全部", null], ["input", "输入", "数据输入"], ["transform", "处理", "数据处理"], ["output", "输出", "数据输出"],
];
const categoryAliases = {
  "筛选与字段": "筛选与清洗", "数据质量": "筛选与清洗", "流程控制": "筛选与清洗",
  "字段转换": "字段与结构", "字段计算": "字段与结构", "结构转换": "字段与结构", "日期时间": "字段与结构",
  "聚合与结构": "聚合与分析", "聚合统计": "聚合与分析", "多表处理": "聚合与分析",
  "文本处理": "文本与编码", "加密与编码": "文本与编码", "CTF 编码解码": "文本与编码", "CTF 密码爆破": "文本与编码",
  "安全与隐私": "安全与流量", "CTF 流量分析": "安全与流量", "CTF 协议提取": "安全与流量", "CTF 检测": "安全与流量",
};

const displayCategory = (plugin) => categoryAliases[plugin.category || ""] || "字段与结构";

const ModuleItem = memo(function ModuleItem({ plugin, onAdd }) {
  const startDrag = useCallback((event) => {
    event.dataTransfer.setData("application/data-workbench-plugin", plugin.id);
    event.dataTransfer.effectAllowed = "move";
  }, [plugin.id]);
  const addModule = useCallback(() => onAdd(plugin), [onAdd, plugin]);

  return (
    <button className="module-item" draggable onDragStart={startDrag} onClick={addModule} title="点击添加到画布，也可以直接拖拽">
      <span className="module-item__icon" style={{ "--module-color": plugin.color }}><Icon name={plugin.icon} size={16} weight="duotone" /></span>
      <span className="module-item__copy"><strong>{plugin.name}</strong><small>{plugin.description}</small></span>
      <DotsSixVertical size={15} className="module-item__grip" />
    </button>
  );
});

export function ModuleLibrary({ plugins, onAdd }) {
  const searchInput = useRef(null);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [scope, setScope] = useState("all");
  const [collapsedGroups, setCollapsedGroups] = useState(() => new Set());
  const [collapsedCategories, setCollapsedCategories] = useState(() => new Set(categoryOrder.filter((category) => !defaultExpandedCategories.has(category))));

  const indexedPlugins = useMemo(() => plugins.map((plugin) => ({
    plugin,
    searchText: `${plugin.name} ${plugin.description} ${plugin.category || ""} ${plugin.group}`.toLocaleLowerCase(),
  })), [plugins]);
  const groupCounts = useMemo(() => Object.fromEntries(groupOrder.map((group) => [group, plugins.filter((plugin) => plugin.group === group).length])), [plugins]);
  const normalizedQuery = deferredQuery.trim().toLocaleLowerCase();
  const selectedGroup = scopeOptions.find(([value]) => value === scope)?.[2] || null;

  const grouped = useMemo(() => {
    const result = new Map(groupOrder.map((name) => [name, []]));
    for (const { plugin, searchText } of indexedPlugins) {
      if (selectedGroup && plugin.group !== selectedGroup) continue;
      if (normalizedQuery && !searchText.includes(normalizedQuery)) continue;
      if (!result.has(plugin.group)) result.set(plugin.group, []);
      result.get(plugin.group).push(plugin);
    }
    return [...result].filter(([, items]) => items.length).map(([group, items]) => ({
      group,
      items,
      categories: categoryOrder.map((category) => ({ category, items: items.filter((plugin) => displayCategory(plugin) === category) })).filter((entry) => entry.items.length),
    }));
  }, [indexedPlugins, normalizedQuery, selectedGroup]);

  const visibleCount = useMemo(() => grouped.reduce((total, entry) => total + entry.items.length, 0), [grouped]);
  const toggleSetValue = useCallback((setter, key) => setter((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  }), []);
  const clearSearch = useCallback(() => setQuery(""), []);

  useEffect(() => {
    const focusSearch = (event) => {
      const tagName = event.target?.tagName;
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(tagName)) return;
      event.preventDefault();
      searchInput.current?.focus();
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  return (
    <aside className="module-library">
      <div className="module-library__header">
        <div className="section-title-row">
          <span><h2>模块库</h2><small>点击添加 · 拖拽编排</small></span>
          <b>{plugins.length}</b>
        </div>
        <label className={`search-box ${query !== deferredQuery ? "is-searching" : ""}`}>
          <MagnifyingGlass size={15} />
          <input ref={searchInput} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Escape" && clearSearch()} placeholder="搜索名称或功能" aria-label="搜索模块" />
          {query ? <button type="button" onClick={clearSearch} aria-label="清除搜索"><X size={13} weight="bold" /></button> : <kbd>/</kbd>}
        </label>
        <nav className="module-scopes" aria-label="模块类型筛选">
          {scopeOptions.map(([value, label, group]) => <button type="button" className={scope === value ? "is-active" : ""} onClick={() => setScope(value)} key={value}>{label}<small>{group ? groupCounts[group] || 0 : plugins.length}</small></button>)}
        </nav>
        {normalizedQuery ? <div className="module-search-meta"><span>找到 {visibleCount} 个模块</span><button type="button" onClick={clearSearch}>清除</button></div> : null}
      </div>
      <div className="module-groups">
        {grouped.map(({ group, items, categories }) => {
          const groupCollapsed = collapsedGroups.has(group) && !normalizedQuery;
          return <section className="module-group" key={group}>
            <h3><button className={`module-group__toggle ${groupCollapsed ? "is-collapsed" : ""}`} onClick={() => toggleSetValue(setCollapsedGroups, group)} aria-expanded={!groupCollapsed}>
              <CaretDown size={13} weight="bold" /><span>{group}</span><small>{items.length}</small>
            </button></h3>
            {!groupCollapsed ? group === "数据处理" ? (
              <div className="module-categories">
                {categories.map(({ category, items: categoryItems }) => {
                  const categoryCollapsed = collapsedCategories.has(category) && !normalizedQuery;
                  return <section className="module-category" key={category}>
                    <h4><button className={`module-category__toggle ${categoryCollapsed ? "is-collapsed" : ""}`} onClick={() => toggleSetValue(setCollapsedCategories, category)} aria-expanded={!categoryCollapsed}>
                      <CaretDown size={11} weight="bold" /><span>{category}</span><small>{categoryItems.length}</small>
                    </button></h4>
                    {!categoryCollapsed ? <div className="module-list">{categoryItems.map((plugin) => <ModuleItem plugin={plugin} onAdd={onAdd} key={plugin.id} />)}</div> : null}
                  </section>;
                })}
              </div>
            ) : <div className="module-list">{items.map((plugin) => <ModuleItem plugin={plugin} onAdd={onAdd} key={plugin.id} />)}</div> : null}
          </section>;
        })}
        {!grouped.length ? <div className="module-library__empty"><MagnifyingGlass size={22} /><strong>没有找到相关模块</strong><span>换个关键词，或切换模块类型</span><button type="button" onClick={() => { setQuery(""); setScope("all"); }}>查看全部模块</button></div> : null}
      </div>
    </aside>
  );
}
