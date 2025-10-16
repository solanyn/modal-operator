"""Re-export Modal's app module to fix import bug."""

from modal.app import *  # noqa: F401, F403
