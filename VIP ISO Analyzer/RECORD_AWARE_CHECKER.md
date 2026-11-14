# Record-aware capacity checker — 2026-11-13

## Integration update

Record/profile-capacity gates are now integrated into the GUI after compilation and in the profile engines before copying. A dedicated v1.1-A compiler and engine produced a verified output byte-identical to the user-tested expanded ISO. See `GUI_BUILD_INTEGRATION.md` for the current workflow and validation. The standalone API description below remains applicable; statements describing integration as future work are historical.

Implemented in `UI Custom Gameplay Music Tools/supporting_tools/vip_capacity.py`. The checker is standalone; the GUI and ISO builders have not been enabled or changed.

## Current behavior

- Checks shared first-layer capacity, sector padding and unsigned size-field bounds.
- When archive paths are supplied, reads supported `Dave` ASSETS and `Hash` STREAMS headers and entry tables. Checks table boundaries, record ranges, stored/decoded size consistency, duplicate STREAMS hashes and unsupported partial payload overlaps. Exact shared payload aliases are counted rather than rejected.
- Reports maximum live offset/end, high/near-boundary records, large decoded resources, empty/directory pointers and trailing bytes. Does not decompress or verify payload contents, decode all filename metadata, inspect nested archives or prove gameplay compatibility.
- Uses 2,147,481,600 bytes as a conservative **live-payload-end ceiling**, based on the passing below-boundary control and failing high-offset loading probe. This is not an absolute game limit or an outer archive-size cap. STREAMS uses the same conservative low-offset policy; high-offset STREAMS support has not been tested.
- Permits larger outer archive lengths under the record policy when live data and metadata pointers remain low and shared capacity fits. Unknown source versions still require profile validation. A source hash match verifies the known reference, not arbitrary replacement contents.
- Blocks live ranges past the conservative ceiling, large untested decoded resources, and high empty/directory pointers. Blocks malformed/unsupported indexes. A passing policy result is not permission to build.
- Numerical size-only input retains the outer-size fallback because record placement is unknown.

## Results on the actual research archives

| Archive | Outer bytes | Maximum live end (exclusive) | Record policy |
|---|---:|---:|---|
| Successful baseline | 1,805,909,737 | 1,805,909,737 | Pass |
| Below-boundary control | 2,147,481,600 | 2,147,479,705 | Pass |
| Failed high-offset probe | 2,154,035,200 | 2,154,033,305 | Block: 26 risky records |
| Successful size-only probe | 2,154,035,200 | 1,805,909,737 | Pass |

All 2,214 actual STREAMS records pass the current index/range policy. Full current evidence is `Boundary_Probes/Record_Aware_Capacity_Results_v2.json`; these checks use the trusted source ISO fingerprint. The CLI was also exercised on the successful size-only archive (`Size_Only_Record_CLI_Check.json`, no source fingerprint supplied in that invocation).

Twenty-two tests passed for arithmetic boundaries, real-size-versus-live-offset classification, read-end crossings, malformed/truncated indexes, out-of-bounds records, duplicate hashes, overlap/alias handling, large decoded resources, changing files, inspection mismatches and CLI error/fallback behavior. Large synthetic lengths are simulated in metadata tests; no multi-gigabyte test fixtures are written.

## Using the checker

From the project root:

```powershell
python ".\UI Custom Gameplay Music Tools\supporting_tools\vip_capacity.py" --assets ".\VIP ISO Analyzer\Boundary_Probes\ASSETS_above_2GiB_size_only.dat" --streams ".\VIP ISO Analyzer\VIP_v11A_STREAMS_Test.dat" --source-iso ".\Base ISO's\Midnight Club 3 VIP v1.1-A.iso"
```

`--report NEW_PATH.json` saves a new report without overwriting. Size-only scenarios still accept `--assets-bytes` and `--streams-bytes` in place of archive paths. Mixed path/numerical inputs inspect only the provided archive.

Exit codes: 0 = size/record policy fits; 2 = exceeds layout/size fields; 3 = unsupported source reference; 4 = record policy or conservative size-only fallback blocks; 5 = malformed/unsupported archive index. A zero exit code without `--source-iso` still labels the layout assumption unverified. No exit code certifies runtime support.

## Importable API and report fields

`assess_archives(assets_path, streams_path, source_sha256=None)` reads the actual indexes. `inspect_archive(path, 'ASSETS' or 'STREAMS')` exposes inspection results. `assess(assets_bytes, streams_bytes, source_sha256=None)` remains the numerical fallback API. Callers can pass fresh matching inspections as `assets_index=` / `streams_index=`; stale or fabricated reports must not be reused as authorization.

- `fits_assumed_layout`: arithmetic capacity only.
- `passes_size_policy`: layout plus applicable record/fallback policy. Separate source-profile checks are still required.
- `assets_policy_basis` / `streams_policy_basis`: `LIVE_RECORD_INDEX` or `OUTER_SIZE_FALLBACK`.
- `assets_live_end_policy_cap_bytes`: conservative end-of-live-data ceiling.
- `max_assets_allocated_with_these_streams`: conditional outer allocation limit from geometry, including any padding; not usable high-offset content capacity.
- `assets_live_offset_headroom_bytes`: distance from the aligned maximum live end to the conservative live-end ceiling. Does not measure reclaimable internal gaps or guarantee that an archive can be extended in place.
- Legacy `max_assets_within_size_policy_bytes`, `assets_tested_size_policy_cap_bytes` and `assets_growth_within_size_policy_bytes` are numerical-fallback values only; they are null for inspected ASSETS to prevent misleading growth figures for padded archives.
- `within_tested_size_envelope`: informational outer-size comparison only; the failed high-offset image has the same outer size as the passing size-only image. It must never be used as a build gate.
- `game_maximum_bytes`: remains unknown/null.

## Next integration work

Run this check after archive compilation and before ISO copying. Require supported source geometry, successful archive-content verification and record policy. Present physical capacity and record-placement risk separately. The v5 ASSETS compiler's original allocation cap and exact-size experimental ISO builder restrictions still need separate research-only generalization; this checker does not lift them.

Future VIP builds need new profile/layout validation and actual compressed archive records checked. Raw source-folder size alone cannot predict compression and record offsets. No new ISO was created during this implementation.
