"""Portable staged MP3/WAV libraries; never import or modify game archives."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

FOLDERS = tuple('Custom Music/'+name for name in (
    '1_Dancehall', '1_Drum_N_Bass', '1_HipHop', '1_Rock', '1_Techno',
    '1_The_Garage_Shop', '2_Win', '2_Lose', '3_Theme Song')) + ('Loading Music',)
MANIFEST = 'music_library.json'
CHUNK = 1024*1024


def audio_path(name):
    path = PurePosixPath(name)
    if (path.as_posix() != name or str(path.parent) not in FOLDERS
            or path.suffix.lower() not in ('.mp3', '.wav')
            or any(c in path.name for c in '<>:"\\|?*')
            or any(ord(c) < 32 for c in path.name) or path.name.endswith((' ', '.'))
            or path.name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('Invalid music-library path: '+name)
    return path


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            value.update(block)
    return value.hexdigest()


def checked_target(root, relative):
    target = root/relative
    current = target
    while current != root:
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('Music-library paths cannot contain links: '+str(current))
        current = current.parent
    if not target.resolve().is_relative_to(root):
        raise ValueError('Music-library path leaves the project')
    return target


def session_state(session, names):
    session = session or {}
    if not isinstance(session, dict):
        raise ValueError('Invalid loading-music settings')
    mode = session.get('loading_mode', 'M')
    slots = session.get('loading_slots', ['']*18)
    if mode not in ('M', 'A', 'E') or not isinstance(slots, list) or len(slots) != 18:
        raise ValueError('Invalid loading-music settings')
    if any(not isinstance(name, str) or (name and 'Loading Music/'+name not in names) for name in slots):
        raise ValueError('Loading assignments reference music outside the exported library')
    return {'loading_mode': mode, 'loading_slots': slots}


def export_library(root, archive, session=None, overwrite=False, progress=lambda *_: None,
                   clear_exported=False, expected_paths=None):
    root, archive = Path(root).resolve(), Path(archive).resolve()
    if archive.exists() and not overwrite:
        raise FileExistsError('The export file already exists')
    sources = []
    for folder in FOLDERS:
        directory = checked_target(root, folder)
        if directory.is_dir():
            for source in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                if source.is_file() and source.suffix.lower() in ('.mp3', '.wav'):
                    name = source.relative_to(root).as_posix()
                    audio_path(name)
                    checked_target(root, name)
                    sources.append((name, source))
    if len({name.casefold() for name, _ in sources}) != len(sources):
        raise ValueError('Library contains filenames differing only by letter case')
    present = {name.casefold() for name, _ in sources}
    missing = [name for name in (expected_paths or []) if name.casefold() not in present]
    if missing:
        raise ValueError('These staged files are missing from disk and cannot be exported. '
                         'Nothing was cleared. Restage them first:\n'+'\n'.join(missing))
    counts = {folder: sum(str(PurePosixPath(name).parent) == folder for name, _ in sources) for folder in FOLDERS}
    state = session_state(session, {name for name, _ in sources})
    total_bytes = sum(source.stat().st_size for _, source in sources)
    if shutil.disk_usage(archive.parent).free < total_bytes + 16*1024**2:
        raise ValueError('Not enough free space for this music export')
    with tempfile.TemporaryDirectory(prefix='.mc3_export_', dir=archive.parent) as temporary:
        candidate = Path(temporary)/'library.zip'
        records = []
        with zipfile.ZipFile(candidate, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as saved:
            for folder in FOLDERS:
                saved.writestr(folder+'/', b'')
            for index, (name, source) in enumerate(sources, 1):
                previous = source.stat()
                value, size = hashlib.sha256(), 0
                with source.open('rb') as inp, saved.open(name, 'w', force_zip64=True) as out:
                    for block in iter(lambda: inp.read(CHUNK), b''):
                        value.update(block); size += len(block); out.write(block)
                current = source.stat()
                if (previous.st_size, previous.st_mtime_ns) != (current.st_size, current.st_mtime_ns):
                    raise ValueError('Music changed during export: '+name)
                records.append({'path': name, 'size': size, 'sha256': value.hexdigest()})
                progress(index, len(sources))
            manifest = {'format': 'MC3 Music Library', 'version': 1, 'folders': list(FOLDERS),
                        'files': records, 'session': state, 'category_counts': counts}
            saved.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        # Verify the complete stored audio before publishing or clearing any source.
        with zipfile.ZipFile(candidate) as verified:
            for record in records:
                value = hashlib.sha256()
                with verified.open(record['path']) as stream:
                    for block in iter(lambda: stream.read(CHUNK), b''):
                        value.update(block)
                if value.hexdigest() != record['sha256']:
                    raise ValueError('Export verification failed: '+record['path'])
        if archive.exists() and not overwrite:
            raise FileExistsError('The export file appeared during export')
        candidate.replace(archive)
    cleared, clear_error = [], ''
    if clear_exported:
        try:
            for record in records:
                source = checked_target(root, record['path'])
                if digest(source) != record['sha256']:
                    raise ValueError('Staged audio changed after export; keeping staged music')
            for name, _ in sources:
                source = checked_target(root, name)
                source.unlink(); cleared.append(name)
        except Exception as error:
            clear_error = 'Archive saved, but staged audio could not be cleared: '+str(error)
            # Restore any files already removed; the verified export is also retained.
            with zipfile.ZipFile(archive) as saved:
                for name in cleared:
                    source = checked_target(root, name)
                    if not source.exists():
                        with saved.open(name) as inp, source.open('xb') as out:
                            shutil.copyfileobj(inp, out)
            cleared = []
    return {'files': len(sources), 'bytes': total_bytes, 'archive': str(archive),
            'cleared': len(cleared), 'clear_error': clear_error, 'category_counts': counts}


def inspect_duplicates(root, archive):
    """Read-only duplicate review; import still validates the entire archive."""
    root = Path(root).resolve(strict=True)
    with zipfile.ZipFile(archive) as saved:
        info = saved.getinfo(MANIFEST)
        if info.file_size > 2*1024**2:
            raise ValueError('Music-library manifest is too large')
        data = json.loads(saved.read(MANIFEST).decode('utf-8'))
        if not isinstance(data, dict) or data.get('format') != 'MC3 Music Library' or data.get('version') != 1:
            raise ValueError('Unsupported music-library format')
        records = data.get('files')
        if not isinstance(records, list) or len(records) > 10000:
            raise ValueError('Invalid music-library manifest')
        duplicates = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('path'), str):
                raise ValueError('Invalid music-library file')
            name = record['path']; audio_path(name)
            target = checked_target(root, name)
            if target.parent.is_dir():
                matches = [p for p in target.parent.iterdir() if p.name.casefold() == target.name.casefold()]
                if matches:
                    existing = checked_target(root, matches[0].relative_to(root).as_posix())
                    if not existing.is_file():
                        raise ValueError('A music destination is not a file: '+name)
                    duplicates.append({'path': name, 'identical': digest(existing) == record.get('sha256')})
        return {'duplicates': duplicates, 'archive': str(archive)}


def import_library(root, archive, replace=False, progress=lambda *_: None, decisions=None):
    root = Path(root).resolve(strict=True)
    with zipfile.ZipFile(archive) as saved:
        infos = saved.infolist()
        if len(infos) > 10032 or len({i.filename.casefold() for i in infos}) != len(infos):
            raise ValueError('Too many files or duplicate paths in music archive')
        allowed_directories = {folder+'/' for folder in FOLDERS} | {'Custom Music/'}
        if any(item.is_dir() and (item.filename not in allowed_directories or stat.S_ISLNK(item.external_attr >> 16))
               for item in infos):
            raise ValueError('Unexpected directory in music archive')
        index = {item.filename: item for item in infos}
        if MANIFEST not in index or index[MANIFEST].file_size > 2*1024**2:
            raise ValueError('Missing or oversized music-library manifest')
        manifest = json.loads(saved.read(MANIFEST).decode('utf-8'))
        if not isinstance(manifest, dict) or manifest.get('format') != 'MC3 Music Library' or manifest.get('version') != 1:
            raise ValueError('Unsupported music-library format')
        records = manifest.get('files')
        if (not isinstance(records, list) or len(records) > 10000
                or len(records) != sum(not info.is_dir() for info in infos)-1):
            raise ValueError('Music archive does not match its manifest')
        seen, total = set(), 0
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('path'), str):
                raise ValueError('Invalid file record')
            name = record['path']; audio_path(name)
            if name.casefold() in seen or name not in index:
                raise ValueError('Duplicate or missing music file: '+name)
            seen.add(name.casefold())
            size, sha = record.get('size'), record.get('sha256')
            info = index[name]
            if (type(size) is not int or size < 0 or size != info.file_size
                    or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
                    or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                raise ValueError('Invalid or encrypted audio record: '+name)
            total += size
        if total > 50*1024**3:
            raise ValueError('Music library exceeds the 50 GiB import limit')
        state = session_state(manifest.get('session'), {r['path'] for r in records})
        for folder in FOLDERS:
            target = checked_target(root, folder)
            if target.exists() and not target.is_dir():
                raise ValueError('A staging directory is occupied by a file: '+folder)
        if shutil.disk_usage(root).free < 2*total + 16*1024**2:
            raise ValueError('Not enough space to stage and safely import this library')
        with tempfile.TemporaryDirectory(prefix='mc3_library_') as temporary:
            staging = Path(temporary)
            if shutil.disk_usage(staging).free < 2*total + 16*1024**2:
                raise ValueError('Not enough temporary space for this library')
            plan = []; identical = skipped = 0
            # Validate all payload hashes before changing any destination file.
            for number, record in enumerate(records):
                name = record['path']; candidate = staging/('audio_'+str(number))
                value, size = hashlib.sha256(), 0
                with saved.open(name) as inp, candidate.open('xb') as out:
                    for block in iter(lambda: inp.read(CHUNK), b''):
                        size += len(block)
                        if size > record['size']:
                            raise ValueError('Audio exceeds its declared size: '+name)
                        value.update(block); out.write(block)
                if size != record['size'] or value.hexdigest() != record['sha256']:
                    raise ValueError('Corrupt or modified music file: '+name)
                target = checked_target(root, name)
                if target.parent.is_dir():
                    matches = [p for p in target.parent.iterdir() if p.name.casefold() == target.name.casefold()]
                    if len(matches) > 1:
                        raise ValueError('Ambiguous existing filename: '+name)
                    if matches:
                        target = checked_target(root, matches[0].relative_to(root).as_posix())
                if target.exists():
                    if not target.is_file():
                        raise ValueError('Music destination is not a regular file: '+name)
                    decision = (decisions or {}).get(name.casefold())
                    if decision not in (None, 'replace', 'skip'):
                        raise ValueError('Invalid duplicate decision')
                    if digest(target) == record['sha256'] and decision != 'replace':
                        identical += 1; continue
                    if decision == 'skip' or (decision is None and not replace):
                        skipped += 1; continue
                backup = staging/('backup_'+str(number))
                if target.exists():
                    shutil.copyfile(target, backup)
                plan.append((target, candidate, backup if backup.exists() else None))
                progress(number+1, len(records))
            installed, created = [], []
            try:
                for folder in FOLDERS:
                    target = root/folder
                    if not target.exists():
                        target.mkdir(parents=True); created.append(target)
                for target, candidate, backup in plan:
                    installed.append((target, backup))
                    shutil.copyfile(candidate, target)
                    if digest(target) != digest(candidate):
                        raise OSError('Imported audio verification failed: '+str(target))
            except Exception:
                for target, backup in reversed(installed):
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        shutil.copyfile(backup, target)
                for folder in reversed(created):
                    folder.rmdir()
                raise
    return {'imported': len(plan), 'identical': identical, 'skipped': skipped, 'session': state}
