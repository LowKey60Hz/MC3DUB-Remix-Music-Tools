"""PCM16 WAV -> Rockstar RSTM with in-process PS-ADPCM.

Independent integer encoder using the format already handled by this project's
rsm_decoder.py. No Sony/MFAudio code, executable, DLL, or subprocess is used.
Based on the independently tested Python prototype; no legacy encoder required.
"""
import argparse
from array import array
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import wave

COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
HEADER_BYTES = 2048
BLOCK_SAMPLES = 28
BLOCK_BYTES = 16


def encode_block(samples, history):
    """Choose a predictor/scale by decoded squared error; preserve channel state.

    Estimate the scale from source residuals, then test it and one finer scale
    with actual quantized feedback. Candidate errors are measured against PCM,
    not against other encoders' bitstreams. Flags stay zero for RSTM playback.
    """
    if len(samples) != BLOCK_SAMPLES:
        raise ValueError('Expected exactly 28 PCM samples')
    best_error = None
    best_frame = None
    best_history = None
    for predictor, (c1, c2) in enumerate(COEFFICIENTS):
        p1, p2 = history
        lowest = highest = 0
        for sample in samples:
            residual = sample - ((p1*c1 + p2*c2 + 32) >> 6)
            lowest = min(lowest, residual)
            highest = max(highest, residual)
            p2, p1 = p1, sample
        shift = 12
        step = 1
        while shift and (highest > 7*step or lowest < -8*step):
            shift -= 1
            step <<= 1
        for scale in range(shift, min(12, shift+1)+1):
            p1, p2 = history
            step = 1 << (12-scale)
            half = step >> 1
            error = 0
            nibbles = []
            for sample in samples:
                predicted = (p1*c1 + p2*c2 + 32) >> 6
                quantized = (sample-predicted+half) // step
                if quantized < -8: quantized = -8
                elif quantized > 7: quantized = 7
                decoded = predicted + quantized*step
                if decoded < -32768: decoded = -32768
                elif decoded > 32767: decoded = 32767
                difference = sample-decoded
                error += difference*difference
                if best_error is not None and error >= best_error:
                    break
                nibbles.append(quantized & 15)
                p2, p1 = p1, decoded
            else:
                frame = bytearray(BLOCK_BYTES)
                frame[0] = predictor << 4 | scale
                for index in range(14):
                    frame[index+2] = nibbles[index*2] | nibbles[index*2+1] << 4
                best_error, best_frame, best_history = error, bytes(frame), (p1, p2)
        # Exact reconstruction cannot be improved.
        if best_error == 0:
            break
    if best_frame is None:
        raise ValueError('No valid ADPCM candidate')
    history[:] = best_history
    return best_frame


def make_header(rate, channels, payload_bytes, loop=False, loop_start=0, loop_end=0):
    group_bytes = BLOCK_BYTES*channels
    if not (8000 <= rate <= 48000 and channels in (1, 2)):
        raise ValueError('Expected 8-48 kHz mono/stereo audio')
    if not 0 < payload_bytes <= 0xffffffff or payload_bytes % group_bytes:
        raise ValueError('Invalid RSTM payload length')
    blocks = payload_bytes // group_bytes
    if loop:
        start, end = 0, payload_bytes-group_bytes
    elif loop_start or loop_end:
        # Preserve the existing CLI's frame units and negative-end convention.
        end_frame = blocks-1+loop_end if loop_end < 0 else (loop_end or blocks-1)
        if not 0 <= loop_start <= end_frame < blocks:
            raise ValueError('Loop frame range is outside the encoded audio')
        start, end = loop_start*group_bytes, end_frame*group_bytes
    else:
        start, end = 0, payload_bytes
    header = bytearray(HEADER_BYTES)
    header[:4] = b'RSTM'
    struct.pack_into('<II', header, 8, rate, channels)
    struct.pack_into('<III', header, 0x18, payload_bytes, start, end)
    marker = b'MC3 Python PS-ADPCM encoder'
    header[-len(marker):] = marker
    return header


def encode_wav(source, destination, *, loop=False, loop_start=0, loop_end=0, replace=False, progress=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Input and output must differ')
    if destination.exists() and not replace:
        raise FileExistsError('Refusing to overwrite: '+str(destination))
    started = time.perf_counter()
    temporary = None
    with wave.open(str(source), 'rb') as audio:
        rate, channels, width, count = audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()
        if width != 2 or audio.getcomptype() != 'NONE' or channels not in (1,2) or not 8000 <= rate <= 48000:
            raise ValueError('Input must be uncompressed 16-bit mono/stereo WAV, 8-48 kHz')
        if count <= 0:
            raise ValueError('Input audio is empty')
        blocks = (count+BLOCK_SAMPLES-1)//BLOCK_SAMPLES
        payload_size = blocks*BLOCK_BYTES*channels
        header = make_header(rate, channels, payload_size, loop, loop_start, loop_end)
        histories = [[0,0] for _ in range(channels)]
        destination.parent.mkdir(parents=True,exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='python_rsm_',suffix='.tmp',dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(header)
                read_frames = 0
                for block in range(blocks):
                    wanted = min(BLOCK_SAMPLES,count-read_frames)
                    data = audio.readframes(wanted)
                    if len(data) != wanted*channels*2:
                        raise ValueError('Truncated WAV data')
                    pcm = array('h'); pcm.frombytes(data)
                    if sys.byteorder != 'little': pcm.byteswap()
                    read_frames += wanted
                    pcm.extend([0]*((BLOCK_SAMPLES-wanted)*channels))
                    for channel in range(channels):
                        out.write(encode_block(pcm[channel::channels], histories[channel]))
                    if progress and ((block+1)%2000==0 or block+1==blocks):
                        progress(block+1,blocks)
                if out.tell() != HEADER_BYTES+payload_size:
                    raise ValueError('RSTM output-size mismatch')
            # An exclusive link publishes the finished file without overwriting
            # another output created while encoding. Both paths share a volume.
            if replace:
                os.replace(temporary,destination)
            else:
                os.link(temporary,destination)
        finally:
            temporary.unlink(missing_ok=True)
    elapsed = time.perf_counter()-started
    return {'sample_rate':rate,'channels':channels,'input_samples_per_channel':count,
            'encoded_samples_per_channel':blocks*BLOCK_SAMPLES,
            'padding_samples_per_channel':blocks*BLOCK_SAMPLES-count,
            'payload_bytes':payload_size,'rsm_bytes':HEADER_BYTES+payload_size,
            'audio_seconds':count/rate,'encoding_seconds':elapsed,
            'audio_seconds_per_encoding_second':(count/rate)/elapsed,
            'loop_full':loop,'external_encoder_executed':False,
            'backend':'python'}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('-o','--output',type=Path,required=True)
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args()
    print(json.dumps(encode_wav(args.source,args.output,loop=args.loop),indent=2))
