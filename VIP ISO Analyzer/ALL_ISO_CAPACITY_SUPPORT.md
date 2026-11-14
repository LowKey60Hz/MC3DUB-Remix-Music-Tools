# Retail and VIP capacity/build support — 2026-11-13

## All three current build paths have user-reported runtime passes

The user confirmed the relocated Retail test image loads/plays successfully, all music and cinematic intros work, and reports everything works. Together with the earlier VIP v1.0-C and v1.1-A results, all three current expanded build configurations now have user-reported runtime evidence with custom music. See `Retail_Expanded_Runtime_Result.json`. Older pending-status notes below are historical. Absolute archive maxima and exhaustive game/hardware compatibility remain unproven.

## Retail relocation update

A verified 911,486,976-byte zero-filled, unmapped prefix region now supports an explicit original-Retail relocation path, with a shared expanded budget of 3,381,344,256 bytes. A separate current-music test ISO passed automated read-back/preservation checks and leaves 771.96 MiB. Retail gameplay validation is still pending. See `RETAIL_EXPANSION.md`; the earlier strict-budget table below records the prior layout and remains available as the non-relocated mode. Restart the GUI to select the original-Retail expanded route. Relocated outputs are blocked from re-import rather than mislabeled as VIP.

## User runtime validation update

The user tested the separate expanded v1.0-C image and confirmed successful boot/load, cinematic intros and logos, races, garage, free roam and custom music throughout the reported gameplay modes. This supplies runtime evidence for the checked expanded v1.0-C layout with the added songs. See `V10_Expanded_Runtime_Result.json`. Retail changed-music runtime validation remains pending; no absolute maximum or every-mode compatibility claim is made.

## Confirmed failure

The user supplied the Step 5 failure message: VIP v1.0-C capacity exceeded by 57,100,288 bytes (54.46 MiB), process exit code 1. This is the capacity gate rejecting the old archive-region budget, not Windows access-denied error 5.

A read-only check of the current compiled workspace reproduced it exactly:

- ASSETS sector-padded size: 1,591,681,024 bytes; 15,839 live records.
- STREAMS sector-padded size: 1,227,808,768 bytes; 2,232 live records.
- Combined usage: 2,819,489,792 bytes.
- Legacy v1.0-C original-region budget: 2,762,389,504 bytes.
- Overrun: 57,100,288 bytes. Both archive record-range checks passed.

Evidence: `Current_Workspace_Capacity_Diagnostic.json`.

## Current budgets

All figures below are the shared sector-padded ASSETS + STREAMS allocation, preserving TEXTURE, BANKS, the manifest reservation and second-layer geometry. They are layout budgets, not absolute engine maxima.

| Mode | Shared bytes | MiB | Scope |
|---|---:|---:|---|
| VIP v1.1-A | 3,381,344,256 | 3,224.70 | Existing dedicated trusted-original path |
| VIP v1.0-C expanded | 3,381,344,256 | 3,224.70 | New explicit original-reference expansion path |
| VIP v1.0-C original region | 2,762,389,504 | 2,634.42 | Retained strict legacy/custom-source budget |
| Retail USA | 2,469,857,280 | 2,355.44 | Existing verified Retail archive region |

Retail's different first archive location consumes more of the first layer; it must not borrow the VIP budget without a separately validated relocation design. Retail capacity failures remain real failures; this change does not make the disc larger or disable its limits.

## Changes

- `vip_capacity.py` supports explicit Retail, strict VIP v1.0-C, expanded VIP v1.0-C, and VIP v1.1-A profiles with separate reference hashes, region endpoints, conditional per-archive limits, sector padding and record guards. Source-version warnings distinguish the v1.1-A runtime probes from untested boundary behavior in other versions.
- `archive_build_gate.py` uses the common model for all profiles, prints actual archive usage/budget/remaining or excess bytes, and can persist a JSON report even when an archive is malformed or over capacity.
- GUI shows the selected version and a post-compilation capacity summary. It saves raw build output to `support_logs/last_build.log` and the gate report to `support_logs/build_capacity_latest.json`. Failed dialogs name the utility and include the reported reason instead of leading with an ambiguous step number. Workspace restart clears these logs with the rest of support_logs as requested.
- Verified original v1.0-C workspaces select the explicit `--expand-v10` route. It requires the fingerprint-authenticated original, exact original geometry, safe records, a checked layout ending before the empty manifest reservation, and read-back verification. Custom/unknown sources cannot enable it. The strict route remains available for legacy custom sources.
- Both legacy profile engines now verify every byte outside allowed archive/root/UDF/manifest changes, including first-layer gaps/tails and the entire second layer. Retail also authenticates the original source through the trusted classifier before building.
- GUI dependency checks include the new preservation helper before legacy builds begin.

The new v1.0-C expansion uses checked first-layer space beyond its old end at sector 1,772,493 and ends before the manifest at 2,074,717. UDF traversal found no reachable file/directory allocation overlapping that region; the manifest reservation is zero-filled and the second-layer descriptor is present. The region contains carried-over data, so runtime testing remains necessary; absence of mapped allocations alone is not a game-compatibility proof.

## Validation and test image

All three actual original ISOs matched their trusted full hashes and source metadata checks. Their original ASSETS/STREAMS indexes were checked in place without extraction: v1.0-C 17,364 / 2,213 live records; v1.1-A 17,471 / 2,213; Retail 16,625 / 2,213. Their executable hashes differ, so v1.1-A boundary observations must not be presented as proof of the other versions' engine limits.

Fifty-three focused tests passed: 36 capacity/routing/report tests, 5 legacy expansion/retail-authentication/preservation tests, 1 isolated GUI build regression, and 11 workspace-restart regressions. Tests use temporary or simulated fixtures; a legacy GUI test was made independent of the user's changing active ISO selection.

A separate image was built from the current compiled v1.0-C additions **without removing songs or modifying the active workspace**:

`MC3_VIP_v10C_Expanded_Music_Test.iso`

SHA-256: `d4790d5f937f8c57da5ecaa0563ecfcc68acaf870660b797cb503c3308728172`.

All 15,839 compiled ASSETS records matched active source files. All 2,232 STREAMS records and manifest names matched active sources. Input archive hashes stayed unchanged during the build. Output archive hashes, ISO9660/UDF metadata, manifest, image size and every protected byte passed read-back verification. Current expanded headroom: 561,854,464 bytes (535.83 MiB). Original and previous working ISOs were preserved; the normal GUI output was not replaced by this test.

Evidence: `V10_Expanded_Build_Verification.json` / `.log`, `V10_Expanded_Capacity_Diagnostic.json`, `V10_Expansion_Allocation_Check.json`, `All_Profile_Capacity_Verification.json`, and `Original_Profile_Record_Checks.json`.

## Next user check

Restart the GUI to load the updated route. Original v1.0-C should show **VIP v1.0-C expanded**. The user has now reported passes for boot/load, cinematic intros/logos, races, garage, free roam and custom music in the separate test image. Loading and win/lose music were not separately named in this latest report. Retail source/layout/index checks passed, but no changed-music Retail ISO or Retail runtime test was performed in this session. Unsupported future reference hashes and modified Retail build sources still require separate validation.
