import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server
from workspace_store import WorkspaceStore
from quality import FrameQuality
from explorer_menu import menu_entries
from batching import is_generated_video


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.work=self.root/'work';self.work.mkdir();self.store=WorkspaceStore(self.root/'profile')
        self.client=server.app.test_client();self.headers={'X-Outmax-Token':server.TOKEN}
        self.patches=[patch.object(server,'BASE',self.root/'profile'),patch.object(server,'workspace',self.store),patch.object(server,'WORK',self.work),patch.dict(server.sources,{},clear=True),patch.dict(server.jobs,{},clear=True)]
        for item in self.patches:item.start()
        (self.root/'profile').mkdir()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def source(self,key='fixture'):
        folder=self.work/key;folder.mkdir(exist_ok=True);path=folder/'source.mp4';path.write_bytes(b'original');poster=folder/'poster.jpg';poster.write_bytes(b'poster')
        entry=dict(id=key,name='44238_model.mp4',relative='44238/44238_model.mp4',info={'duration':10,'width':360,'height':640},model_score=.8,path=path,preview_path=path,poster_path=poster)
        server.sources[key]=entry;return entry
    def payload(self,entry):
        return dict(items=[dict(id='one',name='44238',status='ready',selected=True,candidates=[server.public_source(entry)],snapshot=dict(sources=[server.public_source(entry),None],settings=server.validate_settings({}),playback={'time':3.4,'paused':True}))],mode=True,active='one',single=None,output=str(self.root))
    def test_autosave_keeps_upload_and_poster_after_original_work_is_removed(self):
        source=self.source();saved=self.store.save(self.payload(source),server.sources,{},self.work);original=source['path'];original.unlink();source['poster_path'].unlink()
        cached=saved['sources'][source['id']]
        self.assertEqual(Path(cached['path']).read_bytes(),b'original');self.assertEqual(cached['path'],cached['preview_path'])
        server.sources.clear();restored=self.client.get('/api/session').json
        self.assertFalse(restored['missing']);self.assertFalse(restored['sources']['fixture']['missing']);self.assertEqual(restored['session']['items'][0]['snapshot']['playback']['time'],3.4)
        response=self.client.get('/poster/fixture');self.assertEqual(response.data,b'poster');response.close()
    def test_invalid_snapshot_does_not_replace_previous_queue(self):
        source=self.source();payload=self.payload(source);self.store.save(payload,server.sources,{},self.work)
        with self.assertRaises(ValueError):self.store.save({'items':[], 'bad':float('nan')},server.sources,{},self.work)
        self.assertEqual(self.store.read()['payload']['active'],'one')
    def test_previous_atomic_snapshot_can_recover_a_corrupt_queue(self):
        source=self.source();payload=self.payload(source);self.store.save(payload,server.sources,{},self.work)
        self.store.save(payload|{'active':'later'},server.sources,{},self.work);self.store.file.write_text('{',encoding='utf-8')
        self.assertEqual(self.store.read()['payload']['active'],'one')
    def test_cleanup_saves_media_once_and_second_cleanup_keeps_it(self):
        source=self.source();self.store.save(self.payload(source),server.sources,{},self.work)
        with patch.object(server,'last_workspace_store',self.store),patch.object(server,'cleanup_done',False):
            server.cleanup();saved=self.store.read();cached=Path(saved['sources']['fixture']['path']);self.assertTrue(cached.is_file());self.assertFalse(self.work.exists())
            server.cleanup();self.assertEqual(self.store.read(),saved)
    def test_cleanup_records_a_job_that_finished_during_close(self):
        source=self.source();payload=self.payload(source);payload['batch_id']='batch';payload['items'][0]['status']='running';self.store.save(payload,server.sources,{},self.work)
        output=self.root/'result.mp4';output.write_bytes(b'export')
        server.jobs['finished']=dict(id='finished',item_id='one',source_ids=['fixture',None],status='done',batch_id='batch',progress=100,output=output,variants=[dict(format='standard',output=output,report={})],cancel=threading.Event())
        with patch.object(server,'last_workspace_store',self.store),patch.object(server,'cleanup_done',False):server.cleanup()
        saved=self.store.read();self.assertEqual(saved['payload']['items'][0]['snapshot']['result']['id'],'finished');self.assertEqual(saved['payload']['items'][0]['status'],'done')
    def test_archive_source_location_follows_completed_export(self):
        source=self.source();self.store.save(self.payload(source),server.sources,{},self.work)
        archived=self.root/'result.mp4';archived.write_bytes(b'original');self.store.record_location(source|{'path':archived});server.sources.clear()
        restored=self.client.get('/api/session').json
        self.assertEqual(restored['sources']['fixture']['location'],str(archived));self.assertFalse(restored['missing'])
    def test_missing_native_source_is_reported_without_discarding_settings(self):
        source=self.source();native=self.root/'native.mp4';native.write_bytes(b'original');source['path']=source['preview_path']=native;self.store.save(self.payload(source),server.sources,{},self.work);native.unlink();server.sources.clear()
        data=self.client.get('/api/session').json;self.assertEqual(len(data['missing']),1);self.assertTrue(data['sources']['fixture']['missing']);self.assertEqual(data['session']['items'][0]['name'],'44238')
    def test_presets_crud_and_manual_bounds_are_not_shared(self):
        response=self.client.post('/api/presets',json={'name':'Сайт','settings':{'zooms':[1.5,1.2],'trims':[[0,3],[0,4]]}},headers=self.headers)
        self.assertEqual(response.status_code,200);preset=response.json['presets'][0];self.assertEqual(preset['settings']['trims'],[None,None])
        self.assertEqual(self.client.post('/api/presets',json={'name':'Сайт'},headers=self.headers).status_code,400)
        updated=self.client.post('/api/presets',json={'id':preset['id'],'name':'Каталог','settings':preset['settings']},headers=self.headers).json
        self.assertEqual(updated['presets'][0]['name'],'Каталог')
        self.assertEqual(self.client.post('/api/presets',json={'id':preset['id'],'action':'delete'},headers=self.headers).json['presets'],[])
        self.assertEqual(self.client.post('/api/presets',json={'name':'No token'}).status_code,403)
    def test_named_queue_archive_restores_existing_sources(self):
        source=self.source();self.store.save(self.payload(source),server.sources,{},self.work)
        archived=self.client.post('/api/session/archive',json={'name':'Первая партия'},headers=self.headers).json
        self.assertTrue(archived['saved']);self.assertEqual(self.client.get('/api/session/archives').json['archives'][0]['count'],1)
        self.assertEqual(self.client.get('/api/session?archive='+archived['id']).json['session']['active'],'one')
        self.assertEqual(self.client.get('/api/session?archive=../../other').status_code,400)
    def test_source_locations_and_frame_downloads_require_known_ids(self):
        source=self.source();response=self.client.post('/api/source-location',json={'id':'fixture'},headers=self.headers).json;self.assertEqual(response['path'],str(source['path']))
        self.assertEqual(self.client.post('/api/source-location',json={'id':'missing'},headers=self.headers).status_code,404)
        self.assertEqual(self.client.post('/api/frame',json={'data':'not a PNG'},headers=self.headers).status_code,400)
    def test_reimport_skips_size_variants_and_repeat_exports(self):
        archive=self.root/'44238'/'Руки + Ноги';archive.mkdir(parents=True)
        for name in ('44238_ноги.mp4','44238_руки.mp4'):(archive/name).write_bytes(b'source')
        for name in ('44238.mp4','44238_v2.mp4','44238_900x1200.mp4','44238_640x360_custom_aabb_v2.mp4'):
            path=archive.parent/name;path.write_bytes(b'export');self.assertTrue(is_generated_video(path),name)
        self.assertFalse(is_generated_video(archive/'44238_руки.mp4'))
    def test_explorer_commands_are_scoped_for_folders_files_and_presets(self):
        self.assertNotIn('model',dict(menu_entries([],False)));self.assertIn('hands',dict(menu_entries([],True)));self.assertIn('presets',dict(menu_entries([{'id':'p','name':'Сайт'}])))


class QualityTests(unittest.TestCase):
    def test_black_flash_is_flagged_but_neutral_backdrop_is_not(self):
        quality=FrameQuality();white=np.full((64,64,3),170,np.uint8);quality.add(white,0);quality.add(np.zeros_like(white),1);quality.add(white,2)
        report=quality.report();self.assertEqual(report['black_frames'],1);self.assertEqual(report['findings'][0]['time'],1/30);self.assertEqual(report['loop_difference'],0)
    def test_long_textured_freeze_is_advisory_and_empty_pause_is_ignored(self):
        textured=np.random.default_rng(0).integers(0,255,(64,64,3),dtype=np.uint8);quality=FrameQuality()
        for index in range(100):quality.add(textured,index)
        self.assertTrue(any(f['kind']=='freeze' for f in quality.report()['findings']))
        empty=FrameQuality()
        for index in range(100):empty.add(np.full((64,64,3),150,np.uint8),index)
        self.assertFalse(empty.report()['findings'])

if __name__=='__main__':unittest.main()
