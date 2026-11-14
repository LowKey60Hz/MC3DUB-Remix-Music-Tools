# Two-Win skip-win2 runtime result

## Latest: empty Win/Lose runtime confirmation

2026-11-14: User confirmed a no-song Win/Lose ISO runs normally and plays no song after a race win or loss. This is user-observed evidence that the implemented empty-category handling provides silence without the earlier empty-playlist crash in the tested image. Exact image identity, counts, and cold-boot details were not supplied. One-song Win/Lose playback remains the outstanding runtime case. Earlier statements that zero-song runtime testing was pending are historical.

## Post-implementation two-song confirmation

2026-11-14: Following the UI/removal update, user confirmed both songs play in a two-song ISO and the UI lists them correctly. This is user-observed playback and UI evidence; the exact image identity and build/removal route were not specified, so existing per-image reports are not relabeled. One-song and zero-song Win/Lose playback remain unreported. See ../WIN_LOSE_REMOVAL_UPDATE.md.

## Latest: three-entry runtime observations (2026-11-14)

User chose five tests instead of the suggested ten. The exact allocation of that count between images and race-entry/post-win events was not separately specified; no additional test count is required to record this evidence.

| Image | Playlist | User-reported playback at race transitions and after wins |
|---|---|---|
| ABA | Know Good, Kendrick, Know Good | Know Good only |
| ABB | Know Good, Kendrick, Kendrick | Both Know Good and Kendrick |

Both images have identical audio mappings and identical STREAMS archives. Each image changes only the 24 Win playlists in decoded ASSETS relative to the swapped control. Repeated references survived compiler round-trip.

ABB demonstrates user-observed two-song variety with the three-entry A,B,B arrangement in these tests. ABA did not demonstrate variety. Because both songs played in ABB, a universal fixed-second-entry or fixed-final-entry selector does not explain the full observed set. The ABA-only result and the earlier two-entry position effect do not establish the precise selection algorithm; event sequence, cold boots, save-state use, and silence were not separately specified.

Treat A,B,B as a supported candidate workaround for the observed Retail events, not proof of the general selector or validation across other profiles, Lose playlists, song counts, or more than two distinct songs. Production Win/Lose code remains unchanged. Per-image reports and ../Two_Win_Run_02_ThreeEntry/comparison_results.json now record these user observations. No further runtime count is imposed. A future implementation should preserve two distinct encoded payloads while deliberately retaining the repeated third playlist reference; that remains a separate production change.

## Latest: local playlist-order comparison (2026-11-14)

Follow-up preparation: ABA and ABB three-entry images have now been built and verified in ../Two_Win_Run_02_ThreeEntry. A = Know Good/win1; B = Kendrick/win3. Compiler round-trip preserved the repeated references exactly. Both images retain byte-identical STREAMS from the swapped control, and only the 24 Win playlists change in decoded ASSETS. Production remains unchanged. See that folder's TEST_INSTRUCTIONS.md and per-image result.json. Runtime results for these three-entry images are pending. The proposal paragraph below records the earlier state before those builds.

User reports the local swapped control plays only Kendrick Lamar - Squabble Up when entering races and winning races. The local reversed-playlist image plays only Know Good - Feeling Myself for both event types.

| Local image | Playlist order | Song heard | Selected position |
|---|---|---|---|
| Swapped control | win1 (Know Good), win3 (Kendrick) | Kendrick only | Second |
| Swapped/reversed | win3 (Kendrick), win1 (Know Good) | Know Good only | Second |

The audio mapping is identical between images and STREAMS was verified byte-identical. Only the 24 Win playlists differ in decoded ASSETS. This supports a playlist-position effect in the reported events and shows win1 can play when listed second. A fixed win3-only explanation does not account for this comparison. The earlier slot-name/list-index confounding is resolved for these observations.

Counts, cold-boot repetitions, emulator save-state use, and silence were not separately specified. The exact selection algorithm, a minimum-three rule, and reliable two-song variety remain unvalidated. Race-entry playback is user-observed; its internal engine trigger has not been traced.

Next proposed isolated comparison: retain the same payloads and test three playlist entries with a duplicate reference (A,B,A versus A,B,B), keeping num_songs: 3. First confirm the compiler preserves duplicate references. This tests whether an additional entry permits both tracks; it does not by itself prove why two-entry selection favors the second entry. Log individual events across cold boots and avoid transferring emulator save states between images. No three-entry image has been built and no production change is authorized by these findings alone.

Local machine-readable results are updated in ../Two_Win_Run_01/swapped_result.json and ../Two_Win_Run_01_Order/order_result.json. Historical observations below remain as provenance and are superseded where the latest controlled comparison provides new evidence.

## Historical observations

User reported only Know Good - Feeling Myself plays. The verified mapping is Kendrick Lamar - Squabble Up in win1 and Know Good - Feeling Myself in win3. Therefore win3 is playable in the tested path, but both-song playback is not confirmed.

The number and types of transitions, repeated cold boots, and possible silent selections remain unspecified. Do not infer that win1 is impossible to select from this observation alone, or that the original win2 issue is resolved. No production slot-assignment correction has been implemented.

If repeated events consistently play only Know Good, the next discriminating test is to swap the two songs between win1 and win3 while keeping the same two-entry playlists. If only the new win3 song plays, that supports a slot/selection issue; if Know Good alone still plays, inspect song content/encoding and playback identification. This is a proposed test, not yet built. A loader/selection trace may still be needed.

## Event count clarified

User played three races and transitioned into a race twice. Across these reported events, only Know Good was heard. Race outcomes, repeated cold boots and silent events were not specified, so do not count all five as confirmed Win-playlist selections. The two-song workaround remains unvalidated.

## Swapped-song result

User reported Kendrick Lamar - Squabble Up now plays. In the swapped ISO Kendrick is mapped to win3, and Know Good to win1. The encoded payloads were not changed; every ISO byte except the two STREAMS offset/size pairs was verified identical. In the first test only Know Good (then win3) was reported across three races and two race-entry transitions. The swapped observation follows win3 and proves both encoded tracks can play in that slot. It points toward slot/playlist selection rather than one broken encoded source, but does not identify a hardcoded win3 rule or prove win1 can never play. The swapped test did not explicitly report whether any other song or silence occurred.

The skip-win2/two-entry workaround remains unvalidated for two-song variety. A discriminating next experiment would keep the swapped audio mapping and reverse only the playlist order to win3,win1 while retaining num_songs: 2. Hearing only the second listed entry would then point toward list-index selection. This proposed experiment has not been built; production code remains unchanged.
