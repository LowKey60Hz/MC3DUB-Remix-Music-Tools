#!/usr/bin/env python3
"""Remove current MC3 gameplay music by genre (playlist + unused RSM).

Usage:
  python manage_gameplay_genre.py check
  python manage_gameplay_genre.py check dancehall
  python manage_gameplay_genre.py apply dancehall

No backups are made. The original ISO is never modified.
"""
import argparse
import re
import sys
from pathlib import Path

CITIES = ('atlanta', 'detroit', 'sd', 'tokyo')
GENRES = {
    'dancehall': 'dance_hall_race_music.play',
    'drum-and-bass': 'drums_bass_race_music.play',
    'hip-hop': 'rap_race_music.play',
    'rock': 'pop_race_music.play',
    'techno': 'techno_race_music.play',
    'garage-shop': 'garage.play',
}
HEADER = re.compile(rb'^\s*num_songs\s*:\s*(\d+)\s*$', re.I)


def parse(path, strict=True):
    data = path.read_bytes()
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    lines = data.splitlines()
    match = HEADER.fullmatch(lines[0]) if lines else None
    if not match:
        raise ValueError('Unexpected playlist header: ' + str(path))
    entries = [x for x in lines[1:] if x.strip()]
    if strict and int(match.group(1)) != len(entries):
        raise ValueError('Song count mismatch: ' + str(path))
    if strict and any(b'\x00' in x or b':' in x for x in entries):
        raise ValueError('Unexpected playlist entry: ' + str(path))
    return entries, newline, data.endswith((b'\r\n', b'\n'))


def norm(entry):
    return entry.strip().replace(b'/', b'\\').lower()


def output(entries, newline, trailing):
    return newline.join([f'num_songs: {len(entries)}'.encode(), *entries]) + (newline if trailing else b'')


def relative(path, root):
    return str(path.relative_to(root))


def run(root, genre, apply):
    base = root / 'ASSETS' / 'tune' / 'audio' / 'playlist' / 'city'
    streams = root / 'STREAMS' / 'Music'
    if not streams.is_dir():
        raise ValueError('Missing STREAMS\\Music; no changes made.')
    selected = [base / city / 'music' / GENRES[genre] for city in CITIES]
    citywide = [base / city / 'music' / (city + '.play') for city in CITIES]
    raceeditor = [base / city / 'music' / 'raceeditor.play' for city in CITIES]
    all_plays = sorted((root / 'ASSETS').rglob('*.play'))
    required = selected + citywide + raceeditor
    missing = [p for p in required if not p.is_file()]
    if missing:
        raise ValueError('Missing required playlists:\n' + '\n'.join(map(str, missing)))
    if not all_plays:
        raise ValueError('No .play files found.')
    # Only playlists we intend to edit must follow strict gameplay count rules.
    # Other .play files (speech, mechanic, etc.) are read only for reference safety.
    required_set = set(required)
    parsed = {p: parse(p, strict=(p in required_set)) for p in all_plays}
    targets = {norm(entry) for p in selected for entry in parsed[p][0]}
    if not targets:
        print('[INFO] This genre is already empty. No changes made.')
        return
    if any(not x.startswith(b'music\\') or b'..' in x for x in targets):
        raise ValueError('Unexpected music reference format; no changes made.')
    changes = {}
    print(f'[GENRE] {genre} | {len(targets)} distinct song references')
    for p in required:
        entries, nl, trailing = parsed[p]
        if p in selected:
            kept = []
        else:
            kept = [x for x in entries if norm(x) not in targets]
        changes[p] = output(kept, nl, trailing)
        print(f'[PLAYLIST] {relative(p, root)}: {len(entries)} -> {len(kept)}')
    # A song can be used in a separate genre or special playlist.
    # Evaluate all references against the proposed edits, including Race Editor.
    still_used = {}
    for ref in sorted(targets):
        users = []
        for p, (entries, _, _) in parsed.items():
            remaining = [] if p in selected else ([x for x in entries if norm(x) not in targets] if p in (citywide + raceeditor) else entries)
            if ref in {norm(x) for x in remaining}:
                users.append(relative(p, root))
        if users:
            still_used[ref] = users
    rsm_index = {}
    for p in streams.rglob('*'):
        if p.is_file() and p.suffix.lower() == '.rsm':
            key = str(p.relative_to(streams)).replace('/', '\\').lower()
            rsm_index.setdefault(key, []).append(p)
    deletions = []
    skipped = []
    missing_rsm = []
    for ref in sorted(targets):
        label = ref.decode('utf-8', 'replace')
        if ref in still_used:
            skipped.append((label, f'referenced by {len(still_used[ref])} other playlist(s)'))
            continue
        key = label.removeprefix('music\\') + '.rsm'
        matches = rsm_index.get(key, [])
        if len(matches) != 1:
            missing_rsm.append((label, len(matches)))
            continue
        candidate = matches[0]
        if any(part.lower() == 'win_lose' for part in candidate.parts):
            skipped.append((label, 'protected Win/Lose directory'))
            continue
        deletions.append(candidate)
    for label, reason in skipped:
        print(f'[KEEP RSM] {label}: {reason}')
        ref_key = label.encode('utf-8')
        for user in still_used.get(ref_key, []):
            print(f'    [REFERENCE] {user}')
    for label, count in missing_rsm:
        print(f'[UNRESOLVED RSM] {label}: {count} matching files')
    bytes_saved = sum(p.stat().st_size for p in deletions)
    for p in deletions:
        print(f'[DELETE RSM] {relative(p, root)} ({p.stat().st_size:,} bytes)')
    print(f'[SUMMARY] {len(required)} playlists; {len(deletions)} RSM deletions; {bytes_saved:,} bytes ({bytes_saved / 1048576:.2f} MiB)')
    if not apply:
        print('[CHECK] Preview only. Nothing changed.')
        return
    if missing_rsm:
        raise ValueError('Unresolved RSM references; refusing to apply. Review the output.')
    if not deletions:
        print('[WARNING] No RSM files are eligible for deletion. Playlist changes will still proceed.')
    # Commit playlist edits first, then remove files. No original ISO changes.
    for p, data in changes.items():
        if p.read_bytes() != data:
            p.write_bytes(data)
    for p, data in changes.items():
        if p.read_bytes() != data:
            raise OSError('Playlist verification failed: ' + str(p))
    for p in deletions:
        p.unlink()
    print('[OK] Genre playlist entries cleared and eligible unused RSM files deleted.')
    print('[NEXT] Run your existing Option 5 to rebuild the archives and ISO.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'apply'))
    parser.add_argument('genre', nargs='?', choices=sorted(GENRES))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    if not args.genre:
        print('Available genres: ' + ', '.join(GENRES))
        if args.action == 'apply':
            parser.error('Specify a genre to apply.')
        return
    if args.genre == 'garage-shop':
        from manage_gameplay_soundtrack import change
        change(args.root.resolve(), args.action, 'genre', args.genre)
    else:
        run(args.root.resolve(), args.genre, args.action == 'apply')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        print('[ERROR]', exc, file=sys.stderr)
        sys.exit(1)
