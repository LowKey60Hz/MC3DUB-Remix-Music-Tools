# Local continuation preflight

Read CONTINUE_ON_ANOTHER_PC.md and RUNTIME_RESULTS.md before investigating. The relevant repository is the nested `MC3DUB-Remix-Music-Tools` directory; the sibling top-level VIP ISO Analyzer is an older, separate copy.

## Verified locally

- Both builders and the historical result reports are present.
- Neither historical test ISO is present anywhere under this workspace. Their recorded SHA-256 values have therefore not been independently checked on this PC.
- Three base ISOs are present in the outer `Base ISO's` folder, each 8,539,963,392 bytes. Filenames and lengths alone do not authenticate them.
- The active tools project has no ASSETS, STREAMS, ISO_FILES, or Custom Music directories. There is no local MC3_SOURCE_ISO.txt or either staged song under this workspace.
- The existing .venv runs Python 3.12.10. Actual imports of numpy, scipy, soundfile, sounddevice, PySide6, QMediaPlayer, and QAudioOutput pass. Its configuration records a prior location; the handoff calls for recreating the environment before rebuilding.
- audio_processor.py, rstm_build.py, ps2str.exe, encvag.dll, MFAudio.exe, dave.py, hash_build.py, and MC3_ISO_Builder_Retail.py are present. Encoder execution has not been tested.
- FFmpeg is available at C:\FFMPEG\bin\ffmpeg.exe. Git is unavailable on PATH; the conventional C:\Program Files\Git\cmd\git.exe is absent. No PCSX2 executable was found under this workspace (installation elsewhere was not established).
- Approximately 164 GiB free on the workspace drive at preflight.
- No production code was edited. sync_winlose_folders.py SHA-256: `31d8a9dcfb253d744bf7af0c8c9710e2e869e7d63aa44e212d689f5584de5751`.

An exploratory pydub import failed, but pydub is not a dependency listed by the project installer; this does not block the verified audio/GUI import set.

## Next controlled comparison

The swapped result supports playback of both encoded songs when mapped to win3. Slot name and second playlist position remain confounded. No production correction is justified yet.

Continue by obtaining the historical swapped ISO and authenticating it against swapped_result.json, or preparing a fresh isolated Retail workspace and the same staged songs before running the two existing builders into a fresh run folder. Do not run the builders against the historical evidence folder or substitute a VIP workspace.

For the next experiment, retain the swapped audio mapping and reverse only the 24 Win playlists to win3,win1 with num_songs: 2. Preserve STREAMS, Lose playlists, and all other decoded assets. Verify the compiled ASSETS contents against the authenticated source before building a separate output ISO. Compilation may change compressed archive bytes, so verify decoded asset equality outside the 24 intentional edits rather than claiming an ISO-wide two-line-only patch.

Record each cold boot, race outcome, transition type, song, and silence. Know Good would follow the second entry; Kendrick would follow win3 or another factor. Repeated observations are needed; neither outcome alone establishes the selector algorithm.

No new image was built and no runtime test was performed: the authenticated test image or the extracted Retail workspace and staged songs are missing locally. Historical reports remain unchanged.
