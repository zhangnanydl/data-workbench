from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from dataworkbench.models import ExecutionContext, PluginDefinition


class DataPlugin(ABC):
    definition: PluginDefinition

    @abstractmethod
    def execute(
        self,
        inputs: list[pl.DataFrame],
        config: dict[str, Any],
        context: ExecutionContext,
    ) -> pl.DataFrame:
        raise NotImplementedError

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for item in self.definition.config_fields:
            if item.required and config.get(item.key) in (None, "", []):
                errors.append(f"{item.label}不能为空")
        return errors

    def select_output(self, frame: pl.DataFrame, config: dict[str, Any], output_id: str | None) -> pl.DataFrame:
        """Return the frame exposed by one output port; ordinary plugins have one implicit output."""
        return frame

    @staticmethod
    def require_input(inputs: list[pl.DataFrame]) -> pl.DataFrame:
        if not inputs:
            raise ValueError("该模块需要上游数据")
        return inputs[0]
