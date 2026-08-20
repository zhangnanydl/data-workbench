# 数据工坊 Logo 设计说明

## 设计概念

三组数据模块通过蓝、青、紫三条数据流汇聚，形成抽象的字母 D 和向右输出箭头，表达“多源输入、模块化处理、统一输出”。蓝紫色沿用产品当前的主色体系，透明背景适用于工具栏、网页页签与 Windows 图标。

## 交付资产

- `assets/data-workbench-logo-source.png`：原始生成图
- `assets/data-workbench-icon.png`：256px 应用图标
- `assets/data-workbench.ico`：Windows 多尺寸图标（16/24/32/48/64/128/256px）
- `frontend/src/assets/data-workbench-logo.png`：前端工具栏 Logo
- `frontend/public/favicon.png`：网页页签图标

## 生成方式

使用内置 ImageGen 生成，类型为 `logo-brand`。最终提示词要求：为模块化数据处理工具“数据工坊”设计透明背景图标；三个相连的数据块汇聚成中心数据流或漏斗，形成简洁 D 形与输出方向；采用钴蓝、紫色和少量青色；需在 16px、32px、256px 下清晰；不使用文字、数据库圆柱、齿轮、水印或背景方块。
