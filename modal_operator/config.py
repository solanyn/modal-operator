"""
Compatibility shim for Modal library import bug.

The Modal library incorrectly imports modal_operator.config instead of modal.config.
This module provides a proxy that redirects to modal.config while breaking circular imports.
"""

# Track import state to break circular dependencies
_config_cache = {}


class _ConfigProxy:
    """Proxy object that forwards attribute access to modal.config.config."""

    def __getattr__(self, name):
        return self.__getitem__(name)

    def __getitem__(self, key):
        # During initial import, return safe defaults
        if not _config_cache:
            safe_defaults = {"loglevel": "WARNING", "log_format": "%(message)s"}
            return safe_defaults.get(key, "")

        # After initial import, forward to real config
        import modal.config

        return modal.config.config[key]

    def __setitem__(self, key, value):
        import modal.config

        modal.config.config[key] = value

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, Exception):
            return default


# Create singleton config proxy
config = _ConfigProxy()

# Mark that we've been imported to break circular import
_config_cache["initialized"] = True


def __getattr__(name):
    """Lazy import other modal.config attributes."""
    # For first import during Modal's initialization, return safe defaults
    if not _config_cache.get("modal_loaded"):
        if name == "logger":
            import logging

            return logging.getLogger("modal")
        return None

    # After Modal is loaded, import the real attribute
    import modal.config

    _config_cache["modal_loaded"] = True
    return getattr(modal.config, name)
