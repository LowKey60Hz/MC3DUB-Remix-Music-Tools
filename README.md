# MC3DUB-Remix-Music-Tools
This is a python project to modify music elements of the Midnight Club 3 Dub Edition Remix PS2 Game.

## Launching the GUI

After running `Install_MC3_GUI_Dependencies.ps1`, double-click `Launch.bat` inside `UI Custom Gameplay Music Tools`. Keep its helper at `supporting_tools/Launch_No_Shell.ps1`; the batch launcher calls it automatically to start the GUI without a persistent console window.

## Audio conversion

Audio conversion now uses the included Python PS-ADPCM encoder through `rstm_build.py`. Normal Gameplay, Garage Shop, Win/Lose and Title Theme conversion does not execute or require `ps2str.exe`, `encvag.dll` or `MFAudio.exe`. Loading-screen RAW conversion is unchanged. The original ADS/SS2 input path and loop CLI options remain available. No Windows Security exceptions are needed for these legacy encoders because normal conversion no longer launches them.

Stereo WAV inputs lasting at least 10 seconds use up to two Python workers when two CPU cores are available. Each worker retains its channel's encoding history; unavailable workers fall back to serial encoding. Shorter clips and mono inputs use serial encoding. Batched I/O and encoder-loop optimizations preserve the previous Python encoder's exact RSM output, including loop fields.

Gameplay and Garage Shop Add Tracks also adapt the number of simultaneous songs to available CPU and RAM, rechecking between batches. Concurrency is capped at three songs; each stereo song can use two encoder workers. The budget leaves two logical CPUs, at least 1 GiB and at least half of currently available RAM for other work, using conservative per-track memory estimates. Low or unknown resources and unreadable audio metadata select one song at a time. Resource estimates cannot guarantee against memory pressure caused by other applications. No additional dependency or particular CPU model is required; systems without supported memory detection use serial conversion. CLI users can force one song at a time with `add_gameplay_songs.py <project-folder> --yes --serial`.

Each song converts in its own scratch folder. Only the main process saves completed RSMs and conversion history, in the existing track order. If a song fails, later tracks are not installed; previously saved tracks remain and unchanged tracks are skipped on retry. Active conversions finish before scratch cleanup. The Activity Log identifies each track and reports the selected concurrency and conversion times. This applies automatically through the existing GUI and CLI; playlist/metadata registration still waits for successful conversion.

Win/Lose Replace Existing and Add Tracks use the same adaptive CPU/RAM budget and maximum of three simultaneous songs, including batches containing both categories. All conversions finish in isolated scratch folders before any installed audio, playlists or history are changed. A conversion failure leaves game files unchanged; installation failures retain the existing rollback behavior. Slot assignment, the two-song Win playlist workaround, empty-category behavior and verified Add history are preserved. CLI users can force serial conversion with `sync_winlose_folders.py <project-folder> replace|add --serial`. Legacy Add-history audio verification still runs serially before the installation plan is built.

An isolated throughput test on this computer converted three copies of a 92.34-second stereo MP3 in 18.27 seconds together versus 45.90 seconds sequentially, with identical RSM bytes. The integrated Add Tracks CLI subsequently completed the same three-track test in 19.03 seconds. Batch gains depend on the computer and track lengths; simultaneous songs can each take longer while the overall batch finishes sooner.

An isolated benchmark on this development computer converted a 92.34-second stereo song in 14.64 seconds versus 37.16 seconds previously (2.54× faster); the complete RSM files were byte-identical. A 12-second excerpt over three runs improved from a median of 4.91 to 2.03 seconds. Actual conversion times depend on audio, CPU and other running work; these measurements cover WAV-to-RSM encoding, not the complete Add Tracks pipeline. The benchmark and frozen reference encoder are in `Encoder Research`; byte-equivalence and worker-recovery checks are in `tests`.

## Workspace capacity

Dashboard → **Current Workspace** projects ASSETS/STREAMS usage, remaining space and overage before compiling archives or an ISO. It refreshes after music processing and when returning to the Dashboard, and warns near capacity or at projected record-offset limits. Only processed workspace files are counted; staged MP3/WAV files are excluded.

The first ASSETS compression calculation can take time. It runs in the background and caches unchanged file sizes in `support_logs/workspace_capacity_cache.json`; later scans reuse that work. Estimates stop during active processing or workspace resets. This is an internal archive-space projection, not the final ISO's disk size or a build guarantee. Existing source, archive and capacity validation still runs during Build ISO.

## Exporting and importing a music library

Open **Export/Import Music**, above About, to save your staged MP3/WAV library as a ZIP archive. It preserves filenames (including renamed artist/song titles), genre and Garage Shop folders, Win/Lose sources, title-theme sources, loading music, and the current loading mode/slot selections.

Export keeps staged files by default. The optional **Clear exported staged music** checkbox removes only exported audio after the archive is verified; category folders and game data stay in place.

Import merges the archive into the staging folders. Duplicate filenames offer Replace, Skip, Replace All, Skip All, or Cancel before importing. Archive contents and audio hashes are validated before installation, and import uses rollback copies for write failures. Imported music is staged for the normal music workflows; it does not automatically modify an extracted ISO. Installed RSM/RAW audio, game archives, and conversion/add history are not part of a music-library export.
