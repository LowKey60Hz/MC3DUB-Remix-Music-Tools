import contextlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_build_capacity_integration import legacy, extractor, TOOLS
sys.path.insert(0,str(TOOLS))
from iso_preservation import verify_protected_bytes
import MC3_ISO_Builder_Retail as retail
import archive_build_gate as gate


class LegacyExpansionTests(unittest.TestCase):
    def test_expansion_is_explicit_and_cannot_reach_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'ASSETS.DAT').write_bytes(b'Dave')
            (root/'STREAMS.DAT').write_bytes(b'Hash')
            actual_stat=Path.stat
            sizes={'ASSETS.DAT':1591681024,'STREAMS.DAT':1227808768}
            def virtual_stat(path,*args,**kwargs):
                value=actual_stat(path,*args,**kwargs)
                if path.parent==root and path.name in sizes:
                    return SimpleNamespace(st_mode=value.st_mode,st_size=sizes[path.name])
                return value
            info=legacy.PROFILES['VIP Expansion']['archives']
            with patch.object(Path,'stat',virtual_stat):
                with self.assertRaises(ValueError):
                    legacy.plan(root,info,root)
                rows=legacy.plan(root,info,root,allow_expansion=True)
                self.assertEqual(rows[-1]['end']+1,1800374)
                self.assertLess(rows[-1]['end'],legacy.MANIFEST_SECTOR)
                sizes['ASSETS.DAT']=2147483648+32*1024*1024
                with self.assertRaises(ValueError):
                    legacy.plan(root,info,root,allow_expansion=True)

    def test_custom_source_cannot_enable_original_reference_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'custom.iso'
            source.write_bytes(b'fixture')
            args=['builder','--profile','vip','--source',str(source),'--output',str(root/'new.iso'),'--expand-v10']
            with patch('sys.argv',args),patch.object(extractor,'classify',return_value=('VIP_CUSTOM_WITH_MANIFEST',{},None)), \
                 patch.object(legacy.shutil,'copyfileobj') as copy,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
                legacy.main()
            copy.assert_not_called()

    def test_protected_prefix_gaps_tail_and_image_size_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original,candidate=root/'original.iso',root/'candidate.iso'
            original.write_bytes(bytes(64))
            allowed=[(8,16),(32,40)]
            valid=bytearray(64)
            valid[8:16]=bytes([1])*8
            candidate.write_bytes(valid)
            verify_protected_bytes(original,candidate,allowed)
            for offset in (0,16,31,40,63):
                modified=bytearray(valid)
                modified[offset]=2
                candidate.write_bytes(modified)
                with self.subTest(offset=offset),self.assertRaises(ValueError):
                    verify_protected_bytes(original,candidate,allowed)
            candidate.write_bytes(bytes(65))
            with self.assertRaises(ValueError):
                verify_protected_bytes(original,candidate,allowed)

    def test_retail_rejects_wrong_source_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'wrong.iso'
            source.write_bytes(b'fixture')
            args=['builder','--source',str(source),'--replacement-dir',str(root),'--output',str(root/'new.iso'),'--yes']
            with patch('sys.argv',args),patch.object(extractor,'classify',return_value=('RETAIL_LAYOUT_BUT_HASH_MISMATCH',{},None)), \
                 patch.object(retail.shutil,'copyfileobj') as copy,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
                retail.main()
            copy.assert_not_called()

    def test_verified_retail_source_reaches_its_capacity_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'original.iso'
            source.write_bytes(b'fixture')
            args=['builder','--source',str(source),'--replacement-dir',str(root),'--output',str(root/'new.iso'),'--yes']
            with patch('sys.argv',args),patch.object(extractor,'classify',return_value=('VERIFIED_RETAIL_REFERENCE',{},None)), \
                 patch.object(retail,'inspect_base',return_value=({},100)), \
                 patch.object(gate,'check_records',side_effect=ValueError('capacity stop')) as check, \
                 patch.object(retail.shutil,'copyfileobj') as copy,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
                retail.main()
            check.assert_called_once_with(root,'retail')
            copy.assert_not_called()


if __name__=='__main__':
    unittest.main()
