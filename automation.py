"""Explorer one-click discovery and a UI-independent serial render queue."""
from collections import defaultdict
import json
from pathlib import Path
import re
import threading
import time
import uuid

from batching import VIDEO_EXTENSIONS, is_generated_video, MODEL_WORDS, HANDS_WORDS


def article_hint(path):
    if path.parent.name.isdecimal():return path.parent.name
    if re.match(r'^\d{4}[-.]\d{2}[-.]\d{2}',path.stem):return None
    match=re.match(r'^(\d+)(?:[\s_.()-]|$)',path.stem)
    return match[1] if match else None


def pair_key(path):
    article=article_hint(path)
    if article:return article
    stem=HANDS_WORDS.sub(' ',MODEL_WORDS.sub(' ',path.stem))
    return re.sub(r'[\s_.()-]+',' ',stem).strip().casefold()


def discover(paths):
    files=set();issues=[]
    def eligible(path,root):
        return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and not path.is_symlink() and path.resolve().is_relative_to(root) and not is_generated_video(path)
    for raw in paths:
        selected=Path(raw)
        if not selected.exists():issues.append(dict(name=selected.name,paths=[str(selected)],status='review',message='Файл или папка не найдены.'));continue
        root=selected.resolve() if selected.is_dir() else selected.resolve().parent
        if selected.is_dir():
            for path in root.rglob('*'):
                if eligible(path,root):files.add(path.resolve())
                if len(files)>1000:raise ValueError('За один запуск можно обработать до 1000 исходных видео.')
        else:
            if is_generated_video(selected):issues.append(dict(name=selected.name,paths=[str(selected)],status='skipped',message='Выбран готовый ролик OUTMAX.'));continue
            neighbors=[path.resolve() for path in root.iterdir() if eligible(path,root)]
            same=[path for path in neighbors if pair_key(path)==pair_key(selected)]
            candidates=same if len(same)>1 else neighbors if len(neighbors)==2 else [selected.resolve()]
            files.update(candidates)
    grouped=defaultdict(list)
    for path in sorted(files):grouped[(path.parent,pair_key(path))].append(path)
    # Two differently named clips in a product folder still form one candidate pair.
    folders=defaultdict(list)
    for (parent,key),members in grouped.items():folders[parent].append((key,members))
    result=[]
    for parent,groups in folders.items():
        all_files=[path for _,members in groups for path in members]
        if len(all_files)==2 and not all(article_hint(path) for path in all_files):groups=[('',all_files)]
        for key,members in groups:
            article=article_hint(members[0])
            if len(members)==2 and article_hint(members[1]) not in (None,article):article=None
            name=article or parent.name
            item=dict(name=name,article=article,paths=list(map(str,members)))
            if len(members)!=2:item.update(status='review',message=f'Найдено видео: {len(members)}. Нужны два однозначных исходника.')
            elif not article:item.update(status='review',message='Не удалось определить артикул. Назовите папку или файлы номером товара.')
            else:item.update(status='queued',message='Проверяем пару')
            result.append(item)
    return result+issues


class AutoAssembler:
    def __init__(self,base,settings,process,notify,job_view=lambda key:None,quiet=1.5):
        self.file=Path(base)/'automation.json';self.settings=settings;self.process=process;self.notify=notify;self.job_view=job_view;self.quiet=quiet
        self.condition=threading.Condition(threading.RLock());self.runs=[];self.thread=None;self.closed=False
        try:
            self.runs=json.loads(self.file.read_text(encoding='utf-8'))[-50:]
            for run in self.runs:
                if run['status'] in ('queued','running','cancelling'):run.update(status='interrupted',stage='Прервано. Можно запустить повторно.')
        except (OSError,ValueError,TypeError):self.runs=[]

    @property
    def active(self):
        with self.condition:return any(run['status'] in ('queued','running','cancelling') for run in self.runs)

    def _save(self):
        self.file.parent.mkdir(parents=True,exist_ok=True)
        data=[{key:value for key,value in run.items() if not key.startswith('_')} for run in self.runs[-50:]]
        temporary=self.file.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temporary.replace(self.file)

    def enqueue(self,paths):
        if not isinstance(paths,list) or not 1<=len(paths)<=1000 or any(not isinstance(path,str) or not Path(path).is_absolute() for path in paths):raise ValueError('Выберите существующий файл или папку.')
        settings,preset,output=self.settings()
        with self.condition:
            if self.closed:raise ValueError('Приложение закрывается.')
            previous=self.runs[-1] if self.runs else None
            if previous and previous['status']=='queued' and time.monotonic()-previous['_updated']<self.quiet:
                previous['paths']=list(dict.fromkeys(previous['paths']+paths));previous['_updated']=time.monotonic();run=previous
            else:
                run=dict(id=uuid.uuid4().hex,status='queued',stage='Ожидаем выбранные файлы',created=time.time(),paths=list(dict.fromkeys(paths)),settings=settings,preset=preset,output=str(output),items=[],_updated=time.monotonic(),_cancel=threading.Event())
                self.runs.append(run)
            self._save()
            if self.thread is None or not self.thread.is_alive():self.thread=threading.Thread(target=self._worker,daemon=True);self.thread.start()
            self.condition.notify_all();return run['id']

    def snapshot(self,summary=False):
        with self.condition:
            rows=self.runs[-5:] if summary else self.runs[-50:]
            data=json.loads(json.dumps([{key:value for key,value in run.items() if not key.startswith('_') and (not summary or key in ('id','status','stage','preset','output','created'))} for run in rows]))
        for run in data:
            for item in run.get('items',[]):
                if item.get('job_id') and run['status'] in ('running','cancelling'):
                    job=self.job_view(item['job_id'])
                    if job:item.update(progress=job['progress'],message=job['stage'],eta_seconds=job.get('eta_seconds'))
        return dict(active=self.active,runs=data[::-1])

    def cancel(self,notify=True):
        stopped=[]
        with self.condition:
            for run in self.runs:
                if run['status'] in ('queued','running','cancelling'):
                    if run['status']=='queued':run.update(stage='Автосборка остановлена до запуска',finished=time.time());stopped.append(run)
                    run['_cancel'].set();run['status']='cancelled' if run['status']=='queued' else 'cancelling'
            self._save();self.condition.notify_all()
        if notify:
            for run in stopped:self.notify(run)

    def shutdown(self):
        self.cancel(notify=False)
        with self.condition:self.closed=True;self.condition.notify_all()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(40)

    def _worker(self):
        while True:
            with self.condition:
                pending=next((run for run in self.runs if run['status']=='queued'),None)
                if self.closed:return
                if pending is None:self.condition.wait();continue
                delay=self.quiet-(time.monotonic()-pending['_updated'])
                if delay>0:self.condition.wait(delay);continue
                run=pending;run.update(status='running',stage='Ищем пары');self._save()
            try:
                items=discover(run['paths'])
                if len(items)>500:raise ValueError('За один запуск можно собрать до 500 товаров.')
                with self.condition:run['items']=items;self._save()
                for item in items:
                    if run['_cancel'].is_set():break
                    if item['status']!='queued':continue
                    def update(**values):
                        with self.condition:item.update(values);self._save()
                    update(status='running',message='Готовим исходники')
                    try:item.update(self.process(item,run['settings'],Path(run['output']),run['_cancel'],update))
                    except Exception as error:item.update(status='cancelled' if run['_cancel'].is_set() else 'review',message=str(error))
                    with self.condition:self._save()
                cancelled=run['_cancel'].is_set()
                for item in items:
                    if item['status'] in ('running','queued'):item.update(status='cancelled',message='Сборка остановлена')
                done=sum(item['status']=='done' for item in items);review=sum(item['status']=='review' for item in items);skipped=sum(item['status']=='skipped' for item in items)
                with self.condition:run.update(status='cancelled' if cancelled else 'done_with_review' if review else 'done',stage=f'Готово: {done} · проверить: {review} · пропущено: {skipped}',finished=time.time());self._save()
                self.notify(run)
            except Exception as error:
                with self.condition:run.update(status='error',stage=str(error),finished=time.time());self._save()
                self.notify(run)
