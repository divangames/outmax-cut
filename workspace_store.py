"""Atomic local queue/preset storage. Source footage is never moved by autosave."""
import json
import os
from pathlib import Path
import re
import shutil
import threading


class WorkspaceStore:
    def __init__(self, base):
        self.base=Path(base);self.file=self.base/'queue.json';self.media=self.base/'queue-media'
        self.guard=threading.RLock()

    def read(self):
        with self.guard:
            for path in (self.file,self.file.with_suffix('.previous.json')):
                try:
                    data=json.loads(path.read_text(encoding='utf-8'))
                    if data.get('schema')==1:return data
                except (OSError,ValueError,AttributeError):continue
            return None

    def _copy(self, path, target):
        if target.exists():return target
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.tmp')
        try:os.link(path,temporary)
        except OSError:shutil.copy2(path,temporary)
        temporary.replace(target)
        return target

    def record_location(self, source):
        key=source['id']
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',key):return
        with self.guard:
            folder=self.media/key;folder.mkdir(parents=True,exist_ok=True)
            temporary=folder/'location.tmp';temporary.write_text(str(source['path']),encoding='utf-8');temporary.replace(folder/'location.txt')

    def locate(self, key, fallback):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',key):return fallback
        try:
            candidate=Path((self.media/key/'location.txt').read_text(encoding='utf-8'))
            return candidate if candidate.is_absolute() and candidate.is_file() else fallback
        except OSError:return fallback

    def save(self, payload, sources, jobs, work):
        if not isinstance(payload,dict) or not isinstance(payload.get('items'),list) or len(payload['items'])>500:
            raise ValueError('Некорректная очередь.')
        with self.guard:
            # JSON removes references to objects concurrently changed by the UI/worker.
            payload=json.loads(json.dumps(payload,allow_nan=False))
            used=set()
            snapshots=[i.get('snapshot',{}) for i in payload['items']]+[payload.get('single') or {}]
            for snapshot in snapshots:
                used.update(s['id'] for s in snapshot.get('sources',[]) if isinstance(s,dict) and s.get('id'))
            for item in payload['items']:
                used.update(s['id'] for s in item.get('candidates',[]) if isinstance(s,dict) and s.get('id'))
            entries={}
            for key in used:
                if key not in sources or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',key):continue
                source=dict(sources[key]);folder=self.media/key
                for field in ('path','preview_path','poster_path'):
                    path=source.get(field,work/key/'poster.jpg' if field=='poster_path' else None)
                    if path is None:continue
                    path=Path(path)
                    if path.is_file() and path.resolve().is_relative_to(work.resolve()):
                        # A direct-play proxy may be the uploaded original: keep one copy.
                        name='poster.jpg' if field=='poster_path' else path.name
                        path=self._copy(path,folder/name)
                    source[field]=str(path)
                entries[key]=source
                self.record_location(source)
            saved_jobs={}
            for job in list(jobs.values()):
                if job.get('preview') or job.get('status')!='done':continue
                if not any(key in used for key in job.get('source_ids',[])):continue
                saved_jobs[job['id']]={key:value for key,value in job.items() if key not in ('cancel','thread','started_at')}
            data=dict(schema=1,payload=payload,sources=entries,jobs=saved_jobs)
            self.base.mkdir(parents=True,exist_ok=True)
            temporary=self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,ensure_ascii=False,default=str,allow_nan=False),encoding='utf-8')
            if self.file.exists():
                backup=self.file.with_suffix('.previous.tmp');shutil.copy2(self.file,backup);backup.replace(self.file.with_suffix('.previous.json'))
            temporary.replace(self.file)
            return data
