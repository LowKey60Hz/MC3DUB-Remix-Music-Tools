"""Remove distinct installed Win/Lose songs with rollback and nonempty playlists."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from gameplay_placeholders import stage_metadata, install_metadata

PLACEHOLDERS = {kind: 'music\\Win_Lose\\MC3_Empty'+kind+'Placeholder' for kind in ('Win', 'Lose')}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def slot_entries(kind, stems):
    entries = ['music\\Win_Lose\\'+stem for stem in stems]
    if not entries:
        return [PLACEHOLDERS[kind]]
    if kind == 'Win' and len(entries) == 2:
        return entries+[entries[1]]
    return entries


def remove(root, kind, selected, apply=False):
    if kind not in PLACEHOLDERS:
        raise ValueError('Unknown race soundtrack category')
    root = Path(root).resolve(strict=True)
    prefix = 'win' if kind == 'Win' else 'loose'
    pattern = re.compile(prefix+r'(\d+)\.rsm', re.I)
    folder = root/'STREAMS/Music/Win_Lose'
    paths = sorted((p for p in folder.iterdir() if p.is_file() and pattern.fullmatch(p.name)),
                   key=lambda p: (int(pattern.fullmatch(p.name)[1]), p.name.casefold()))
    by_name = {p.name.casefold(): p for p in paths}
    names = set()
    for name in selected:
        if not pattern.fullmatch(name) or name.casefold() not in by_name:
            raise ValueError('Selected installed file is missing or invalid: '+name)
        names.add(name.casefold())
    if not names:
        raise ValueError('Select at least one installed soundtrack')
    identities = {p: digest(p) for p in paths}
    removed = {identities[by_name[name]] for name in names}
    survivors = []
    seen = set()
    for path in paths:
        identity = identities[path]
        if identity not in removed and identity not in seen:
            survivors.append(path)
            seen.add(identity)
    numbers = [1, 3] if len(survivors) == 2 else list(range(1, len(survivors)+1))
    stems = [prefix+str(number) for number in numbers]
    entries = slot_entries(kind, stems)
    city_root = root/'ASSETS/tune/audio/playlist/city'
    glob = '*_raceover_music.play' if kind == 'Win' else '*_raceover_lose_music.play'
    playlists = sorted(city_root.glob('*/music/'+glob))
    if len(playlists) != 24:
        raise ValueError(f'Expected 24 {kind} playlists, found {len(playlists)}')
    changed = {}
    original_playlists = {}
    known_refs = {'music\\win_lose\\'+p.stem.casefold() for p in paths}
    previous = None
    for path in playlists:
        raw = path.read_bytes()
        original_playlists[path] = raw
        lines = raw.decode('utf-8-sig').splitlines()
        if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip()):
            raise ValueError('Invalid playlist header: '+str(path))
        refs = [x.strip() for x in lines[1:] if x.strip()]
        if len(refs) != int(lines[0].split(':', 1)[1]):
            raise ValueError('Invalid playlist count: '+str(path))
        if any(ref.casefold() not in known_refs | {PLACEHOLDERS[kind].casefold()} for ref in refs):
            raise ValueError('Unknown or missing race audio reference: '+str(path))
        if previous is not None and refs != previous:
            raise ValueError('Race playlists disagree; no changes made')
        previous = refs
        newline = '\r\n' if b'\r\n' in raw else '\n'
        changed[path] = (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + (
            newline.join([f'num_songs: {len(entries)}']+entries)+newline).encode()
    # Renumbering must not change audio used by another playlist/category.
    for path in (root/'ASSETS').rglob('*.play'):
        if path in changed:
            continue
        refs = {line.strip().replace('/', '\\').casefold()
                for line in path.read_text(encoding='utf-8-sig').splitlines()[1:]}
        if refs & known_refs:
            raise ValueError('Race audio is referenced by another playlist: '+str(path))
    history = root/'support_logs/winlose_add_history.json'
    history_bytes = None
    if history.exists():
        data = json.loads(history.read_text(encoding='utf-8'))
        data.pop(kind, None)
        history_bytes = (json.dumps(data, indent=2)+'\n').encode()
    summary = dict(kind=kind, removed_distinct=len(removed), remaining_distinct=len(survivors),
                   playlist_entries=entries, placeholder=not survivors)
    print(json.dumps(summary, indent=2), flush=True)
    if not apply:
        return summary
    metadata_temp = None
    try:
        metadata = []
        if not survivors:
            # Same six-language dot metadata used by gameplay's empty-category guard.
            metadata_temp, metadata = stage_metadata(root, {PLACEHOLDERS[kind]: 'HipHop'}, ())
        with tempfile.TemporaryDirectory(prefix='mc3_race_remove_') as temporary:
            scratch = Path(temporary)
            candidates = {}
            for stem, source in zip(stems, survivors):
                staged = scratch/(stem+'.rsm')
                shutil.copyfile(source, staged)
                if digest(staged) != identities[source]:
                    raise ValueError('Audio staging verification failed')
                candidates[folder/staged.name] = staged
            destinations = set(paths) | set(candidates) | set(changed) | {p for p, _ in metadata}
            if history_bytes is not None:
                destinations.add(history)
            backups = {}
            for index, path in enumerate(sorted(destinations)):
                if path.exists():
                    saved = scratch/('original_'+str(index))
                    shutil.copyfile(path, saved)
                    backups[path] = saved
                else:
                    backups[path] = None
            # Refuse stale selections if anything changed while staging metadata/audio.
            if any(digest(p) != identity for p, identity in identities.items()):
                raise ValueError('Installed audio changed during preparation')
            if any(path.read_bytes() != raw for path, raw in original_playlists.items()):
                raise ValueError('Race playlists changed during preparation')
            try:
                install_metadata(metadata)
                for path, raw in changed.items():
                    path.write_bytes(raw)
                    if path.read_bytes() != raw:
                        raise OSError('Playlist installation verification failed')
                for path in paths:
                    path.unlink()
                for path, staged in candidates.items():
                    shutil.copyfile(staged, path)
                    if digest(path) != digest(staged):
                        raise OSError('Audio installation verification failed')
                if history_bytes is not None:
                    history.write_bytes(history_bytes)
            except Exception:
                for path, saved in backups.items():
                    if saved is None:
                        path.unlink(missing_ok=True)
                    else:
                        shutil.copyfile(saved, path)
                print('[ROLLBACK] Previous audio, playlists, metadata and history restored.', flush=True)
                raise
    finally:
        if metadata_temp is not None:
            metadata_temp.cleanup()
    print('[OK] Selected race soundtracks removed. Build an ISO to test.', flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--kind', choices=('Win', 'Lose'), required=True)
    parser.add_argument('--selected', nargs='+', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    remove(args.root, args.kind, args.selected, args.apply)


if __name__ == '__main__':
    main()
