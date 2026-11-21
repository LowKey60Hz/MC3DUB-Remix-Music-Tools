#!/usr/bin/env python3
# Generates an RSTM sound file for Midnight Club 3: DUB Edition and Bully
# The input type is usually meant to be ADS/SS2 but WAV is also accepted.
# Project integration: WAV input uses the Python PS-ADPCM encoder.
# The original Edness ADS/SS2 container path is retained below.

# Usage:
#     rstm_build.py  "X:\path\to\sound.ads"
#   Optional:
#     -o  | --output    <str> Path to the output file;  defaults to the input folder
#     -lf | --loopfull        Loop the entire sound file
#     -ls | --loopstart <int> Set manual loop start position in frames (28 samples each)
#     -le | --loopend   <int> Set manual loop end position in frames (28 samples each)
#       rstm_build.py  "/path/to/sound.wav"  -o "/path/to/sound.rsm"  -lf

# Written by Edness   2022-02-26 - 2025-04-07   v1.4.2

import os

def read_int(file, bytes):
    return int.from_bytes(file.read(bytes), "little")

def write_int(file, int, bytes):
    return file.write(int.to_bytes(bytes, "little"))

def build_rstm(path, output=str(), loopfull=False, loop_start=int(), loop_end=int()):
    path = os.path.abspath(path)
    if not output:
        output = os.path.splitext(path)[0] + ".rsm"
    output = os.path.abspath(output)

    #if sample_rate:
    #    assert sample_rate <= 48000, ERR_FREQ

    with open(path, "rb") as file:
        header = file.read(0x4)
        assert header in {b"RIFF", b"SShd"}, ERR_TYPE

        if header == b"RIFF":
            from ps_adpcm_encoder import encode_wav
            def progress(done, total):
                print(f'[RSM] Encoding {done / total:.0%}', flush=True)
            print('[RSM] Using the Python PS-ADPCM encoder.', flush=True)
            encode_wav(path, output, loop=loopfull, loop_start=loop_start,
                       loop_end=loop_end, replace=True, progress=progress)
            print('Success! RSTM sound file written to', output, flush=True)
            return
        ads_path = path

    #with open(ads_path, "rb") as ads, open(output, "wb") as rsm:
    with open(ads_path, "rb") as file:
        header = file.read(0x4)
        assert header == b"SShd", ERR_ADS2
        sshd_size = read_int(file, 0x4)
        encoding = read_int(file, 0x4)
        assert encoding == 0x10, ERR_ADS2
        sample_rate = read_int(file, 0x4)
        assert sample_rate <= 48000, ERR_ADS2
        channels = read_int(file, 0x4)
        assert 1 <= channels <= 2, ERR_ADS2
        interleave = read_int(file, 0x4)
        if channels > 1: assert interleave == 0x10, ERR_ADS2
        # not using loop flags from here, use -lf/-ls/-le instead
        #loop_start = read_int(file, 0x4)
        #loop_end = read_int(file, 0x4)
        #if loop_start != 0xFFFFFFFF: loop_start *= 0x10
        #if loop_end != 0xFFFFFFFF: loop_end *= 0x10
        file.seek(sshd_size + 0x8)
        header = file.read(0x4)
        assert header == b"SSbd", ERR_ADS2
        ssbd_size = read_int(file, 0x4)
        assert not ssbd_size & 0xF, ERR_SIZE
        rsm_data = bytearray(file.read(ssbd_size))
        frame_size = 0x10 * channels
        # wipe SPU flags written by MFAudio, Bully is very unhappy with these
        rsm_data[0x1::0x10] = bytes(len(rsm_data) // 0x10)
        # wipe SPU initialization frame written by PS2STR, RSMs don't have these
        if rsm_data.startswith(bytes(frame_size)):
            rsm_data = rsm_data[frame_size:]
        # wipe SPU end flag frame written by both MFAudio and PS2STR, also not needed
        rsm_data = rsm_data[:-frame_size]

    os.makedirs(os.path.split(output)[0], exist_ok=True)
    with open(__file__) as file: rsm_header = file.read(0x800)
    rsm_header = rsm_header[rsm_header.index(" ".join([chr(x) for x in (35, 87)])) + 0x2:]
    rsm_header = rsm_header.splitlines()[0].split(); rsm_header = " ".join(rsm_header[:3]), rsm_header[-1]
    rsm_header = " - ".join((os.path.split(__file__)[1], *rsm_header[::-1])).encode("UTF-8")
    with open(output, "wb") as file:
        file.write(b"RSTM")
        file.seek(0x8)
        write_int(file, sample_rate, 0x4)
        write_int(file, channels, 0x4)
        file.seek(0x18)
        write_int(file, len(rsm_data), 0x4)
        if loopfull:
            write_int(file, 0x0, 0x4)
            write_int(file, len(rsm_data) - frame_size, 0x4)
        elif loop_start or loop_end:
            write_int(file, loop_start * frame_size, 0x4)  # can be 0x0
            if loop_end < 0: loop_end = (len(rsm_data) - frame_size) // frame_size + loop_end
            write_int(file, loop_end * frame_size if loop_end else len(rsm_data) - frame_size, 0x4)
        else:  # no looping
            write_int(file, 0x0, 0x4)
            write_int(file, len(rsm_data), 0x4)
        file.seek(0x800 - len(rsm_header))
        file.write(rsm_header)
        file.write(rsm_data)

    print("Success! RSTM sound file written to", output)

ERR_ADS2 = "Error! Unsupported ADS/SS2 format.\nInput needs to be a PS-ADPCM encoded stream up to 2 channels with 16 byte interleaving."
ERR_DATA = "Error! Couldn't locate the WAV data section."
ERR_FREQ = "Error! Invalid sample rate."
ERR_SIZE = "Error! Invalid file size."
ERR_TYPE = "Error! Not a WAV or ADS/SS2 input file."
ERR_WAVE = "Error! Unsupported WAV format.\nInput needs to be a signed 16-bit PCM uncompressed WAV up to 2 channels."

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Builds Rockstar San Diego RSTM sound files")
    parser.add_argument("path", type=str, help="path to a WAV or ADS/SS2 sound file")
    parser.add_argument("-o", "--output", type=str, default=str(), help="path to the output file")
    #parser.add_argument("-sr", "--samplerate", type=int, default=int(), help="override the sample rate (WAV only)")
    parser.add_argument("-lf", "--loopfull", action="store_true", help="loop the whole stream")
    parser.add_argument("-ls", "--loopstart", type=int, default=int(), help="set the loop start frame (28 samples each)")
    parser.add_argument("-le", "--loopend", type=int, default=int(), help="set the loop end frame (28 samples each)")

    args = parser.parse_args()
    build_rstm(args.path, args.output, args.loopfull, args.loopstart, args.loopend)
