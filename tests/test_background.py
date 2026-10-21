import io
import threading
import unittest
from unittest.mock import patch
import app as server


class BackgroundImportTests(unittest.TestCase):
    def test_preview_preparation_does_not_hold_request_worker(self):
        started, release = threading.Event(), threading.Event()
        def prepare(path, folder, name, relative, cancel):
            started.set()
            release.wait(5)
            return dict(id=folder.name,name=name,relative=relative,info={'duration':1},
                        model_score=.5,preview_path=folder/'preview.mp4')
        task=None
        try:
            with patch.object(server,'register_source',side_effect=prepare):
                client=server.app.test_client()
                response=client.post('/api/upload',data={'file':(io.BytesIO(b'fixture'),'44238_руки.mp4')},
                    headers={'X-Outmax-Token':server.TOKEN})
                self.assertEqual(response.status_code,200)
                task=server.imports[response.json['id']]
                self.assertTrue(started.wait(1))
                self.assertEqual(client.get('/api/imports/'+task['id']).json['status'],'running')
                self.assertEqual(client.get('/api/config').status_code,200)
                release.set();task['thread'].join(3)
                self.assertEqual(task['status'],'done')
                self.assertFalse(task['errors'])
                self.assertEqual(task['groups'][0]['candidates'][0]['name'],'44238_руки.mp4')
        finally:
            release.set()
            if task:task['thread'].join(3);server.imports.pop(task['id'],None)

if __name__=='__main__':unittest.main()
