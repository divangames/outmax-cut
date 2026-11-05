const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="outmax-token"]').content;
const state = {sources: [null, null], uploading: [false, false], job: null, running: false, result: null, preview: null, stale: false, externalLocked: false};
let pollTimer;
let nativeApp = false;
const editorPreferences={mode:'smart',bitrate_kbps:2500,sensitivity:40};
const touchedPreferences=new Set();
let preferenceWrite=Promise.resolve();
function editorDefaults(){return {mode:editorPreferences.mode,transition:'lens',crops:[.824,.5],crops_x:[.5,.5],format:'standard',formats:['standard'],sensitivity:editorPreferences.sensitivity,bitrate_kbps:editorPreferences.bitrate_kbps};}
function persistEditorPreference(key,value){
  editorPreferences[key]=value;touchedPreferences.add(key);
  preferenceWrite=preferenceWrite.catch(()=>{}).then(()=>api('/api/settings',{[key]:value})).catch(error=>showError('Не удалось сохранить настройку: '+error.message));
}
const mb = n => (n / 1e6).toLocaleString('ru-RU', {maximumFractionDigits: 2});
function updateBitrateMetrics() {
  const bitrate = +$('bitrate').value;
  $('bitrateMetric').textContent = bitrate.toLocaleString('ru-RU');
  const duration=state.preview?.report?.result?.duration||state.result?.report?.result?.duration||685/30;
  $('sizeMetric').textContent = mb((bitrate + 64) * 1000 * duration / 8);
}
$('bitrate').addEventListener('change', () => {updateBitrateMetrics();persistEditorPreference('bitrate_kbps',+$('bitrate').value);markChanged(false);});
updateBitrateMetrics();
async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST', headers: {'X-Outmax-Token': token}, body: body instanceof FormData ? body : JSON.stringify(body)
  };
  if (body !== undefined && !(body instanceof FormData)) options.headers['Content-Type'] = 'application/json';
  const res = await fetch(path, options);
  let data;
  try { data = await res.json(); } catch { throw new Error('Сервис недоступен. Перезапустите приложение.'); }
  if (!res.ok) throw new Error(data.error || `Ошибка сервиса (${res.status}).`);
  return data;
}
function uploadRequest(path, body, onProgress) {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST',path);xhr.setRequestHeader('X-Outmax-Token',token);
    xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress?.({progress:e.loaded/e.total*100,stage:'Передаём файл',transfer:true});};
    xhr.onerror=()=>reject(new Error('Не удалось передать файл. Повторите импорт.'));
    xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);xhr.status>=200&&xhr.status<300?resolve(data):reject(new Error(data.error||'Ошибка импорта.'));}catch{reject(new Error('Сервис недоступен.'));}};
    xhr.send(body);
  });
}
function importLabel(task) {
  const eta=task.eta_seconds;
  const wait=eta==null?'считаем время…':eta<60?`осталось ≈ ${Math.max(1,eta)} с`:`осталось ≈ ${Math.ceil(eta/60)} мин`;
  return `${task.stage} · ${Math.round(task.progress||0)}%${task.transfer?'':` · ${wait}`}`;
}
async function prepareSource(path, body, onProgress) {
  const task=body instanceof FormData?await uploadRequest(path,body,onProgress):await api(path,body);
  if(task.source===null)return null;
  if(task.info)return task; // Also accepts sources from older local servers.
  for(;;){
    const result=await api(`/api/imports/${task.id}`);
    onProgress?.(result);
    if(result.status!=='running'){
      const source=result.groups.flatMap(group=>group.candidates)[0];
      if(!source)throw new Error(result.errors[0]?.error||'Импорт отменён.');
      return source;
    }
    await new Promise(resolve=>setTimeout(resolve,250));
  }
}
function showError(message) { $('errorMessage').textContent = message; $('errorMessage').hidden = !message; }
function markChanged(previewChanged=true) {
  if(previewChanged)window.livePreview?.edit();
  if(previewChanged){
    state.preview=null;$('previewTab').disabled=true;
    if($('previewTab').getAttribute('aria-selected')==='true')$('viewerLabel').textContent='Превью обновляется…';
  }
  if (state.result) {
    state.stale = true;
    $('resultActions').hidden = true;
    $('viewerLabel').textContent = $('resultTab').getAttribute('aria-selected') === 'true' ? 'Предыдущая версия · нужен новый монтаж' : 'Оригинальный ролик';
  }
  refresh();
  window.batchController?.changed();
  if(previewChanged||!state.preview)window.autoPreview?.schedule();
}
function refresh() {
  const count = state.sources.filter(Boolean).length;
  const locked = state.running || state.externalLocked;
  $('sourceCount').textContent = `${count} из 2`;
  $('renderButton').disabled = count !== 2 || locked || state.uploading.some(Boolean);
  document.querySelectorAll('#exportFormats input').forEach(input=>input.disabled=locked);
  $('renderButton').querySelector('span').textContent = state.result ? 'Собрать заново' : 'Собрать видео';
  $('readyHint').textContent = state.running ? 'Можно отменить экспорт в любой момент.' : state.stale ? 'Исходники или настройки изменены. Соберите видео заново.' : count === 2 ? 'После экспорта исходники переместятся в «Руки + Ноги».' : 'Добавьте оба исходника, чтобы начать монтаж.';
  for (let i=0; i<2; i++) {
    $('file'+i).disabled = locked || state.uploading[i];
    $('crop'+i).disabled = locked;
    $('cropX'+i).disabled = locked;
    $('resetCrop'+i).disabled=locked;$('resetCrop'+i).hidden=!state.sources[i];
    $('drop'+i).classList.toggle('busy', locked || state.uploading[i]);
  }
  document.querySelectorAll('.replace').forEach(b => b.disabled = locked || state.uploading[+b.dataset.slot]);
  ['mode','transition','sensitivity','bitrate','outputFormat'].forEach(id => $(id).disabled = locked);
  window.batchController?.refreshLocks();
}
async function upload(slot, file, native = false) {
  if ((!file && !native) || state.running || state.externalLocked || state.uploading[slot]) return;
  if (file && file.size > 2 * 1024**3) { showError('Файл больше 2 ГБ. Выберите короткий исходный ролик.'); return; }
  state.uploading[slot] = true;
  const status = $('uploadStatus'+slot);
  status.classList.remove('failed');
  status.textContent = 'Читаем видео и готовим предпросмотр…';
  const progress=$('uploadProgress'+slot);progress.hidden=false;progress.removeAttribute('value');
  const report=task=>{progress.value=task.progress||0;status.textContent=importLabel(task);};
  showError('');
  refresh();
  try {
    let source;
    if (native) { source = await prepareSource('/api/choose-source', {},report); if (!source) { status.textContent = ''; return; } }
    else { const body = new FormData(); body.append('file', file); source = await prepareSource('/api/upload', body,report); }
    state.sources[slot] = source;
    $('drop'+slot).hidden = true; $('loaded'+slot).hidden = false; $('cropControl'+slot).hidden = false;
    $('name'+slot).textContent = source.name;
    $('meta'+slot).textContent = `${source.info.duration.toFixed(1)} с · ${source.info.width} × ${source.info.height} · ${mb(source.info.size)} МБ`;
    const video = $('sourceVideo'+slot); video.src = source.preview; video.style.objectPosition = cropPosition(slot);
    video.onloadedmetadata = () => { video.currentTime = Math.min(3, video.duration / 2); };
    status.textContent = source.info.hdr ? 'HDR исходник · экспорт с преобразованием в SDR' : '';
    markChanged();
  } catch (error) {
    status.textContent = error.message; status.classList.add('failed');
  } finally { state.uploading[slot] = false; progress.hidden=true; $('file'+slot).value = ''; refresh();window.autoPreview?.schedule(); }
}
const formatSpecs={standard:[1080,1080],marketplace:[900,1200],vertical:[1080,1920]};
const formatNames={standard:'Стандарт',marketplace:'Маркетплейс',vertical:'Вертикальный'};
function selectedFormats(){return [...document.querySelectorAll('#exportFormats input:checked')].map(input=>input.value);}
function syncFormats(formats=selectedFormats()){
  document.querySelectorAll('#exportFormats input').forEach(input=>input.checked=formats.includes(input.value));
  [...$('outputFormat').options].forEach(option=>option.disabled=!formats.includes(option.value));
  if(!formats.includes($('outputFormat').value))$('outputFormat').value=formats[0];
}
document.querySelectorAll('#exportFormats input').forEach(input=>input.addEventListener('change',()=>{
  const formats=selectedFormats();
  if(!formats.length){input.checked=true;showError('Должно быть выбрано хотя бы одно разрешение.');return;}
  const oldFormat=$('outputFormat').value;syncFormats(formats);markChanged(oldFormat!==$('outputFormat').value);updateFormat();
}));
function resultVariant(job=state.result){return job?.variants?.find(v=>v.format===$('resultFormat').value)||job?.variants?.[0]||job;}
function updateResultFormats(){
  const previous=$('resultFormat').value;
  $('resultFormat').replaceChildren();
  for(const variant of state.result?.variants||[]){const [w,h]=formatSpecs[variant.format];$('resultFormat').add(new Option(`${formatNames[variant.format]} · ${w} × ${h}`,variant.format));}
  if([...$('resultFormat').options].some(option=>option.value===previous))$('resultFormat').value=previous;
}
$('resultFormat').onchange=()=>selectTab(true);
function cropPosition(slot){return `${$('cropX'+slot).value}% ${$('crop'+slot).value}%`;}
function updateFormat(){
  const [width,height]=formatSpecs[$('outputFormat').value]||formatSpecs.standard;
  document.querySelectorAll('.source-preview').forEach(el=>el.style.aspectRatio=`${width}/${height}`);
  const source=$('mainVideo').dataset.sourceSlot!==undefined;
  const viewing=$('previewTab').getAttribute('aria-selected')==='true'?state.preview:resultVariant();
  const dims=source||window.livePreview?.active?[width,height]:$('referenceTab').getAttribute('aria-selected')==='true'?[1080,1080]:viewing?[viewing.report.result.width,viewing.report.result.height]:[width,height];
  $('viewer').style.setProperty('--video-ratio',dims[0]/dims[1]);
  document.querySelectorAll('.preset-label span,.export-summary span').forEach(el=>el.textContent=`${width} × ${height} · 30 кадров/с`);
}
$('outputFormat').addEventListener('change',()=>{markChanged();updateFormat();});
syncFormats();updateFormat();
for (let slot=0; slot<2; slot++) {
  const input = $('file'+slot), drop = $('drop'+slot);
  input.addEventListener('click', e => { if (nativeApp) { e.preventDefault(); upload(slot, null, true); } });
  input.addEventListener('change', () => upload(slot, input.files[0]));
  drop.addEventListener('keydown', e => { if (e.key==='Enter'||e.key===' ') { e.preventDefault(); input.click(); } });
  drop.addEventListener('dragover', e => {e.preventDefault(); if (!state.running) drop.classList.add('dragover');});
  drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
  drop.addEventListener('drop', e => {e.preventDefault(); drop.classList.remove('dragover'); upload(slot,e.dataTransfer.files[0]);});
  $('loaded'+slot).addEventListener('dragover', e => e.preventDefault());
  $('loaded'+slot).addEventListener('drop', e => {e.preventDefault(); upload(slot,e.dataTransfer.files[0]);});
  for(const id of ['crop','cropX'])$(id+slot).addEventListener('input', () => {
    $('cropValue'+slot).textContent = `${Math.round(+$('crop'+slot).value)}%`;
    $('cropXValue'+slot).textContent = `${Math.round(+$('cropX'+slot).value)}%`;
    $('sourceVideo'+slot).style.objectPosition = cropPosition(slot);
    markChanged();
    if($('mainVideo').dataset.sourceSlot===String(slot))$('mainVideo').style.objectPosition=cropPosition(slot);
  });
  $('resetCrop'+slot).onclick=()=>{
    $('cropX'+slot).value=50;$('crop'+slot).value=slot?50:82.4;
    $('crop'+slot).dispatchEvent(new Event('input',{bubbles:true}));
  };
}
document.querySelectorAll('.replace').forEach(b => b.addEventListener('click', () => $('file'+b.dataset.slot).click()));
function syncModeHelp(){
  const smart = $('mode').value === 'smart';
  motion.visible($('smartOptions'),smart);
  $('modeHelp').textContent = smart ? 'Удаляет длинные остановки; сохраняет появление и полный уход. Скорость ×1,25.' : 'Сохраняет последовательность действий без удаления пауз. Скорость ×1,25.';
}
$('mode').addEventListener('change', () => {
  syncModeHelp();persistEditorPreference('mode',$('mode').value);markChanged();
});
$('sensitivity').addEventListener('input', () => {$('sensitivityValue').textContent = `${$('sensitivity').value}%`; markChanged();});
$('sensitivity').addEventListener('change',()=>persistEditorPreference('sensitivity',+$('sensitivity').value));
$('transition').addEventListener('change', () => {
  $('transitionHelp').textContent = {
    lens:'Мягкий Lens Blur между планами и плавный возврат к началу.',
    morph:'Преобразование формы через оптический поток. На разных ракурсах возможны искажения; обработка дольше.',
    cut:'Мгновенная смена планов без размытия и деформации.'
  }[$('transition').value];
  markChanged();
});
let playerRevision=0;
function selectTab(result, preview=false, playback=null) {
  const selected=preview?state.preview:result?resultVariant():null;
  if ((result||preview) && !selected) return;
  const revision=++playerRevision,video=$('mainVideo');
  delete video.dataset.userSourceView;
  if(!playback)window.livePreview?.stop();
  $('mainVideo').pause();
  $('mainVideo').loop=!!selected;
  $('mainVideo').onloadeddata=null;delete $('mainVideo').dataset.sourceSlot;$('mainVideo').style.objectFit='contain';
  const restore=()=>{
    if(revision!==playerRevision)return;
    const time=Math.min(playback?.time??.1,Math.max(0,video.duration-1/30));
    const finish=()=>{
      if(revision!==playerRevision)return;
      playback?.onRestored?.();
      if(playback&&!playback.paused)video.play().catch(()=>{});else video.pause();
    };
    if(Math.abs(video.currentTime-time)>1/120){video.addEventListener('seeked',finish,{once:true});video.currentTime=time;}
    else if(video.readyState>=2)finish();else video.addEventListener('loadeddata',finish,{once:true});
  };
  $('mainVideo').onloadedmetadata=selected?restore:null;
  const videoPath=selected ? `/result/${preview?state.preview.id:state.result.id}${!preview&&selected.format?'?format='+selected.format:''}` : '/reference';
  if($('mainVideo').getAttribute('src')!==videoPath){$('mainVideo').src=videoPath;if(playback)$('mainVideo').currentTime=playback.time;else motion.reveal($('viewer'));}
  else if(selected&&video.readyState>=1)restore();
  $('mainVideo').setAttribute('aria-label', preview?'Автоматическое превью':result ? 'Готовое видео' : 'Видео эталона');
  $('resultFormatControl').hidden=!result||preview||($('resultFormat').options.length<2);
  for(const id of ['previewModel','previewHands'])if($(id))$(id).setAttribute('aria-pressed','false');
  $('referenceTab').setAttribute('aria-selected', String(!result&&!preview));
  $('resultTab').setAttribute('aria-selected', String(result&&!preview));
  $('previewTab').setAttribute('aria-selected', String(preview));
  $('viewerLabel').textContent = preview?'Автопревью · 30 кадров/с':result ? (state.stale ? 'Предыдущая версия · нужен новый монтаж' : 'Ваш готовый ролик') : 'Оригинальный ролик';
  $('videoDuration').textContent = selected ? selected.report.result.duration.toFixed(2)+' с' : '00:22.83';
  if(selected){
    const report=selected.report,model=report.model_frames/30,hands=report.hands_frames/30;
    document.querySelector('.clip-model span').textContent=model.toFixed(2).replace('.',',')+' с';
    document.querySelector('.clip-hands span').textContent=hands.toFixed(2).replace('.',',')+' с';
    document.querySelector('.clip-model').style.flex=report.model_frames;
    document.querySelector('.clip-hands').style.flex=report.hands_frames;
    document.querySelector('.clip-end').style.flex=18;
    document.querySelector('.timeline-label>span').textContent=report.result.duration.toFixed(2)+' с · ×1,25';
    document.querySelector('.timeline-times').lastElementChild.textContent='0:'+String(Math.ceil(report.result.duration)).padStart(2,'0');
    updateBitrateMetrics();
  }
  $('videoSize').textContent = selected ? `${mb(selected.report.result.size)} МБ · ${selected.report.result.width} × ${selected.report.result.height}` : '2,99 МБ';
  updateFormat();
}
$('referenceTab').onclick = () => selectTab(false);
$('resultTab').onclick = () => selectTab(true);
$('previewTab').onclick = () => selectTab(false,true);
document.querySelectorAll('[role=tab]').forEach(button => button.addEventListener('keydown', e => {
  if (['ArrowLeft','ArrowRight'].includes(e.key)) {
    const tabs=[$('referenceTab'),$('resultTab'),$('previewTab')].filter(tab=>!tab.disabled);
    const index=tabs.indexOf(button),step=e.key==='ArrowRight'?1:-1;
    e.preventDefault();const next=tabs[(index+step+tabs.length)%tabs.length];next.click();next.focus();
  }
}));
const seekReference=()=>{if($('mainVideo').getAttribute('src')==='/reference' && $('mainVideo').readyState>=1)$('mainVideo').currentTime=Math.min(2,$('mainVideo').duration/2);};
$('mainVideo').addEventListener('loadedmetadata',seekReference);
seekReference();
async function pollJob() {
  try {
    const job = await api(`/api/jobs/${state.job}`);
    showError('');
    motion.progress($('progressBar'),job.progress);
    $('progressValue').textContent = `${job.progress}%`;
    $('progressStage').textContent = job.stage;
    $('stageText').textContent = job.stage;
    if (job.status === 'running') { pollTimer = setTimeout(pollJob, 750); return; }
    state.running = false;
    $('renderOverlay').hidden = true; $('progressArea').hidden = true;
    if (job.status === 'done' && job.preview) {
      state.preview=job;$('previewTab').disabled=false;selectTab(false,true);
    } else if (job.status === 'done') {
      state.result = job;
      state.stale = false;
      updateResultFormats();
      $('resultTab').disabled = false;
      $('resultActions').hidden = false;
      $('outputPath').textContent = job.variants.map(v=>v.output).join('\n');
      $('successText').textContent = `Сохранено вариантов: ${job.variants.length} · ${job.report.result.duration.toFixed(2)} с · ×1,25`;
      selectTab(true);
    } else if (job.status === 'error') showError(job.error);
    else showError('Экспорт отменён. Можно запустить заново.');
    if ((job.status !== 'done'||job.preview) && state.result && !state.stale) $('resultActions').hidden = false;
    refresh();
    window.batchController?.completed(job);
  } catch (error) {
    // Keep the job active on transient polling failures; do not launch a duplicate render.
    showError('Связь с обработкой прервана. Проверяем повторно…');
    pollTimer = setTimeout(pollJob, 2500);
  }
}
async function startAssembly() {
  if (state.running || state.externalLocked) return;
  state.running = true; showError(''); refresh();
  window.autoPreview?.cancel();
  window.livePreview?.stop();
  try {
    const job = await api('/api/render', {
      article: window.batchController?.exportContext().folder ? undefined : $('articleNumber').value.trim(),
      sources: state.sources.map(s=>s.id), mode:$('mode').value, transition:$('transition').value,
      ...editorSnapshot().settings,
      ...window.batchController?.exportContext()
    });
    state.job = job.id;
    $('stageTitle').textContent='Собираем ваш ролик';
    $('mainVideo').pause();
    $('renderOverlay').hidden = false; $('progressArea').hidden = false; $('resultActions').hidden = true;
    motion.progress($('progressBar'),0); $('progressValue').textContent = '0%';
    $('cancelButton').disabled = false; $('cancelButton').textContent = 'Отменить экспорт';
    pollJob();
  } catch(error) {state.running=false; showError(error.message); refresh();}
}
$('renderButton').onclick=()=>startAssembly();
$('cancelButton').onclick = async () => {
  try {
    await api(`/api/jobs/${state.job}/cancel`, {});
    $('cancelButton').disabled=true; $('cancelButton').textContent='Отменяем…';
  } catch(error) {showError(error.message);}
};
$('saveButton').onclick = async () => {
  try {
    const result=await api(`/api/save/${state.result.id}`, {format:resultVariant()?.format});
    if (result.download) {const link=document.createElement('a');link.href=result.download;link.download='';link.click();}
    if (result.saved) $('outputPath').textContent=result.saved;
  } catch(error) {showError(error.message);}
};
$('folderButton').onclick = async () => {try {await api('/api/folder',window.batchController?.folderContext()||{});} catch(error){showError(error.message);}};
$('helpButton').onclick = () => motion.openDialog($('helpDialog'));
$('closeHelp').onclick = () => motion.closeDialog($('helpDialog'));
$('helpDialog').addEventListener('click', e => {if(e.target===$('helpDialog')) {const r=$('helpDialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)motion.closeDialog($('helpDialog'));}});
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());
refresh();

function editorSnapshot() {
  return {sources:[...state.sources], result:state.result, preview:state.preview, stale:state.stale,
    playback:$('mainVideo').getAttribute('src')?.startsWith('/result/')?{time:$('mainVideo').currentTime,paused:$('mainVideo').paused}:null,
    settings:{mode:$('mode').value, transition:$('transition').value,
      crops:[+$('crop0').value/100,+$('crop1').value/100], crops_x:[+$('cropX0').value/100,+$('cropX1').value/100], format:$('outputFormat').value,formats:selectedFormats(), sensitivity:+$('sensitivity').value, bitrate_kbps:+$('bitrate').value}};
}
function loadEditor(snapshot) {
  window.autoPreview?.cancel();
  window.livePreview?.stop(true);
  state.sources=[...snapshot.sources];state.result=snapshot.result||null;state.preview=snapshot.preview||null;state.stale=!!snapshot.stale;
  for(let i=0;i<2;i++){
    const source=state.sources[i],video=$('sourceVideo'+i);
    video.pause();
    $('drop'+i).hidden=!!source;$('loaded'+i).hidden=!source;$('cropControl'+i).hidden=!source;
    $('uploadStatus'+i).textContent='';
    if(source){
      $('name'+i).textContent=source.name;
      $('meta'+i).textContent=`${source.info.duration.toFixed(1)} с · ${source.info.width} × ${source.info.height}`;
      if(video.getAttribute('src')!==source.preview)video.src=source.preview;video.onloadedmetadata=()=>{video.currentTime=Math.min(3,video.duration/2);};
    }else{video.removeAttribute('src');video.load();}
    $('crop'+i).value=snapshot.settings.crops[i]*100;
    $('cropValue'+i).textContent=`${Math.round(snapshot.settings.crops[i]*100)}%`;
    $('cropX'+i).value=(snapshot.settings.crops_x?.[i]??.5)*100;
    $('cropXValue'+i).textContent=`${Math.round(+$('cropX'+i).value)}%`;
    video.style.objectPosition=cropPosition(i);
  }
  $('mode').value=snapshot.settings.mode;$('transition').value=snapshot.settings.transition;
  $('bitrate').value=snapshot.settings.bitrate_kbps ?? 2500;
  $('outputFormat').value=snapshot.settings.format||'standard';
  syncFormats(snapshot.settings.formats||[snapshot.settings.format||'standard']);
  updateBitrateMetrics();
  $('sensitivity').value=snapshot.settings.sensitivity;$('sensitivityValue').textContent=snapshot.settings.sensitivity+'%';
  $('smartOptions').hidden=snapshot.settings.mode!=='smart';
  $('modeHelp').textContent=snapshot.settings.mode==='smart'?'Удаляет длинные остановки. Скорость ×1,25.':'Сохраняет последовательность действий без удаления пауз. Скорость ×1,25.';
  $('transitionHelp').textContent={lens:'Мягкий Lens Blur между планами.',morph:'Оптический поток. На разных ракурсах возможны искажения.',cut:'Мгновенная смена планов.'}[snapshot.settings.transition];
  $('resultTab').disabled=!state.result;$('resultActions').hidden=!state.result||state.stale;
  $('previewTab').disabled=!state.preview;
  updateResultFormats();
  $('renderOverlay').hidden=true;$('progressArea').hidden=true;showError('');
  if(state.result){$('outputPath').textContent=(state.result.variants||[state.result]).map(v=>v.output).join('\n');$('successText').textContent=`Сохранено вариантов: ${state.result.variants?.length||1} · ${state.result.report.result.duration.toFixed(2)} с · ×1,25`;}
  const showPreview=!!state.preview&&(!state.result||state.stale);
  selectTab(!showPreview&&!!state.result,showPreview,snapshot.playback);refresh();
  window.autoPreview?.schedule(100);
}

$('settingsButton').onclick = () => motion.openDialog($('settingsDialog'));
$('closeSettings').onclick = () => motion.closeDialog($('settingsDialog'));
$('saveProcessingLog').disabled = true;
const preferencesReady=api('/api/config').then(config => {
  nativeApp = config.native;
  for(const key of ['mode','bitrate_kbps','sensitivity'])if(!touchedPreferences.has(key)){
    editorPreferences[key]=config.preferences[key]??editorPreferences[key];
    $(key==='bitrate_kbps'?'bitrate':key).value=editorPreferences[key];
  }
  $('sensitivityValue').textContent=$('sensitivity').value+'%';syncModeHelp();updateBitrateMetrics();
  $('saveProcessingLog').checked = config.preferences.save_processing_log;
  $('saveProcessingLog').disabled = false;
}).catch(error => showError(error.message));
$('saveProcessingLog').onchange = async () => {
  const input = $('saveProcessingLog');
  input.disabled = true;
  $('settingsError').hidden = true;
  try { await api('/api/settings', {save_processing_log:input.checked}); }
  catch(error) { input.checked = !input.checked; $('settingsError').textContent = error.message; $('settingsError').hidden = false; }
  finally { input.disabled = false; }
};

