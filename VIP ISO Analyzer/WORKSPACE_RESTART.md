# Fresh ISO workspace restart — 2026-11-13

## User flow

Restart the GUI to load the update. In **ISO Extraction**, browse to a supported ISO. If an existing workspace or nonempty support log folder is present, the GUI asks **ISO Workspace Already Loaded** and offers to restart.

- **No:** selection is canceled; existing workspace files and the prior ISO selection stay unchanged.
- **Yes:** authorizes clearing this project's `STREAMS`, `ASSETS`, `ISO_FILES` and `support_logs` for the selected ISO and starts validation/extraction automatically. No duplicate extraction confirmation is requested for that same authorized restart.
- The new ISO must first pass both existing preflight/profile checks. An unsupported ISO leaves the previous workspace intact.
- Only then does a background cleanup worker clear the four directories. `support_logs` is recreated empty; extraction/decompilation recreate the three workspace folders.
- Track lists, previews, profile verification, title preview state and loading-slot choices reset. Staged music source files, utilities, original ISOs and top-level built ISOs are not cleanup targets.
- Extraction continues into fresh staging and activates the newly extracted archives before decompilation. Final profile verification and soundtrack loading use the new workspace.

Choosing Run ISO Extraction again with an existing workspace also offers the same restart confirmation, even without browsing to a different ISO.

## Failure behavior

Conflicting GUI operations/profile validation must finish before selecting/extracting another ISO. All media previews are stopped before reset work. A source ISO stored inside a cleanup target is rejected: move it outside those folders first.

Cleanup is fixed to the four direct project children, validates resolved paths and the project marker, and rejects symlinks/junctions/reparse points anywhere in their trees. All trees are validated before the first deletion and rechecked before each removal. A failed cleanup stops extraction and reports the worker's error. Deletion is permanent; if a locked file causes failure after some directories were cleared, the remaining files are retained and the cleared directories are named in the worker's message. No automatic rollback is claimed.

Authorization is bound to the selected ISO and project, consumed by cleanup, reset on failure or successful extraction, and invalidated on changing project folders. Unique staging paths avoid overwriting previous failed extraction staging; those partial staging directories remain for inspection rather than being silently deleted. The selected ISO is revalidated by the extractor as usual.

## Implementation

- `UI Custom Gameplay Music Tools/gui/workspace_cleanup.py`: allowlisted cleanup helper and subprocess entry point.
- `UI Custom Gameplay Music Tools/gui/main.py`: restart prompt, preflight-before-cleanup sequencing, background worker, dynamic staging activation/progress, preview/cache reset and worker error reporting.

## Validation

Nineteen tests passed: seven filesystem cleanup tests, eleven offscreen restart tests, and the existing offscreen build-workflow regression test. Coverage includes No/Yes behavior, no repeated confirmation, failed preflight preserving old files, cleanup failure stopping extraction, resetting cached state, source-in-target rejection, reparse rejection before deletion, partial-failure reporting, operation-busy checks, stale authorization, project switching, dynamic staging activation, and a real background cleanup/extraction QProcess chain using miniature stub archives.

**All deletions during testing were confined to temporary test fixtures. The user's current project workspace and support logs were not cleared.** No real ISO extraction or new multi-gigabyte artifacts were needed for this feature's tests.
