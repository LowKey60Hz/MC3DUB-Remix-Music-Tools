"""Read-only second-layer ISO9660 map and post-ASSETS data samples."""
import importlib.util
import json
from pathlib import Path
import struct
from collections import Counter

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('iso_scan', root / 'MC3_VIP_ISO_Analyzer_v0_2.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
iso = root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
base = 2084944
files, samples = [], []
with iso.open('rb') as stream:
    stream.seek((base + 16) * 2048)
    pvd = stream.read(2048)
    if pvd[:7] != b'\x01CD001\x01':
        raise ValueError('Second layer PVD missing')
    extent, length = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
    visited = set()
    class LayerView:
        def seek(self, position):
            return stream.seek(base * 2048 + position)
        def read(self, size):
            return stream.read(size)
    view = LayerView()
    def walk(path, extent, length, depth=0):
        if depth > 32 or (extent, length) in visited:
            raise ValueError('Unexpected directory recursion')
        visited.add((extent, length))
        for name, sector, size, directory in module.directory_records(view, extent, length):
            full = path + '/' + name
            if directory:
                walk(full, sector, size, depth + 1)
            else:
                if (base + sector) * 2048 + size > iso.stat().st_size:
                    raise ValueError('Layer-relative file outside image')
                files.append({'path': full, 'relative_sector': sector, 'physical_sector': base + sector, 'bytes': size})
    walk('', extent, length)
    for item in files:
        stream.seek(item['physical_sector'] * 2048)
        item['first_four_bytes_hex'] = stream.read(4).hex()
    for sector in (1811133, 1815229, 1901245, 2003645, 2074716):
        stream.seek(sector * 2048)
        block = stream.read(2048)
        samples.append({'sector': sector, 'first_64_bytes_hex': block[:64].hex(),
                        'distinct_byte_values': len(set(block)),
                        'most_common': Counter(block).most_common(4),
                        'repeats_first_16_bytes': block == block[:16] * 128})
result = {'base_sector': base, 'root_extent': extent, 'files': files, 'samples': samples,
          'note': 'Second-layer addresses interpreted relative to its PVD base. No game compatibility or free-space claim.'}
(root / 'Layer2_And_Region_Diagnostic.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'files': len(files), 'signature_counts': dict(Counter(x['first_four_bytes_hex'] for x in files)), 'samples': samples}, indent=2))
