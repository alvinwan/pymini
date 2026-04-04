"""Public package interface for pymini."""

from importlib.metadata import PackageNotFoundError, version

from .pymini import minify

try:
    __version__ = version("pymini")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__", "minify"]
