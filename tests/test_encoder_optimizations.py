"""Byte-exact regression checks against the frozen, game-tested encoder."""
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'Encoder Research'))
import reference_ps_adpcm_encoder_v1 as reference
sys.path.insert(0, str(ROOT/'UI Custom Gameplay Music Tools/supporting_tools'))
import ps_adpcm_encoder as encoder


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wav(self, count, channels=2, rate=8000):
        rng = random.Random(348)
        source = self.root/'input.wav'
        with wave.open(str(source), 'wb') as audio:
            audio.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            audio.writeframes(b''.join(struct.pack('<h', rng.randint(-32768,32767))
                                       for _ in range(count*channels)))
        return source

    def compare(self, source, **kwargs):
        original = self.root/'reference.rsm'
        actual = self.root/'actual.rsm'
        loops = {k:v for k,v in kwargs.items() if k in ('loop','loop_start','loop_end')}
        reference.encode_wav(source, original, replace=True, **loops)
        report = encoder.encode_wav(source, actual, replace=True, **kwargs)
        self.assertEqual(actual.read_bytes(), original.read_bytes())
        self.assertFalse(list(self.root.glob('*.tmp')))
        return report

    def test_frames_and_histories_match_including_silence_after_sound(self):
        rng = random.Random(112)
        cases = [[0]*28, [32767,-32768]*14, [4096]*28]
        cases += [[rng.randint(-32768,32767) for _ in range(28)] for _ in range(300)]
        cases += [[0]*28]
        for initial in ([0,0], [32767,-32768], [-2000,1800]):
            a, b = list(initial), list(initial)
            for samples in cases:
                self.assertEqual(reference.encode_block(samples,a), encoder.encode_block(samples,b))
                self.assertEqual(a,b)

    def test_serial_mono_and_stereo_across_batches_and_loop_modes(self):
        for channels in (1,2):
            source = self.wav(28*2048+13, channels)
            for options in ({}, {'loop':True}, {'loop_start':2,'loop_end':-1}):
                with self.subTest(channels=channels, options=options):
                    self.assertEqual(self.compare(source, workers=1, **options)['workers'],1)

    def test_actual_spawned_workers_retain_history_across_batches(self):
        source = self.wav(28*2048+13)
        self.assertEqual(self.compare(source,workers=2,loop=True)['workers'],2)

    def test_auto_workers_for_long_stereo(self):
        source = self.wav(80001)
        with patch.object(encoder.os,'cpu_count',return_value=2):
            self.assertEqual(self.compare(source)['workers'],2)

    def test_short_mono_or_one_cpu_stays_serial(self):
        for count,channels,cpus in ((79999,2,2),(80001,1,2),(80001,2,1),(80001,2,None)):
            source = self.wav(count,channels)
            with patch.object(encoder.os,'cpu_count',return_value=cpus), patch.object(
                    encoder,'ProcessPoolExecutor',side_effect=AssertionError('Should stay serial')):
                self.assertEqual(self.compare(source)['workers'],1)

    def test_worker_start_failure_falls_back_without_changing_bytes(self):
        source = self.wav(113)
        with patch.object(encoder,'ProcessPoolExecutor',side_effect=OSError('unavailable')):
            self.assertEqual(self.compare(source,workers=2)['workers'],1)

    def test_worker_failure_after_one_batch_retries_with_original_history(self):
        class FailingPool:
            calls = 0
            def submit(self, function, *args):
                self.calls += 1
                future = Future()
                if self.calls > 2:
                    future.set_exception(BrokenProcessPool('worker stopped'))
                else:
                    future.set_result(function(*args))
                return future
            def shutdown(self, **kwargs): pass
        source = self.wav(28*2048+13)
        with patch.object(encoder,'ProcessPoolExecutor',return_value=FailingPool()):
            self.compare(source,workers=2)

    def test_progress_failure_preserves_destination_and_cleans_temp(self):
        source = self.wav(57)
        target = self.root/'keep.rsm'
        target.write_bytes(b'keep')
        def fail(*args): raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            encoder.encode_wav(source,target,workers=2,replace=True,progress=fail)
        self.assertEqual(target.read_bytes(),b'keep')
        self.assertFalse(list(self.root.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
