"""Prepare test copies; verify the supplied media remain byte-for-byte unchanged."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import probe


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    manifest=ROOT/'analysis/qa16/real-inputs.json'
    if '--verify' in sys.argv:
        data=json.loads(manifest.read_text(encoding='utf-8'))
        for entry in data['files']:
            assert digest(Path(entry['original']))==entry['sha256'],entry['original']
        print(f"PASS: {len(data['files'])} original test videos unchanged (SHA-256)")
        return
    target=ROOT/'analysis/qa16'/('real-inputs-'+uuid.uuid4().hex[:8])
    files=[]
    for source in sorted((ROOT/'видео').rglob('*')):
        if not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.m4v','.mkv','.avi','.webm'):
            continue
        destination=target/source.relative_to(ROOT/'видео')
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        files.append(dict(original=str(source),copy=str(destination),sha256=digest(source),info=probe(source)))
    assert files,'No real test videos found'
    manifest.write_text(json.dumps(dict(root=str(target),files=files),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Prepared {len(files)} test copies at {target}')
    print(json.dumps([dict(name=Path(entry['original']).name,info=entry['info']) for entry in files],ensure_ascii=False))


if __name__=='__main__':main()
