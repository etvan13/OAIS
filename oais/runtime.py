"""Compatibility import for older projects referring to runtime.py."""
try:
    from .meta_terminal import MetaTerminal, OAISRuntime
except ImportError:
    from meta_terminal import MetaTerminal, OAISRuntime
