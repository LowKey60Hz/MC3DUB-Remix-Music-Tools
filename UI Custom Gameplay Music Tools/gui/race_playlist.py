"""Read-only playlist validation and installed Win/Lose audio inventory."""
from pathlib import Path
import hashlib
import re


def read_race_tracks(root, kind):
    if kind not in ('Win', 'Lose'):
        raise ValueError('Unknown race soundtrack category')
    prefix = 'win' if kind == 'Win' else 'loose'
    pattern = '*_raceover_music.play' if kind == 'Win' else '*_raceover_lose_music.play'
    city_root = Path(root)/'ASSETS/tune/audio/playlist/city'
    playlists = sorted(city_root.rglob(pattern)) if city_root.is_dir() else []
    if not playlists:
        raise ValueError('No extracted race-over playlists found')
    groups = []
    for path in playlists:
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip()):
            raise ValueError(f'Invalid playlist: {path.name}')
        tracks = [line.strip() for line in lines[1:] if line.strip()]
        if len(tracks) != int(lines[0].split(':', 1)[1]):
            raise ValueError(f'Playlist count mismatch: {path.name}')
        placeholder = 'music\\Win_Lose\\MC3_Empty'+kind+'Placeholder'
        if any(not re.fullmatch(r'music\\Win_Lose\\'+prefix+r'\d+', track, re.I)
               and track.casefold() != placeholder.casefold() for track in tracks):
            raise ValueError(f'Unexpected track reference: {path.name}')
        groups.append(tracks)
    if any(group != groups[0] for group in groups[1:]):
        raise ValueError('Race-over playlists differ across cities')
    return groups[0]


def read_display_race_tracks(root, kind):
    """Inventory distinct installed slot audio, independently of playback playlists."""
    if kind not in ('Win', 'Lose'):
        raise ValueError('Unknown race soundtrack category')
    prefix = 'win' if kind == 'Win' else 'loose'
    audio = set()
    result = []
    folder = Path(root)/'STREAMS/Music/Win_Lose'
    if not folder.is_dir():
        raise ValueError('Installed Win/Lose audio folder is missing')
    pattern = re.compile(prefix+r'(\d+)\.rsm', re.I)
    paths = [p for p in folder.iterdir() if p.is_file() and pattern.fullmatch(p.name)]
    paths.sort(key=lambda p: (int(pattern.fullmatch(p.name)[1]), p.name.casefold(), p.name))
    for path in paths:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                digest.update(block)
        identity = (path.stat().st_size, digest.digest())
        if identity in audio:
            continue
        audio.add(identity)
        result.append('music\\Win_Lose\\'+path.stem)
    return result
