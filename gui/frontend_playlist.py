"""Read the four MC3 city frontend playlists and resolve their active RSM.

Read-only helper. The title replacement engine remains responsible for writes.
"""
from pathlib import Path
import re

CITIES = ('atlanta', 'detroit', 'sd', 'tokyo')
_REFERENCE = re.compile(r'music\\[A-Za-z0-9_() .-]+\\[A-Za-z0-9_().-]+', re.I)


class FrontendPlaylistError(ValueError):
    pass


def current_frontend_reference(root):
    root = Path(root)
    base = root / 'ASSETS' / 'tune' / 'audio' / 'playlist' / 'city'
    references = {}
    for city in CITIES:
        playlist = base / city / 'music' / 'frontend.play'
        try:
            lines = playlist.read_text(encoding='ascii').splitlines()
        except (OSError, UnicodeError) as exc:
            raise FrontendPlaylistError(f'Cannot read {city} frontend.play: {exc}') from exc
        if len(lines) < 2 or lines[0].strip() != 'num_songs: 1':
            raise FrontendPlaylistError(f'{city} frontend.play is not a supported one-song playlist.')
        ref = lines[1].strip()
        if not _REFERENCE.fullmatch(ref):
            raise FrontendPlaylistError(f'{city} frontend.play has an invalid RSM reference: {ref!r}')
        references[city] = ref
    if len({ref.casefold() for ref in references.values()}) != 1:
        raise FrontendPlaylistError('City frontend playlists disagree: ' + ', '.join(
            f'{city}={ref}' for city, ref in references.items()))
    return references[CITIES[0]]


def resolve_frontend_rsm(root):
    """Return (reference, existing RSM Path). No silent fallback to a hardcoded song."""
    ref = current_frontend_reference(root)
    streams = Path(root) / 'STREAMS'
    parts = ref.split('\\')
    folder = streams
    # Case-insensitive path lookup accommodates both STREAMS/Music and STREAMS/music.
    for name in parts[:-1]:
        if not folder.is_dir():
            raise FrontendPlaylistError(f'STREAMS directory is missing: {folder}')
        match = next((p for p in folder.iterdir() if p.is_dir() and p.name.casefold() == name.casefold()), None)
        if match is None:
            raise FrontendPlaylistError(f'Playlist directory is missing: {folder / name}')
        folder = match
    if not folder.is_dir():
        raise FrontendPlaylistError(f'Playlist directory is missing: {folder}')
    target = (parts[-1] + '.rsm').casefold()
    match = next((p for p in folder.iterdir() if p.is_file() and p.name.casefold() == target), None)
    if match is None:
        raise FrontendPlaylistError(f'Playlist references {ref}, but its RSM is missing in {folder}')
    return ref, match
