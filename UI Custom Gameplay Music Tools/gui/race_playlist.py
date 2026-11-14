"""Read-only Win/Lose playlist validation shared by the menu and dashboard."""
from pathlib import Path
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
        if any(not re.fullmatch(r'music\\Win_Lose\\'+prefix+r'\d+', track, re.I) for track in tracks):
            raise ValueError(f'Unexpected track reference: {path.name}')
        groups.append(tracks)
    if any(group != groups[0] for group in groups[1:]):
        raise ValueError('Race-over playlists differ across cities')
    return groups[0]
