# 插件开发指南

数据工坊使用元数据驱动的 Python 插件系统。插件定义了自己的名称、分类、配置项和执行函数；前端根据元数据自动生成模块库条目与配置面板。

## 最小插件

创建 `plugins_external/my_plugin/plugin.py`：

```python
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


class AddPrefixPlugin(DataPlugin):
    definition = PluginDefinition(
        id="example.add_prefix",
        name="添加前缀",
        kind=PluginKind.TRANSFORM,
        group="数据处理",
        category="文本处理",
        description="给指定字段的文本添加前缀",
        icon="text-t",
        color="#2563eb",
        config_fields=(
            ConfigField("column", "选择字段", "column", required=True),
            ConfigField("prefix", "前缀", default="CTF-"),
        ),
    )

    def execute(
        self,
        inputs: list[pl.DataFrame],
        config: dict[str, Any],
        context: ExecutionContext,
    ) -> pl.DataFrame:
        frame = self.require_input(inputs)
        column = str(config["column"])
        prefix = str(config.get("prefix", ""))
        return frame.with_columns(
            pl.concat_str([pl.lit(prefix), pl.col(column).cast(pl.String)]).alias(column)
        )


PLUGINS = [AddPrefixPlugin]
```

重启应用后，插件会出现在“数据处理 / 文本处理”分类中。

## 目录与发现规则

```text
plugins_external/
└─ my_plugin/
   ├─ plugin.py       # 必需
   └─ ...             # 可选资源或辅助模块
```

注册表只扫描直接子目录下的 `plugin.py`，并读取模块级 `PLUGINS` 列表。列表项必须是 `DataPlugin` 子类，而不是实例。

额外插件根目录可以通过 `DATAWORKBENCH_PLUGIN_PATH` 指定；Windows 下多个目录使用 `;` 分隔。EXE 便携版默认扫描 EXE 同目录的 `plugins_external`。

## PluginDefinition

| 字段 | 说明 |
| --- | --- |
| `id` | 全局唯一、稳定的机器 ID；推荐 `<组织>.<动作>` |
| `name` | 用户界面名称 |
| `kind` | `INPUT`、`TRANSFORM` 或 `OUTPUT` |
| `group` | 一级分组，一般为数据输入/数据处理/数据输出 |
| `category` | 模块库二级分类 |
| `description` | 一句话说明用途 |
| `icon` | 前端支持的图标键 |
| `color` | 节点主题色，十六进制颜色 |
| `config_fields` | 配置表单定义 |
| `accepts_multiple` | 是否允许连接多个上游，默认 `False` |

发布后不要随意修改插件 ID，否则现有项目将无法恢复对应节点。

## 配置字段

`ConfigField(key, label, field_type, ...)` 当前常用类型：

| `field_type` | 用途 |
| --- | --- |
| `text` | 单行文本，默认类型 |
| `textarea` | 多行文本/高级表达式 |
| `number` | 数值输入 |
| `boolean` | 开关 |
| `select` | 固定下拉选项，配合 `options` |
| `password` | 密码输入 |
| `file` / `save_file` | 原生打开/保存文件对话框 |
| `column` | 自动读取上游的单字段选择 |
| `columns` | 自动读取上游的多字段选择 |
| `mysql_database` | 根据连接参数发现 MySQL 数据库 |
| `mysql_table` | 根据所选数据库发现 MySQL 数据表 |

公共属性还包括：

- `default`：默认值；
- `required`：是否必填；
- `options`：`[{"label": "...", "value": "..."}]`；
- `placeholder`：输入提示；
- `help_text`：配置说明。

复杂的映射、聚合等场景已经有专用可视化编辑器。新增复杂字段类型前，请先评估是否能复用现有规则结构，并保持旧项目 JSON 兼容。

## 执行约定

### 输入插件

输入插件通常忽略 `inputs`，并返回一个 `polars.DataFrame`。文件路径和连接信息来自 `config`。

### 处理插件

单输入处理插件使用：

```python
frame = self.require_input(inputs)
```

多输入插件把 `accepts_multiple=True`，并自行校验 `len(inputs)`。不要就地修改上游结果；返回新的 DataFrame。

### 输出插件

输出插件必须区分预览与正式运行：

```python
frame = self.require_input(inputs)
if context.preview:
    return frame

# 只有正式运行才写文件或数据库
write_full_result(frame, config)
return frame
```

预览期间禁止创建文件、写数据库或产生其他外部副作用。文件导出建议先写同目录临时文件，成功后原子替换。

## ExecutionContext

稳定的公开字段：

- `preview`：`True` 表示样本/实时预览；
- `preview_limit`：前端请求的页大小；
- `project_dir`：当前项目运行目录；
- `variables`：一次执行内的扩展状态。

`variables` 中的内部键可能在 `1.0.0` 前调整。外部插件应尽量只使用公开字段；如确需进度、PCAP 索引等高级能力，请先提交 Issue 讨论稳定 API。

## 校验与错误

基类会根据 `required=True` 完成必填校验。插件可覆盖：

```python
def validate(self, config: dict[str, Any]) -> list[str]:
    errors = super().validate(config)
    if config.get("mode") == "advanced" and not config.get("pattern"):
        errors.append("高级模式需要填写表达式")
    return errors
```

运行错误请抛出 `ValueError` 或语义清晰的异常。错误消息会展示给用户，因此应说明具体配置项和修复方式，不要只写“执行失败”。

## 大数据注意事项

- 避免 `frame.to_dicts()`、逐行 Python 循环和不必要的 pandas 转换；优先使用 Polars 表达式。
- 输出插件不能把 `context.preview` 的表格当成正式结果。
- 输入插件如果主动提供“最多读取 N 行”配置，必须明确说明它会限制正式运行范围。
- 不要把大型二进制 Payload 复制成多个字符串列。
- 需要真正的全链路流式处理时，请先扩展核心执行协议，不要在插件内静默丢弃批次。

## 测试插件

推荐把测试加入 `backend/tests/`：

```python
import polars as pl

from dataworkbench.models import ExecutionContext
from plugins_external.my_plugin.plugin import AddPrefixPlugin


def test_add_prefix():
    frame = pl.DataFrame({"value": ["abc"]})
    result = AddPrefixPlugin().execute(
        [frame],
        {"column": "value", "prefix": "CTF-"},
        ExecutionContext(preview=True),
    )
    assert result["value"].to_list() == ["CTF-abc"]
```

执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

提交插件时还应验证：必填项、空输入、空表、空值、非 ASCII 文本、大数据路径，以及输出插件在预览阶段没有副作用。

## 发布兼容性清单

- 插件 ID 唯一且不会随名称调整而变化；
- 没有硬编码密码、绝对路径或比赛私有数据；
- 配置项有默认值、占位提示和可理解的错误消息；
- 预览无外部写入；
- 正式导出覆盖完整数据；
- 依赖在插件 README 中声明，且许可证兼容；
- 至少提供一个自动化测试和一个最小流程示例。
