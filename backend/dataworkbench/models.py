from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class PluginKind(StrEnum):
    INPUT = "input"
    TRANSFORM = "transform"
    OUTPUT = "output"


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    field_type: str = "text"
    default: Any = None
    required: bool = False
    options: list[dict[str, Any]] = field(default_factory=list)
    placeholder: str = ""
    help_text: str = ""


@dataclass(frozen=True)
class PluginDefinition:
    id: str
    name: str
    kind: PluginKind
    group: str
    description: str
    icon: str
    color: str
    config_fields: tuple[ConfigField, ...] = ()
    accepts_multiple: bool = False
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass
class ExecutionContext:
    preview: bool = True
    preview_limit: int = 100
    project_dir: str = ""
    variables: dict[str, Any] = field(default_factory=dict)
