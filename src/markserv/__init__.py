from importlib.metadata import version as _metadata_version

from .cli import main

__all__ = ["__version__", "main"]
__version__ = _metadata_version("markserv")
