import { useMemo, useState } from "react";
import { CaretDown, DotsSixVertical, MagnifyingGlass } from "@phosphor-icons/react";
import { Icon } from "./Icon.jsx";

const groupOrder = ["数据输入", "数据处理", "数据输出", "扩展模块"];
const categoryOrder = ["常用处理", "文本与编码", "CTF 流量", "安全检测"];
const defaultExpandedCategories = new Set(["常用处理"]);
const categoryAliases = {
  "筛选与字段": "常用处理", "字段转换": "常用处理", "聚合与结构": "常用处理",
  "文本处理": "文本与编码", "加密与编码": "文本与编码", "CTF 编码解码": "文本与编码", "CTF 密码爆破": "文本与编码",
  "CTF 流量分析": "CTF 流量", "CTF 协议提取": "CTF 流量",
  "安全与隐私": "安全检测", "CTF 检测": "安全检测", "其他": "常用处理",
};
const displayCategory = (plugin) => categoryAliases[plugin.category || "其他"] || "常用处理";

export function ModuleLibrary({ plugins, onAdd }) {
  const [query, setQuery] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState(() => new Set());
  const [collapsedCategories, setCollapsedCategories] = useState(() => new Set(categoryOrder.filter((category) => !defaultExpandedCategories.has(category))));
  const grouped = useMemo(() => {
    const result = new Map(groupOrder.map((name) => [name, []]));
    for (const plugin of plugins) {
      if (query && !`${plugin.name}${plugin.description}${plugin.category || ""}`.toLowerCase().includes(query.toLowerCase())) continue;
      if (!result.has(plugin.group)) result.set(plugin.group, []);
      result.get(plugin.group).push(plugin);
    }
    return [...result].filter(([, items]) => items.length);
  }, [plugins, query]);

  const startDrag = (event, plugin) => {
    event.dataTransfer.setData("application/data-workbench-plugin", plugin.id);
    event.dataTransfer.effectAllowed = "move";
  };

  const toggleSetValue = (setter, key) => setter((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });

  const renderItem = (plugin) => (
    <button
      className="module-item"
      key={plugin.id}
      draggable
      onDragStart={(event) => startDrag(event, plugin)}
      onClick={() => onAdd(plugin)}
      title={`${plugin.description}；点击或拖拽添加`}
    >
      <span className="module-item__icon" style={{ color: plugin.color }}><Icon name={plugin.icon} size={17} weight="duotone" /></span>
      <span>{plugin.name}</span>
      <DotsSixVertical size={16} className="module-item__grip" />
    </button>
  );

  return (
    <aside className="module-library">
      <div className="module-library__header">
        <div className="section-title-row"><h2>模块库</h2><span>{plugins.length}</span></div>
        <label className="search-box">
          <MagnifyingGlass size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索模块" />
        </label>
      </div>
      <div className="module-groups">
        {grouped.map(([group, items]) => (
          <section className="module-group" key={group}>
            <h3><button className={`module-group__toggle ${collapsedGroups.has(group) ? "is-collapsed" : ""}`} onClick={() => toggleSetValue(setCollapsedGroups, group)} aria-expanded={!collapsedGroups.has(group)}>
              <CaretDown size={13} weight="bold" /><span>{group}</span><small>{items.length}</small>
            </button></h3>
            {!collapsedGroups.has(group) || query ? group === "数据处理" ? (
              <div className="module-categories">
                {categoryOrder.map((category) => {
                  const categoryItems = items.filter((plugin) => displayCategory(plugin) === category);
                  if (!categoryItems.length) return null;
                  return <section className="module-category" key={category}>
                    <h4><button className={`module-category__toggle ${collapsedCategories.has(category) ? "is-collapsed" : ""}`} onClick={() => toggleSetValue(setCollapsedCategories, category)} aria-expanded={!collapsedCategories.has(category)}>
                      <CaretDown size={11} weight="bold" /><span>{category}</span><small>{categoryItems.length}</small>
                    </button></h4>
                    {!collapsedCategories.has(category) || query ? <div className="module-list">{categoryItems.map(renderItem)}</div> : null}
                  </section>;
                })}
              </div>
            ) : <div className="module-list">{items.map(renderItem)}</div> : null}
          </section>
        ))}
      </div>
    </aside>
  );
}
