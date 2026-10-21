import sys,pathlib,threading,json,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from engine import probe,render
root=pathlib.Path(__file__).resolve().parents[1]; work=root/'analysis/render-test'; work.mkdir(exist_ok=True)
files=[root/'видео/2026-10-01 16.09.54.MOV',root/'видео/2026-09-30 14.45.00.MOV']
start=time.monotonic()
last=[-1]
def progress(p,s):
 if int(p)//5 != last[0]:
  print(round(p),s,flush=True);last[0]=int(p)//5
report=render(files,[probe(p) for p in files],dict(mode='template',transition='lens',crops=[.824,.5],sensitivity=40),work,root/'analysis/OUTMAX-test.mp4',progress,threading.Event())
print(json.dumps(report['result']), 'ELAPSED',time.monotonic()-start,flush=True)
