# Continuation findings — 2026-11-12

## 2026-11-13: original Retail loading RAW size survey

Inspected loading assets directly inside the full-hash-verified original Retail ASSETS.DAT, without extracting into or modifying the workspace. Found 18 slots / 26 records; duplicate names have identical decoded contents. Decoded sizes range 169,302 bytes (slot 14) to 291,904 bytes (slot 2). No original record equals or exceeds 460,800. Therefore the stock-size survey does not establish a 450-KiB engine boundary; neither does it prove larger files work. Full data: `Retail_Original_Loading_Audio.json` / `.md`; interpretation: `LOADING_AUDIO_LIMIT_FINDINGS.md`. GUI/converter wording now identifies 450 KiB (460,800 bytes, 9.6 seconds at current format) as the current tool cap, not a verified engine maximum. Value unchanged; no game files modified. Next research is controlled audible loading-slot probes above the cap, distinguishing per-file and aggregate-memory/selection behavior.

## 2026-11-13: user-run Retail GUI build validated

User confirmed that a Retail ISO built through the integrated UI runs with the integrated custom music working perfectly. This validates the actual user-run Retail GUI path beyond the earlier standalone relocation test. No hash collected for the later user-generated output; do not reuse the standalone test-image hash as its identity. Current layout/record checks remain enabled.

## 2026-11-13: expanded Retail runtime pass confirmed

User confirmed the Retail test image loads and plays successfully, all music and cinematic intros work, and reports everything works. Saved in `Retail_Expanded_Runtime_Result.json`; updated `RETAIL_EXPANSION.md`. Retail, VIP v1.0-C and VIP v1.1-A current expanded builds now all have user-reported runtime passes with custom music, alongside automated layout/content/preservation verification. This does not establish absolute archive maxima, exhaustive game-mode coverage or physical PS2 compatibility. No files or ISOs changed beyond documentation/results.

## 2026-11-13: Retail capacity overrun addressed with guarded relocation

User reported Retail exceeded its original region by 102,023,168 bytes / 97.30 MiB. Verified the original Retail hash and 911,486,976 zero bytes in sectors 9,702..454,763 with no ISO9660/UDF allocation overlaps. Added explicit --relocate-archives, retail-expanded budget/profile, and GUI routing for the verified original. Guards, manifest boundary and whole-image protected-byte verification remain enforced. Relocated Retail re-import is deliberately blocked by executable fingerprint to avoid false VIP classification.

Created separate `VIP ISO Analyzer/MC3_Retail_Expanded_Music_Test.iso`, SHA-256 `530066993e82e60a80b0464981545e5ef9bbf71627713abbcb0a1131deacf9c0`, with all current songs retained. Verified 15,100 ASSETS / 2,232 STREAMS source records, input stability, all output payloads/metadata/manifest and protected bytes including the full second layer. Remaining shared capacity: 809,463,808 bytes / 771.96 MiB. Originals, working ISOs and active editable workspace preserved. Fifty-seven focused tests passed. Runtime Retail gameplay validation pending: user should test the separate image. Restart GUI to load Retail USA expanded. See `RETAIL_EXPANSION.md`.

## 2026-11-13: expanded v1.0-C runtime validation passed

User confirmed the expanded v1.0-C test ISO boots/loads, plays cinematic intros and logos, and works in races, garage and free roam with custom music. Saved in `V10_Expanded_Runtime_Result.json`. This supplies user-reported runtime evidence for the guarded v1.0-C expanded layout and current added music, alongside prior automated checks. Retail changed-music runtime testing remains pending. Loading/win-lose tracks were not separately named in this latest report; no absolute archive maximum is claimed.

## 2026-11-13: all-profile checks and explicit v1.0-C expansion

User supplied the Step 5 capacity failure (exit 1), confirming the reproduced 57,100,288-byte / 54.46-MiB v1.0-C original-region overrun. Unified profile budgets/reporting now cover Retail, strict/custom v1.0-C, expanded original v1.0-C, and v1.1-A. GUI persists last_build.log and capacity JSON, shows used/remaining/over capacity, and names the failing utility. Verified original v1.0-C selects guarded --expand-v10; Retail retains its own verified region and now authenticates its source. Both legacy engines verify all protected bytes. Actual source hashes/layouts and original indexes for all three versions passed. Fifty-three focused tests passed.

Built separate `VIP ISO Analyzer/MC3_VIP_v10C_Expanded_Music_Test.iso` from the current added-music workspace without removing songs or changing active archives. Independent ASSETS/STREAMS source-content checks and full ISO read-back/preservation passed. SHA-256 `d4790d5f937f8c57da5ecaa0563ecfcc68acaf870660b797cb503c3308728172`; 535.83 MiB shared headroom remains. Runtime validation pending: user should test this image in PCSX2. Normal working GUI output and original ISOs preserved. Restart GUI to load the updated original-v1.0-C route. See `ALL_ISO_CAPACITY_SUPPORT.md` for evidence and Retail/runtime limitations.

## 2026-11-13: fresh workspace restart/cleanup added

GUI ISO selection now offers restart when a workspace is loaded. Yes automatically starts validation, then clears only STREAMS, ASSETS, ISO_FILES and support_logs after the selected ISO passes existing preflight/profile checks; No keeps files and selection. Cleanup runs in a background helper with fixed targets, source containment and reparse/path guards. It resets cached music/preview/profile/loading-slot state and continues fresh extraction using unique staging. Nineteen fixture/offscreen/regression tests passed, including the actual background worker chain on miniature stub archives and authorization reset on project switching. The current real workspace was not cleared. Restart the GUI to load the feature. See `WORKSPACE_RESTART.md`.

## 2026-11-13: changed-music GUI build validated in gameplay

The user confirmed both newly added song/garage tracks play in-game and entering a race succeeds without crashing. Combined with the prior successful GUI build and game load, the changed-input v1.1-A build workflow now has user-reported runtime passes for new music and race entry. See `GUI_BUILD_INTEGRATION.md`. No new image hash was collected and no broader game-coverage claim is made.

## 2026-11-13: user-run GUI rebuild with new music loads

User added a new song and garage song, confirmed VIP v1.1-A builds, and confirmed the game loads. Record as a user-observed successful changed-input GUI build and game load. Playback of the two new tracks remains unreported. The automated verification build's earlier SHA-256 must not be assigned to this newer output without hashing it.

## 2026-11-13: GUI capacity/build integration complete

Dedicated v1.1-A compiler/ISO engine and record/profile-capacity gates are integrated into the GUI. Restart the GUI to load them. The new parser matched all 19,328 independent reference records; the dedicated compiler verified all 17,471 active file records and matched successful research ASSETS exactly. Five focused integration tests and an offscreen GUI sequencing/failure test passed. Actual GUI QProcess workflow built `UI Custom Gameplay Music Tools/MC3_Modified_VIP.iso` with full read-back/protected-byte verification. SHA-256 `3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3` exactly matches the already user-tested successful expanded ISO. Source ISO path binding was repaired after recorded-hash verification. Original ISOs and editable source files were not changed. See `GUI_BUILD_INTEGRATION.md` and `Integrated_Build_Verification.json` for evidence and scope/remaining support limits.

## 2026-11-13: record-aware checker implemented and verified

`vip_capacity.py` now inspects Dave/Hash record tables and actual payload ranges. All four ASSETS research archives classify as expected: baseline, below control and size-only pass; high-offset probe blocks with 26 risky records. Actual STREAMS has 2,214 passing records. Twenty-two boundary/corruption/CLI tests passed. `assess_archives` is the new file API; numerical input retains conservative outer-size fallback. Evidence: `Boundary_Probes/Record_Aware_Capacity_Results_v2.json`; current documentation: `RECORD_AWARE_CHECKER.md`. GUI/build behavior unchanged, no new ISOs created. Next: integrate after compilation alongside source/profile and content validation, while separately generalizing the research compiler/build restrictions.

## 2026-11-13: above-2-GiB size-only runtime pass

User confirmed the latest standalone/size-only ISO boots and plays cinematics, main menu, free roam, music, races and garage/music. Saved in `Boundary_Probes/size_only_runtime_result.json`. Outer ASSETS length above 2 GiB alone is not the demonstrated failure cause; the prior high-offset probe's career crash now more strongly implicates high-offset access. Exact engine behavior remains unproven. Existing size checker still uses a conservative outer-size fallback; next implementation should inspect live record offsets/end positions instead of calling 2 GiB an absolute archive maximum. No ISOs changed.

## 2026-11-13: above-2-GiB size-only isolation probe ready

Built `Boundary_Probes/MC3_ASSETS_above_2GiB_size_only.iso`. ASSETS has the same length (2,154,035,200 bytes) and identical outer metadata as the failed high-offset probe, but every resource record and original archive byte remains unchanged from the successful baseline; only zero archive padding was appended. All live payloads end at byte 1,805,909,737. Automated preservation/read-back/zero-padding/metadata checks and two small-fixture tests passed. SHA-256: `cacc0ce11b6bc3b038a4aaf618d390c272d31d58a3e37ea39dd96e62cd38afde`. Runtime test pending: fresh boot, continue career, free roam/garage and loading music. See `Boundary_Probes/SIZE_ONLY_TEST.md`. Existing images preserved; size policy unchanged.

## 2026-11-13: above-2-GiB career crash; below control passes

User reports ABOVE reaches menus/cinematics but crashes on continuing career. BELOW loads free roam, garage, loading music and works. Saved in `Boundary_Probes/Runtime_Results.json`. `vip_capacity.py` now blocks sector-padded ASSETS at/above 2 GiB, using 2,147,481,600 bytes as a conservative tested size ceiling; eight boundary tests passed. This is not a proven absolute game limit. The next diagnostic is an above-2-GiB size-only image retaining successful low resource offsets to separate size/metadata handling from high-offset reads. No new images were built in response to this report.

## 2026-11-13: real-resource 2 GiB ASSETS probes ready

`build_assets_boundary_probes.py --build` created two separately named images in `Boundary_Probes`. The below control has ASSETS size 2,147,481,600 bytes; the above probe has size 2,154,035,200. All 26 records for 18 loading-screen tracks were moved to high offsets (all below or all above 2 GiB respectively), preserving exact payloads and the successful source image. Both archive/ISO read-back and protected-byte checks passed. Four probe-planning tests passed. Runtime status remains NOT TESTED. Next: user tests BELOW first, then ABOVE, with fresh boots and actual loading-screen music playback; see `Boundary_Probes/TEST_INSTRUCTIONS.md`.

## 2026-11-13: standalone capacity checker added

`supporting_tools/vip_capacity.py` in the active tools project calculates conditional v1.1-A layout headroom, sector rounding, per-archive ceilings, unknown-source status and builder/runtime warnings. Six boundary tests passed and `V11A_Capacity_Check.json` records the current files against the trusted original ISO. No GUI/build integration was performed. `CAPACITY_LIMITS.md` separates arithmetic ceilings from unknown runtime maxima and specifies meaningful high-offset tests rather than padding-only probes. Next research step is generalizing research-only compilers to produce independently verified boundary probes, particularly ASSETS across 2 GiB.

## 2026-11-13: planned PCSX2 checks complete

The user additionally confirmed story, tutorial, and reward cinematics play in the experimental expanded ISO. All planned runtime categories now have user-reported passes: boot, custom songs, garage, loading-screen music, win/lose music, and cinematics. Automated build preservation checks also passed previously. Next development step: integrate v1.1-A expansion into the active build workflow with explicit supported geometry, capacity limits, and preserved validation. The standalone experimental builder is still restricted to this exact tested proposal; it is not a general expansion builder.

## 2026-11-13: user confirmed music playback in PCSX2

The user confirmed the experimental expanded ISO boots and plays custom songs, garage music, loading-screen music, and win/lose music. Record these as user-observed passes. Story/tutorial/reward cinematics remain unreported; GUI integration is not yet implemented. Next runtime check is cinematic playback, followed by integration based on the tested v1.1-A layout and explicit capacity limits.

## 2026-11-13: experimental expanded ISO built

`MC3_VIP_v11A_Expansion_Experimental.iso` was created (8,539,963,392 bytes). Full read-back verification passed for archive payloads/padding, ISO9660/UDF metadata, embedded manifest, image size, and every byte outside allowed write ranges, including the entire second layer. SHA-256: `3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3`. Original ISOs were not modified. Next: PCSX2 boot, music, menu, loading, and cinematic testing. No game compatibility claim is made by the successful build.

## 2026-11-13: isolated builder preflight passed

`build_v11a_expansion_test.py` now provides preflight and an explicit `--build` mode for a separately named experimental ISO. Full reference hashing, 2,214 STREAMS payload comparisons, 17,471 ASSETS comparisons, and manifest checks passed. Four preservation fault-injection tests passed. No expanded ISO was created. See `EXPERIMENTAL_BUILD.md` for evidence, commands, remaining runtime uncertainty, and game-test expectations. The exact expansion range's sampled contents match Flash PCK data; it remains suspected leftover data rather than certified free space.

## Expansion planner completed

See `V11A_Expansion_Plan.md` and `V11A_Expansion_Plan.json`. Current STREAMS projects to 1,087,309,824 bytes (2,214 files). Combining it with v5 ASSETS requires 51,695,616 extra bytes beyond the original v1.1-A archive region. Proposed BANKS and ASSETS locations change; no mapped protected-allocation overlaps were found. The legacy manifest reservation is all zero. The 539,820,032-byte unexplained region matches v1.0-C exactly, but runtime relevance remains unresolved. No ISO was built.

## Follow-up: active source verification passed

Full independent validation against `UI Custom Gameplay Music Tools/ASSETS` passed for all 17,471 archive records. All 15,946 unique active source files are represented; there are no missing or extra source paths. The 81 differing paths reported below all match the active GUI folder exactly. The earlier failure was a comparison against a different research snapshot, not evidence of v5 corruption.

Evidence: `V5_Active_GUI_Validation.json`, `V5_Source_Reconciliation.json`, and `V5_Source_Coverage.json`. Reproduce the full validation with `python validate_v5_snapshot.py --source "../UI Custom Gameplay Music Tools/ASSETS" --report NEW_REPORT.json`. The validator refuses to overwrite an existing report.

The UDF traversal mapped 70 files and 5 directories, checking descriptor checksums, CRCs, and supported allocation bounds. No reachable UDF file extent intersects the scanned post-ASSETS region. One reference-image quirk is explicitly flagged: ASSETS uses a full 32-bit extent length whose high bits have extent-type meaning under ECMA-167. This diagnostic follows the existing tools' observed interpretation only for that single ASSETS descriptor; it is not generic UDF validation. Evidence: `UDF_Allocation_Map.json`.

The second-layer ISO9660 traversal mapped 106 cinematic files. Every mapped physical start has MPEG pack signature `000001ba`, supporting the layer-relative address interpretation. Evidence: `Layer2_And_Region_Diagnostic.json`. No video file was modified or fully decoded by this check.

The nonzero post-ASSETS region remains unidentified. Its absence from reachable UDF files does not prove it is safe to overwrite. Next work is a conservative expansion planner that preserves both-layer metadata and all 106 cinematic extents, followed by a separately named test image and game testing. The current v5 archive itself needs no rebuild merely to resolve the earlier research-folder mismatch.

Independent checks read existing archives and the original ISO; no game data was modified.

## Existing v5 output

`VIP_v11A_ASSETS_v5_Test.dat` is 1,805,909,737 bytes, leaving 2,416,919 bytes inside the original ASSETS allocation.

All 17,471 file records decoded to their recorded sizes. Filename table/reference checks passed and no payload overlap was detected. However, 89 records (81 unique paths) differ from the current `VIP_v11A_ASSETS_Decompiled` folder. Consequently this output is **not verified against current sources**. Differences do not by themselves establish corruption: the folder may have changed since the archive was built.

Compared with the original archive, v5 contains 88 changed file records: 26 audio, 2 fonts, and 60 tune records. This comparison does not establish that those changes are intended.

Detailed results: `V5_Independent_Validation.json`. Reproduce with `python validate_v5_snapshot.py` from this folder. The command returns failure when source mismatches exist.

## ISO growth constraints

Fresh ISO9660 metadata confirms ASSETS starts at sector 928161 and occupies 1,808,326,656 bytes, ending at sector 1811133 (exclusive). STREAMS starts at 397807; BANKS starts at 902298. The archives are contiguous, so STREAMS growth requires relocation or another layout strategy.

Scanning sectors 1811133 through 2074716 read 539,820,032 bytes. Every 8 MiB chunk (including the final shorter chunk) contained nonzero data. This is not proof that every sector is occupied, but the region is not empty padding. Its data must be identified before using any part for growth. The scan stops at the existing builder's manifest sector, not a verified free-space boundary.

Fresh metadata: `Current_v11A_Layout.json`. Region diagnostic: `Expansion_Region_Diagnostic.json`; reproduce with `python inspect_expansion_region.py`.

## Next implementation work

1. Establish the intended source snapshot for ASSETS (current decompiled research folder versus the active GUI project's ASSETS folder) and reconcile the 81 differing paths.
2. Produce a separately named rebuild from that snapshot and independently verify it. Existing experimental outputs must remain intact.
3. Map UDF file allocations and both layer layouts, including data omitted by the first-layer ISO9660 listing. Identify the nonzero post-ASSETS data before planning relocation.
4. Only then implement an isolated expandable ISO builder and validate filesystem metadata and unchanged content. PCSX2 boot, cinematics, and custom music still require game testing.

The existing v5 builder remains capped at the original allocation. The existing ISO test patcher is a same-extent replacement tool. Neither implements expandable ISO support. The older README's v3-only status is historical and should not be treated as current validation evidence.
## Loading-screen audio policy integrated: 445 KiB

Following user authorization, active converter, GUI adapter, batch adapter and UI hint now enforce 455,680 bytes (445 KiB), approximately 9.493 seconds of 24 kHz mono s16le RAW, across Retail USA and both VIP profiles. User-reported Retail probes worked at 455,680 and crashed at 455,682; this is a practical Retail-tested policy, not a traced universal buffer specification. Five tests in `test_loading_audio_limit.py` passed, covering exact output/resampling boundaries and failure-without-slot-modification behavior. Four changed source files passed syntax parsing. Existing extracted audio and ISOs were not changed. See active project `LOADING_AUDIO_LIMIT.md` for usage and research `Loading_Audio_Probes/OBSERVED_BOUNDARY.md` for evidence.

