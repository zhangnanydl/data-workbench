# 参与贡献

感谢你帮助改进数据工坊。项目当前处于早期预览阶段，优先接受可复现的缺陷修复、数据完整性改进、安全格式支持、测试和文档完善。

参与社区讨论与协作时，请遵守 [行为准则](CODE_OF_CONDUCT.md)。安全漏洞不要提交公开 Issue，请按 [SECURITY.md](SECURITY.md) 报告。

## 提交 Issue

提交缺陷前请先搜索现有 Issue。缺陷报告至少包含：

- 数据工坊版本或提交哈希；
- Windows、Python、Node.js 和 MySQL（如适用）版本；
- 可以公开的最小复现数据，或生成测试数据的脚本；
- 节点和连接顺序、关键配置、预期结果与实际结果；
- 是否发生在实时预览、正式运行或导出阶段；
- 错误信息和脱敏后的日志。

请勿上传真实密码、令牌、个人数据、未脱敏流量包或受比赛规则限制的题目文件。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test,build]"

cd frontend
npm ci
cd ..
```

开发桌面版前先构建前端：

```powershell
cd frontend
npm run build
cd ..
python app.py
```

只调试界面：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 4173
```

## 分支与提交

- 从 `main` 创建短生命周期分支，例如 `fix/full-export-count` 或 `feat/zeek-input`。
- 一个 Pull Request 聚焦一个问题，避免混入无关格式化或重构。
- 提交消息推荐使用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`build:` 前缀。
- 不要提交 `.venv/`、`node_modules/`、`build/`、`dist/`、`projects/`、缓存、导出数据和数据库凭据。

## 代码约定

### Python

- 目标版本 Python 3.11+；
- 新的数据交换逻辑优先使用 Polars；
- 公共函数添加类型标注，错误消息面向最终用户；
- 输出插件在 `context.preview=True` 时不得写入外部系统；
- 新插件遵循 [插件开发指南](docs/PLUGIN_DEVELOPMENT.md)。

### React

- 保持插件 UI 元数据驱动，避免为单个普通插件硬编码完整配置页面；
- 把纯逻辑放入 `frontend/src/lib/` 并尽量保持可测试；
- 保持中文桌面工作台的紧凑布局、单行标签和键盘可访问性；
- 不要重新引入 minimap 或占用主画布的永久项目导航栏。

## 测试要求

提交前运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q

cd frontend
npm run build
npm run test:sites
```

涉及数据范围、分页或导出的变更，必须增加“预览较少但正式结果完整”的回归测试。涉及 UI 的变更，还要实际打开页面，确认无空白页、框架错误层或相关控制台错误，并验证目标交互。

## Pull Request 清单

- [ ] 变更范围清晰，并关联 Issue（如有）；
- [ ] 新增/修改行为有自动化测试；
- [ ] 后端测试、前端构建和前端测试通过；
- [ ] 文档、配置示例和 `CHANGELOG.md` 已按需更新；
- [ ] 没有提交密钥、用户数据、缓存和构建产物；
- [ ] 预览没有意外副作用，正式运行/导出覆盖完整数据；
- [ ] 新依赖确有必要且许可证与 Apache-2.0 兼容。

提交贡献即表示你同意按本项目的 Apache License 2.0 授权该贡献。
