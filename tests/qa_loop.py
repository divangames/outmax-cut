"""Encode supplied footage and inspect every frame, including the wrap and transition endpoints."""
from pathlib import Path
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import make_proxy,probe,render

OUT=ROOT/'analysis/qa17'
PAIRS=[('45555','45555_ноги.mov','45555_руки.mp4'),('47433','47433.MOV','47433.mp4'),
       ('47467','47467.MOV','47467.mp4'),('47469','47469.MOV','47469.mp4'),
       ('47656','47656_2.MOV','47656_1.MOV'),('47664','47664_1.MOV','47664_2.MOV')]


def prepared(pair):
    article,model,hands=pair
    source=ROOT/'видео'/article/hands
    proxy=OUT/(article+'-hands.mp4')
    if not proxy.exists():make_proxy(source,probe(source),proxy)
    return [OUT/(article+'-model.mp4'),proxy]


def inspect(path, report=None):
    cap=cv2.VideoCapture(str(path))
    frames=[];details=[];means=[];changes=[];previous=None
    while True:
        ok,frame=cap.read()
        if not ok:break
        small=cv2.resize(frame,(128,128));gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        means.append(float(gray.mean()))
        gray=cv2.GaussianBlur(gray,(5,5),0)
        details.append(float(np.mean(cv2.absdiff(gray,cv2.GaussianBlur(gray,(15,15),0)))))
        if previous is not None:changes.append(float(np.mean(cv2.absdiff(small,previous))))
        previous=small
        if len(frames)<3:frames.append(small)
    cap.release()
    first=frames[0];last=previous
    seam=float(np.mean(cv2.absdiff(first,last)))
    if report:assert len(means)==report['frames'],(path,len(means))
    assert min(means)>20,(path,'black frame',min(means))
    assert seam<4,(path,'loop jump',seam)
    if report:
        assert details[0]<1.4,(path,'missing empty opening')
        assert details[report['model_frames']-1]<1.4,(path,'model has not fully left')
        assert max(details[:report['model_frames']])>2,(path,'missing model action')
    return dict(frames=len(means),seam_mae=round(seam,4),min_luma=round(min(means),2),
                model_detail_min=round(min(details[:277]),3),
                transition_end_mae=[round(changes[i],3) for i in (275,276,298,299,651,652,671,672)],
                first_step_mae=round(changes[0],3))


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    proxies=list(ThreadPoolExecutor(max_workers=2).map(prepared,PAIRS))
    results=[]
    cases=[(i,mode,fmt,True) for i in range(6) for mode in ('smart','template') for fmt in ('standard','vertical')]
    if '--full' in sys.argv:cases=[(0,'smart','standard',False),(1,'template','vertical',False)]
    kind=next((arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--transition=')),'lens')
    if kind!='lens':cases=[(0,'smart','standard',True)]
    for i,mode,fmt,preview in cases:
        article,model,hands=PAIRS[i]
        paths=proxies[i] if preview else [ROOT/'видео'/article/model,ROOT/'видео'/article/hands]
        infos=[probe(path) for path in paths]
        name=f'{article}-{mode}-{fmt}-'+('preview' if preview else 'full')
        if kind!='lens':name+='-'+kind
        work=OUT/(name+'-work');work.mkdir(exist_ok=True)
        output=OUT/(name+'.mp4')
        if output.exists():output=OUT/(name+f'-{time.time_ns()}.mp4')
        start=time.monotonic()
        settings=dict(mode=mode,transition=kind,crops=[.824,.5],crops_x=[.5,.5],format=fmt,preview=preview,sensitivity=40,bitrate_kbps=1500)
        report=render(paths,infos,settings,work,output,lambda *_:None,threading.Event())
        metrics=inspect(output,report)
        result=dict(article=article,mode=mode,format=fmt,preview=preview,seconds=round(time.monotonic()-start,2),
                    bounds=report['content_bounds'],path=str(output),metrics=metrics)
        results.append(result);print(json.dumps(result),flush=True)
    record=kind+'-loops.json' if kind!='lens' else 'full-loops.json' if '--full' in sys.argv else 'preview-loops.json'
    (OUT/record).write_text(json.dumps(results,indent=2),encoding='utf8')
    print(f'PASS: {len(results)} encoded loops; all frames checked for black flashes, empty model frames and wrap mismatch')


if __name__=='__main__':main()
