"""Known-vector, quality, interleave and failure checks; temporary files only."""
import contextlib
import io
import math
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'UI Custom Gameplay Music Tools/supporting_tools'))
import ps_adpcm_encoder as encoder
from rsm_decoder import convert, decode_frame


class EncoderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def wav(self,pcm,rate=44100,width=2):
        source=self.root/'input.wav'
        pcm=np.asarray(pcm)
        if pcm.ndim==1: pcm=pcm[:,None]
        with wave.open(str(source),'wb') as out:
            out.setparams((pcm.shape[1],width,rate,0,'NONE','not compressed'))
            out.writeframes(pcm.astype('<i2').tobytes() if width==2 else bytes(len(pcm)*pcm.shape[1]))
        return source

    def roundtrip(self,pcm,**kwargs):
        source=self.wav(pcm)
        output=self.root/'output.rsm'
        report=encoder.encode_wav(source,output,**kwargs)
        decoded=self.root/'decoded.wav'
        with contextlib.redirect_stdout(io.StringIO()): convert(output,decoded,None)
        with wave.open(str(decoded),'rb') as audio:
            data=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').reshape(-1,audio.getnchannels())
        return output,report,data

    def test_known_zero_and_constant_vectors(self):
        history=[0,0]
        zero=encoder.encode_block([0]*28,history)
        self.assertEqual(zero,bytes([12,0])+bytes(14))
        self.assertEqual(decode_frame(zero,[0,0]),[0]*28)
        history=[0,0]
        frame=encoder.encode_block([4096]*28,history)
        self.assertEqual(decode_frame(frame,[0,0]),[4096]*28)

    def test_silence_and_partial_frame_header(self):
        output,report,decoded=self.roundtrip(np.zeros((29,2),dtype=np.int16))
        self.assertEqual(report['padding_samples_per_channel'],27)
        self.assertEqual(report['payload_bytes'],64)
        self.assertEqual(len(decoded),56)
        self.assertTrue(np.all(decoded==0))
        raw=output.read_bytes()
        self.assertEqual(raw[:4],b'RSTM')
        self.assertEqual(struct.unpack_from('<II',raw,8),(44100,2))
        self.assertEqual(struct.unpack_from('<III',raw,0x18),(64,0,64))
        self.assertEqual(len(raw),2112)

    def test_stereo_independent_tones_quality_and_flags(self):
        t=np.arange(4410)/44100
        pcm=np.rint(np.column_stack((16000*np.sin(2*np.pi*440*t),12000*np.sin(2*np.pi*997*t)))).astype(np.int16)
        output,_,decoded=self.roundtrip(pcm)
        actual=decoded[:len(pcm)].astype(float)
        expected=pcm.astype(float)
        for channel in (0,1):
            snr=10*np.log10(np.sum(expected[:,channel]**2)/np.sum((actual[:,channel]-expected[:,channel])**2))
            self.assertGreater(snr,30)
            self.assertGreater(np.corrcoef(expected[:,channel],actual[:,channel])[0,1],0.995)
        self.assertLess(abs(np.corrcoef(expected[:,0],actual[:,1])[0,1]),0.1)
        payload=output.read_bytes()[2048:]
        self.assertTrue(all(payload[index]==0 for index in range(1,len(payload),16)))
        self.assertTrue(all(payload[index]>>4<5 and payload[index]&15<=12 for index in range(0,len(payload),16)))

    def test_silent_channel_has_no_crosstalk(self):
        t=np.arange(1000)/44100
        pcm=np.column_stack((np.rint(18000*np.sin(2*np.pi*440*t)),np.zeros(len(t)))).astype(np.int16)
        _,_,decoded=self.roundtrip(pcm)
        self.assertTrue(np.all(decoded[:,1]==0))

    def test_extremes_determinism_and_loop_header(self):
        samples=[-32768,32767]*14
        a=encoder.encode_block(samples,[0,0]); b=encoder.encode_block(samples,[0,0])
        self.assertEqual(a,b)
        self.assertTrue(all(-32768<=sample<=32767 for sample in decode_frame(a,[0,0])))
        output,report,_=self.roundtrip(np.tile(samples,2),loop=True)
        self.assertEqual(struct.unpack_from('<III',output.read_bytes(),0x18),(32,0,16))

    def test_existing_destination_is_preserved(self):
        source=self.wav([1]*28)
        output=self.root/'output.rsm'; output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError): encoder.encode_wav(source,output)
        self.assertEqual(output.read_bytes(),b'keep')

    def test_replace_mode_is_atomic_on_failure(self):
        source=self.wav([1]*56)
        output=self.root/'output.rsm'; output.write_bytes(b'keep')
        with patch.object(encoder,'encode_block',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError): encoder.encode_wav(source,output,replace=True)
        self.assertEqual(output.read_bytes(),b'keep')
        self.assertFalse(list(self.root.glob('*.tmp')))
        encoder.encode_wav(source,output,replace=True)
        self.assertEqual(output.read_bytes()[:4],b'RSTM')

    def test_manual_loops_preserve_frame_units_and_negative_end_convention(self):
        header=encoder.make_header(44100,2,320,loop_start=2,loop_end=-1)
        self.assertEqual(struct.unpack_from('<III',header,0x18),(320,64,256))
        for start,end in ((-1,3),(7,2),(0,10)):
            with self.assertRaises(ValueError): encoder.make_header(44100,2,320,loop_start=start,loop_end=end)

    def test_wav_builder_routes_to_python_and_matches_legacy_loop_fields(self):
        import rstm_build
        source=self.wav([1000]*280)
        for options in ((False,0,0),(True,0,0),(False,2,7),(False,2,-1)):
            loop,start,end=options
            output=self.root/f'builder_{loop}_{start}_{end}.rsm'
            with patch('subprocess.Popen',side_effect=AssertionError('No external encoder')),patch('os.system',side_effect=AssertionError('No shell')),contextlib.redirect_stdout(io.StringIO()):
                rstm_build.build_rstm(str(source),str(output),loop,start,end)
            data=output.read_bytes()
            payload=len(data)-2048
            expected=encoder.make_header(44100,1,payload,loop,start,end)
            self.assertEqual(data[:0x24],expected[:0x24])

    def test_bad_input_and_truncated_input_publish_nothing(self):
        for pcm,rate,width in [([],44100,2),([1]*28,96000,2),([1]*28,44100,1)]:
            source=self.wav(pcm,rate,width)
            output=self.root/'output.rsm'
            with self.assertRaises(ValueError): encoder.encode_wav(source,output)
            self.assertFalse(output.exists())
        source=self.wav([1]*56)
        raw=source.read_bytes(); source.write_bytes(raw[:-8])
        with self.assertRaisesRegex(ValueError,'Truncated'): encoder.encode_wav(source,self.root/'output.rsm')
        self.assertFalse((self.root/'output.rsm').exists())
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_failure_cleans_temporary_and_does_not_execute_subprocesses(self):
        source=self.wav([1]*56)
        with patch.object(encoder,'encode_block',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError): encoder.encode_wav(source,self.root/'output.rsm')
        self.assertFalse((self.root/'output.rsm').exists())
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_success_never_starts_an_external_encoder(self):
        source=self.wav([0,1000,-1000,3000]*28)
        with patch('subprocess.Popen',side_effect=AssertionError('No subprocess allowed')),patch('os.system',side_effect=AssertionError('No shell allowed')):
            report=encoder.encode_wav(source,self.root/'output.rsm')
        self.assertFalse(report['external_encoder_executed'])

    def test_rsm_fields_and_audio_match_existing_writer_without_native_encoding(self):
        # Existing builder accepts already encoded SShd/SSbd input. Exercise
        # only its container path, explicitly forbidding encoder execution.
        import rstm_build
        for channels in (1,2):
            for loop in (False,True):
                with self.subTest(channels=channels,loop=loop):
                    source=self.wav(np.full((56,channels),1000,dtype=np.int16))
                    prototype=self.root/f'prototype_{channels}_{loop}.rsm'
                    report=encoder.encode_wav(source,prototype,loop=loop)
                    data=prototype.read_bytes()
                    group=16*channels
                    payload=bytes(group)+data[2048:]+bytes(group)
                    ads=self.root/'input.ads'
                    ads.write_bytes(struct.pack('<4sI6I4sI',b'SShd',24,16,44100,channels,16,0xffffffff,0xffffffff,b'SSbd',len(payload))+payload)
                    reference=self.root/f'reference_{channels}_{loop}.rsm'
                    with patch('subprocess.check_call',side_effect=AssertionError('No encoder allowed')),patch('os.system',side_effect=AssertionError('No shell allowed')),contextlib.redirect_stdout(io.StringIO()):
                        rstm_build.build_rstm(str(ads),str(reference),loopfull=loop)
                    expected=reference.read_bytes()
                    self.assertEqual(data[:0x24],expected[:0x24])
                    self.assertEqual(data[2048:],expected[2048:])


if __name__=='__main__':
    unittest.main(verbosity=2)
