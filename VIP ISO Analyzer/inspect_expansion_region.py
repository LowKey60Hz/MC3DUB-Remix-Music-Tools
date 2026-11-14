"""Read-only diagnostic of the region after VIP v1.1-A ASSETS.DAT."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
iso = root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
start, stop = 1811133, 2074717
nonzero = []
with iso.open('rb') as stream:
    stream.seek(start * 2048)
    position = start * 2048
    while position < stop * 2048:
        data = stream.read(min(8 * 1024 * 1024, stop * 2048 - position))
        if not data:
            raise ValueError('Unexpected EOF')
        if data.strip(b'\0'):
            nonzero.append({'start_sector': position // 2048, 'bytes': len(data)})
        position += len(data)
result = {'start_sector': start, 'end_exclusive_sector': stop,
          'bytes_scanned': (stop - start) * 2048, 'nonzero_chunks': nonzero,
          'interpretation': 'Not proof of free space; UDF allocation and both layer layouts still require validation.'}
(root / 'Expansion_Region_Diagnostic.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
