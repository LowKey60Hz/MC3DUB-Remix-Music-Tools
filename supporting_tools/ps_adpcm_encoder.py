"""PCM16 WAV -> Rockstar RSTM with Python PS-ADPCM.

Independent integer encoder using the format already handled by this project's
rsm_decoder.py. No external encoder executable or DLL is used. Long stereo
inputs can use two Python workers, retaining each channel's encoding history.
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
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

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
    if not any(samples):
        history[:] = (0, 0)
        return b'\x0c\x00' + bytes(14)
    best_error = None
    best_nibbles = None
    best_history = None
    for predictor, (c1, c2) in enumerate(COEFFICIENTS):
        p1, p2 = history
        lowest = highest = 0
        for sample in samples:
            residual = sample - ((p1*c1 + p2*c2 + 32) >> 6)
            if residual < lowest: lowest = residual
            elif residual > highest: highest = residual
            p2, p1 = p1, sample
        shift = 12
        step = 1
        while shift and (highest > 7*step or lowest < -8*step):
            shift -= 1
            step <<= 1
        for scale in range(shift, shift+2 if shift < 12 else 13):
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
                best_error, best_nibbles, best_history = error, nibbles, (p1, p2)
                best_header = predictor << 4 | scale
        # Exact reconstruction cannot be improved.
        if best_error == 0:
            break
    if best_nibbles is None:
        raise ValueError('No valid ADPCM candidate')
    frame = bytearray(BLOCK_BYTES)
    frame[0] = best_header
    for index in range(14):
        frame[index+2] = best_nibbles[index*2] | best_nibbles[index*2+1] << 4
    history[:] = best_history
    return bytes(frame)


def _encode_channel(samples, history):
    history = list(history)
    data = bytearray()
    for start in range(0, len(samples), BLOCK_SAMPLES):
        data.extend(encode_block(samples[start:start+BLOCK_SAMPLES], history))
    return bytes(data), history


def _interleave(parts):
    if len(parts) == 1:
        return parts[0]
    left, right = parts
    if len(left) != len(right) or len(left) % BLOCK_BYTES:
        raise ValueError('Invalid encoded channel lengths')
    data = bytearray(len(left)*2)
    for byte in range(BLOCK_BYTES):
        data[byte::32] = left[byte::16]
        data[byte+16::32] = right[byte::16]
    return data


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


def encode_wav(source, destination, *, loop=False, loop_start=0, loop_end=0, replace=False, progress=None, workers=None):
    """Encode atomically; auto-use two workers for stereo inputs of 10s or more.

    Set workers=1 to force serial encoding or workers=2 to request two workers.
    Unavailable workers fall back to serial encoding without changing output.
    """
    if workers not in (None, 1, 2):
        raise ValueError('workers must be None, 1 or 2')
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
        pool = None
        worker_count = 1
        destination.parent.mkdir(parents=True,exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='python_rsm_',suffix='.tmp',dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd,'wb') as out:
                parallel = channels == 2 and (workers == 2 or (
                    workers is None and count >= rate*10 and (os.cpu_count() or 1) >= 2))
                if parallel:
                    try:
                        pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn'))
                    except OSError:
                        pool = None
                out.write(header)
                read_frames = 0
                completed = 0
                while completed < blocks:
                    batch_blocks = min(2048, blocks-completed)
                    wanted = min(BLOCK_SAMPLES*batch_blocks,count-read_frames)
                    data = audio.readframes(wanted)
                    if len(data) != wanted*channels*2:
                        raise ValueError('Truncated WAV data')
                    pcm = array('h'); pcm.frombytes(data)
                    if sys.byteorder != 'little': pcm.byteswap()
                    read_frames += wanted
                    pcm.extend([0]*((batch_blocks*BLOCK_SAMPLES-wanted)*channels))
                    channels_pcm = [pcm[channel::channels].tolist() for channel in range(channels)]
                    if pool is not None:
                        try:
                            futures = [pool.submit(_encode_channel, samples, histories[channel]) for channel,samples in enumerate(channels_pcm)]
                            results = [future.result() for future in futures]
                            worker_count = 2
                        except (OSError, BrokenProcessPool):
                            pool.shutdown(wait=True, cancel_futures=True)
                            pool = None
                            results = [_encode_channel(samples, histories[channel]) for channel,samples in enumerate(channels_pcm)]
                    else:
                        results = [_encode_channel(samples, histories[channel]) for channel,samples in enumerate(channels_pcm)]
                    histories = [result[1] for result in results]
                    out.write(_interleave([result[0] for result in results]))
                    completed += batch_blocks
                    if progress:
                        progress(completed,blocks)
                if out.tell() != HEADER_BYTES+payload_size:
                    raise ValueError('RSTM output-size mismatch')
            # An exclusive link publishes the finished file without overwriting
            # another output created while encoding. Both paths share a volume.
            if replace:
                os.replace(temporary,destination)
            else:
                os.link(temporary,destination)
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)
            temporary.unlink(missing_ok=True)
    elapsed = time.perf_counter()-started
    return {'sample_rate':rate,'channels':channels,'input_samples_per_channel':count,
            'encoded_samples_per_channel':blocks*BLOCK_SAMPLES,
            'padding_samples_per_channel':blocks*BLOCK_SAMPLES-count,
            'payload_bytes':payload_size,'rsm_bytes':HEADER_BYTES+payload_size,
            'audio_seconds':count/rate,'encoding_seconds':elapsed,
            'audio_seconds_per_encoding_second':(count/rate)/elapsed,
            'loop_full':loop,'external_encoder_executed':False,
            'backend':'python','workers':worker_count}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('-o','--output',type=Path,required=True)
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args()
    print(json.dumps(encode_wav(args.source,args.output,loop=args.loop),indent=2))
