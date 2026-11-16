"""Explicit vendor profiles and immutable HTTP inference archives."""
from .backend import Backend
from .config import Profile, load_profile
from .contracts import ApiFailure, BackendDescription, BackendResponse

__all__=['Backend','Profile','load_profile','ApiFailure','BackendDescription','BackendResponse']

__version__ = "1.0.0"
INTERFACE_VERSION = "model-api-1"

def implementation_identity():
    """Hash the installed SDK, independently of a pipeline checkout."""
    from pathlib import Path
    from ._json import filehash
    root = Path(__file__).resolve().parent
    return {"package": "eab-model-api", "version": __version__,
            "interface": INTERFACE_VERSION,
            "files": {p.name: filehash(p) for p in sorted(root.glob("*.py"))}}
