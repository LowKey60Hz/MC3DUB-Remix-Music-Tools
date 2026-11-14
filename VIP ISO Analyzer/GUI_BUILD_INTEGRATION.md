# GUI build integration — 2026-11-13

## Retail GUI runtime validation

The user confirmed a Retail ISO built through the integrated GUI runs with the integrated custom music working perfectly. This adds user-observed end-to-end Retail GUI evidence to the prior v1.1-A changed-music GUI pass and standalone expanded v1.0-C/ Retail tests. No new output hash was collected for this user-generated Retail build.

## User validation after changing music

The user added a new song and garage song, successfully built the VIP v1.1-A ISO through the GUI, and confirmed the resulting game loads. The user subsequently confirmed both new tracks play in-game and entering a race succeeds without a crash. This validates the reported changed-input GUI build, music playback and race-entry workflows beyond the earlier byte-identical reproduction. It does not establish coverage of every game mode or future modification.

The earlier output SHA-256 below identifies the automated verification build only. Do not assume it identifies the user's subsequently rebuilt ISO.

## Result

The GUI supports compiling/building from the trusted original VIP v1.1-A source. The active record-aware checker is integrated after archive compilation, and profile-specific ISO engines repeat the relevant gates before any ISO copying.

The integrated verification run produced:

`UI Custom Gameplay Music Tools/MC3_Modified_VIP.iso`

Size: 8,539,963,392 bytes.

SHA-256: `3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3`.

**This is byte-identical to the successful expanded ISO already tested by the user.** The current content therefore has the same runtime evidence as that image; this does not establish compatibility of arbitrary future modifications.

## Using it

Restart the GUI with `UI Custom Gameplay Music Tools/Launch_MC3_GUI.bat`. Wait for workspace verification, open **Build ISO**, and choose **Compile DAT Archives & Build ISO**. Review the normal build confirmation. Current v1.1-A builds use six steps:

1. Validate recorded source fingerprint.
2. Compile and independently verify ASSETS via the dedicated v1.1-A compiler.
3. Compile STREAMS and its manifest.
4. Validate compiled workspace bindings.
5. Check both archive record ranges and the correct profile's shared capacity.
6. Validate contents/metadata and build/read-back a pending ISO; publish only after success.

Progress uses the actual step count. Errors include the utility's final reported reason and details remain in Activity Log. The Build button is disabled while conflicting music/extraction operations are busy. The source ISO remains read-only, and an existing final GUI output is replaced only after its pending replacement verifies.

The old moved source path in `ISO_FILES/MC3_SOURCE_ISO.txt` was repaired only after matching the current original ISO to the previously recorded trusted SHA-256. No source ISO or editable source ASSETS/STREAMS files were changed.

## Code

- `supporting_tools/MC3_ASSETS_Builder_V11A.py`: parses original filename/record tables directly from the trusted ISO, rather than depending on research reports or extracted research copies. Preserves duplicate names, record order, compression categories and observed alignments. Optimizes only already-compressed unchanged PCKs. Supports changed file sizes while enforcing the conservative live-end ceiling. Independently verifies all file records against source files before atomically replacing compiled ASSETS.
- `supporting_tools/MC3_ISO_Builder_V11A.py`: dedicated source-hash and geometry validation; record-aware capacity gate; ASSETS source-content/category/alignment checks; STREAMS source-content and manifest checks; relocation/padding; metadata/CRC updates; read-back and whole-image preservation outside permitted ranges. The entire second layer is preserved and checked.
- `supporting_tools/archive_build_gate.py`: record gates for all build paths, plus separate Retail, legacy VIP and v1.1-A capacity budgets.
- `supporting_tools/MC3_ISO_Builder.py`: routes explicit `vip-v11a` requests to the dedicated engine.
- Legacy Retail/VIP engines: enforce the record gate and their original capacity budgets. Legacy VIP distinguishes original/custom sources using validated classification instead of the filename, so a renamed original is not incorrectly treated as custom.
- `gui/main.py`: selects the dedicated compiler/engine for `VERIFIED_VIP_V11A_REFERENCE` and inserts the gate before copying. Legacy paths retain their separate engines and budgets.

## Validation

- All 19,328 new parser records matched the independent original archive report, including names, offsets and sizes.
- Full original fingerprint verified before rebinding the moved workspace source path.
- Dedicated compiler rebuilt and independently verified all 17,471 active file records. Its output hash matched the successful research ASSETS archive.
- All 17,471 compiled records also passed explicit compression-category and alignment checks.
- Five build integration tests passed: profile-budget separation, record-gate failure before copying, compiler output preservation on source failure, padded layout contiguity, and renamed-original legacy classification.
- Offscreen GUI test passed: v1.1-A Build button readiness, dedicated compiler/engine selection, stage order, dynamic progress, reported gate reason, and no advancement after a gate/output-handling failure.
- Actual GUI QProcess chain ran source validation, STREAMS compilation, workspace validation, the capacity/record gate, and ISO construction/publication. The already completed/verified ASSETS compile was reused to avoid repeating it in this run.
- Dedicated engine verified every ASSETS/STREAMS file against active sources, manifest, ISO/UDF metadata, archive payload hashes and sector padding, image size and all protected bytes. The final output hash exactly matched the user-tested expanded ISO.

Evidence: `Integrated_Build_Verification.json` and `.log`. No extra probe images were generated; one normal GUI output ISO was created.

## Limits

Only the trusted original v1.1-A reference is accepted as the dedicated engine's source. A future VIP release or re-import of an expanded output requires separate extractor/profile support; it is not silently treated as this original. The active editable ASSETS tree must preserve the trusted reference's path set. New/removed paths are rejected instead of dropped. Variable-size edits to existing files are supported within compression-category, record-offset and shared-capacity limits.

The exact engine cause of high-offset crashes remains unproven. The checker retains conservative live-record guards. Payload policy/geometry passes are not blanket gameplay compatibility claims. Retail did not receive an end-to-end runtime rebuild in this session; it uses its existing engine with the new gate, and legacy behavior was covered by focused integration tests. The separate legacy batch menu was not converted into the new v1.1-A GUI workflow.
