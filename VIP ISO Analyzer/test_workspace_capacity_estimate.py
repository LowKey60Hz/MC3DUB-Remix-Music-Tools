"""Projection parity with real builders; only small temporary archives written."""
import contextlib
import io
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

TOOLS=Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools/supporting_tools'
sys.path.insert(0,str(TOOLS))
import workspace_capacity as estimate
import dave
import hash_build
import MC3_ASSETS_Builder_V11A as v11


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'ASSETS').mkdir()
        (self.root/'STREAMS/Music').mkdir(parents=True)
        (self.root/'ISO_FILES').mkdir()
        self.profile('retail','VERIFIED_RETAIL_REFERENCE')
        rng=random.Random(44)
        data={'audio/a.raw':b'a'*2000,'audio/abc.raw':rng.randbytes(2048),
              'audio/abcd.raw':b'b'*67,'audio/empty.raw':b'',
              'flash/a.pck':b'c'*4096,'resources/city/a.pck':b'd'*4096,
              'resources/vehicle/a.pck':b'e'*4096,'root.pck':b'f'*4096}
        for name,payload in data.items():
            p=self.root/'ASSETS'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(payload)
        for name,size in (('A.rsm',2048),('B.rsm',2050),('C.rsm',0)):
            (self.root/'STREAMS/Music'/name).write_bytes(b'g'*size)

    def profile(self,name,kind):
        (self.root/'ISO_FILES/MC3_PROFILE.txt').write_text(name)
        (self.root/'ISO_FILES/MC3_SOURCE_CLASS.txt').write_text(kind)

    def test_retail_and_vip_dave_and_streams_match_real_compilers(self):
        for dirs in (False,True):
            with self.subTest(directories=dirs),contextlib.redirect_stdout(io.StringIO()):
                profile,kind=('vip','VERIFIED_VIP_REFERENCE') if dirs else ('retail','VERIFIED_RETAIL_REFERENCE')
                self.profile(profile,kind)
                output=self.root/('compiled_'+str(dirs)+'.bin')
                dave.build_dave(str(self.root/'ASSETS'),str(output),compfiles=True,forcecomp=1,compnames=True,dirs=dirs,compalign=True)
                projected=estimate.estimate(self.root)
                self.assertEqual(projected['assets_bytes'],output.stat().st_size)
                streams=self.root/('streams_'+str(dirs)+'.bin')
                hash_build.build_hash(str(self.root/'STREAMS'),str(streams),'MClub')
                self.assertEqual(projected['streams_bytes'],streams.stat().st_size)

    def test_cache_reuses_unchanged_and_invalidates_changed_added_removed(self):
        cache=self.root/'cache.json'
        first=estimate.estimate(self.root,cache)
        second=estimate.estimate(self.root,cache)
        self.assertGreater(first['new_compression_calculations'],0)
        self.assertEqual(second['new_compression_calculations'],0)
        p=self.root/'ASSETS/audio/a.raw'; p.write_bytes(b'new'*900)
        self.assertEqual(estimate.estimate(self.root,cache)['new_compression_calculations'],1)
        extra=self.root/'ASSETS/audio/added.raw'; extra.write_bytes(b'new'*90)
        self.assertEqual(estimate.estimate(self.root,cache)['new_compression_calculations'],1)
        extra.unlink()
        estimate.estimate(self.root,cache)
        self.assertNotIn('audio/added.raw',json.loads(cache.read_text())['rows'])

    def test_dave_exact_table_alignment_and_name_prefix_reset(self):
        import shutil
        shutil.rmtree(self.root/'ASSETS')
        (self.root/'ASSETS').mkdir()
        for index in range(128):
            (self.root/'ASSETS'/f'common_prefix_{index:03}.pck').write_bytes(b'a'*(32 if index%2 else 2048))
        with contextlib.redirect_stdout(io.StringIO()):
            output=self.root/'boundary.bin'
            dave.build_dave(str(self.root/'ASSETS'),str(output),compfiles=True,forcecomp=1,compnames=True,compalign=True)
        self.assertEqual(estimate.estimate(self.root)['assets_bytes'],output.stat().st_size)

    def test_staged_audio_excluded_and_no_game_files_written(self):
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        a=estimate.estimate(self.root)
        (self.root/'Loading Music').mkdir()
        (self.root/'Loading Music/long.wav').write_bytes(b'new'*100000)
        b=estimate.estimate(self.root)
        self.assertEqual(a,b)
        self.assertFalse(b['staged_audio_included'])
        self.assertTrue(all((self.root/name).read_bytes()==data for name,data in before.items()))
        self.assertEqual({p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()},set(before)|{'Loading Music/long.wav'})

    def test_source_mutation_does_not_publish_cache(self):
        cache=self.root/'cache.json'
        real=estimate.compressed_size
        def mutate(path):
            count=real(path)
            path.write_bytes(path.read_bytes()+b'changed')
            return count
        with patch.object(estimate,'compressed_size',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):
            estimate.estimate(self.root,cache)
        self.assertFalse(cache.exists())

    def test_overcapacity_and_record_limit_reported(self):
        projected={'bytes':2**31,'max_live_end':2**31,'records':1,'max_decoded':1}
        with patch.object(estimate,'project_dave',return_value=projected),patch.object(estimate,'project_streams',return_value=projected):
            report=estimate.estimate(self.root)
        self.assertGreater(report['over_capacity_bytes'],0)
        self.assertEqual(report['remaining_bytes'],0)
        self.assertEqual(len(report['record_risks']),2)

    def test_v11_duplicate_records_compression_and_alignment_match_compiler(self):
        # Replace fixture sources with the two trusted-layout names.
        import shutil
        shutil.rmtree(self.root/'ASSETS')
        folder=self.root/'ASSETS/audio'; folder.mkdir(parents=True)
        old=b'a'*2000; payload=zlib.compress(old)[2:-4]
        (folder/'one.raw').write_bytes(old)
        (folder/'two.pck').write_bytes(b'changed'*500)
        entries=[]; prefix=bytearray(6144)
        struct.pack_into('<4sIII',prefix,0,b'Dave',3,2048,2048)
        iso=self.root/'source.iso'
        with iso.open('wb') as out:
            out.write(prefix)
            for index,(name,offset) in enumerate((('audio/one.raw',6144),('audio/one.raw',8192),('audio/two.pck',8256))):
                out.seek(offset); out.write(payload)
                entries.append(dict(index=index,name=name,offset=offset,full=len(old),stored=len(payload),directory=False))
        self.profile('vip','VERIFIED_VIP_V11A_REFERENCE')
        (self.root/'ISO_FILES/MC3_SOURCE_ISO.txt').write_text(str(iso))
        with patch.object(v11,'START',0),patch.object(v11,'reference_entries',return_value=(entries,bytes(prefix))),patch.object(v11,'sha256_file',return_value=v11.TRUSTED_VIP_V11A_SHA256),contextlib.redirect_stdout(io.StringIO()):
            forecast=estimate.estimate(self.root,self.root/'cache.json')
            output=self.root/'compiled_v11.bin'
            v11.compile_assets(iso,self.root/'ASSETS',output)
            self.assertEqual(forecast['assets_bytes'],output.stat().st_size)
            self.assertEqual(estimate.estimate(self.root,self.root/'cache.json')['new_compression_calculations'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
