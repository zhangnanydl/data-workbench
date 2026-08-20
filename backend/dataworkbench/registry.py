from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Iterable

from dataworkbench.plugins.base import DataPlugin


class PluginRegistry:
    def __init__(self, external_paths: Iterable[str | Path] | None = None) -> None:
        self._plugins: dict[str, DataPlugin] = {}
        from dataworkbench.plugins.builtin import PLUGINS

        for plugin in PLUGINS:
            self.register(plugin())

        paths = list(external_paths or [])
        env_paths = os.getenv("DATAWORKBENCH_PLUGIN_PATH", "")
        paths.extend(item for item in env_paths.split(os.pathsep) if item)
        for path in paths:
            self.discover(Path(path))

    def register(self, plugin: DataPlugin, *, replace: bool = False) -> None:
        plugin_id = plugin.definition.id
        if plugin_id in self._plugins and not replace:
            raise ValueError(f"插件 ID 已存在: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> DataPlugin:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"未找到插件: {plugin_id}") from exc

    def list_definitions(self) -> list[dict]:
        order = {"input": 0, "transform": 1, "output": 2}
        return [
            plugin.definition.to_dict()
            for plugin in sorted(
                self._plugins.values(),
                key=lambda item: (order[item.definition.kind.value], item.definition.group, item.definition.name),
            )
        ]

    def discover(self, directory: Path) -> None:
        if not directory.exists():
            return
        for plugin_file in directory.glob("*/plugin.py"):
            module = self._load_module(plugin_file)
            for plugin_type in getattr(module, "PLUGINS", []):
                self.register(plugin_type())

    @staticmethod
    def _load_module(path: Path) -> ModuleType:
        module_name = f"dataworkbench_external_{path.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载插件: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
