# Capacity limits and checker — 2026-11-13

## Current implementation: record-aware checks

The checker now inspects actual ASSETS/STREAMS indexes when paths are supplied. It classifies the passing size-only archive separately from the failed high-offset archive (26 risky records). All four research archives match the expected policy classifications, and 22 tests passed. The conservative outer-size fallback remains only for numerical inputs without an index. See `RECORD_AWARE_CHECKER.md` for the authoritative current API, limits, exit codes and evidence; earlier sections below document the progression of the investigation.

## Update: above-2-GiB size-only probe passed

The user reports successful PCSX2 boot, cinematics, main menu, free roam, music, races and garage/music in the 2,154,035,200-byte size-only probe. All live payloads remain below byte 1,805,909,737. Therefore 2 GiB is **not established as an outer archive-size maximum**. Comparison with the failed high-offset probe points more strongly toward high-offset reads. The exact engine cause remains unresolved.

The checker's outer-size block remains a conservative fallback because it does not yet inspect resource records. It must not be described as a proven game-size limit. Next implementation: inspect each live ASSETS payload's offset and end, validate the archive table/bounds, and distinguish an oversized-but-low-offset archive from an archive with unverified high-offset resources. Do not remove the existing guard based on file length alone. Follow with analogous STREAMS record inspection and shared-capacity enforcement.

## Update: 2 GiB probe results and enforced policy

The user reports that the 2,147,481,600-byte control loads into free roam, garage and plays loading music. The 2,154,035,200-byte above-boundary probe reaches menus/cinematics but crashes on continuing career. Both had passed automated preservation and payload checks.

The checker now enforces a **sector-padded ASSETS size policy ceiling of 2,147,481,600 bytes (2 GiB minus one 2,048-byte sector)**. With the original tested 1,805,909,737-byte ASSETS payload, this leaves 341,571,584 bytes (325.75 MiB) of ASSETS growth under that policy, subject also to shared capacity. This is not the larger arithmetic ceiling listed below. It does not claim all smaller arbitrary archives are compatible.

`passes_size_policy` is false at/above 2 GiB after padding, and CLI exit 4 denotes this policy failure. `max_assets_within_size_policy_bytes` and `assets_growth_within_size_policy_bytes` are the policy-aware values for future GUI use. Existing `max_assets_allocated_with_these_streams` continues to report the mathematical layout ceiling for research. Eight checker tests now pass, including a single-byte growth that rounds allocation up to the blocked boundary. Existing compiler restrictions still apply independently.

The actual engine maximum and cause remain unresolved: these probes changed both archive size and high-offset placement. Next isolation test is an above-2-GiB outer archive with all game-used record offsets kept at their successful low positions. A failure would implicate archive-size/metadata handling; a pass would strengthen the high-offset-read hypothesis. Neither outcome alone identifies a particular signed-integer code path.

## What is established

For the observed VIP v1.1-A first-layer arrangement, keeping TEXTURE and BANKS unchanged and stopping before the current manifest reservation:

| Quantity | Bytes |
|---|---:|
| Combined sector-padded ASSETS + STREAMS budget | 3,381,344,256 |
| ASSETS ceiling with current STREAMS | 2,294,034,432 |
| STREAMS ceiling with current padded ASSETS | 1,575,434,240 |
| Shared headroom for tested combination | 488,124,416 (465.51 MiB) |

These are arithmetic layout ceilings, not established runtime maxima. They are conditional on the current start sector, manifest reservation, unchanged TEXTURE/BANKS, and reuse of previously inspected carried-over space. The entire potential region up to the reservation has not been overwritten and game-tested. Other arrangements could have different capacity; crossing the manifest or changing layer geometry is a separate investigation.

The tested ASSETS payload is 1,805,909,737 bytes; the tested STREAMS is 1,087,309,824 bytes. User-reported boot/music/cinematic passes apply to that exact experimental image. They are not evidence that arbitrary archives of those sizes, or any smaller ones, work.

## Independent constraints

1. **Shared disc allocation:** each archive is rounded up to 2,048 bytes. An extra byte can consume an entire sector. Both archives compete for one budget.
2. **Archive and filesystem fields:** local Dave/Hash tooling uses unsigned 32-bit offsets/sizes. The size checker rejects allocations that cannot fit those fields or the current layout. This field width alone does not establish a game limit.
3. **Observed UDF encoding:** the current builder writes full archive lengths into one short allocation descriptor. ECMA-167 defines its bottom 30 bits as length and its top two bits as extent type. Our known-working image follows the observed MC3 layout rather than generic UDF semantics. ASSETS at/above 2 GiB changes those top bits again. That boundary is a research warning, not a proven signed-integer failure threshold.
4. **Compiler policy:** existing v5 ASSETS output is capped at 1,808,326,656 bytes. It must be generalized deliberately before producing larger probes. The experimental ISO builder is restricted to the exact tested sizes.
5. **Game/runtime behavior:** absolute ASSETS/STREAMS maxima remain unknown. File counts, name tables, individual resources, offsets and decoder behavior may impose additional constraints.

Reference: [ECMA-167, section 4/14.14.1.1](https://ecma-international.org/wp-content/uploads/ECMA-167_3rd_edition_june_1997.pdf).

## Standalone checker

`UI Custom Gameplay Music Tools/supporting_tools/vip_capacity.py` is importable for later GUI integration. No GUI or build pipeline has been enabled or changed. `assess(assets_bytes, streams_bytes, source_sha256=None)` reports padded usage, remaining/overflow bytes, each conditional ceiling, current compiler restrictions and runtime research warnings. No result authorizes an ISO write.

From the project root:

```powershell
python ".\UI Custom Gameplay Music Tools\supporting_tools\vip_capacity.py" --assets ".\VIP ISO Analyzer\VIP_v11A_ASSETS_v5_Test.dat" --streams ".\VIP ISO Analyzer\VIP_v11A_STREAMS_Test.dat" --source-iso ".\Base ISO's\Midnight Club 3 VIP v1.1-A.iso"
```

Use `--assets-bytes` / `--streams-bytes` instead of paths for hypothetical sizes. Without `--source-iso`, the checker explicitly treats the layout as an unverified assumption. With an unknown source hash, it reports unsupported source and exits 3, even if the numbers fit. Over-capacity sizes exit 2. Exit 0 means size arithmetic fits, never game compatibility. Optional `--report PATH` writes JSON without overwriting existing files. Archive path checks read the magic only; this checker does not parse or verify every payload.

The saved real-input result is `V11A_Capacity_Check.json`. Six tests cover exact capacity, sector overrun, shared budget, 2 GiB warning, unknown source and invalid/overflow inputs.

## How to establish practical supported limits

Use separate probe images, keeping original ISOs and the successful experimental image intact. First generalize research-only compilers with explicit calculated capacity, source/version validation, and 32-bit field checks. Do not simply remove the old allocation guard.

ASSETS probes with current STREAMS should target just below 2 GiB, just above 2 GiB, then the layout ceiling (2,294,034,432 bytes). STREAMS probes with current ASSETS should target its ceiling (1,575,434,240 bytes). Recompute ceilings if the other archive changes. A one-sector-over-capacity case must be rejected before any image write.

**Padding an archive is insufficient to prove high-offset access works.** Each probe must place a known game-used file beyond the boundary under test, update real archive record pointers correctly, independently verify contents, and exercise that specific resource in PCSX2. For STREAMS, play a track whose record points into the newly added tail. For ASSETS, load the specific relocated menu/game resource. Recheck the music and cinematic regression suite. Record exact image hashes, resource names, record offsets, emulator/version settings and observed results.

An observed failure must be diagnosed before naming a maximum: a bad rebuild or metadata encoding can mimic a game limit. A pass supports a tested configuration; it does not prove an absolute maximum. The GUI should ultimately distinguish **over capacity**, **fits layout but requires testing**, and **tested source/build configuration**.

## New VIP versions

A new release must be scanned afresh: source fingerprint, archive locations/sizes, TEXTURE/BANKS changes, ISO9660/UDF references, first/second-layer boundaries, cinematic extents and manifest reservation. Calculate capacity from that verified profile. Do not silently assign the v1.1-A budget to a future ISO merely because the filename or ASSETS size looks familiar.
