# MC3DUB-Remix-Music-Tools
This is a python project to modify music elements of the Midnight Club 3 Dub Edition Remix PS2 Game.

## Launching the GUI

After running `Install_MC3_GUI_Dependencies.ps1`, double-click `Launch.bat` inside `UI Custom Gameplay Music Tools`. Keep its helper at `supporting_tools/Launch_No_Shell.ps1`; the batch launcher calls it automatically to start the GUI without a persistent console window.

## Workspace capacity

Dashboard → **Current Workspace** projects ASSETS/STREAMS usage, remaining space and overage before compiling archives or an ISO. It refreshes after music processing and when returning to the Dashboard, and warns near capacity or at projected record-offset limits. Only processed workspace files are counted; staged MP3/WAV files are excluded.

The first ASSETS compression calculation can take time. It runs in the background and caches unchanged file sizes in `support_logs/workspace_capacity_cache.json`; later scans reuse that work. Estimates stop during active processing or workspace resets. This is an internal archive-space projection, not the final ISO's disk size or a build guarantee. Existing source, archive and capacity validation still runs during Build ISO.

## Exporting and importing a music library

Open **Export/Import Music**, above About, to save your staged MP3/WAV library as a ZIP archive. It preserves filenames (including renamed artist/song titles), genre and Garage Shop folders, Win/Lose sources, title-theme sources, loading music, and the current loading mode/slot selections.

Export keeps staged files by default. The optional **Clear exported staged music** checkbox removes only exported audio after the archive is verified; category folders and game data stay in place.

Import merges the archive into the staging folders. Duplicate filenames offer Replace, Skip, Replace All, Skip All, or Cancel before importing. Archive contents and audio hashes are validated before installation, and import uses rollback copies for write failures. Imported music is staged for the normal music workflows; it does not automatically modify an extracted ISO. Installed RSM/RAW audio, game archives, and conversion/add history are not part of a music-library export.
