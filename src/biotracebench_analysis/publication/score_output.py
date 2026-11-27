"""Compatibility imports for the replay namespace."""
from ..replay.score_output import *
from ..replay import score_output as _implementation

def __getattr__(name):
    return getattr(_implementation, name)

if __name__ == "__main__":
    _implementation.main()
