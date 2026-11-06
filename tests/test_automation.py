import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server
from automation import AutoAssembler,discover
from workspace_store import WorkspaceStore
from video_formats import DEFAULT_FORMATS
from explorer_menu import menu_entries


class DiscoveryTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def video(self,name):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'video');return path
    def test_one_file_finds_matching_article_without_other_products(self):
        leg=self.video('45555_ноги.mov');hands=self.video('45555_руки.mp4');self.video('47433_ноги.mov');self.video('47433_руки.mp4')
        result=discover([str(leg)]);self.assertEqual(len(result),1);self.assertEqual(set(result[0]['paths']),{str(leg),str(hands)});self.assertEqual(result[0]['article'],'45555')
    def test_folder_and_multi_selection_deduplicate_the_same_pair(self):
        leg=self.video('45555/one.mov');hands=self.video('45555/two.mp4');self.video('47433/47433_model.mov');self.video('47433/47433_hands.mp4')
        result=discover([str(self.root),str(leg),str(hands)]);self.assertEqual(len(result),2);self.assertTrue(all(item['status']=='queued' for item in result))
    def test_ambiguous_incomplete_and_date_names_need_review(self):
        self.video('49999/one.mov');self.video('49999/two.mp4');self.video('49999/three.mp4');self.video('48888/only.mov')
        self.video('dated/2026-10-01 12.00.mov');self.video('dated/2026-10-01 13.00.mp4')
        result=discover([str(self.root)]);self.assertTrue(all(item['status']=='review' for item in result))
    def test_two_different_articles_are_not_paired(self):
        self.video('45555_model.mov');self.video('47433_hands.mp4')
        result=discover([str(self.root)]);self.assertEqual(len(result),2);self.assertTrue(all(item['status']=='review' for item in result))
    def test_menu_offers_one_click_for_files_and_folders(self):
        self.assertEqual(dict(menu_entries([],True))['auto'],'Собрать автоматически');self.assertIn('auto',dict(menu_entries([],False)))


class AutoQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.manager=None
        self.paths=[]
        for name in ('45555_ноги.mov','45555_руки.mp4'):
            path=self.root/name;path.write_bytes(b'video');self.paths.append(str(path))
    def tearDown(self):
        if self.manager:self.manager.shutdown()
        self.temp.cleanup()
    def test_worker_runs_without_browser_coalesces_selection_and_persists_results(self):
        calls=[];finished=threading.Event()
        def process(item,settings,output,cancel,update):calls.append(item);return dict(status='done',outputs=['result.mp4'],message='Готово')
        self.manager=AutoAssembler(self.root,lambda:({'zooms':[1,1]},'Пресет',self.root),process,lambda run:finished.set(),quiet=.03)
        first=self.manager.enqueue([self.paths[0]]);second=self.manager.enqueue([self.paths[1]]);self.assertEqual(first,second)
        self.assertTrue(finished.wait(4));self.assertEqual(len(calls),1);self.assertEqual(self.manager.snapshot()['runs'][0]['status'],'done')
        self.assertNotIn('items',self.manager.snapshot(summary=True)['runs'][0])
        self.assertTrue((self.root/'automation.json').is_file())
        self.manager.shutdown();self.manager=AutoAssembler(self.root,lambda:None,None,None)
        self.assertEqual(self.manager.snapshot()['runs'][0]['preset'],'Пресет')
    def test_cancel_before_start_does_not_render(self):
        render=Mock();notify=Mock();self.manager=AutoAssembler(self.root,lambda:({},'Пресет',self.root),render,notify,quiet=2)
        self.manager.enqueue([self.paths[0]]);self.manager.cancel();self.assertFalse(self.manager.active);render.assert_not_called();self.assertEqual(self.manager.snapshot()['runs'][0]['status'],'cancelled');notify.assert_called_once()
    def test_interrupted_history_is_not_restarted_without_a_click(self):
        (self.root/'automation.json').write_text(json.dumps([dict(id='old',status='running',items=[],stage='',created=1,output=str(self.root),preset='Пресет')]),encoding='utf-8')
        self.manager=AutoAssembler(self.root,lambda:None,Mock(),Mock());self.assertFalse(self.manager.active);self.assertEqual(self.manager.snapshot()['runs'][0]['status'],'interrupted')


class AutomaticAppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.base=self.root/'profile';self.base.mkdir();self.work=self.root/'work';self.work.mkdir()
        self.patches=[patch.object(server,'BASE',self.base),patch.object(server,'SETTINGS_FILE',self.base/'settings.json'),patch.object(server,'workspace',WorkspaceStore(self.base)),patch.object(server,'WORK',self.work),patch.object(server,'automation',None),patch.dict(server.preferences,dict(mode='smart',bitrate_kbps=2500,sensitivity=40,save_processing_log=False,video_formats=DEFAULT_FORMATS),clear=True),patch.dict(server.jobs,{},clear=True),patch.dict(server.sources,{},clear=True)]
        for item in self.patches:item.start()
        self.client=server.app.test_client();self.headers={'X-Outmax-Token':server.TOKEN}
    def tearDown(self):
        if server.automation:server.automation.shutdown()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def test_last_applied_preset_wins_and_manual_cuts_are_not_reused(self):
        first=self.client.post('/api/presets',json={'name':'Сайт','settings':{'zooms':[1.4,1.2],'trims':[[0,4],[0,4]]}},headers=self.headers).json['presets'][0]
        self.client.post('/api/presets',json={'name':'Каталог','settings':{'zooms':[2,2]}},headers=self.headers)
        self.client.post('/api/automation/preset',json={'id':first['id']},headers=self.headers)
        settings,name,_=server.automation_settings();self.assertEqual(name,'Сайт');self.assertEqual(settings['zooms'],[1.4,1.2]);self.assertEqual(settings['trims'],[None,None]);self.assertEqual(server.load_preferences()['last_preset_id'],first['id'])
    def test_no_preset_uses_last_export_settings_and_output(self):
        output=self.root/'exports';payload=dict(items=[],single=None,lastSettings={'zooms':[1.2,1.3],'bitrate_kbps':750},output=str(output))
        server.workspace.save(payload,{}, {},self.work)
        settings,name,path=server.automation_settings();self.assertEqual(settings['zooms'],[1.2,1.3]);self.assertEqual(settings['bitrate_kbps'],750);self.assertEqual(path,output)
    def test_auto_command_does_not_show_or_steal_focus_from_open_editor(self):
        window=Mock();manager=Mock();manager.enqueue.return_value='run'
        with patch.object(server,'window',window),patch.object(server,'get_automation',return_value=manager),patch.object(server,'ensure_background_tray'):
            response=self.client.post('/api/shell/enqueue',json={'action':'auto','paths':[str(self.root/'45555_model.mov')]},headers=self.headers)
        self.assertEqual(response.status_code,200);window.show.assert_not_called();window.restore.assert_not_called();manager.enqueue.assert_called_once()
    def test_completion_banner_opens_its_own_output_without_activating_editor(self):
        first=self.root/'Готовые ролики';first.mkdir()
        second=self.root/'Другая сборка';second.mkdir()
        for status in ('done','done_with_review'):
            with self.subTest(status=status),patch.object(server,'ensure_background_tray'),patch.object(server.notifications,'notify') as notify:
                server.automation_finished(dict(status=status,stage='Готово: 6',output=str(first)))
                click=notify.call_args.kwargs['on_click']
                self.assertFalse(notify.call_args.kwargs['activate_on_click'])
                manager=Mock();manager.snapshot.return_value={'runs':[{'output':str(second)}]}
                with patch.object(server,'get_automation',return_value=manager),patch.object(server.os,'startfile') as open_folder:
                    click()
                open_folder.assert_called_once_with(str(first));manager.snapshot.assert_not_called()
    def test_failed_or_cancelled_banner_keeps_report_action(self):
        for status in ('error','cancelled'):
            with self.subTest(status=status),patch.object(server,'ensure_background_tray'),patch.object(server.notifications,'notify') as notify:
                server.automation_finished(dict(status=status,stage='Остановлено',output=str(self.root)))
                self.assertIs(notify.call_args.kwargs['on_click'],server.show_automation_report)
                self.assertTrue(notify.call_args.kwargs['activate_on_click'])
    def test_removed_output_folder_falls_back_to_report(self):
        with patch.object(server,'show_automation_report') as report,patch.object(server.os,'startfile') as open_folder:
            server.open_automation_folder(self.root/'Удалено')
        report.assert_called_once();open_folder.assert_not_called()
    def test_existing_output_skips_before_reading_or_moving_sources(self):
        folder=self.root/'exports'/'45555';folder.mkdir(parents=True);(folder/'45555.mp4').write_bytes(b'keep')
        with patch.object(server,'register_source') as prepare:
            result=server.process_automatic_pair(dict(article='45555',name='45555',paths=['none','none2']),server.validate_settings({}),folder.parent,threading.Event(),lambda **_:None)
        self.assertEqual(result['status'],'skipped');prepare.assert_not_called();self.assertEqual((folder/'45555.mp4').read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
