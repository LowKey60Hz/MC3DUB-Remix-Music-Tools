# VIP v1.1-A expansion proposal

Generated from the active STREAMS folder and the independently validated v5 ASSETS archive. This is a diagnostic proposal, not an ISO-ready layout.

## Capacity

| Input | Bytes |
|---|---:|
| STREAMS projected from 2,214 active files | 1,087,309,824 |
| Validated v5 ASSETS payload | 1,805,909,737 |
| ASSETS sector-padded allocation | 1,805,910,016 |
| Additional space beyond original v1.1-A archive region | 51,695,616 (49.3 MiB) |

STREAMS size is calculated using the current `hash_build.py` packing rules, including per-file sector padding, index size, filename order, and hash collision checks. It is not content or playback verification of a rebuilt STREAMS archive.

## Proposed sectors

End sectors are exclusive.

| Archive | Start | End |
|---|---:|---:|
| TEXTURE | 9,702 | 397,807 |
| STREAMS | 397,807 | 928,720 |
| BANKS | 928,720 | 954,583 |
| ASSETS | 954,583 | 1,836,375 |

The original archive region ends at 1,811,133. BANKS and ASSETS would move. A builder must update ISO9660 and UDF references and verify unchanged archives after relocation.

## Checks

- Fresh ISO9660 and constrained UDF allocation scans found no overlaps between this proposal and mapped protected files or directories.
- All 106 second-layer cinematic start signatures were rechecked. The proposal ends before the second-layer boundary at sector 2,084,944.
- The existing 1 MiB STREAMS.LST reservation at sector 2,074,717 is entirely zero-filled and outside the proposed archives.
- All 539,820,032 bytes checked after original ASSETS and before that reservation match the same region in VIP v1.0-C exactly. This identifies unchanged carried-over data, not its purpose or runtime relevance.
- UDF traversal flags the reference image's unusual full-width ASSETS extent length. Existing tools interpret it as a raw length; a new builder must handle that deliberately and test compatibility.

## Remaining work

The 49.3 MiB extension would overwrite part of the unidentified carried-over region. No production write is justified by these checks alone. Next, characterize that exact extension range and inspect game access/layout assumptions. An isolated test builder can then be developed with full reference hashing, metadata checks, preservation of everything outside explicitly changed ranges, and separately named output. PCSX2 boot, music and cinematic tests remain necessary.

Reproduce: `python plan_v11a_expansion.py` from this folder. Full machine-readable results: `V11A_Expansion_Plan.json`. No game files or ISOs were modified.
