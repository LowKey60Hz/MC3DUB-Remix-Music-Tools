# VIP v1.1-A expansion test builder

## User-reported PCSX2 results — 2026-11-13

For `MC3_VIP_v11A_Expansion_Experimental.iso`, the user confirmed successful boot, custom song playback, garage music, loading-screen music, and win/lose music. These are user-observed runtime results, separate from automated build verification.

The user subsequently confirmed story, tutorial, and reward cinematics also play. All planned runtime categories for this experimental image have user-reported passes. Broader game coverage and GUI integration remain pending. These results do not establish general compatibility beyond this tested image and reported workflows.

The isolated builder is `build_v11a_expansion_test.py`. Production GUI/builders were not changed.

## Completed checks (2026-11-13)

- Full original ISO SHA-256 matched the trusted v1.1-A reference.
- All 2,214 experimental STREAMS records matched the active STREAMS files, with no hash collisions or manifest source-name differences.
- All 17,471 experimental ASSETS records matched active ASSETS files.
- ISO9660/UDF source geometry, manifest reservation, and the exact inspected proposal's sizes and end sector passed preflight.
- Four fault-injection tests passed for the preservation verifier: allowed changes, forbidden changes across protected gaps, image truncation/growth, and invalid change ranges.
- **Expanded experimental ISO built and read-back verified on 2026-11-13.** Archive payload hashes and padding, ISO9660/UDF metadata, embedded manifest, unchanged image size, and every byte outside permitted changes passed. This includes preservation of the entire second layer. The user subsequently reported passes for all planned PCSX2 categories listed above.

Output: `MC3_VIP_v11A_Expansion_Experimental.iso` (8,539,963,392 bytes).

SHA-256: `3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3`.

Machine-readable build evidence: `Expansion_Builder_Result.json`. Original reference images were opened read-only.

The exact 51,695,616-byte extension range is identical in both VIP references. Three 128-byte samples match existing Flash vehicle-menu PCK contents (125, 375, and 502 files respectively). The known retail profile's ASSETS region ends at sector 2,074,717, which is also the start of the zero-filled manifest reservation. These observations support a leftover-data hypothesis but do not establish runtime safety. Raw executable searches found no exact little-endian constants for the tested boundaries; that is not code-flow analysis and does not rule out computed accesses. Full evidence: `Extension_Characterization.json`.

## Commands

From this folder, run the preflight again:

```powershell
python .\build_v11a_expansion_test.py
```

The command used to create the separate experimental image (it now refuses a repeat because the output exists):

```powershell
python .\build_v11a_expansion_test.py --build
```

Output: `MC3_VIP_v11A_Expansion_Experimental.iso`. Requires approximately 8.54 GB free space. Existing output or `.partial` files are never overwritten. A failure may leave a partial file for inspection.

The builder preserves the observed full-width UDF ASSETS extent encoding. It embeds the matching STREAMS manifest. Before finalizing a test ISO, it checks archive payload hashes and padding, output metadata, manifest integrity, unchanged image size, and every byte outside the explicit archive, metadata, and manifest change ranges. These checks include preservation of the entire second layer. They do not prove the game tolerates relocated archives or overwritten leftover data.

For PCSX2 testing: confirm boot, intro playback, menus/garage, custom gameplay music, win/lose and loading music, and multiple story/tutorial/reward cinematics. Record failures against the experimental image and retain all originals.
