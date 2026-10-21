"""Real FFmpeg export smoke test on disposable synthetic sources."""
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as server
from engine import binary, probe, run


def main():
    with tempfile.TemporaryDirectory(prefix='outmax-export-') as temporary:
        root = Path(temporary)
        server.jobs.clear()
        server.sources.clear()
        server.preferences['save_processing_log'] = False
        def pair(article, broken=False):
            ids = []
            for role in ('ноги', 'руки'):
                key = article + role
                path = root / f'{key}.mp4'
                run([binary('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                     'testsrc2=size=160x160:rate=30:duration=1', '-c:v', 'libx264', str(path)], threading.Event())
                info = probe(path)
                if broken:
                    path.write_bytes(b'broken media')
                server.sources[key] = dict(path=path, name=path.name, info=info)
                ids.append(key)
            return dict(name=article, sources=ids, transition='cut', mode='template')
        def verify(article, originals):
            folder = root / 'output' / article
            result = probe(folder / f'{article}.mp4')
            assert (result['width'], result['height']) == (1080, 1080)
            assert abs(result['duration'] - 685/30) < .1
            assert {p.name for p in folder.iterdir()} == {f'{article}.mp4', 'Руки + Ноги'}
            for role, (path, digest) in zip(('ноги', 'руки'), originals):
                assert not path.exists()
                assert hashlib.sha256((folder / 'Руки + Ноги' / f'{article}_{role}.mp4').read_bytes()).digest() == digest
        def originals(item):
            return [(server.sources[k]['path'], hashlib.sha256(server.sources[k]['path'].read_bytes()).digest()) for k in item['sources']]
        one = pair('44238')
        before = originals(one)
        job = server.create_job(one | {'output':str(root / 'output')})
        server.execute_job(job)
        assert job['status'] == 'done', job
        verify('44238', before)
        print('PASS single export, dimensions, duration, byte-identical archives, no logs', flush=True)
        items = [pair('44239'), pair('44240', broken=True), pair('44241')]
        before = [originals(item) for item in items]
        client = server.app.test_client()
        response = client.post('/api/batch/render', json={'output':str(root / 'output'), 'items':items}, headers={'X-Outmax-Token':server.TOKEN})
        assert response.status_code == 200, response.json
        batch = server.batches[response.json['id']]
        batch['thread'].join(240)
        assert not batch['thread'].is_alive()
        assert [server.jobs[k]['status'] for k in batch['jobs']] == ['done', 'error', 'done']
        verify('44239', before[0])
        verify('44241', before[2])
        assert all(path.read_bytes() == b'broken media' for path, _ in before[1])
        assert not (root / 'output/44240/Руки + Ноги').exists()
        assert not list((root / 'output').rglob('*.partial.mp4'))
        print('PASS batch: two completed, failed source preserved, queue continued', flush=True)

if __name__ == '__main__':
    main()
