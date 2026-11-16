"""A fresh source archive is complete, code-only and byte-reproducible."""
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile,unittest,zipfile
ROOT=Path(__file__).resolve().parents[1]
class SourceDistributionTests(unittest.TestCase):
 def test_archive_is_reproducible_and_all_contents_verify(self):
  with tempfile.TemporaryDirectory()as t:
   reports=[]
   for name in['first','second']:
    raw=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/build_source.py'),'--out',str(Path(t)/name)],cwd=ROOT,text=True)
    reports.append(json.loads(raw))
   self.assertEqual(reports[0]['sha256'],reports[1]['sha256'])
   with zipfile.ZipFile(reports[0]['archive'])as archive:
    manifest=json.loads(archive.read('source-manifest.json'))
    for name,want in manifest['files'].items():
     self.assertEqual(hashlib.sha256(archive.read('BioTraceBench/'+name)).hexdigest(),want)
     self.assertNotIn(Path(name).suffix,{'.csv','.docx','.gz','.bin'})
    self.assertEqual(sum(name.startswith('figures/')and Path(name).suffix in{'.png','.svg'}for name in manifest['files']),18)
if __name__=='__main__':unittest.main()
