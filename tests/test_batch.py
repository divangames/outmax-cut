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

    def tearDown(self):
        for batch in server.batches.values():
            batch["cancel"].set()
            batch["thread"].join(5)
        for task in server.imports.values():
            task["cancel"].set()
            task["thread"].join(5)
        server.imports.clear()
        self.preferences.stop()
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
        self.assertEqual(suggest_pair([a])[0],[None,None])

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
        self.assertEqual(groups[1]["sources"],[None,None])
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

    def test_success_moves_original_bytes_without_extra_files(self):
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
        self.assertTrue(all(not path.exists() for path in original))
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
            self.assertEqual(server.load_preferences(), {"save_processing_log":False})
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


if __name__=="__main__":
    unittest.main()

