import { useEffect, useState } from "react";
import { CheckCircle, Database, Desktop, FloppyDisk, SpinnerGap, WarningCircle, X } from "@phosphor-icons/react";
import { bridge } from "../lib/bridge.js";

const defaults = {
  mode: "local",
  mysql: { host: "127.0.0.1", port: 3306, username: "root", password: "", database: "dataworkbench", table: "projects", charset: "utf8mb4", timezone: "+08:00", ssl_mode: "disabled", connect_timeout: 5, read_timeout: 30, write_timeout: 30 },
};

export function StorageSettings({ open, onClose, pluginCount, onSaved }) {
  const [config, setConfig] = useState(defaults);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!open) return;
    setMessage(null);
    bridge.getStorageConfig().then((saved) => setConfig({ mode: saved?.mode || "local", mysql: { ...defaults.mysql, ...(saved?.mysql || {}) } }));
  }, [open]);

  if (!open) return null;
  const updateMysql = (key, value) => setConfig((current) => ({ ...current, mysql: { ...current.mysql, [key]: value } }));
  const runAction = async (action) => {
    setBusy(action);
    setMessage(null);
    try {
      const result = action === "test"
        ? await bridge.testStorageConnection(config)
        : action === "initialize"
          ? await bridge.initializeStorage(config)
          : await bridge.configureStorage(config);
      setMessage({ ok: result.ok, text: result.message || result.error });
      if (result.ok && result.config) setConfig(result.config);
      if (result.ok && (action === "save" || action === "initialize")) onSaved?.(result.config?.mode || config.mode);
    } catch (error) {
      setMessage({ ok: false, text: error?.message || String(error) });
    } finally {
      setBusy("");
    }
  };

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="simple-modal settings-modal storage-settings-modal">
      <header><div><span>项目与流程配置</span><h2>存储模式</h2></div><button onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
      <p>选择项目、节点配置和流程记录的保存位置。切换模式不会自动迁移已有项目。</p>
      <div className="storage-mode-selector">
        <button className={config.mode === "local" ? "is-active" : ""} onClick={() => setConfig((current) => ({ ...current, mode: "local" }))}><Desktop size={20} /><span><strong>本地模式</strong><small>保存在软件目录的 JSON 文件中</small></span></button>
        <button className={config.mode === "mysql" ? "is-active" : ""} onClick={() => setConfig((current) => ({ ...current, mode: "mysql" }))}><Database size={20} /><span><strong>数据库存储</strong><small>多台设备可连接同一个 MySQL 数据源</small></span></button>
      </div>
      {config.mode === "mysql" ? <div className="storage-database-form">
        <div className="storage-form-grid">
          <label><span>主机</span><input value={config.mysql.host} onChange={(event) => updateMysql("host", event.target.value)} /></label>
          <label><span>端口</span><input type="number" value={config.mysql.port} onChange={(event) => updateMysql("port", Number(event.target.value))} /></label>
          <label><span>用户名</span><input value={config.mysql.username} onChange={(event) => updateMysql("username", event.target.value)} /></label>
          <label><span>密码</span><input type="password" value={config.mysql.password} onChange={(event) => updateMysql("password", event.target.value)} /></label>
          <label><span>配置数据库</span><input value={config.mysql.database} onChange={(event) => updateMysql("database", event.target.value)} placeholder="不存在时自动创建" /></label>
          <label><span>项目配置表</span><input value={config.mysql.table} onChange={(event) => updateMysql("table", event.target.value)} placeholder="不存在时自动创建" /></label>
          <label><span>字符集</span><select value={config.mysql.charset} onChange={(event) => updateMysql("charset", event.target.value)}><option value="utf8mb4">utf8mb4</option><option value="utf8">utf8</option><option value="gbk">GBK</option></select></label>
          <label><span>SSL 模式</span><select value={config.mysql.ssl_mode} onChange={(event) => updateMysql("ssl_mode", event.target.value)}><option value="disabled">禁用 SSL</option><option value="preferred">优先 SSL</option><option value="required">必须 SSL</option></select></label>
          <label><span>连接时区</span><input value={config.mysql.timezone} onChange={(event) => updateMysql("timezone", event.target.value)} /></label>
          <label><span>连接超时（秒）</span><input type="number" min="1" value={config.mysql.connect_timeout} onChange={(event) => updateMysql("connect_timeout", Number(event.target.value))} /></label>
        </div>
        <div className="database-scope-note"><Database size={16} /><span><strong>初始化内容</strong><small>自动创建配置数据库、项目表、结构版本表和更新时间索引；重复初始化不会清空已有项目。</small></span></div>
      </div> : <div className="local-storage-note"><Desktop size={18} /><span><strong>本地项目目录</strong><small>projects/*.json，可直接备份和复制；无需数据库。</small></span></div>}
      {message ? <div className={`storage-message ${message.ok ? "is-ok" : "is-error"}`}>{message.ok ? <CheckCircle size={15} weight="fill" /> : <WarningCircle size={15} />}{message.text}</div> : null}
      <div className="settings-brief"><span>当前插件</span><strong>{pluginCount} 个</strong></div>
      <footer><button disabled={Boolean(busy)} onClick={() => runAction("test")}>{busy === "test" ? <SpinnerGap className="is-spinning" size={15} /> : <Database size={15} />}测试连接</button><button disabled={Boolean(busy) || (config.mode === "mysql" && (!config.mysql.host || !config.mysql.username || !config.mysql.database || !config.mysql.table))} onClick={() => runAction("initialize")}>{busy === "initialize" ? <SpinnerGap className="is-spinning" size={15} /> : <Database size={15} />}初始化存储</button><button className="primary" disabled={Boolean(busy) || (config.mode === "mysql" && (!config.mysql.host || !config.mysql.username || !config.mysql.database || !config.mysql.table))} onClick={() => runAction("save")}>{busy === "save" ? <SpinnerGap className="is-spinning" size={15} /> : <FloppyDisk size={15} />}保存配置</button></footer>
    </section>
  </div>;
}
