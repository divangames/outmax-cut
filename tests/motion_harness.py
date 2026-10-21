"""Isolated local UI stress harness: 500 rows, real previews and a real export.
Run this harness, use its page through browser automation, and read /test-health.
It copies fixtures; never moves the user's source videos.
"""
from pathlib import Path
import sys, tempfile, shutil, threading, time, json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server
from flask import jsonify
from waitress import serve
root=Path(tempfile.mkdtemp(prefix='outmax-motion-'))
server.OUTPUT=root/'exports'
server.SETTINGS_FILE=root/'settings.json'
server.preferences['save_processing_log']=False
originals=Path(__file__).resolve().parents[1]/'видео/Иваныч/47433'
entries=[]
for path in sorted(originals.iterdir()):
 if path.suffix.lower() not in ('.mov','.mp4'):continue
 copied=root/path.name;shutil.copyfile(path,copied)
 folder=server.WORK/('stress-'+path.suffix.lower()[1:]);folder.mkdir(exist_ok=True)
 entries.append(server.register_source(copied,folder,path.name,path.name))
entries.sort(key=lambda entry:entry['model_score'],reverse=True)
groups=[dict(name=str(60000+i),candidates=[server.public_source(e) for e in entries],sources=[e['id'] for e in entries],detection='Тест большой очереди') for i in range(500)]
server.imports['stress']=dict(id='stress',status='done',processed=1000,total=1000,errors=[],skipped=0,groups=groups,cancel=threading.Event())
delivered=False
def import_stress():
 global delivered
 if delivered:return jsonify(pending=False)
 delivered=True
 return jsonify(id='stress')
server.app.view_functions['import_shell']=import_stress
original_index=server.app.view_functions['index']
def stress_index():
 global delivered
 delivered=False
 return original_index().replace('</body>','<script src="/test-probe.js"></script></body>')
server.app.view_functions['index']=stress_index
@server.app.get('/test-probe.js')
def probe_script():
 return '''
 window.motionMeasurements={frames:[],longTasks:[],inputs:[],mutations:0};
 let previous=performance.now();
 function sample(now){if(!document.hidden){const frames=motionMeasurements.frames;frames.push(now-previous);if(frames.length>3600)frames.shift();}previous=now;requestAnimationFrame(sample)}requestAnimationFrame(sample);
 new PerformanceObserver(list=>{motionMeasurements.longTasks.push(...list.getEntries().map(e=>e.duration))}).observe({type:'longtask',buffered:true});
 document.addEventListener('click',()=>{const start=performance.now();requestAnimationFrame(()=>motionMeasurements.inputs.push(performance.now()-start));},true);
 new MutationObserver(records=>{motionMeasurements.mutations+=records.filter(r=>r.type==='childList').length;}).observe(document.getElementById('batchList'),{childList:true});
 const reset=document.createElement('button');reset.id='testReset';reset.textContent='Начать измерение';reset.style.cssText='position:fixed;right:4px;bottom:0;z-index:999;font-size:10px';reset.onclick=()=>{motionMeasurements={frames:[],longTasks:[],inputs:[],mutations:0};previous=performance.now();};document.body.append(reset);
 ''',200,{'Content-Type':'application/javascript'}
@server.app.get('/test-health')
def health():return jsonify(output=str(root),jobs=[server.job_view(j) for j in server.jobs.values()])
print('Stress harness http://127.0.0.1:8877; disposable output:',root,flush=True)
serve(server.app,host='127.0.0.1',port=8877,threads=6)
