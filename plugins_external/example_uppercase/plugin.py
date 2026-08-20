from typing import Any

import polars as pl

from dataworkbench.models import ConfigField, ExecutionContext, PluginDefinition, PluginKind
from dataworkbench.plugins.base import DataPlugin


class UppercasePlugin(DataPlugin):
    """外部插件示例：把指定字段转换为大写。"""

    definition = PluginDefinition(
        id="external.uppercase",
        name="转为大写",
        kind=PluginKind.TRANSFORM,
        group="扩展模块",
        description="外部插件示例",
        icon="text-aa",
        color="#ec4899",
        config_fields=(ConfigField("field", "字段", "column", required=True),),
    )

    def execute(self, inputs: list[pl.DataFrame], config: dict[str, Any], context: ExecutionContext) -> pl.DataFrame:
        frame = self.require_input(inputs)
        return frame.with_columns(pl.col(config["field"]).cast(pl.String).str.to_uppercase())


PLUGINS = [UppercasePlugin]
