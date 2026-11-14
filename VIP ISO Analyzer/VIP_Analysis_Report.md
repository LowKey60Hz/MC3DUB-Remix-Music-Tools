# MC3 VIP ISO Compatibility Report

Diagnostic only. Does not establish that an ISO is compatible or bootable.

## Input images

| Property | Known working | New candidate |
|---|---|---|
| Path | `C:\Users\PCS Admin\Desktop\Base ISO's\Midnight Club 3 VIP v1.0-C.iso` | `C:\Users\PCS Admin\Desktop\Base ISO's\Midnight Club 3 VIP v1.1-A.iso` |
| Bytes | `8539963392` | `8539963392` |
| 2048-byte sectors | `4169904` | `4169904` |
| SHA-256 | `906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c` | `b792163c131b57d76f6ebff99a0e0029f67f653309c97e02a136c3767f2c839d` |

## ISO9660

- **Detected:** `True` → `True`
- **Volume ID:** `MC3REMIX` → `MC3REMIX`
- **Volume sectors:** `2084960` → `2084960`
- **Root extent:** `261` → `261`

## Filesystem and archive layout differences

| File | Old sector / bytes | New sector / bytes |
|---|---|---|
| `/ASSETS.DAT` | 928161 / 1729191936 | 928161 / 1808326656 |

## Other changes

- **image / sha256:** `906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c` → `b792163c131b57d76f6ebff99a0e0029f67f653309c97e02a136c3767f2c839d`

## Interpretation

- A different SHA-256 alone does not prove a layout change.
- Matching file extents do not prove matching file contents.
- ISO9660 directory records may not describe all UDF-visible content.
- UDF marker detection is not full UDF filesystem validation.
- Layer boundaries, protected sectors, archive internals and profile-specific rules require integration with existing MC3 scripts.
- Do not modify working extractor/builder validation based only on this report.

## Warnings

None.

## Existing MC3 tool compatibility checks

| Check | v1.0-C | v1.1-A |
|---|---|---|
| `physical_sector_count` | PASS | PASS |
| `layer_pvd_16` | PASS | PASS |
| `layer_pvd_2084960` | PASS | PASS |
| `udf_partition` | PASS | PASS |
| `root_directory` | PASS | PASS |
| `archive_TEXTURE.DAT` | PASS | PASS |
| `archive_STREAMS.DAT` | PASS | PASS |
| `archive_BANKS.DAT` | PASS | PASS |
| `archive_ASSETS.DAT` | PASS | PASS |
| `archive_contiguity` | PASS | PASS |
| `archive_layer_boundary` | PASS | PASS |
| `manifest_reserved_zero` | PASS | PASS |
| `fits_old_vip_archive_region` | PASS | FAIL |
| `matches_v10c_layout` | PASS | FAIL |
| `matches_v10c_sha256` | PASS | FAIL |

- Expected current extractor classification for candidate: **`UNSUPPORTED_MANIFEST_FREE_LAYOUT`**.
- Old VIP builder archive region exceeded by candidate: **79,134,720 bytes**.
- The current builder also uses source-path equality to decide whether a VIP source is modified; a renamed original may be incorrectly treated as modified.
- This report does not authorize bypassing signature, UDF, manifest, sector, or SHA-256 validation.
- A new version-specific archive capacity and trusted reference must be verified before patching.

### Failed candidate checks

- **fits_old_vip_archive_region**: candidate end exclusive=1811133; v1.0-C end exclusive=1772493; overrun=38640 sectors
- **matches_v10c_layout**: Exact archive sector/size match required by current manifest-free extractor
- **matches_v10c_sha256**: Current trusted VIP SHA-256; skipped hash cannot establish a match
