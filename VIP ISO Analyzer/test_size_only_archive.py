import tempfile
from pathlib import Path
import unittest
from build_assets_boundary_probes import make_archive


class SizeOnlyTests(unittest.TestCase):
    def test_padding_preserves_every_original_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'source.dat', root / 'output.dat'
            data = bytes(range(256)) * 16
            source.write_bytes(data)
            make_archive(source, output, {'records': [], 'archive_bytes': 8192})
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(output.read_bytes(), data + bytes(4096))

    def test_existing_archive_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'source.dat', root / 'output.dat'
            source.write_bytes(b'source')
            output.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                make_archive(source, output, {'records': [], 'archive_bytes': 8192})
            self.assertEqual(output.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
