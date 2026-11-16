"""Standalone multi-provider conversation client; no benchmark dependency."""
from .client import Conversation, VERSION
from .adapters import Adapter
from .profiles import load as load_profile
from .archive import Stop

__version__ = "1.2.0"
__all__ = ["Conversation", "Adapter", "load_profile", "Stop", "VERSION"]
