# Two custom Win songs, skipping win2 — Retail test

This research build tests playlist selection directly. It does not modify the production Win/Lose engine or apply changes to the active workspace. Its build is complete only when `result.json` exists and all verification fields pass.

Expected ISO: `MC3_Retail_Two_Win_1_and_3.iso` in this folder.

| Song | RSM |
|---|---|
| Kendrick Lamar - Squabble Up-WIN.mp3 | win1.rsm |
| Know Good  - Feeling Myself-WIN.mp3 | win3.rsm |

All 24 Win race-over playlists contain `num_songs: 2`, followed by `music\Win_Lose\win1` and `music\Win_Lose\win3`. No win2 RSM is installed in the test. Lose audio/playlists and other extracted assets must compare unchanged with the source workspace. All staged custom audio outside these selected two remains untouched in the active project.

## PCSX2 check

1. Select the exact test ISO by its full filename. Cold boot without loading an emulator save state; an ordinary in-game career save is fine.
2. Keep a tally of recognizable Win clips during race wins, entering races, and changing locations. Try at least 10–20 relevant transitions if convenient, including multiple fresh boots. Record the clip heard and the transition. Normal gameplay/loading music is not evidence that a Win clip was selected.
3. The behavioral pass is hearing **both distinct songs** through the expected Win/race-transition path, without crashes or missing audio. Strict alternation is not required; the game's selection algorithm has not been established.
4. If only win1 is heard, report the number and types of transitions. A finite sequence of one song does not prove win3 cannot be selected; the result is inconclusive without more evidence or a debugger trace. If win3 is selected but silent/crashes, record that separately.
5. Trigger a race loss to check that the existing Lose music still plays. This test does not establish compatibility for every VIP executable; it tests the proposed Retail playlist mapping.

After a runtime pass, the production fix can use the same slot mapping in both Replace and Add modes, with isolated regression tests covering those planners. The current production duplication workaround is unchanged by this experiment.

The test copies and compiled DATs are generated artifacts. Keep the test ISO and result/log files until the runtime result is recorded; cleanup can remove intermediate copies afterward to reclaim space. Original ISO and active project folders must be preserved.
