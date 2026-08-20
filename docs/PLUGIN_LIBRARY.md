# 插件库与扩展模块

数据工坊的输入、处理和输出能力都由插件提供。插件库是左侧“模块库”背后的能力目录：应用启动时读取所有内置插件和外部插件的元数据，再自动生成模块条目、分类、节点外观和配置表单。

- 想使用现有能力：阅读本文的“插件库结构”和“安装外部插件”。
- 想开发自己的节点：继续阅读[插件开发指南](PLUGIN_DEVELOPMENT.md)。
- 想了解执行引擎：阅读[架构设计](ARCHITECTURE.md)。

## 插件库结构

插件按数据流角色分为三种类型：

| 类型 | 作用 | 典型模块 |
| --- | --- | --- |
| 数据输入 | 从文件、数据库或流量包产生表格 | Excel/CSV、LOG、EVTX、MySQL、PCAP |
| 数据处理 | 接收一个或多个上游表格并返回新表格 | 过滤、分列、聚合、编码解码、协议提取 |
| 数据输出 | 在正式运行时写入完整结果 | Excel/CSV、JSONL、SQLite、MySQL |

模块库中的“常用处理”“文本与编码”“CTF 流量”“安全检测”等是展示分类，不改变插件的执行规则。输入、处理、输出统一通过 `polars.DataFrame` 交换数据，因此可以自由组合。

## 内置插件与外部插件

### 内置插件

内置插件随程序发布，源码位于：

```text
backend/dataworkbench/plugins/builtin/
├─ inputs.py       # 文件、数据库和流量输入
├─ transforms.py   # 通用数据处理
├─ ctf.py          # CTF、协议与安全分析
└─ outputs.py      # 文件和数据库输出
```

内置插件适合通用、稳定、需要随主程序测试和发布的能力。

### 外部插件

外部插件不需要修改核心代码，默认放在：

```text
plugins_external/<插件目录>/plugin.py
```

源码运行时扫描仓库根目录的 `plugins_external`；EXE 运行时扫描 `数据工坊.exe` 同目录下的 `plugins_external`。应用需要重启后才会重新发现插件。

外部插件适合：

- 比赛专用编码或 Flag 规则；
- 企业内部日志解析器；
- 临时数据库、接口或文件格式；
- 尚未准备合并到主仓库的实验模块。

## 安装外部插件

1. 确认插件来自可信来源。插件是本地 Python 代码，拥有与数据工坊相同的文件和网络权限。
2. 解压后保持“一层插件目录 + `plugin.py`”结构。
3. 将整个插件目录复制到 `plugins_external`。
4. 如插件声明额外 Python 依赖，在数据工坊使用的 Python 环境中安装依赖；便携 EXE 默认不能动态补装未打包的二进制依赖。
5. 完全退出并重新打开数据工坊。
6. 在左侧模块库中搜索插件名称；外部示例默认显示在“扩展模块”。

例如：

```text
数据工坊/
├─ 数据工坊.exe
├─ _internal/
└─ plugins_external/
   └─ example_uppercase/
      └─ plugin.py
```

也可以通过环境变量添加一个或多个插件根目录：

```powershell
$env:DATAWORKBENCH_PLUGIN_PATH = 'D:\my-plugins;E:\team-plugins'
python app.py
```

每个根目录仍须使用 `<插件目录>/plugin.py` 结构。Windows 使用分号分隔多个目录。

## 自定义插件的最短路径

仓库已经提供可直接复制的示例：

```text
plugins_external/example_uppercase/plugin.py
```

开发一个处理插件通常只需五步：

1. 新建 `plugins_external/my_plugin/plugin.py`；
2. 继承 `DataPlugin`；
3. 用 `PluginDefinition` 声明名称、分类和配置项；
4. 在 `execute()` 中接收并返回 `polars.DataFrame`；
5. 在文件末尾导出 `PLUGINS = [MyPlugin]`，重启应用。

最小模板：

```python
from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


class MyPlugin(DataPlugin):
    definition = PluginDefinition(
        id="my_team.my_plugin",
        name="我的处理模块",
        kind=PluginKind.TRANSFORM,
        group="扩展模块",
        category="文本与编码",
        description="说明这个模块会对数据做什么",
        icon="puzzle-piece",
        color="#6366f1",
        config_fields=(
            ConfigField("column", "选择字段", "column", required=True),
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
        return frame.with_columns(pl.col(column).cast(pl.String).str.strip_chars())


PLUGINS = [MyPlugin]
```

配置中的 `column` 类型会自动读取上游字段，普通用户不需要手写列名。更多表单类型、多输入插件、输入/输出插件、预览安全和测试方式见[插件开发指南](PLUGIN_DEVELOPMENT.md)。

## 插件选择建议

- 能用现有模块组合完成时，优先组合，不要重复开发插件。
- 通用清洗使用 Polars 表达式，避免逐行 Python 循环。
- 读取大型文件时不要为了预览而永久截断正式数据。
- 输出插件在 `context.preview` 为 `True` 时禁止写文件、建表或调用有副作用的接口。
- 插件 ID 一经用于项目文件就应保持稳定，显示名称可以调整。
- 密码、Token 和比赛私有数据不得硬编码到插件源码。

## 故障排查

### 模块库里看不到插件

依次检查：

1. 是否已经完全重启应用；
2. 路径是否严格为 `plugins_external/<名称>/plugin.py`；
3. 文件末尾是否存在 `PLUGINS = [插件类]`；
4. `PLUGINS` 中放的是类而不是 `MyPlugin()` 实例；
5. 插件 ID 是否与现有插件重复；
6. 导入的第三方依赖是否已安装。

### 插件可以显示但运行失败

- 检查必填配置和上游连线；
- 用空表、空值、中文字段名和非字符串类型测试；
- 确认返回值始终是 `polars.DataFrame`；
- 确认表达式引用的字段真实存在；
- 先在源码开发模式运行测试，再打包到 EXE。

### EXE 中可用、换一台机器后失败

纯 Python 单文件插件通常可以直接复制。需要 DLL、系统驱动或额外 Python 包的插件必须把依赖纳入正式打包流程，并在插件 README 中说明操作系统、架构和许可证要求。

## 发布插件时建议包含

```text
my_plugin/
├─ plugin.py
├─ README.md          # 用途、配置、依赖、示例和许可证
└─ tests/             # 可选；推荐提供自动化测试
```

发布前请完成[插件开发指南中的兼容性清单](PLUGIN_DEVELOPMENT.md#发布兼容性清单)。
