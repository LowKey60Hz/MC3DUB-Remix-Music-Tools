"""Shared placeholder naming and STRTBL metadata helpers for MC3 gameplay tools."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CITIES = ('atlanta', 'detroit', 'sd', 'tokyo')
GENRE_INTERNAL = {'dancehall':'Dancehall','drum-and-bass':'Drum_N_Bass','hip-hop':'HipHop','rock':'Rock','techno':'Techno'}
STEM = 'MC3_EmptyGenrePlaceholder'
ALL_STEM = 'MC3_AllGenresPlaceholder'
EDITOR_STEM = 'MC3_RaceEditorPlaceholder'

def genre_ref(internal):
    return f'music\\{internal}\\{STEM}'

def all_ref():
    return f'music\\HipHop\\{ALL_STEM}'

def editor_ref():
    return f'music\\HipHop\\{EDITOR_STEM}'

def placeholder_refs():
    return {genre_ref(x).casefold() for x in GENRE_INTERNAL.values()} | {all_ref().casefold(), editor_ref().casefold()}

def is_placeholder(entry):
    return entry.strip().replace('/', '\\').casefold() in placeholder_refs()

def key_from_ref(ref):
    return ref.replace('\\', '_')

def codec_path(root):
    p = root / 'supporting_tools' / 'strtbl.py'
    return p if p.is_file() else root / 'strtbl.py'

def table_paths(root):
    return [root / 'ASSETS' / 'fonts' / f'{x}.strtbl' for x in ('mcstrings02','mcstrings08')]

def _run_codec(codec, mode, path):
    result = subprocess.run([sys.executable, str(codec), mode, str(path)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'String table {mode} failed: {path.name}: {result.stdout} {result.stderr}')

def stage_metadata(root, additions, removals, song_removals=()):
    """Return (temporary directory, [(live_path, candidate_path),...]); caller must cleanup.

    additions: mapping of placeholder reference -> internal genre used as template.
    removals: iterable of placeholder references no longer used anywhere.
    song_removals: iterable of unreferenced real-song keys to delete from both tables.
    """
    codec = codec_path(root)
    tables = table_paths(root)
    if not codec.is_file() or any(not p.is_file() or p.stat().st_size < 1024 for p in tables):
        raise ValueError('Missing strtbl.py or valid mcstrings02/08.strtbl; no changes made.')
    temp = tempfile.TemporaryDirectory(prefix='mc3_placeholder_')
    planned = []
    try:
        for table in tables:
            work = Path(temp.name) / table.stem
            work.mkdir()
            source = work / table.name
            shutil.copy2(table, source)
            _run_codec(codec, 'dec', source)
            js = work / (table.stem + '.json')
            data = json.loads(js.read_text(encoding='utf-8'))
            if data.get('config', {}).get('version') != {'hash': 1, 'table': 2}:
                raise ValueError(f'Unexpected string table version: {table.name}')
            entries = data['data']
            folded = {k.casefold(): k for k in entries}
            changed = False
            for ref, internal in additions.items():
                key = key_from_ref(ref)
                existing = folded.get(key.casefold())
                if existing:
                    record = entries[existing]
                    if not isinstance(record, dict) or any(not isinstance(v, dict) or v.get('text') != '.' for v in record.values()):
                        raise ValueError(f'Placeholder metadata key collision: {key} in {table.name}')
                    continue
                candidates = [v for k, v in entries.items() if k.casefold().startswith(('music_' + internal + '_').casefold()) and isinstance(v, dict)]
                templates = [v for v in candidates if len(v) == 6 and all(isinstance(item,dict) and 'text' in item and 'font' in item for item in v.values())]
                if not templates:
                    raise ValueError(f'No six-language template for {internal} in {table.name}')
                record = copy.deepcopy(templates[0])
                for lang in record:
                    record[lang]['text'] = '.'
                entries[key] = record
                folded[key.casefold()] = key
                changed = True
                print(f'[METADATA ADD] {table.name}: {key}')
            for ref in removals:
                key = key_from_ref(ref)
                existing = folded.get(key.casefold())
                if existing:
                    record = entries[existing]
                    if not isinstance(record, dict) or any(not isinstance(v, dict) or v.get('text') != '.' for v in record.values()):
                        raise ValueError(f'Refusing to remove non-placeholder metadata: {key}')
                    del entries[existing]
                    changed = True
                    print(f'[METADATA REMOVE] {table.name}: {key}')
            for ref in song_removals:
                key = key_from_ref(ref.replace('/', chr(92)))
                existing = folded.get(key.casefold())
                if existing:
                    # Delete only exact reference keys. Never remove other game text.
                    if not existing.casefold().startswith('music_'):
                        raise ValueError(f'Unexpected song metadata key: {existing}')
                    del entries[existing]
                    changed = True
                    print(f'[SONG METADATA REMOVE] {table.name}: {existing}')
            if not changed:
                continue
            js.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding='utf-8')
            source.unlink()
            _run_codec(codec, 'enc', js)
            candidate = work / table.name
            if not candidate.is_file() or candidate.stat().st_size < 1024:
                raise ValueError(f'Encoded output missing: {table.name}')
            verify = work / 'verify'
            verify.mkdir()
            verify_file = verify / table.name
            shutil.copy2(candidate, verify_file)
            _run_codec(codec, 'dec', verify_file)
            checked = json.loads((verify / (table.stem + '.json')).read_text(encoding='utf-8'))
            if checked != data:
                raise ValueError(f'Metadata round-trip mismatch: {table.name}')
            planned.append((table, candidate))
        return temp, planned
    except Exception:
        temp.cleanup()
        raise

def install_metadata(planned):
    """Install prepared metadata files; caller handles rollback if later operations fail."""
    for live, candidate in planned:
        stage = live.with_name(live.name + '.placeholder.tmp')
        try:
            shutil.copyfile(candidate, stage)
            stage.replace(live)
        finally:
            stage.unlink(missing_ok=True)
        print(f'[METADATA UPDATED] {live.name}')
