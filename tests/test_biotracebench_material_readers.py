"""Synthetic regression cases: native object data, previews and legacy merges."""
import io
import json
import sqlite3
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from biotracebench.common import Stop
from biotracebench.embedded import compound_streams, object_references, prism_object
from biotracebench.materials import workbook


def compound(payload):
    """A small synthetic CFB with one stream; exercise regular and mini FAT."""
    sectors, links = [], []
    def allocate(raw):
        first = len(sectors)
        for at in range(0, len(raw), 512):
            sectors.append(raw[at:at+512].ljust(512, b'\0'))
            links.append(len(sectors) if at+512 < len(raw) else 0xFFFFFFFE)
        return first
    small = len(payload) < 4096
    if small:
        units = (len(payload)+63)//64
        mini_root = payload.ljust(units*64, b'\0')
        root_first = allocate(mini_root)
        mini_first = allocate(struct.pack('<128I', *([i+1 for i in range(units-1)] + [0xFFFFFFFE] + [0xFFFFFFFF]*(128-units))))
        first = 0
    else:
        first = allocate(payload)
        root_first, mini_first = 0xFFFFFFFE, 0xFFFFFFFE
    def entry(name, kind, sector, size):
        row = bytearray(128);label=(name+'\0').encode('utf-16-le');row[:len(label)]=label
        struct.pack_into('<H',row,64,len(label));row[66]=kind;row[67]=1
        struct.pack_into('<III',row,68,0xFFFFFFFF,0xFFFFFFFF,1 if kind==5 else 0xFFFFFFFF)
        struct.pack_into('<IQ',row,116,sector,size)
        return bytes(row)
    directory = allocate(entry('Root Entry',5,root_first,len(mini_root) if small else 0)+entry('CONTENTS',2,first,len(payload)))
    fat = len(sectors);links.append(0xFFFFFFFD)
    sectors.append(struct.pack('<128I',*(links+[0xFFFFFFFF]*(128-len(links)))))
    header=bytearray(512);header[:8]=bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<HHHHH',header,24,0x3E,3,0xFFFE,9,6)
    for at,val in [(44,1),(48,directory),(56,4096),(60,mini_first),(64,int(small)),(68,0xFFFFFFFE),(72,0)]:
        struct.pack_into('<I',header,at,val)
    struct.pack_into('<109I',header,76,fat,*([0xFFFFFFFF]*108))
    return bytes(header)+b''.join(sectors)


def prism(extra=None):
    data=io.BytesIO()
    members={'document.json':json.dumps({'title':'合成材料'}).encode(),
             'data/tables/test/data.csv':'label,value\n中文,0\n'.encode(),
             'data/tables/test/content.json':b'{"numberOfRows":2,"numberOfColumns":2}',
             'graphs/test/data.bin':b'synthetic drawing bytes'}
    members.update(extra or {})
    with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_STORED) as z:
        for name,value in members.items():z.writestr(name,value)
    raw=data.getvalue()
    return compound(struct.pack('<I',len(raw)+4)+raw)


REF=[{'part':'ppt/slides/slide5.xml','relationship_id':'rId1','program_id':'Prism10.Document',
      'preview_parts':['ppt/media/image1.png']}]


class EmbeddedTests(unittest.TestCase):
    def test_small_and_large_compound_stream_exact_bytes(self):
        for data in [b'\0zero\xe4\xb8\xad\xe6\x96\x87',b'x'*5000]:
            self.assertEqual(compound_streams(compound(data))['CONTENTS'],data)

    def test_cyclic_chain_is_rejected(self):
        raw=bytearray(compound(b'x'*5000));fat=struct.unpack_from('<I',raw,76)[0]
        struct.pack_into('<I',raw,(fat+1)*512,0)
        with self.assertRaises(Stop):compound_streams(bytes(raw))

    def test_native_values_and_metadata_are_verbatim_with_preview_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            record,blocks=prism_object(prism(),Path(tmp)/'obj','ppt/embeddings/test.bin',REF)
            self.assertEqual(record['table_count'],1)
            self.assertEqual(record['references'],REF)
            csv_block=next(b for b in blocks if b['native_member'].endswith('data.csv'))
            self.assertEqual(csv_block['text'],'label,value\n中文,0\n')
            self.assertTrue((Path(tmp)/'obj/source.prism').is_file())
            drawing=next(m for m in record['members'] if m['member'].endswith('data.bin'))
            self.assertEqual(drawing['representation'],'archived_binary_not_semantically_decoded')

    def test_unknown_object_and_missing_preview_block(self):
        for refs in [[],[{**REF[0],'program_id':'Unknown.App'}],[{**REF[0],'preview_parts':[]}]]:
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(Stop):
                prism_object(prism(),Path(tmp)/'obj','test.bin',refs)

    def test_unknown_native_member_blocks(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(Stop):
            prism_object(prism({'unknown.dat':b'x'}),Path(tmp)/'obj','test.bin',REF)

    def test_pdf_member_is_rejected_without_opening_it(self):
        original=zipfile.ZipFile.read
        def guarded(z,name,*args,**kwargs):
            if str(name).endswith('.pdf'):raise AssertionError('PDF member was opened')
            return original(z,name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch.object(zipfile.ZipFile,'read',guarded):
            with self.assertRaises(Stop) as ctx:
                prism_object(prism({'forbidden.pdf':b'never open'}),Path(tmp)/'obj','test.bin',REF)
            self.assertEqual(ctx.exception.status,'blocked_format')

    def test_slide_relationships_preserve_original_object_and_picture_locations(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:
            z.writestr('ppt/slides/slide5.xml','<s xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><oleObj progId="Prism10.Document" r:id="rId1"><blip r:embed="rId2"/></oleObj></s>')
            z.writestr('ppt/slides/_rels/slide5.xml.rels','<Relationships><Relationship Id="rId1" Target="../embeddings/test.bin"/><Relationship Id="rId2" Target="../media/image1.png"/></Relationships>')
            z.writestr('ppt/embeddings/test.bin',b'test');z.writestr('ppt/media/image1.png',b'test')
        with zipfile.ZipFile(raw) as z:self.assertEqual(object_references(z)['ppt/embeddings/test.bin'],REF)


class LegacyWorkbookTests(unittest.TestCase):
    def test_xls_labelled_native_ooxml_never_converts_and_keeps_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.xls'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合成" sheetId="1" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="n"><v>0</v></c></row><row r="2"><c r="A2" t="n"><v>-2.2999999999999998</v></c></row></sheetData></worksheet>')
            before=source.read_bytes();folder=root/'output';folder.mkdir()
            db=sqlite3.connect(':memory:');db.execute('CREATE TABLE cells (material TEXT,sheet TEXT,row INTEGER,col INTEGER,coordinate TEXT,data TEXT)')
            with patch('biotracebench.materials.office_convert',side_effect=AssertionError('Native OOXML must not be converted')):
                meta=workbook(source,folder,db,'m1',None)
            self.assertFalse(meta['legacy_conversion']);self.assertTrue(meta['native_ooxml_with_legacy_extension'])
            self.assertEqual((folder/'reader-native.xlsx').read_bytes(),before)
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(json.loads(db.execute('SELECT data FROM cells').fetchone()[0])['raw'],0)
            precise=json.loads(db.execute('SELECT data FROM cells WHERE coordinate=?',('A2',)).fetchone()[0])
            self.assertEqual(precise['source_numeric_lexeme'],'-2.2999999999999998')
            self.assertIn('-2.2999999999999998',(folder/'content.txt').read_text())
            db.close()

    def test_range_shorthand_fix_preserves_zero_formula_cache_and_display_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.xls';source.write_bytes(b'synthetic legacy input')
            converted=root/'converted.xlsx'
            with zipfile.ZipFile(converted,'w') as z:
                z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合成" sheetId="1" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>中文</t></is></c></row><row r="2"><c r="A2" t="n"><v>0</v></c><c r="B2" t="n"><f>A2</f><v>0</v></c></row></sheetData><mergeCells count="1"><mergeCell ref="1:1"/></mergeCells></worksheet>')
            folder=root/'output';(folder/'converted').mkdir(parents=True)
            db=sqlite3.connect(':memory:');db.execute('CREATE TABLE cells (material TEXT,sheet TEXT,row INTEGER,col INTEGER,coordinate TEXT,data TEXT)')
            before=converted.read_bytes()
            with patch('biotracebench.materials.office_convert',return_value=converted):
                meta=workbook(source,folder,db,'m1',None)
            rows={r[0]:json.loads(r[1]) for r in db.execute('SELECT coordinate,data FROM cells')}
            self.assertEqual(rows['A1']['raw'],'中文');self.assertEqual(rows['A2']['raw'],0)
            self.assertEqual(rows['B2']['raw'],'=A2');self.assertEqual(rows['B2']['cached'],0)
            self.assertEqual(rows['B2']['number_format'],'General')
            self.assertEqual(meta['reader_range_normalizations'][0]['equivalent_range'],'A1:XFD1')
            self.assertEqual(converted.read_bytes(),before);self.assertEqual(source.read_bytes(),b'synthetic legacy input')
            self.assertIn('"merged_range":"1:1"',(folder/'content.txt').read_text())
            db.close()
