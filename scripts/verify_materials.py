"""Validate the separately supplied publication materials package."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from biotracebench_analysis.publication.verification import main
if __name__ == "__main__":
    main()
