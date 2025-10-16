"""
Compatibility shim for Modal library import bug.

The Modal library (v1.1.4) incorrectly imports from modal_operator._utils
instead of modal._utils. This package re-exports Modal's internal utilities
to work around this bug until it's fixed upstream.
"""

import importlib


def __getattr__(name: str):
    """Dynamically import submodules from modal._utils."""
    # Import the corresponding modal._utils submodule
    try:
        modal_submodule = importlib.import_module(f"modal._utils.{name}")
        # Cache it for future access
        globals()[name] = modal_submodule
        return modal_submodule
    except ImportError:
        # If it's not a submodule, try getting it as an attribute
        from modal import _utils as modal_utils

        if hasattr(modal_utils, name):
            attr = getattr(modal_utils, name)
            globals()[name] = attr
            return attr

    raise AttributeError(f"module 'modal_operator._utils' has no attribute '{name}'")
