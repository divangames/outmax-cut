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
        server.sources.update({"a":source("a","model.mov"), "b":source("b","hands.mov")})

    def tearDown(self):
        for batch in server.batches.values():
            batch["cancel"].set()
            batch["thread"].join(5)
        self.temp.cleanup()

    def item(self, **kwargs):
        return dict(name="Товар", item_id="one", sources=["a","b"], mode="template",
                    transition="lens", crops=[.8,.5], sensitivity=40) | kwargs

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

    def test_original_single_name_and_full_folder_hierarchy(self):
        server.sources["a"]["name"] = "Артикул 123.MOV"
        with patch.object(server, "OUTPUT", self.root):
            job = server.create_job(self.item())
            self.assertEqual(job["output"].name, "Артикул 123_модель+ноги.mp4")
            again = server.create_job(self.item())
            self.assertEqual(again["output"].name, "Артикул 123_модель+ноги_2.mp4")
        hierarchy = "/".join(["Каталог", "Сезон", "Мужские", "Обувь", "Кроссовки", "Бренд", "А"*90])
        job = server.create_job(self.item(folder=hierarchy, output=str(self.root)))
        self.assertEqual(job["output"].parent, self.root / pathlib.Path(hierarchy))

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

    def test_generated_exports_are_not_reimported(self):
        import json
        video=self.root/"Монтаж.mp4"
        video.write_bytes(b"export")
        self.assertFalse(is_generated_video(video))
        video.with_suffix(".json").write_text(json.dumps({"generator":"OUTMAX Cut"}))
        self.assertTrue(is_generated_video(video))
        response=self.client.post("/api/batch/import",json={"path":str(self.root)},headers=self.headers)
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
                self.item(item_id="two",transition="morph"),
                self.item(item_id="three",crops=[.2,.9])]},headers=self.headers)
            self.assertEqual(response.status_code,200,response.json)
            result=self.wait(response.json["id"])
        self.assertEqual(result["status"],"done_with_errors")
        self.assertEqual([j["status"] for j in result["jobs"]],["done","error","done"])
        self.assertEqual(seen[-1]["crops"],[.2,.9])
        self.assertEqual(len({j["output"] for j in result["jobs"]}),3)
        self.assertTrue((self.root/"Товар/Монтаж.mp4").exists())
        self.assertTrue((self.root/"Товар/Монтаж_3.mp4").exists())

    def test_cancel_current_and_pending(self):
        started=threading.Event()
        def fake_render(sources,infos,settings,work,output,progress,cancel):
            started.set()
            cancel.wait(4)
            raise Cancelled()
        with patch.object(server,"render",fake_render):
            response=self.client.post("/api/batch/render",json={"output":str(self.root),
                "items":[self.item(),self.item(item_id="two")]},headers=self.headers)
            key=response.json["id"]
            self.assertTrue(started.wait(2))
            self.assertEqual(self.client.post("/api/render",json=self.item(),headers=self.headers).status_code,409)
            self.client.post("/api/batches/"+key+"/cancel",json={},headers=self.headers)
            result=self.wait(key)
        self.assertEqual([j["status"] for j in result["jobs"]],["cancelled","cancelled"])

    def test_reject_entire_queue_when_one_pair_is_missing(self):
        response=self.client.post("/api/batch/render",json={"output":str(self.root),
            "items":[self.item(),self.item(sources=["a",None])]},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertFalse(server.jobs)


if __name__=="__main__":
    unittest.main()

