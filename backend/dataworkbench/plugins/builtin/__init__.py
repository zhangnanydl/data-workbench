from .inputs import INPUT_PLUGINS
from .outputs import OUTPUT_PLUGINS
from .transforms import TRANSFORM_PLUGINS
from .ctf import CTF_PLUGINS
from .analysis import ANALYSIS_PLUGINS

PLUGINS = [*INPUT_PLUGINS, *TRANSFORM_PLUGINS, *ANALYSIS_PLUGINS, *CTF_PLUGINS, *OUTPUT_PLUGINS]

__all__ = ["PLUGINS"]
