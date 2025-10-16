"""Re-export Modal's _runtime package to fix import bug."""

import importlib


def __getattr__(name):
    """Lazy-load submodules from modal._runtime."""
    # Import the corresponding modal._runtime submodule
    try:
        modal_submodule = importlib.import_module(f"modal._runtime.{name}")
        # Cache it for future access
        globals()[name] = modal_submodule
        return modal_submodule
    except ImportError:
        # If it's not a submodule, try getting it as an attribute
        from modal import _runtime as modal_runtime

        if hasattr(modal_runtime, name):
            attr = getattr(modal_runtime, name)
            globals()[name] = attr
            return attr

    raise AttributeError(f"module 'modal_operator._runtime' has no attribute '{name}'")
