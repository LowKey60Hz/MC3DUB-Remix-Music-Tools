# Continuing the two-Win-song investigation

## Current conclusion

No production slot-assignment fix has been applied. The shared `supporting_tools/sync_winlose_folders.py` still contains its earlier win2/win3 duplication behavior. The experiment has not validated skipping win2 as a two-song solution. Do not silently replace the production flow based on the hypothesis alone.

Both isolated Retail tests contain exactly two playlist entries, in this order:

```text
num_songs: 2
music\Win_Lose\win1
music\Win_Lose\win3
```

| Test ISO | win1 | win3 | User observation |
|---|---|---|---|
| MC3_Retail_Two_Win_1_and_3.iso | Kendrick Lamar - Squabble Up | Know Good - Feeling Myself | Only Know Good heard across three races and two race-entry transitions |
| MC3_Retail_Two_Win_1_and_3_SWAPPED.iso | Know Good - Feeling Myself | Kendrick Lamar - Squabble Up | Kendrick now plays; event count and whether another song played were not specified |

The swapped test exchanges only two STREAMS offset/size pairs. Every other ISO byte is identical to the first test; the audio was not reencoded. Both songs therefore can play when mapped to win3. However, win3 is also the second playlist entry in both tests: slot-name selection and list-index selection remain confounded. A division/rounding/minimum-three rule is a hypothesis, not an established mechanism.

## Next proposed experiment — NOT YET BUILT

Keep the swapped audio mapping, reverse only all 24 Win playlist entries to win3,win1, and retain `num_songs: 2`. Know Good playing would follow the second entry; Kendrick continuing to play would follow win3 or another factor. Record cold boots, race outcomes, transition types, songs heard, and silence. Neither a short sequence nor strict alternation alone establishes the random/selection algorithm. A three-entry experiment can follow; preserve Lose music and avoid production changes until findings support a correction.

## What Git includes

- `../build_two_win_skip2_test.py`: builds the first isolated Retail test from a copy of the active extracted workspace, with the alphabetically first two staged Win MP3/WAVs. It uses existing conversion/compiler tools without editing the production Win/Lose engine.
- `../build_two_win_swapped_test.py`: authenticates the first test ISO and swaps its two Win record references, checking every other byte against the first ISO.
- `result.json`, `swapped_result.json`, `RUNTIME_RESULTS.md`, and `TEST_INSTRUCTIONS.md`: provenance, exact hashes, user observations, and test procedure. Absolute paths in historical JSON reports document the original computer; use local paths on the new PC.
- Existing project source, earlier research scripts, and regression tests are already tracked separately.

## Local files required on the other PC

ISOs, extracted game files, custom audio, encoder binaries/DLLs, logs, and virtual environments are not supplied by this handoff commit. The verified Retail base ISO is needed only if rebuilding, not to boot a transferred complete test image.

Fastest continuation: copy the two test ISOs separately into this folder and verify their SHA-256 values against the reports. Existing result reports intentionally prevent an accidental rebuild over those artifacts. Install PCSX2 and use cold boots rather than emulator save states for comparisons.

For a fresh rebuild instead, prepare an extracted Retail workspace with the latest tools on that PC. Confirm that `ISO_FILES/MC3_SOURCE_ISO.txt` points to its local base ISO. Supply the same two staged songs, the Python audio/GUI dependencies, `audio_processor.py`, `rstm_build.py`, `ps2str.exe` with `encvag.dll` (or the supported MFAudio encoder), and other tracked compiler/build dependencies. Recreate the virtual environment; do not copy the old `.venv`. Different staged music or source workspace contents will change the resulting ISO hash.

The builders accept `--test-dir` so fresh builds can preserve these tracked historical results. From the repository root in PowerShell, after preparing the local dependencies, sources and workspace:

```powershell
& '.\UI Custom Gameplay Music Tools\.venv\Scripts\python.exe' '.\VIP ISO Analyzer\build_two_win_skip2_test.py' --test-dir '.\VIP ISO Analyzer\Two_Win_Run_01'
& '.\UI Custom Gameplay Music Tools\.venv\Scripts\python.exe' '.\VIP ISO Analyzer\build_two_win_swapped_test.py' --test-dir '.\VIP ISO Analyzer\Two_Win_Run_01'
```

Choose a fresh run-folder name if that folder already exists. `Two_Win_Run_*` folders are ignored by Git to exclude generated game data. Do not delete tracked evidence to bypass overwrite guards. `--resume` is only for an interrupted first-test preparation before compilation, not for completed test reports. The swapped builder requires the first ISO beside its report and refuses an existing swapped ISO/report. It resolves the original ISO locally instead of using the old computer's absolute report path.

The generated source copies and compiled DAT intermediates on the original computer were deleted after verification to reclaim space; the two test ISOs and these reports remain. Production source and active workspace were verified unchanged by the original isolated builds.
