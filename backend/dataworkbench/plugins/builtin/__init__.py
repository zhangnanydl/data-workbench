from .inputs import INPUT_PLUGINS
from .outputs import OUTPUT_PLUGINS
from .transforms import TRANSFORM_PLUGINS
from .ctf import CTF_PLUGINS

PLUGINS = [*INPUT_PLUGINS, *TRANSFORM_PLUGINS, *CTF_PLUGINS, *OUTPUT_PLUGINS]

__all__ = ["PLUGINS"]
