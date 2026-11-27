"""Compatibility imports for the replay namespace."""
from ..replay.eligibility import *
from ..replay import eligibility as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
