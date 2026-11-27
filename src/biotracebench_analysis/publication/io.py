"""Compatibility imports for the replay namespace."""
from ..replay.io import *
from ..replay import io as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
