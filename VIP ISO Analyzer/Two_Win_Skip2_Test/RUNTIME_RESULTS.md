# Two-Win skip-win2 runtime result

User reported only Know Good - Feeling Myself plays. The verified mapping is Kendrick Lamar - Squabble Up in win1 and Know Good - Feeling Myself in win3. Therefore win3 is playable in the tested path, but both-song playback is not confirmed.

The number and types of transitions, repeated cold boots, and possible silent selections remain unspecified. Do not infer that win1 is impossible to select from this observation alone, or that the original win2 issue is resolved. No production slot-assignment correction has been implemented.

If repeated events consistently play only Know Good, the next discriminating test is to swap the two songs between win1 and win3 while keeping the same two-entry playlists. If only the new win3 song plays, that supports a slot/selection issue; if Know Good alone still plays, inspect song content/encoding and playback identification. This is a proposed test, not yet built. A loader/selection trace may still be needed.

## Event count clarified

User played three races and transitioned into a race twice. Across these reported events, only Know Good was heard. Race outcomes, repeated cold boots and silent events were not specified, so do not count all five as confirmed Win-playlist selections. The two-song workaround remains unvalidated.

## Swapped-song result

User reported Kendrick Lamar - Squabble Up now plays. In the swapped ISO Kendrick is mapped to win3, and Know Good to win1. The encoded payloads were not changed; every ISO byte except the two STREAMS offset/size pairs was verified identical. In the first test only Know Good (then win3) was reported across three races and two race-entry transitions. The swapped observation follows win3 and proves both encoded tracks can play in that slot. It points toward slot/playlist selection rather than one broken encoded source, but does not identify a hardcoded win3 rule or prove win1 can never play. The swapped test did not explicitly report whether any other song or silence occurred.

The skip-win2/two-entry workaround remains unvalidated for two-song variety. A discriminating next experiment would keep the swapped audio mapping and reverse only the playlist order to win3,win1 while retaining num_songs: 2. Hearing only the second listed entry would then point toward list-index selection. This proposed experiment has not been built; production code remains unchanged.
