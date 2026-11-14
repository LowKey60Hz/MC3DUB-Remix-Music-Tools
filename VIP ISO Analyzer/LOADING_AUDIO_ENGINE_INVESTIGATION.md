# Loading-screen audio size investigation

## Subsequent runtime evidence — corrected result

FINAL SEARCH UPDATE: The subsequent all-slot Retail synthetic search reached 455,680 bytes working and 455,682 bytes crashing, adjacent 16-bit samples. The working size is exactly 445 KiB, not 450 KiB. Both payloads have the same compressed length and preserve all original offsets. See `Loading_Audio_Probes/OBSERVED_BOUNDARY.md` and `Observed_Boundary.json`. This is a user-observed boundary for these probes, not yet a traced buffer limit or universal per-file maximum; repeat endpoint tests, one-slot isolation and real-music/VIP validation remain pending. Production code is unchanged.

LATEST CORRECTION: The user subsequently reported that the 460,800-byte control also crashes. Earlier at-cap loading-screen successes are superseded. Current evidence is playback at 432,000 bytes and crashes at 460,800 and 460,802 bytes. The inclusive 460,800-byte production cap is therefore not a verified safe limit. Do not remove or increase it; production code remains unchanged as requested. Re-confirm the lower control and investigate between 432,000 and 460,800 bytes before selecting a supported cap. All-slot aggregate effects and the untraced loader remain caveats. The chronological paragraph below describes an intermediate conclusion that this correction supersedes.

After this initial static investigation, isolated Retail probes were built with original archive offsets and filesystem metadata preserved. User reported playback at 432,000 bytes and a loading screen that loads at 460,800 bytes. The initially reported 460,802-byte pass was retracted: the wrong ISO had been loaded. On retesting the intended above-cap ISO, the user reported a crash (typing 460,803 bytes; the actual generated probe is 460,802). This supports the existing cap as a runtime-backed Retail safeguard; exact engine mechanism and fully repeatable boundary remain unverified. Both boundary probes have identical compressed lengths, but replace all 18 slots, and at-cap playback was not explicitly reported. Preserve the cap and repeat the identified at-cap/above-cap pair before a stronger maximum claim. The initial findings below describe evidence available before these runtime probes.

Date: 2026-11-13. Scope: read-only production-code review, original Retail asset survey, and bounded Retail executable survey. No converter, UI, archive, ISO, or size restriction changed during this investigation.

## Finding

**460,800 bytes is a verified tool policy, not a verified game-engine maximum. The actual supported maximum remains unknown.** There is insufficient evidence to remove or increase the production cap. Longer files are plausible candidates for controlled testing, not established supported inputs.

## Original Retail assets

Source: `Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso`, SHA-256 `de199f7e7f57b7cb603a129217f7482d50644fd66558450dfeb5612857b732f9`. The existing original survey authenticated that source and decoded records directly from its ASSETS.DAT, avoiding the modified working extraction. Detailed hashes and archive offsets are in `Retail_Original_Loading_Audio.json`.

| Slot | Decoded RAW bytes | Stored archive bytes | Records |
|---:|---:|---:|---:|
|1|256,204|248,120|2|
|2|291,904|284,297|1|
|3|259,118|253,380|2|
|4|242,452|232,409|2|
|5|270,812|262,403|1|
|6|244,270|240,400|2|
|7|247,890|231,534|1|
|8|252,876|247,635|1|
|9|255,304|242,784|1|
|10|237,986|229,164|2|
|11|243,734|239,182|1|
|12|236,188|221,955|1|
|13|253,224|230,451|1|
|14|169,302|163,107|1|
|15|230,344|219,837|1|
|16|261,544|248,075|2|
|17|223,708|210,607|2|
|18|228,264|218,764|2|

There are 18 unique slot names and 26 archive records. Duplicate records of each slot decode to identical content. Largest: slot 2, 291,904 bytes (285.06 KiB). Smallest: slot 14, 169,302 bytes (165.33 KiB). None equals or exceeds 460,800. The shipped sizes neither establish this cap nor demonstrate that larger files work. These files have no RIFF/WAVE header; their original PCM rate is not established from names and lengths alone. Durations obtained by dividing these sizes by 48,000 are conditional on the current custom format.

## Current implementation

`supporting_tools/convert_loading_raw.py` produces little-endian signed 16-bit mono PCM at 24,000 Hz using soundfile, NumPy, and SciPy. The historical FFmpeg description matches its output format, but the active converter is Python based. The output is headerless RAW, not RSM. The cap is checked after conversion and before the output is committed.

The GUI adapter `gui/loading_apply.py` independently enforces 460,800 bytes and converts selected sources before replacing slot files, with rollback on copy errors. The batch adapter `supporting_tools/customize_loading_screens.py` also defines the cap. Raising one constant would not consistently change the workflow.

At this format, output bytes = output samples × 2 and duration = bytes / 48,000. The cap permits 230,400 samples, or 9.6 seconds. There is no universal MP3/WAV input-size ceiling equivalent to this output cap: compressed bitrate, WAV format, channels, rate, and metadata affect input size. Decoded duration and resampling determine RAW size. Exact boundary checks must use actual converted sample counts because resampling can round upward. Input duration is an estimate; converted byte count is authoritative for the tool.

## Archive and executable evidence

The Dave archive stores per-record name offset, data offset, decoded size, and stored size in four unsigned 32-bit fields. Original loading files are compressed and have differing decoded and stored lengths. The table therefore describes variable-length files, not an observed fixed 460,800-byte slot. A rebuild must update metadata and payload placement coherently. Those field widths do not prove the engine accepts enormous allocations, and archive layout capacity is separate from an audio-loader buffer limit.

The read-only `inspect_loading_executable.py` reads SLUS_213.55 directly from the Retail ISO and writes metadata only. Results: `Retail_Loading_Executable_Survey.json`. Executable SHA-256: `1b237ade5cafaf8ddd9fd049f40d81eb46f38f2600a8f1c7273d4f836973fe9d`; 5,264,872 bytes; ELF32 little endian; no ELF symbol-table sections. The string `audio/Loadscreen/%d` occurs at file offset 0x499570, mapped virtual address 0x6394f0. A candidate MIPS LUI/ADDIU address-construction pair occurs at 0x1ac478/0x1ac480, destination register 6. This is a debugger starting point, not a traced loader or a confirmed function signature.

No literal little-endian 32-bit 460,800 value was found in this executable. **This does not rule out a limit:** MIPS can construct constants in instructions, derive sizes arithmetically, or use limits in other modules. The string and candidate reference have not been followed through allocation, decompression, transfer, or playback. No fixed audio buffer size, read limit, truncation rule, or supported maximum has been verified. VIP executables differ, so findings cannot automatically transfer to them.

## Risks of longer replacements

Possible unverified constraints include a fixed destination buffer, allocation pressure in EE or IOP memory, audio-transfer capacity, sample-count assumptions, and transition cleanup timing. Larger files may increase loading time or fail only under particular game states. Archive expansion and changed compression can independently exhaust a verified region or expose offset restrictions; that would not demonstrate a per-file audio ceiling. Repeated transitions may expose leaks or delayed cleanup. Music stopping when loading finishes is normal lifecycle behavior and alone does not prove a byte limit.

## Proposed controlled PCSX2 procedure — not executed

1. Preserve the known-working ISO and stock files. Use a separate research workspace and build path that can stage probe RAWs without changing or disabling production validation. Record source/build hashes, emulator version, BIOS, settings, game executable version, archive metadata, decoded and stored sizes, and total archive sizes. Avoid retaining many full probe ISOs on the space-constrained machine.
2. Establish a reproducible loading transition and identify which slot it uses. Start with one slot, updating every archive record for that name consistently. Use audible slot/time markers and identical content prefixes so actual probe playback is identifiable. Keep the other 17 slots unchanged. If the slot cannot be identified, resolve that before interpreting a pass or failure.
3. Compare probes of exactly 432,000 bytes (9 s), 460,800 (9.6 s), 460,802 (one sample above the guard), 480,000 (10 s), 576,000 (12 s), 720,000 (15 s), then 960,000 (20 s). Advance only after stable repeated passes. Use the same PCM format, amplitude, and similar signal content. Validate rebuilt records by extracting and hashing their decoded payloads. Keep archive placement and capacity within already verified bounds.
4. Cold boot each probe without save states. Repeat the same career/loading transition and then race, free roam, and garage transitions. Log clip identity, crash/stall/noise/early cutoff, and repeated-transition behavior. Confirm the control remains stable after any failure. A game reaching its menu is insufficient. A clip ending with a short loading screen is not a failed long-file test, but it also does not prove the entire clip was consumed.
5. For stronger evidence, use the EE debugger around the candidate reference to trace the actual path formatting and file-open/read/decompression calls. Record decoded size, allocation request and result, destination extent, actual read length, sample length, and any IOP/audio transfer. Follow the real call path before choosing watchpoints; do not assume register 6 is a size or buffer. Check writes against the identified allocation and investigate failures at the faulting PC. Other modules may implement the restriction.
6. If a size fails, reproduce with a passing neighboring size and separate file-size effects from archive offsets, total allocation, compression, and changed transitions. Refine the failing interval only after the failure is attributable to audio size. If one larger slot succeeds, then test all 18 enlarged slots to assess aggregate memory pressure, followed by varied transitions and repeated cold boots.
7. Repeat independently for Retail and each supported VIP executable. PCSX2 results establish a tested lower bound for that configuration, not a universal engine maximum or physical-PS2 guarantee. Hardware validation would be a separate compatibility step.

## Decision

Keep the working 450 KiB guard and its description as an unverified conservative policy. Original sizes do not justify treating it as an engine requirement. The next useful evidence is a controlled just-over-cap runtime probe plus a loader trace. Only after repeatable results should a separate change propose a supported tested limit, UI duration estimates, and consistent validation updates. No actual engine maximum can responsibly be claimed from the current evidence.
