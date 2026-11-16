"""Prepare and run the paper's database-construction workflow."""
from pathlib import Path
import argparse,json,sys
ALLOWED=('prepare','preflight-matrix','draft','freeze','run','recover','export')
def main(argv=None):
 argv=list(sys.argv[1:]if argv is None else argv)
 if not argv or argv[0]in['-h','--help']:
  p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=ALLOWED);p.print_help();return 0
 if argv[0]not in ALLOWED:raise ValueError('Select a publication workflow command: '+', '.join(ALLOWED))
 for flag in['--template','--draft','--manifest']:
  if flag not in argv or '--help'in argv:continue
  d=json.loads(Path(argv[argv.index(flag)+1]).read_text())
  if d.get('scope')!='generation'or d.get('stages')!=['i0']:raise ValueError('The publication workflow requires a generation-scoped configuration')
 from .cli import main as execute
 return execute(argv)
if __name__=='__main__':raise SystemExit(main())
