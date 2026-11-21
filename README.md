# MC3 Ultimate Music Tools v1.1
Add your own music to Midnight Club 3: DUB Edition Remix, including gameplay, garage, main menu, race transitions, and loading screens, then build a modified ISO.

Designed for **Windows** and use with the **PCSX2** emulator.

## Setup Instructions

1. Download the project using GitHub **Code → Download ZIP**, then **Extract All** to a short, writable local path, such as `C:\MC3Tools`. Alternatively, clone the repository with Git. Run the tools from the extracted folder, not from inside the ZIP. Avoid repeated nested download folders to reduce Windows path-length errors during installation.
2. Open the project root, containing `README.md`, `Install_MC3_GUI_Dependencies.ps1`, `Launch.bat`, `gui`, and `supporting_tools`. Setup and launch files are directly in this folder; keep them together.
3. Open PowerShell in that folder and run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install_MC3_GUI_Dependencies.ps1"
   ```

   Setup finds Python **3.12**, or attempts to install it with Windows Package Manager (`winget`). It creates a local `.venv`, installs the required Python packages, and checks the imports. An internet connection is needed for installation. If Python is missing and `winget` is unavailable, install Python 3.12 from python.org, reopen PowerShell, and rerun setup. Wait for **Setup complete** before continuing.
4. Double-click **Launch.bat**. It calls `supporting_tools/Launch_No_Shell.ps1` automatically; keep that helper in place. For later launches, use the same batch file without rerunning setup.
5. Supply your own supported base ISO: **Retail USA**, **VIP v1.0-C**, or **VIP v1.1-A**. In the app, open **ISO Extraction - Start Here**, select the ISO, and run extraction. Wait for workspace/profile verification to finish.
6. Use the music menus to stage and apply MP3/WAV tracks. Open **Build ISO** when ready, then test the resulting ISO in **PCSX2**.

Allow disk space for the original ISO, extracted workspace, rebuilt archives, and output ISO. Game ISOs, extracted game files, personal audio, and Python environments are not included in the GitHub download. Development research and test folders are not required to run the application.

### Moving your music from another computer

Use **Export/Import Music** on the old computer to export your staged music library. Copy that ZIP and your base ISO to the new computer. After setup and ISO extraction, import the library and apply its tracks through the music menus. The library does not transfer already modified game archives or an extracted workspace. Run setup on the new computer to create its own `.venv`. If you relocate the application folder, recreate its Python environment at the new location instead of copying the old `.venv`.

### Setup troubleshooting

- **Python was installed but not detected:** close and reopen PowerShell, then rerun setup.
- **Python environment not found:** run `Install_MC3_GUI_Dependencies.ps1` from the complete project download.
- **Launch.bat fails:** keep `gui`, `supporting_tools`, and the launcher together at the project root; check the root's `launcher_logs` folder for GUI startup errors.
- **PySide6 installation reports a missing deeply nested file / long-path warning:** extract into a shorter location such as `C:\MC3Tools` and rerun setup with a fresh `.venv` there.
- **A supporting file is missing:** restore the complete project download and rerun setup.

## Audio conversion

Gameplay, Garage Shop, Win/Lose and Title Theme conversion use the included Python PS-ADPCM encoder through `rstm_build.py`. No separate encoder executable is required. Loading-screen music uses its separate RAW conversion workflow. The original ADS/SS2 input path and loop CLI options remain available.

Stereo WAV inputs lasting at least 10 seconds use up to two Python workers when two CPU cores are available. Each worker retains its channel's encoding history; unavailable workers fall back to serial encoding. Shorter clips and mono inputs use serial encoding. Batched I/O and encoder-loop optimizations preserve the previous Python encoder's exact RSM output, including loop fields.

Gameplay and Garage Shop Add Tracks also adapt the number of simultaneous songs to available CPU and RAM, rechecking between batches. Concurrency is capped at three songs; each stereo song can use two encoder workers. The budget leaves two logical CPUs, at least 1 GiB and at least half of currently available RAM for other work, using conservative per-track memory estimates. Low or unknown resources and unreadable audio metadata select one song at a time. Resource estimates cannot guarantee against memory pressure caused by other applications. No additional dependency or particular CPU model is required; systems without supported memory detection use serial conversion. CLI users can force one song at a time with `add_gameplay_songs.py <project-folder> --yes --serial`.

Each song converts in its own scratch folder. Only the main process saves completed RSMs and conversion history, in the existing track order. If a song fails, later tracks are not installed; previously saved tracks remain and unchanged tracks are skipped on retry. Active conversions finish before scratch cleanup. The Activity Log identifies each track and reports the selected concurrency and conversion times. This applies automatically through the existing GUI and CLI; playlist/metadata registration still waits for successful conversion.

Win/Lose Replace Existing and Add Tracks use the same adaptive CPU/RAM budget and maximum of three simultaneous songs, including batches containing both categories. All conversions finish in isolated scratch folders before any installed audio, playlists or history are changed. A conversion failure leaves game files unchanged; installation failures retain the existing rollback behavior. Slot assignment, the two-song Win playlist workaround, empty-category behavior and verified Add history are preserved. CLI users can force serial conversion with `sync_winlose_folders.py <project-folder> replace|add --serial`. Legacy Add-history audio verification still runs serially before the installation plan is built.

An isolated throughput test on this computer converted three copies of a 92.34-second stereo MP3 in 18.27 seconds together versus 45.90 seconds sequentially, with identical RSM bytes. The integrated Add Tracks CLI subsequently completed the same three-track test in 19.03 seconds. Batch gains depend on the computer and track lengths; simultaneous songs can each take longer while the overall batch finishes sooner.

An isolated benchmark on this development computer converted a 92.34-second stereo song in 14.64 seconds versus 37.16 seconds previously (2.54× faster); the complete RSM files were byte-identical. A 12-second excerpt over three runs improved from a median of 4.91 to 2.03 seconds. Actual conversion times depend on audio, CPU and other running work; these measurements cover WAV-to-RSM encoding, not the complete Add Tracks pipeline.

## Workspace capacity

Dashboard → **Current Workspace** projects ASSETS/STREAMS usage, remaining space and overage before compiling archives or an ISO. It refreshes after music processing and when returning to the Dashboard, and warns near capacity or at projected record-offset limits. Only processed workspace files are counted; staged MP3/WAV files are excluded.

The first ASSETS compression calculation can take time. It runs in the background and caches unchanged file sizes in `support_logs/workspace_capacity_cache.json`; later scans reuse that work. Estimates stop during active processing or workspace resets. This is an internal archive-space projection, not the final ISO's disk size or a build guarantee. Existing source, archive and capacity validation still runs during Build ISO.

## Exporting and importing a music library

Open **Export/Import Music**, above About, to save your staged MP3/WAV library as a ZIP archive. It preserves filenames (including renamed artist/song titles), genre and Garage Shop folders, Win/Lose sources, title-theme sources, loading music, and the current loading mode/slot selections.

Export keeps staged files by default. The optional **Clear exported staged music** checkbox removes only exported audio after the archive is verified; category folders and game data stay in place.

Import merges the archive into the staging folders. Duplicate filenames offer Replace, Skip, Replace All, Skip All, or Cancel before importing. Archive contents and audio hashes are validated before installation, and import uses rollback copies for write failures. Imported music is staged for the normal music workflows; it does not automatically modify an extracted ISO. Installed RSM/RAW audio, game archives, and conversion/add history are not part of a music-library export.
