# MC3DUB-Remix-Music-Tools
This is a python project to modify music elements of the Midnight Club 3 Dub Edition Remix PS2 Game.

## Exporting and importing a music library

Open **Export/Import Music**, above About, to save your staged MP3/WAV library as a ZIP archive. It preserves filenames (including renamed artist/song titles), genre and Garage Shop folders, Win/Lose sources, title-theme sources, loading music, and the current loading mode/slot selections.

Export keeps staged files by default. The optional **Clear exported staged music** checkbox removes only exported audio after the archive is verified; category folders and game data stay in place.

Import merges the archive into the staging folders. Duplicate filenames offer Replace, Skip, Replace All, Skip All, or Cancel before importing. Archive contents and audio hashes are validated before installation, and import uses rollback copies for write failures. Imported music is staged for the normal music workflows; it does not automatically modify an extracted ISO. Installed RSM/RAW audio, game archives, and conversion/add history are not part of a music-library export.
