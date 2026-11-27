"""Compatibility imports for the replay namespace."""
from ..replay.demo import *
from ..replay import demo as _implementation

def __getattr__(name):
    return getattr(_implementation, name)

if __name__ == "__main__":
    _implementation.main()
