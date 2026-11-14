#!/usr/bin/env python3
"""Manage MC3 gameplay songs: view, check/apply all, or selected songs.

The existing manage_gameplay_genre.py remains the tested genre removal tool.
Usage:
  python manage_gameplay_soundtrack.py view
  python manage_gameplay_soundtrack.py check all
  python manage_gameplay_soundtrack.py apply all
  python manage_gameplay_soundtrack.py check song "music\\Drum_N_Bass\\SongName"
  python manage_gameplay_soundtrack.py apply song "music\\Drum_N_Bass\\SongName"
  python manage_gameplay_soundtrack.py check songs "music\\HipHop\\SongA" "music\\HipHop\\SongB"
"""
import argparse
import json
import subprocess
import re
import shutil
import sys
import tempfile
from pathlib import Path
from gameplay_placeholders import (CITIES, GENRE_INTERNAL, genre_ref, all_ref,
    editor_ref, is_placeholder, placeholder_refs, stage_metadata, install_metadata)

GENRES = {'dancehall':'dance_hall_race_music.play', 'drum-and-bass':'drums_bass_race_music.play',
          'hip-hop':'rap_race_music.play','rock':'pop_race_music.play','techno':'techno_race_music.play'}
GAME_DIRS = {x.casefold(): x for x in GENRE_INTERNAL.values()}
GARAGE = 'garage-shop'
GARAGE_FILE = 'garage.play'
GARAGE_INTERNAL = 'Instrumental'

def norm(s):
    return s.strip().replace('\\','/').casefold()

def parse(path, strict=False):
    raw = path.read_bytes()
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):
        raise ValueError(f'Unsupported UTF-16 playlist: {path}')
    text = raw.decode('utf-8-sig')
    lines = text.splitlines()
    if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip(), re.I):
        if strict:
            raise ValueError(f'Invalid gameplay playlist header: {path}')
        return raw, None, [], False
    entries = [x.strip() for x in lines[1:] if x.strip()]
    if strict and int(lines[0].split(':',1)[1]) != len(entries):
        raise ValueError(f'Song count mismatch: {path}')
    if strict and len({norm(x) for x in entries}) != len(entries):
        raise ValueError(f'Duplicate playlist entries: {path}')
    return raw, ('\r\n' if b'\r\n' in raw else '\n'), entries, raw.endswith((b'\r\n',b'\n'))

def encode(entries,nl,trailing):
    return (nl.join([f'num_songs: {len(entries)}', *entries]) + (nl if trailing else '')).encode('utf-8')

def collect(root):
    base=root/'ASSETS'/'tune'/'audio'/'playlist'/'city'
    genre_paths={base/c/'music'/name: g for c in CITIES for g,name in GENRES.items()}
    genre_paths.update({base/c/'music'/GARAGE_FILE: GARAGE for c in CITIES})
    city_paths={base/c/'music'/(c+'.play') for c in CITIES}
    editor_paths={base/c/'music'/'raceeditor.play' for c in CITIES}
    required=set(genre_paths)|city_paths|editor_paths
    missing=[p for p in sorted(required) if not p.is_file()]
    if missing:
        raise ValueError('Missing required gameplay playlists:\n'+'\n'.join(map(str,missing)))
    paths=sorted((root/'ASSETS').rglob('*.play'))
    parsed={p:parse(p,strict=p in required) for p in paths}
    return parsed,genre_paths,city_paths,editor_paths

def gameplay_ref(ref):
    bits=norm(ref).split('/')
    return len(bits)==3 and bits[0]=='music' and bits[1] in (*GAME_DIRS, GARAGE_INTERNAL.casefold()) and bits[2] and bits[2] not in ('.','..') and not is_placeholder(ref)

def read_song_titles(root):
    """Read English song titles without modifying the live STRTBL files."""
    codec = root / 'supporting_tools' / 'strtbl.py'
    if not codec.is_file():
        codec = root / 'strtbl.py'
    if not codec.is_file():
        print('[WARNING] strtbl.py not found; displaying references instead.')
        return {}
    titles = {}
    with tempfile.TemporaryDirectory(prefix='mc3_view_metadata_') as directory:
        for filename in ('mcstrings02.strtbl', 'mcstrings08.strtbl'):
            source = root / 'ASSETS' / 'fonts' / filename
            if not source.is_file():
                continue
            staged = Path(directory) / filename
            shutil.copy2(source, staged)
            result = subprocess.run([sys.executable, str(codec), 'dec', str(staged)],
                                    capture_output=True, text=True)
            if result.returncode:
                print(f'[WARNING] Unable to read {filename}; trying next table.')
                continue
            try:
                records = json.loads(staged.with_suffix('.json').read_text(encoding='utf-8'))['data']
            except (OSError, ValueError, KeyError, TypeError):
                print(f'[WARNING] Invalid metadata in {filename}; trying next table.')
                continue
            for key, languages in records.items():
                if not key.casefold().startswith('music_') or not isinstance(languages, dict):
                    continue
                english = languages.get('Language 00')
                if not isinstance(english, dict) or not isinstance(english.get('text'), str):
                    continue
                value = english['text'].strip()
                # Typical STRTBL text: '"Song Title"\nby Artist Name'
                match = re.fullmatch(r'\s*"([^"\n]+)"\s*\n\s*by\s+(.+?)\s*', value, re.I | re.S)
                if not match:
                    continue
                title, artist = match.groups()
                # A reference is 'music\Genre\Stem'; the STRTBL key uses underscores.
                # Match keys by known genre prefixes to avoid ambiguity from underscores.
                for internal in (*GENRE_INTERNAL.values(), GARAGE_INTERNAL):
                    prefix = 'music_' + internal + '_'
                    if key.casefold().startswith(prefix.casefold()):
                        ref = 'music/' + internal + '/' + key[len(prefix):]
                        titles.setdefault(norm(ref), f'{artist.strip()} - {title.strip()}')
                        break
    return titles

def view(root):
    parsed,genres,citywide,editors=collect(root)
    print('=== CURRENT GAMEPLAY SOUNDTRACK ===')
    for c in CITIES:
        print(f'\n[{c.upper()}]')
        for g,filename in (*GENRES.items(), (GARAGE, GARAGE_FILE)):
            p=root/'ASSETS'/'tune'/'audio'/'playlist'/'city'/c/'music'/filename
            entries=parsed[p][2]
            real=[x for x in entries if gameplay_ref(x)]
            print(f'  {g:15} {len(real):3} real song(s)' + (' [PLACEHOLDER]' if any(is_placeholder(x) for x in entries) else ''))
        p=root/'ASSETS'/'tune'/'audio'/'playlist'/'city'/c/'music'/(c+'.play')
        entries=parsed[p][2]
        print(f'  All Genres      {sum(gameplay_ref(x) for x in entries):3} real song(s)')
        p=p.with_name('raceeditor.play')
        print(f'  Race Editor     {sum(gameplay_ref(x) for x in parsed[p][2]):3} real song(s)')
    print_song_list(root, parsed, genres)
    print('\n[VIEW] Read-only. Nothing changed.')


def soundtrack_entries(root, parsed, genres):
    """Stable current-session numbering grouped by genre and sorted by metadata title."""
    refs = {norm(x) for p in genres for x in parsed[p][2] if gameplay_ref(x)}
    titles = read_song_titles(root) if refs else {}
    groups = []
    for genre in (*GENRES, GARAGE):
        internal = (GARAGE_INTERNAL if genre == GARAGE else GENRE_INTERNAL[genre]).casefold()
        songs = [(ref, titles.get(ref, ref.replace('/', chr(92))))
                 for ref in refs if ref.split('/')[1] == internal]
        songs.sort(key=lambda item: (item[1].casefold(), item[0]))
        groups.append((genre, songs))
    return groups


def print_song_list(root, parsed=None, genres=None):
    if parsed is None:
        parsed, genres, _, _ = collect(root)
    groups = soundtrack_entries(root, parsed, genres)
    print('\n===================================================')
    print('             CURRENT GAMEPLAY SONGS')
    print('===================================================')
    numbered = []
    for genre, songs in groups:
        print(f'\n[{genre.upper()}]')
        if not songs:
            print('  (No songs)')
        for ref, title in songs:
            numbered.append((ref, title))
            print(f'  {len(numbered):3}. {title}')
    print('\n===================================================')
    print(f'Total Gameplay and Garage Shop Songs: {len(numbered)}')
    print('===================================================')
    return numbered


def select_song(root):
    """Interactive removal using current metadata numbering; no edits until confirmed."""
    print('\n===================================================')
    print('        REMOVE INDIVIDUAL GAMEPLAY SONG')
    print('===================================================')
    numbered = print_song_list(root)
    while True:
        print('\nEnter song number, [P] Print Soundtrack, [B] Back')
        selection = input('Selection: ').strip()
        if selection.casefold() == 'b':
            print('[BACK] Returning to soundtrack menu.')
            return
        if selection.casefold() == 'p':
            numbered = print_song_list(root)
            continue
        if not selection.isdecimal() or not 1 <= int(selection) <= len(numbered):
            print('[ERROR] Invalid song number. Press P to review the current list.')
            continue
        ref, title = numbered[int(selection) - 1]
        print(f'\n[SELECTED] {title}')
        print(f'[REFERENCE] {ref.replace("/", chr(92))}')
        print('\n[PREVIEW] Individual-song removal')
        try:
            change(root, 'check', 'song', ref)
        except (OSError, ValueError, UnicodeError, KeyError) as exc:
            print('[ERROR] Preview failed:', exc)
            continue
        print('\n[WARNING] Applying will delete the RSM and update playlists/metadata.')
        confirm = input('Remove this song? (Y/N): ').strip().casefold()
        if confirm != 'y':
            print('[CANCELLED] No changes applied.')
            continue
        try:
            change(root, 'apply', 'song', ref)
        except (OSError, ValueError, UnicodeError, KeyError) as exc:
            print('[ERROR] Removal failed:', exc)
            print('[WARNING] Review your files before attempting another removal.')
            return
        print('\n[UPDATED] Soundtrack list refreshed after removal.')
        numbered = print_song_list(root)

def change(root,action,scope,requested=None):
    streams=root/'STREAMS'/'Music'
    if not streams.is_dir():
        raise ValueError('Missing STREAMS\\Music')
    parsed,genres,citywide,editors=collect(root)
    required=set(genres)|citywide|editors
    # Genre playlists and Garage Shop define selectable songs; special playlists protect shared references.
    available={norm(x) for p in genres for x in parsed[p][2] if gameplay_ref(x)}
    if scope=='all':
        targets=available
    elif scope=='genre':
        if requested not in (*GENRES, GARAGE):
            raise ValueError('Unknown genre or Garage Shop category: '+str(requested))
        targets={norm(x) for p,g in genres.items() if g==requested for x in parsed[p][2] if gameplay_ref(x)}
    elif scope in ('song', 'songs'):
        references = requested if scope == 'songs' else [requested]
        if not references or not isinstance(references, (list, tuple)):
            raise ValueError('Select at least one gameplay song.')
        targets = set()
        for reference in references:
            key=norm(reference)
            if not gameplay_ref(key):
                raise ValueError('Not a valid gameplay music reference: '+str(reference))
            if key not in available:
                raise ValueError('Song not found in a genre playlist: '+str(reference))
            targets.add(key)
    else:
        raise ValueError('Unknown removal scope: '+str(scope))
    if not targets:
        print('[INFO] No real gameplay songs to remove.')
        return
    print(f'[SCOPE] {scope} | {len(targets)} distinct song reference(s)')
    proposed={}
    changes={}
    additions={}
    for p in sorted(required):
        raw,nl,entries,trailing=parsed[p]
        # Preserve unrelated playlists byte-for-byte. Re-encoding them can
        # change their original formatting even when no song was removed.
        if not any(norm(x) in targets for x in entries):
            proposed[p]=entries
            continue
        kept=[x for x in entries if norm(x) not in targets]
        real=[x for x in kept if not is_placeholder(x)]
        if not real:
            if p in genres and genres[p] == GARAGE:
                kept=[]
                placeholder=None
                internal=None
            elif p in genres:
                internal=GENRE_INTERNAL[genres[p]]
                placeholder=genre_ref(internal)
            elif p in citywide:
                internal='HipHop';placeholder=all_ref()
            else:
                internal='HipHop';placeholder=editor_ref()
            if placeholder is not None:
                kept=[placeholder]
                additions[placeholder]=internal
        else:
            kept=real
        proposed[p]=kept
        data=encode(kept,nl,trailing)
        if data!=raw:
            changes[p]=data
            print(f'[PLAYLIST] {p.relative_to(root)}: {len(entries)} -> {len(kept)}' + (' [EMPTY GARAGE]' if p in genres and genres[p] == GARAGE and not real else (' [PLACEHOLDER]' if not real else '')))
    final={p:proposed.get(p,record[2]) for p,record in parsed.items()}
    # For non-gameplay playlists, don't trust their song counts, but DO honor references.
    used={norm(x) for entries in final.values() for x in entries}
    removals={ref.replace('/','\\') for ref in placeholder_refs() if norm(ref) not in used}
    additions={ref:internal for ref,internal in additions.items() if norm(ref) in used}
    index={}
    for p in streams.rglob('*'):
        if p.is_file() and p.suffix.casefold()=='.rsm':
            index.setdefault(norm(str(p.relative_to(streams).with_suffix(''))),[]).append(p)
    deletions=[]
    for ref in sorted(targets):
        if ref in used:
            print(f'[KEEP RSM] {ref}: still referenced elsewhere')
            continue
        matches=index.get(ref.removeprefix('music/'),[])
        if len(matches)>1:
            raise ValueError('Ambiguous RSM file location: '+ref)
        if not matches:
            print(f'[MISSING RSM] {ref}: already absent')
            continue
        p=matches[0]
        if any(part.casefold()=='win_lose' for part in p.parts):
            raise ValueError('Protected Win/Lose audio encountered: '+str(p))
        deletions.append(p)
        print(f'[DELETE RSM] {p.relative_to(root)} ({p.stat().st_size:,} bytes)')
    total=sum(p.stat().st_size for p in deletions)
    print(f'[SUMMARY] {len(changes)} changed playlists; {len(additions)} placeholder keys; '
          f'{len(deletions)} RSM deletions; {total:,} bytes ({total/1048576:.2f} MiB)')
    for ref in additions:
        print(f'[PLACEHOLDER METADATA] {ref} -> .')
    if action=='check':
        print('[CHECK] Preview only. Nothing changed.')
        return
    if not changes and not deletions and not additions and not removals:
        print('[INFO] No changes needed.')
        return
    # Only remove metadata for references no longer used by ANY playlist.
    metadata_removals={ref for ref in targets if ref not in used}
    temp,planned=stage_metadata(root,additions,removals, metadata_removals)
    with temp, tempfile.TemporaryDirectory(prefix='mc3_manager_rollback_') as rollback:
        originals={}
        for i,p in enumerate(dict.fromkeys([*changes,*(p for p,_ in planned)])):
            b=Path(rollback)/str(i)
            shutil.copy2(p,b)
            originals[p]=b
        try:
            install_metadata(planned)
            for p,data in changes.items():
                staged=p.with_name(p.name+'.manager.tmp')
                try:
                    staged.write_bytes(data)
                    staged.replace(p)
                finally:
                    staged.unlink(missing_ok=True)
            for p,data in changes.items():
                if p.read_bytes()!=data:
                    raise OSError('Playlist verification failed: '+str(p))
        except Exception:
            for p,b in originals.items():
                shutil.copy2(b,p)
            raise
        # Delete only after the playlist and metadata changes are verified.
        for p in deletions:
            p.unlink()
    print('[OK] Gameplay/Garage Shop soundtrack changes applied. Rebuild ISO to test.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('view','check','apply','select-song'))
    parser.add_argument('scope',nargs='?',choices=('all','song','songs','genre'))
    parser.add_argument('reference',nargs='*')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    args=parser.parse_args()
    if args.action=='view':
        view(args.root.resolve())
    elif args.action=='select-song':
        select_song(args.root.resolve())
    else:
        if args.scope is None or (args.scope in ('song','songs','genre') and not args.reference):
            parser.error('Use check/apply all, song REFERENCE, songs REFERENCE [REFERENCE ...], or genre CATEGORY')
        if (args.scope in ('song','genre') and len(args.reference)!=1) or (args.scope=='all' and args.reference):
            parser.error('song/genre requires exactly one reference; all takes no references')
        requested = args.reference if args.scope=='songs' else (args.reference[0] if args.reference else None)
        change(args.root.resolve(),args.action,args.scope,requested)

if __name__=='__main__':
    try:
        main()
    except (OSError,ValueError,UnicodeError,KeyError) as exc:
        print('[ERROR]',exc,file=sys.stderr)
        sys.exit(1)
