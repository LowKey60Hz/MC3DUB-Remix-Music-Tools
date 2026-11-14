# Loading-screen RAW limit findings — 2026-11-13

## Original Retail evidence

Read directly from ASSETS.DAT inside the untouched Retail USA ISO, authenticated against trusted full-image SHA-256 `de199f7e7f57b7cb603a129217f7482d50644fd66558450dfeb5612857b732f9`. Source filesystem/archive extent checks passed. The active editable ASSETS folder was not used as the original reference.

- 18 original loading-screen filenames, represented by 26 archive records.
- Duplicate records for a given slot have identical decoded sizes and SHA-256 hashes.
- Smallest decoded file: slot 14, **169,302 bytes** (165.33 KiB).
- Largest decoded file: slot 2, **291,904 bytes** (285.06 KiB).
- Original records exactly at 460,800 bytes: **0**.
- Original records above 460,800 bytes: **0**.

The detailed 18-slot table is in `Retail_Original_Loading_Audio.md`; full record offsets, stored sizes, decoded sizes, hashes and header observations are in `Retail_Original_Loading_Audio.json`. Compressed bytes stored inside Dave are reported separately from the decoded RAW length to avoid comparing different quantities.

## Interpretation

The stock assets do not demonstrate a 460,800-byte boundary. They also do not prove that larger files are supported. Their largest observed size is an example shipped by the game, not a discovered buffer capacity or maximum.

The earlier approximately 6.7 MB conversion was rejected by the tool before being tested in the game. It established enforcement of the guard, not engine rejection. Custom loading music has user-reported PCSX2 passes, but no controlled size test above the tool cap has been established by this investigation.

At the current converter's known output format (24,000 Hz, mono, PCM16), output uses 48,000 bytes per second. Thus the policy cap equals 9.6 seconds. MP3/WAV input byte size has no universal equivalent: decoded duration and conversion format determine RAW length. Original sample parameters are not established merely by the .raw filename or file length; format-equivalent durations in the JSON are explicitly conditional.

The GUI and converter wording now say **current tool cap: 450 KiB (460,800 bytes)** and distinguish it from an unverified game-engine maximum. The numerical cap and conversion behavior were not relaxed. No source audio, slot, archive, or ISO was modified.

## Next research step

Use isolated runtime probes with the established output format and known audible test content. Begin just above the cap (for example, 12 seconds = 576,000 bytes), compare with a working short control, and verify the game actually selects and plays the probe slot. Keep converted byte counts and archive read-back evidence. A later failure needs separation of per-file size, total simultaneously loaded audio, selection/loop behavior, and available game memory before naming an engine maximum. Longer duration alone does not prove a universal byte-size ceiling, and moving the tool cap without runtime evidence is not justified by stock sizes alone.
