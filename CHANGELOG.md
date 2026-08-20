# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，并计划在稳定后遵循语义化版本。

## [Unreleased]

### 新增

- 画布底部增加预览加载与全量运行进度条，展示百分比、处理条数、当前输出、节点位置和耗时；
- README 增加工作台、全量运行截图、快速上手、进度指标说明和常见问题。

### 修复

- Windows PowerShell 5.1 使用系统 ANSI 代码页时导致应用目录和 EXE 中文名乱码；
- 不同高度节点自动布局后连接点未按中心对齐，导致末端连线弯折。

### 计划

- 全链路流式/外存执行；
- 更多安全取证输入格式和协议提取模块；
- 项目格式迁移器和更稳定的插件 SDK；
- 自动化 Windows Release 构建与安装包。

## [0.1.0] - 2026-08-20

### 新增

- React + @xyflow/react 可视化节点画布和 pywebview Windows 桌面外壳；
- 9 个数据输入、30 个数据处理和 5 个数据输出节点；
- Excel/CSV、TXT、LOG、JSON/JSONL、EVTX、SQLite、MySQL 和 PCAP 输入；
- PCAP 会话、TCP 重组、HTTP/DNS/ICMP、Hex/Base、XOR/凯撒和 Flag 扫描；
- 输入/处理结果双预览、分页、列选择和复制；
- 本地 JSON 与 MySQL 项目存储模式；
- 大数据规模评估、样本预览、正式运行进度和完整导出；
- 外部 Python 插件发现和示例插件。

### 修复

- 预览分页错误限制后续处理和导出范围；
- 数据脱敏保留后几位为 `0` 时重复内容；
- 小画布连线命中区域、自动布局间距和方向箭头；
- 空画布启动、新项目自动创建、撤销与清空画布；
- 上游字段未传播导致列选择无法勾选；
- 多次运行导致界面长时间未响应的问题。

[Unreleased]: https://github.com/zhangnanydl/data-workbench/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zhangnanydl/data-workbench/releases/tag/v0.1.0
