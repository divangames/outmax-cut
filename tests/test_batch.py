import pathlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import app as server
from batching import group_sources, safe_folder, suggest_pair, is_generated_video
from engine import Cancelled


def source(key, name, relative=None, score=.5):
    return dict(id=key, name=name, relative=relative or name, model_score=score,
                info={"duration":10}, path=pathlib.Path("input-"+key))


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.client = server.app.test_client()
        self.headers = {"X-Outmax-Token":server.TOKEN}
        server.jobs.clear()
        server.batches.clear()
        server.sources.clear()
        server.sources.update({"a":source("a","44238_model.mp4"), "b":source("b","44238_hands.mp4")})
        for key, entry in server.sources.items():
            entry["path"] = self.root / entry["name"]
            entry["path"].write_bytes(("original-" + key).encode())
        self.preferences = patch.dict(server.preferences, save_processing_log=False)
        self.preferences.start()
        self.workspace=patch.object(server,'workspace',server.WorkspaceStore(self.root/'profile'))
        self.workspace.start()

    def tearDown(self):
        for batch in server.batches.values():
            batch["cancel"].set()
            batch["thread"].join(5)
        for task in server.imports.values():
            task["cancel"].set()
            task["thread"].join(5)
        server.imports.clear()
        self.preferences.stop()
        self.workspace.stop()
        self.temp.cleanup()

    def item(self, **kwargs):
        return dict(name="44238", item_id="one", sources=["a","b"], mode="template",
                    transition="lens", crops=[.8,.5], sensitivity=40) | kwargs

    def extra_pair(self, article):
        keys = [article + role for role in ("model", "hands")]
        for key in keys:
            server.sources[key] = source(key, key + ".mp4")
            server.sources[key]["path"] = self.root / (key + ".mp4")
            server.sources[key]["path"].write_bytes(b"original")
        return keys

    def wait(self, key):
        server.batches[key]["thread"].join(5)
        self.assertFalse(server.batches[key]["thread"].is_alive())
        return self.client.get("/api/batches/"+key).json

    def test_pairing_by_names_and_images(self):
        a=source("a","SKU руки.mov",score=.9)
        b=source("b","SKU модель.mov",score=.1)
        self.assertEqual(suggest_pair([a,b])[0],["b","a"])
        a["name"]="one.MOV";b["name"]="two.MOV"
        self.assertEqual(suggest_pair([a,b])[0],["a","b"])
        self.assertEqual(suggest_pair([a])[0],["a",None])

    def test_single_clip_keeps_named_role_before_image_suggestion(self):
        for name,score,pair,missing in (
                ("45555_ноги.mov",.1,["a",None],"рук"),
                ("45555_руки.mp4",.9,[None,"a"],"ног"),
                ("47433.MOV",.78,["a",None],"рук"),
                ("47433.mp4",.58,[None,"a"],"ног")):
            with self.subTest(name=name):
                assigned,note=suggest_pair([source("a",name,score=score)])
                self.assertEqual(assigned,pair)
                self.assertIn("Нет видео "+missing,note)
                self.assertIn("пропущен",note)
        self.assertEqual(suggest_pair([])[0],[None,None])

    def test_exact_article_path_and_existing_folder(self):
        dest = self.root / "44238"
        dest.mkdir()
        with patch.object(server, "OUTPUT", self.root):
            job = server.create_job(self.item())
            self.assertEqual(job["output"], dest / "44238.mp4")
            with self.assertRaises(ValueError):
                server.create_job(self.item())
        server.jobs.clear()
        job = server.create_job(self.item(folder="Каталог/Сезон/44238", output=str(self.root)))
        self.assertEqual(job["output"], dest / "44238.mp4")
        server.jobs.clear()
        job = server.create_job(self.item(output=str(dest)))
        self.assertEqual(job["output"], dest / "44238.mp4")

    def test_shell_selection_coalesces_and_deduplicates(self):
        video = self.root / "Артикул модель.mov"
        video.write_bytes(b"fixture")
        server.shell_paths.clear()
        try:
            for _ in range(2):
                response = self.client.post("/api/shell/enqueue", json={"paths":[str(video)]}, headers=self.headers)
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.post("/api/shell/import", json={}, headers=self.headers).json, {"pending":False})
            server.shell_updated -= 2
            with patch.object(server, "start_import", return_value={"id":"test"}) as start:
                self.assertEqual(self.client.post("/api/shell/import", json={}, headers=self.headers).json["id"], "test")
                files, skipped = start.call_args.args
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0][0], video)
                self.assertEqual(skipped, 0)
        finally:
            server.shell_paths.clear()

    def test_folder_grouping_and_ambiguous_sources(self):
        entries=[source("a","model.mov","A/model.mov"),source("b","hands.mov","A/hands.mov"),
                 source("c","random.mov","B/random.mov")]
        groups=group_sources(entries)
        self.assertEqual(len(groups),2)
        self.assertEqual(groups[0]["sources"],["a","b"])
        self.assertEqual(groups[1]["sources"],[None,"c"])
        entries=[source(str(i),name,"A/"+name) for i,name in enumerate(
            ["123_model.mov","123_hands.mov","456_модель.mov","456_руки.mov"])]
        self.assertEqual(len(group_sources(entries)),2)
        entries.append(source("x","extra.mov","A/extra.mov"))
        self.assertEqual(group_sources(entries)[0]["sources"],[None,None])

    def test_safe_output_hierarchy(self):
        path=safe_folder("../../CON/Товар:1")
        self.assertNotIn("..",path.parts)
        self.assertIn("_CON",path.parts)
        self.assertNotIn(":",str(path))
        self.assertFalse(path.is_absolute())

    def test_article_named_input_is_not_mistaken_for_export(self):
        folder = self.root / "47433"
        folder.mkdir()
        video = folder / "47433.mp4"
        video.write_bytes(b"original")
        self.assertFalse(is_generated_video(video))
        archive = folder / "Руки + Ноги"
        archive.mkdir()
        (archive / "47433_ноги.MOV").write_bytes(b"legs")
        (archive / "47433_руки.mp4").write_bytes(b"hands")
        self.assertTrue(is_generated_video(video))

    def test_generated_exports_are_not_reimported(self):
        import json
        folder = self.root / "generated"
        folder.mkdir()
        video=folder/"Монтаж.mp4"
        video.write_bytes(b"export")
        self.assertFalse(is_generated_video(video))
        video.with_suffix(".json").write_text(json.dumps({"generator":"OUTMAX Cut"}))
        self.assertTrue(is_generated_video(video))
        response=self.client.post("/api/batch/import",json={"path":str(folder)},headers=self.headers)
        self.assertEqual(response.status_code,400)
        video.with_suffix(".json").write_text('[]')
        self.assertFalse(is_generated_video(video))

    def test_queue_snapshots_settings_continues_after_failure_and_no_overwrite(self):
        seen=[]
        def fake_render(sources,infos,settings,work,output,progress,cancel):
            seen.append(settings)
            if settings["transition"]=="morph":
                raise RuntimeError("Bad source")
            output.write_bytes(b"export")
            return {"result":{"size":6}}
        with patch.object(server,"render",fake_render):
            response=self.client.post("/api/batch/render",json={"output":str(self.root),"items":[
                self.item(item_id="one",transition="cut"),
                self.item(name="44239",item_id="two",transition="morph",sources=self.extra_pair("44239")),
                self.item(name="44240",item_id="three",crops=[.2,.9],sources=self.extra_pair("44240"))]},headers=self.headers)
            self.assertEqual(response.status_code,200,response.json)
            result=self.wait(response.json["id"])
        self.assertEqual(result["status"],"done_with_errors")
        self.assertEqual([j["status"] for j in result["jobs"]],["done","error","done"])
        self.assertEqual(seen[-1]["crops"],[.2,.9])
        self.assertEqual(len({j["output"] for j in result["jobs"]}),3)
        self.assertTrue((self.root/"44238/44238.mp4").exists())
        self.assertTrue((self.root/"44240/44240.mp4").exists())

    def test_cancel_current_and_pending(self):
        started=threading.Event()
        def fake_render(sources,infos,settings,work,output,progress,cancel):
            started.set()
            cancel.wait(4)
            raise Cancelled()
        with patch.object(server,"render",fake_render):
            response=self.client.post("/api/batch/render",json={"output":str(self.root),
                "items":[self.item(),self.item(name="44239",item_id="two",sources=self.extra_pair("44239"))]},headers=self.headers)
            key=response.json["id"]
            self.assertTrue(started.wait(2))
            self.assertEqual(self.client.post("/api/render",json=self.item(),headers=self.headers).status_code,409)
            self.client.post("/api/batches/"+key+"/cancel",json={},headers=self.headers)
            result=self.wait(key)
        self.assertEqual([j["status"] for j in result["jobs"]],["cancelled","cancelled"])

    def test_success_copies_original_bytes_and_preserves_inputs(self):
        original = [entry["path"] for entry in server.sources.values()]
        def fake_render(paths, infos, settings, work, output, progress, cancel):
            self.assertTrue(all(path.exists() for path in original))
            self.assertFalse((output.parent / "Руки + Ноги").exists())
            output.write_bytes(b"export")
            return {"result":{"size":6}}
        job = server.create_job(self.item(output=str(self.root)))
        with patch.object(server, "render", fake_render):
            server.execute_job(job)
        self.assertEqual(job["status"], "done")
        self.assertTrue(all(path.exists() for path in original))
        folder = self.root / "44238"
        self.assertEqual({p.name for p in folder.iterdir()}, {"44238.mp4", "Руки + Ноги"})
        self.assertEqual((folder / "Руки + Ноги/44238_ноги.mp4").read_bytes(), b"original-a")
        self.assertEqual((folder / "Руки + Ноги/44238_руки.mp4").read_bytes(), b"original-b")

    def test_failure_preserves_originals(self):
        job = server.create_job(self.item(output=str(self.root)))
        with patch.object(server, "render", side_effect=RuntimeError("broken")):
            server.execute_job(job)
        self.assertEqual(job["status"], "error")
        self.assertTrue(all(s["path"].exists() for s in server.sources.values()))
        self.assertFalse((self.root / "44238/Руки + Ноги").exists())

    def test_export_preserves_excluded_and_selected_sources_in_place(self):
        excluded=self.extra_pair("47433")
        before={entry['path']:entry['path'].read_bytes() for entry in server.sources.values()}
        def fake_render(paths,infos,settings,work,output,progress,cancel):
            output.write_bytes(b'export');return {'result':{'size':6}}
        with patch.object(server,'render',fake_render):
            response=self.client.post('/api/batch/render',json={'output':str(self.root),'items':[self.item(formats=['standard','marketplace','vertical'])]},headers=self.headers)
            result=self.wait(response.json['id'])
        self.assertEqual(result['status'],'done')
        self.assertEqual(len(result['jobs'][0]['variants']),3)
        for path,data in before.items():self.assertEqual(path.read_bytes(),data)
        self.assertFalse((self.root/'47433').exists())
        self.assertTrue(all(server.sources[key]['path'] in before for key in excluded))

    def test_preview_works_without_article_or_output_and_preserves_sources(self):
        original=[entry["path"] for entry in server.sources.values()]
        for entry in server.sources.values():entry["preview_path"]=entry["path"]
        job=server.create_job({"sources":["a","b"],"format":"vertical","crops_x":[.1,.9]}, preview=True)
        def render(paths,infos,settings,work,output,progress,cancel):
            output.write_bytes(b"preview")
            return {"result":{"size":7}}
        with patch.object(server,"render",render),patch.object(server,"archive_sources") as archive:
            server.execute_job(job)
        self.assertEqual(job["status"],"done")
        archive.assert_not_called()
        self.assertTrue(all(path.exists() for path in original))
        self.assertTrue(job["output"].is_relative_to(server.WORK))
        self.assertEqual(job["settings"]["crops_x"],[.1,.9])

    def test_archive_copy_failure_retains_both_originals(self):
        job = server.create_job(self.item(output=str(self.root)))
        job["output"].parent.mkdir()
        job["output"].write_bytes(b"export")
        with patch.object(server.shutil, "copyfileobj", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                server.archive_sources(job)
        self.assertTrue(all(s["path"].exists() for s in server.sources.values()))
        self.assertFalse((job["output"].parent / "Руки + Ноги").exists())

    def test_existing_export_is_never_overwritten(self):
        folder = self.root / "44238"
        folder.mkdir()
        output = folder / "44238.mp4"
        output.write_bytes(b"previous result")
        response = self.client.post("/api/render", json=self.item(output=str(self.root)), headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(output.read_bytes(), b"previous result")
        self.assertTrue(all(s["path"].exists() for s in server.sources.values()))

    def test_conflicting_archive_is_never_overwritten(self):
        folder = self.root / "44238/Руки + Ноги"
        folder.mkdir(parents=True)
        existing = folder / "44238_руки.mp4"
        existing.write_bytes(b"keep")
        job = server.create_job(self.item(output=str(self.root)))
        with patch.object(server, "render") as render:
            server.execute_job(job)
            render.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"keep")
        self.assertTrue(all(s["path"].exists() for s in server.sources.values()))

    def test_log_preference_persists_and_creates_only_opt_in_log(self):
        with patch.object(server, "SETTINGS_FILE", self.root / "settings.json"):
            self.assertFalse(server.load_preferences()["save_processing_log"])
            self.assertEqual(server.load_preferences()["mode"], "smart")
            response = self.client.post("/api/settings", json={"save_processing_log":True}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(server.load_preferences()["save_processing_log"])
            job = server.create_job(self.item(output=str(self.root)))
            def fake_render(paths, infos, settings, work, output, progress, cancel):
                output.write_bytes(b"export")
                return {"result":{"size":6}}
            with patch.object(server, "render", fake_render):
                server.execute_job(job)
            self.assertEqual(job["status"], "done")
            self.assertTrue((job["output"].parent / "монтаж.txt").exists())
            response = self.client.post("/api/settings", json={"save_processing_log":False}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(server.load_preferences()["save_processing_log"])

    def test_reject_entire_queue_when_one_pair_is_missing(self):
        response=self.client.post("/api/batch/render",json={"output":str(self.root),
            "items":[self.item(),self.item(sources=["a",None])]},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertFalse(server.jobs)

    def test_three_formats_archive_only_after_all_are_ready(self):
        seen=[]
        originals=[s["path"] for s in server.sources.values()]
        def render(paths, infos, settings, work, output, progress, cancel):
            self.assertTrue(all(p.exists() for p in originals))
            seen.append(settings["format"])
            output.write_bytes(settings["format"].encode())
            return {"result":{"size":output.stat().st_size}}
        job=server.create_job(self.item(output=str(self.root), formats=["standard","marketplace","vertical"]))
        with patch.object(server,"render",render),patch.object(server,"archive_sources",wraps=server.archive_sources) as archive:
            server.execute_job(job)
        self.assertEqual(job["status"],"done")
        self.assertEqual(seen,["standard","marketplace","vertical"])
        archive.assert_called_once()
        self.assertEqual([v["output"].name for v in job["variants"]],["44238_1080x1080.mp4","44238_900x1200.mp4","44238_1080x1920.mp4"])
        self.assertTrue((self.root/"44238/Руки + Ноги/44238_ноги.mp4").exists())
        view=self.client.get('/api/jobs/'+job['id']).json
        self.assertEqual(len(view['variants']),3)
        response=self.client.get('/result/'+job['id']+'?format=vertical')
        self.assertEqual(response.data,b'vertical');response.close()
        self.assertEqual(self.client.get('/result/'+job['id']+'?format=unknown').status_code,404)

    def test_multi_format_failure_or_cancel_rolls_back_own_outputs(self):
        for failure in (RuntimeError("encoder failed"),Cancelled()):
            server.jobs.clear()
            job=server.create_job(self.item(output=str(self.root),formats=["standard","vertical"]))
            def render(paths,infos,settings,work,output,progress,cancel):
                if settings['format']=='vertical':raise failure
                output.write_bytes(b'first variant')
                return {"result":{"size":13}}
            with patch.object(server,"render",render):server.execute_job(job)
            self.assertIn(job['status'],('error','cancelled'))
            self.assertTrue(all(s['path'].exists() for s in server.sources.values()))
            self.assertFalse(any(v['output'].exists() for v in job['variants']))

    def test_collision_in_later_format_prevents_every_render(self):
        folder=self.root/'44238';folder.mkdir()
        existing=folder/'44238_1080x1920.mp4';existing.write_bytes(b'keep')
        response=self.client.post('/api/render',json=self.item(output=str(self.root),formats=['standard','vertical']),headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertFalse(server.jobs)
        self.assertEqual(existing.read_bytes(),b'keep')

    def test_preview_cache_ignores_export_only_choices(self):
        for s in server.sources.values():s['preview_path']=s['path']
        def render(paths,infos,settings,work,output,progress,cancel):
            output.write_bytes(b'preview')
            return {'result':{'size':7}}
        with patch.object(server,'render',render):
            first=self.client.post('/api/preview',json=self.item(),headers=self.headers).json
            server.jobs[first['id']]['thread'].join(3)
            second=self.client.post('/api/preview',json=self.item(bitrate_kbps=500,formats=['standard','vertical']),headers=self.headers).json
        self.assertEqual(first['id'],second['id'])
        self.assertTrue(second['cached'])

    def test_preferences_are_partial_persistent_and_validated(self):
        before=dict(server.preferences)
        try:
            with patch.object(server,'SETTINGS_FILE',self.root/'settings.json'):
                for body in ({'mode':'template'},{'bitrate_kbps':750},{'sensitivity':73},{'save_processing_log':True}):
                    self.assertEqual(self.client.post('/api/settings',json=body,headers=self.headers).status_code,200)
                restored=server.load_preferences()
                self.assertEqual(restored,{'mode':'template','bitrate_kbps':750,'sensitivity':73,'save_processing_log':True,'video_formats':server.DEFAULT_FORMATS})
                for body in ({'mode':'wrong'},{'bitrate_kbps':True},{'sensitivity':101},{'save_processing_log':1}):
                    self.assertEqual(self.client.post('/api/settings',json=body,headers=self.headers).status_code,400)
                self.assertEqual(server.load_preferences(),restored)
        finally:
            server.preferences.clear();server.preferences.update(before)


if __name__=="__main__":
    unittest.main()

