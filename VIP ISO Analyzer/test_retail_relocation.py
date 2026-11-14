import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
from test_build_capacity_integration import TOOLS, extractor
sys.path.insert(0,str(TOOLS))
import MC3_ISO_Builder_Retail as retail


class RetailRelocationTests(unittest.TestCase):
    def test_over_capacity_replacements_fit_only_when_relocation_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'ASSETS.DAT').write_bytes(b'Dave')
            (root/'STREAMS.DAT').write_bytes(b'Hash')
            sizes={'ASSETS.DAT':1344071680,'STREAMS.DAT':1227808768}
            actual=Path.stat
            def virtual_stat(path,*args,**kwargs):
                value=actual(path,*args,**kwargs)
                if path.parent==root and path.name in sizes:
                    return SimpleNamespace(st_mode=value.st_mode,st_size=sizes[path.name])
                return value
            info=retail.PROFILES['Retail USA']['archives']
            with patch.object(Path,'stat',virtual_stat):
                with self.assertRaises(ValueError):
                    retail.plan(root,info,root)
                rows=retail.plan(root,info,root,relocate_archives=True)
                self.assertEqual(rows[0]['sector'],9702)
                self.assertEqual(rows[0]['base_sector'],454764)
                self.assertTrue(all(a['end']+1==b['sector'] for a,b in zip(rows,rows[1:])))
                self.assertLess(rows[-1]['end'],retail.MANIFEST_SECTOR)
                sizes['ASSETS.DAT']+=1024*1024*1024
                with self.assertRaises(ValueError):
                    retail.plan(root,info,root,relocate_archives=True)

    def test_nonzero_gap_is_rejected(self):
        source=MagicMock()
        source.open.return_value.__enter__.return_value.read.return_value=b'\x01'
        with self.assertRaises(ValueError):
            retail.check_relocation_space(source)

    def test_relocated_retail_cannot_be_misclassified_as_vip(self):
        with patch.object(extractor,'executable_sha256',return_value=extractor.TRUSTED_RETAIL_EXECUTABLE_SHA256):
            kind=extractor.custom_layout_kind(Path('relocated.iso'),dict(extractor.VIP_LAYOUT))
        self.assertEqual(kind,'UNSUPPORTED_RETAIL_RELOCATED_LAYOUT')

    def test_existing_custom_layout_classifications_remain_available(self):
        with patch.object(extractor,'executable_sha256',return_value='vip executable'):
            self.assertEqual(extractor.custom_layout_kind(Path('vip.iso'),dict(extractor.VIP_LAYOUT)),'VIP_CUSTOM_WITH_MANIFEST')
        with patch.object(extractor,'executable_sha256') as read:
            self.assertEqual(extractor.custom_layout_kind(Path('retail.iso'),dict(extractor.RETAIL_LAYOUT)),'RETAIL_CUSTOM_WITH_MANIFEST')
            read.assert_not_called()


if __name__=='__main__':
    unittest.main()
