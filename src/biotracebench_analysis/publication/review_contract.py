"""Compatibility imports for the replay namespace."""
from ..replay.review_contract import *
from ..replay import review_contract as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
