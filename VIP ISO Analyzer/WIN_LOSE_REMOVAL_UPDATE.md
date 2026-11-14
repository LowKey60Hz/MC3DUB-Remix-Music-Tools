# Win/Lose current-soundtrack removal

## User runtime confirmation

2026-11-14, subsequent empty-category test: User reports: "I also tested a no song win or lose iso and confirmed the game runs perfectly. When a race is won or lost no song is played which confirms functionality". Record user-observed normal operation of the no-song Win/Lose image and silence after both wins and losses. This confirms the empty-category behavior in the reported test. Exact image filename/hash, event counts, and cold-boot details were not specified; do not relabel an earlier image report. The one-song Win/Lose runtime cases remain unreported. Earlier pending-empty statements below describe the state before this confirmation.

2026-11-14: User reports: "I tested a two song Iso and confirmed both songs play. In the UI they get listed correctly". Record this as user-observed two-song playback and correct distinct-song UI listing after the implementation update. The exact ISO filename/hash, event counts, cold-boot details, and whether the image was produced by Replace or removal were not specified. Do not assign this observation to a particular historical image or infer validation of every removal transition. One-song and empty Win/Lose runtime cases remain pending.

Implemented following the user's request to update removal on 2026-11-14. This supersedes the earlier instruction to leave production code unchanged for this requested implementation; historical experimental reports remain untouched.

The current lists/dashboard inventory numeric Win/Lose RSM slots directly and group byte-identical files as one soundtrack. Each current list has a Remove Selected button and supports multiple selections. The confirmation identifies selected files and explains duplicate cleanup, the nonempty placeholder, retained staged sources, and pending runtime checks. The asynchronous utility shares the existing busy-state and refresh workflow.

`supporting_tools/remove_race_soundtracks.py` validates selections, all 24 affected playlists, external references, and metadata before committing. It removes selected audio identities including legacy duplicates, compacts survivors, invalidates the affected add-history, and preserves the other category. Two survivors use slots 1 and 3; two Win songs use the user-observed A,B,B reference arrangement with only two RSM files. One survivor uses one reference. Zero survivors use a dedicated MC3_EmptyWinPlaceholder or MC3_EmptyLosePlaceholder reference with six-language dot metadata, using the existing gameplay metadata helper. There is no placeholder RSM, and the folder-based UI counts zero real soundtracks.

Changes to audio, playlists, metadata, and history have temporary rollback copies. Audio referenced by another playlist is rejected before renumbering/removal. Selected audio and playlists are rechecked before installation. CLI defaults to a dry run; --apply is required to write.

`sync_winlose_folders.py` now accepts repeated references and the empty-category references so Add/Replace continue to work after removal. Two-source Win Replace creates win1/win3 once and uses A,B,B, replacing the earlier three-RSM duplicate-file workaround. Add strips the placeholder when real audio is added and counts existing byte-identical copies once when composing the playlist.

Verification: 9 removal/replacement tests and 16 dashboard/UI tests passed. Coverage includes the real string-table encoder/decoder against copies of extracted Retail tables, duplicate cleanup, 3-to-2 and 2-to-1 transitions, zero-song Win and Lose metadata, rejected missing metadata/external references, Add after placeholder, repeated Replace, UI selection/cancel, and rollback after simulated disk failure. All writes in tests used temporary workspaces. No live extracted game files or existing test ISOs were modified.

Runtime status: A,B,B has prior user-reported Retail playback evidence. The one-song Win/Lose cases and dedicated empty Win/Lose placeholders require PCSX2 testing; gameplay-placeholder behavior alone does not establish their runtime behavior. No new ISO was built in this implementation step.
