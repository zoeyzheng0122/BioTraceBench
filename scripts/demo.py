"""Run a synthetic scoring demonstration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from biotracebench_analysis.replay.demo import main
if __name__=='__main__':main()
