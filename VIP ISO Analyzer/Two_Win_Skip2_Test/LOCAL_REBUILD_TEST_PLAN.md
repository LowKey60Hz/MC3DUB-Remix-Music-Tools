# Local rebuild runtime plan

The two staged MP3 sources and their locally regenerated RSM payloads match the historical SHA-256 values in result.json. The local builds use a freshly extracted original Retail source; do not assume complete ISO equality with the older custom workspace build. Use each new build report to authenticate its corresponding image.

Production Win/Lose code remains unchanged. Generated local data belongs in Two_Win_Run_* folders; preserve historical reports here.

## Images and mappings

1. Two_Win_Run_01/MC3_Retail_Two_Win_1_and_3.iso: win1 = Kendrick; win3 = Know Good; playlist win1,win3.
2. Two_Win_Run_01/MC3_Retail_Two_Win_1_and_3_SWAPPED.iso: win1 = Know Good; win3 = Kendrick; playlist win1,win3. This must differ from image 1 only at the two STREAMS offset/size pairs.
3. Two_Win_Run_01_Order/MC3_Retail_Two_Win_SWAPPED_REVERSED.iso: same mapping as image 2; playlist win3,win1. STREAMS must match image 2 exactly; all decoded ASSETS except the 24 Win playlist records must match.

All three local builds completed automated verification on 2026-11-14. Their respective result.json, swapped_result.json, and order_result.json reports exist. No runtime observations have been collected for these new images.

| Image | SHA-256 |
|---|---|
| Baseline | 41834214bd9875939ba173cf80604481b3ba166605ba9b359a86ab81a95fb7a5 |
| Swapped | 5b9259593ef8cc7180fe13f23e90d5a52453525cc658faf01377e044428dd7e4 |
| Swapped/reversed | 958050463eaaadb1d2ade7ab83bf77b10c3010283f36f73cb0a8bdeb368d8af3 |

The reversed build was finalized with finalize_two_win_order_test.py after the sandbox denied the final hard link. That finalizer rechecked source authentication, exact decoded playlist reversal, unchanged other assets and STREAMS, all ISO archive extents, protected bytes, embedded manifest, and the original production-engine hash before publishing the final filename.

## Runtime observations

Cold-boot each image, without restoring emulator save states from another image. First confirm that the two recreated control images reproduce the old behavior. For the swapped control and reversed-order comparison, use comparable race types/outcomes and multiple cold boots.

Record one row per event:

| Image | Cold boot # | Race/event | Outcome | Transition type | Song heard | Silence/other notes |
|---|---|---|---|---|---|---|
| | | | | | | |

Count race wins separately from race-entry transitions; a race-entry event alone is not confirmed to invoke the Win playlist. Record Lose playback and unexpected changes as well.

If the reversed image plays Know Good while the swapped control plays Kendrick, the observation follows the second listed entry. If Kendrick continues, the observation follows win3 or another factor. Hearing both or silence is also useful evidence. No short sequence establishes a random algorithm, minimum-three rule, or a production fix.
