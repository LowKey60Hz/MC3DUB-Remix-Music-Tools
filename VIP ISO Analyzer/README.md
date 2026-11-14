# MC3 VIP ISO Analyzer — portable project snapshot (2026-11-12)

This ZIP contains the available analyzer scripts, standalone VIP v1.1-A extractor, all three experimental Dave archive builders, dave.py, and the existing JSON/Markdown reports.

## Latest validated result

Experimental Builder **v3** (`MC3_VIP_v11A_Experimental_Builder_v3.py`) rebuilt an **unchanged** VIP v1.1-A ASSETS.DAT:
- 19,328 archive entries; 17,471 file records; 15,946 unique extracted files.
- 17,471 original compressed/uncompressed payloads reused.
- Rebuilt archive: 1,808,326,377 bytes, 279 bytes below the original 1,808,326,656-byte allocation.
- Builder verified all 17,471 records; separate `dave.py` extraction and SHA-256 comparison verified all 15,946 files identical.
- **No PCSX2 boot test yet. No modified-music archive has been validated.**

Builder v1 and v2 are retained for historical experiments; **use v3** for continued research. Do not patch a production ISO without further validation.

## Files NOT included

The original VIP v1.0-C / v1.1-A ISOs, original `ASSETS.DAT`/`STREAMS.DAT`, the rebuilt `VIP_v11A_ASSETS_Experimental.dat`, and the multi-GB extracted directories were not available in this session and are NOT in the ZIP. Transfer those from the previous PC separately if needed.

## Expected working folder layout for v3

```
VIP ISO Analyzer/
  MC3_VIP_v11A_Experimental_Builder_v3.py
  VIP_v11A_Archive_Entry_Report.json       # included
  dave.py                                  # included
  VIP_v11A_Extraction_Test/
    ASSETS.DAT                             # transfer separately
  VIP_v11A_ASSETS_Decompiled/              # transfer separately, or extract from ASSETS.DAT
  VIP_v11A_ASSETS_Experimental.dat         # output; do not pre-create
```

## Commands (PowerShell, in working directory)

Extract source assets (only if the decompiled directory is missing):
```
py .\dave.py X ".\VIP_v11A_Extraction_Test\ASSETS.DAT" -o ".\VIP_v11A_ASSETS_Decompiled"
```
Preflight (read-only):
```
py .\MC3_VIP_v11A_Experimental_Builder_v3.py
```
Experimental rebuild and verify (requires the source archive and extracted folder):
```
py .\MC3_VIP_v11A_Experimental_Builder_v3.py --build --verify
```
The builder refuses to overwrite an existing output; rename or remove an old *experimental* output first. Use Python 3.9+ (3.10+ recommended).

## Safety

The included report contains metadata about game assets, but not the game files themselves. The scripts are research tools and have not been validated for modified archive game compatibility. Preserve original ISOs and backups.
