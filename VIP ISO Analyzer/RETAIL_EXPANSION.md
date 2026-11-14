# Guarded Retail archive relocation — 2026-11-13

## User-reported runtime pass

The user subsequently rebuilt Retail through the integrated GUI and confirmed that resulting ISO runs with the integrated custom music working perfectly. This confirms the user-run GUI path in addition to the earlier standalone relocation test. No hash was collected for this later GUI-built output; the standalone image hash below must not be assigned to it.

The user confirmed this separate expanded Retail image loads and plays successfully, all music plays, cinematic intros play, and reports everything works. See `Retail_Expanded_Runtime_Result.json`. This supplies runtime evidence for the relocated layout with the current custom music, alongside automated preservation checks. It does not establish an absolute engine maximum or exhaustive game coverage.

## Failure and verified space

The reported 102,023,168-byte (97.30 MiB) overrun is a capacity failure against Retail's original archive region, not a Windows permissions error.

The exact original Retail USA ISO was authenticated by full SHA-256. Sectors 9,702 through 454,763 contain **911,486,976 zero bytes** (about 869.26 MiB), with no overlapping ISO9660 files or reachable UDF file/directory allocations. The source's manifest reservation is also zero-filled. Evidence: `Retail_Relocation_Inspection.json`.

The guarded proposal moves the four DAT archives into that prefix gap, rather than extending across the manifest or cinematic layer. It preserves the executable and other low-sector files. Original game/data references are updated in both ISO9660 and UDF and checked after writing. Static allocation checks and empty bytes support the proposal; they do not prove the Retail game tolerates relocation.

## Implementation

- `MC3_ISO_Builder_Retail.py --relocate-archives` requires the exact original Retail reference and original archive geometry, then rechecks every byte of the zero gap before copying. It plans from sector 9,702 and retains the original end boundary at sector 2,074,717.
- The `retail-expanded` capacity profile has 3,381,344,256 shared bytes for padded ASSETS + STREAMS, preserving TEXTURE and BANKS. The original strict Retail profile remains 2,469,857,280 bytes. No capacity or live-offset guard was disabled.
- The GUI chooses this explicit path only for `VERIFIED_RETAIL_REFERENCE` and displays **Retail USA expanded** after restart. Reports and logs use the same version-aware checks as the other profiles.
- Whole-image preservation verification checks every byte outside the explicitly permitted DAT/root/UDF/manifest changes, including the entire second layer.
- Relocated Retail output re-import is intentionally blocked. Its new sector anchor resembles VIP, so the classifier fingerprints the unchanged executable and returns `UNSUPPORTED_RETAIL_RELOCATED_LAYOUT` instead of incorrectly recording it as VIP. Keep using the original Retail ISO as the build source. Fresh-extraction preflight will reject the unsupported relocated input before clearing a current workspace.

## Current music build

The active Retail workspace's complete compiled contents were verified against active editable files: **15,100 ASSETS records and 2,232 STREAMS records**, including matching manifest names. No songs were removed and the active workspace was not changed.

| Quantity | Bytes |
|---|---:|
| Padded ASSETS | 1,351,626,752 |
| Padded STREAMS | 1,220,253,696 |
| Shared expanded budget | 3,381,344,256 |
| Remaining | 809,463,808 (771.96 MiB) |

Separate test output: `MC3_Retail_Expanded_Music_Test.iso`.

SHA-256: `530066993e82e60a80b0464981545e5ef9bbf71627713abbcb0a1131deacf9c0`.

Automated source-content, archive read-back, manifest, ISO9660/UDF integrity, image-size and protected-byte checks passed. The source/compiled input hashes remained unchanged during construction. Original and existing working ISOs were preserved.

Evidence: `Retail_Expanded_Build_Verification.json` / `.log` and `Retail_Expanded_Capacity_Diagnostic.json`. The actual output also passed the classifier's anti-misidentification check.

Fifty-seven focused regression tests passed: 36 capacity/routing/report tests; 4 Retail relocation/classification tests; 5 legacy preservation/authentication tests; 1 GUI build regression; 11 workspace restart regressions. These are not game runtime tests.

## Next runtime validation

The user has reported successful game load/play, all music and cinematic intros for this image. The absolute Retail archive/decoder limits remain unknown; the low-offset policy is conservative, not proof that the v1.1-A boundary behavior applies to Retail. Further changed inputs and untested game modes require their own validation.

Restart the GUI before rebuilding so it uses **Retail USA expanded**. A GUI instance left open before this update will still submit the old strict layout. Do not select the relocated test output as an extraction/build source; select `Midnight Club 3 - DUB Edition Remix (USA).iso`.
