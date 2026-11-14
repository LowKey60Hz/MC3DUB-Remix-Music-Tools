"""Read-only, bounded ELF/string survey; does not establish loader behavior."""
import hashlib, json, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = ROOT.parent / "Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso"
with source.open('rb') as f:
    f.seek(16 * 2048)
    pvd = f.read(2048)
    sector, length = struct.unpack_from('<II', pvd, 158)
    f.seek(sector * 2048)
    directory = f.read(length)
    pos = 0
    entries = []
    while pos < len(directory) and directory[pos]:
        row = directory[pos:pos + directory[pos]]
        name = row[33:33 + row[32]].decode('ascii', 'replace')
        if name.startswith('SLUS_213.55'):
            entries.append((name, struct.unpack_from('<I', row, 2)[0], struct.unpack_from('<I', row, 10)[0]))
        pos += directory[pos]
    assert len(entries) == 1, entries
    name, sector, length = entries[0]
    f.seek(sector * 2048)
    data = f.read(length)
assert data[:6] == b'\x7fELF\x01\x01'
phoff, shoff = struct.unpack_from('<II', data, 28)
phentsize, phnum, shentsize, shnum = struct.unpack_from('<HHHH', data, 42)
segments = []
for i in range(phnum):
    values = struct.unpack_from('<8I', data, phoff + i * phentsize)
    segments.append(dict(zip(('type','offset','vaddr','paddr','filesz','memsz','flags','align'), values)))
def va(offset):
    return next((hex(s['vaddr'] + offset - s['offset']) for s in segments if s['type'] == 1 and s['offset'] <= offset < s['offset'] + s['filesz']), None)
strings = []
for match in re.finditer(rb'[\x20-\x7e]{5,}', data):
    value = match.group().decode('ascii')
    if re.search(r'loadscreen|load.screen|\.raw|audio[/\\]|sound.*alloc|alloc.*sound', value, re.I):
        strings.append(dict(file_offset=hex(match.start()), virtual_address=va(match.start()), text=value))
sections = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)] if shoff else []
xrefs = []
target_va = 0x6394f0
for segment in segments:
    if segment['type'] != 1 or not segment['flags'] & 1:
        continue
    for off in range(segment['offset'], segment['offset'] + segment['filesz'] - 24, 4):
        word = struct.unpack_from('<I', data, off)[0]
        if word >> 26 != 15 or word & 65535 != (target_va + 0x8000) >> 16:
            continue
        reg = (word >> 16) & 31
        for distance in range(4, 24, 4):
            second = struct.unpack_from('<I', data, off + distance)[0]
            if second >> 26 == 9 and (second >> 21) & 31 == reg and second & 65535 == target_va & 65535:
                xrefs.append(dict(lui_va=va(off), addiu_va=va(off+distance), destination_register=(second >> 16)&31,
                                  caveat='Candidate address-construction pair only; control flow and intervening register writes not validated'))
result = dict(source=str(source), executable=name, sector=sector, bytes=length,
              sha256=hashlib.sha256(data).hexdigest(), segments=segments,
              section_count=shnum, symbol_table_sections=sum(s[1] in (2,11) for s in sections),
              relevant_strings=strings,
              loadscreen_path_candidate_xrefs=xrefs,
              literal_460800_le_offsets=[hex(m.start()) for m in re.finditer(re.escape(struct.pack('<I',460800)), data)],
              caveat='String/constant presence or absence cannot establish allocation, read lengths, or a maximum. No loader call path has been traced.')
target = ROOT / 'Retail_Loading_Executable_Survey.json'
target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
