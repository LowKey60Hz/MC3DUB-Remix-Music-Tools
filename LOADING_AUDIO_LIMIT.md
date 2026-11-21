# Loading-screen audio limit

The converter, GUI adapter and batch adapter accept at most **455,680 bytes (445 KiB)** per converted loading-screen RAW. This policy applies to Retail USA, VIP v1.0-C and VIP v1.1-A. It does not limit the MP3/WAV input file's byte size.

Output is headerless signed 16-bit little-endian PCM, 24,000 Hz, mono: 48,000 bytes/second. The limit is 227,840 samples, or 9.4933333333 seconds. UI duration is approximate (9.493 seconds); actual converted size determines acceptance, including resampling rounding. Files are rejected rather than automatically trimmed.

The isolated Retail PCSX2 probe sequence produced user-reported success at 455,680 bytes and a crash at the next sample, 455,682 bytes. Each probe replaced all 18 slots, including duplicate archive records, and preserved archive offsets and ISO metadata. This is an observed Retail-tested boundary adopted as policy across supported versions; it is not a traced engine-buffer specification or independent boundary validation of every VIP executable.

The previous 460,800-byte / 450 KiB cap has been lowered by 5,120 bytes. Existing staged or extracted RAWs are not automatically trimmed or replaced; reapply affected loading-screen assignments to validate them under the new cap. No ISO is rebuilt automatically.

Validation: `VIP ISO Analyzer/test_loading_audio_limit.py` checks exact-cap acceptance, one-sample-over rejection, resampling at 48 kHz, preservation of an existing output on rejection, GUI application at the cap, and no slot changes when mixed GUI/batch inputs include oversized audio. All five tests passed when this policy was integrated.
