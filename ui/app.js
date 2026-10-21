const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="outmax-token"]').content;
const state = {sources: [null, null], uploading: [false, false], job: null, running: false, result: null, stale: false, externalLocked: false};
let pollTimer;
const mb = n => (n / 1e6).toLocaleString('ru-RU', {maximumFractionDigits: 2});
function updateBitrateMetrics() {
  const bitrate = +$('bitrate').value;
  $('bitrateMetric').textContent = bitrate.toLocaleString('ru-RU');
  $('sizeMetric').textContent = mb((bitrate + 64) * 1000 * (658 / 30) / 8);
}
$('bitrate').addEventListener('change', () => {updateBitrateMetrics(); markChanged();});
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
function showError(message) { $('errorMessage').textContent = message; $('errorMessage').hidden = !message; }
function markChanged() {
  if (state.result) {
    state.stale = true;
    $('resultActions').hidden = true;
    $('viewerLabel').textContent = $('resultTab').getAttribute('aria-selected') === 'true' ? 'Предыдущая версия · нужен новый монтаж' : 'Оригинальный ролик';
  }
  refresh();
  window.batchController?.changed();
}
function refresh() {
  const count = state.sources.filter(Boolean).length;
  const locked = state.running || state.externalLocked;
  $('sourceCount').textContent = `${count} из 2`;
  $('renderButton').disabled = count !== 2 || locked || state.uploading.some(Boolean);
  $('renderButton').querySelector('span').textContent = state.result ? 'Собрать заново' : 'Собрать видео';
  $('readyHint').textContent = state.running ? 'Можно отменить экспорт в любой момент.' : state.stale ? 'Исходники или настройки изменены. Соберите видео заново.' : count === 2 ? 'Исходные файлы останутся без изменений.' : 'Добавьте оба исходника, чтобы начать монтаж.';
  for (let i=0; i<2; i++) {
    $('file'+i).disabled = locked || state.uploading[i];
    $('crop'+i).disabled = locked;
    $('drop'+i).classList.toggle('busy', locked || state.uploading[i]);
  }
  document.querySelectorAll('.replace').forEach(b => b.disabled = locked || state.uploading[+b.dataset.slot]);
  ['mode','transition','sensitivity','bitrate'].forEach(id => $(id).disabled = locked);
  window.batchController?.refreshLocks();
}
async function upload(slot, file) {
  if (!file || state.running || state.externalLocked || state.uploading[slot]) return;
  if (file.size > 2 * 1024**3) { showError('Файл больше 2 ГБ. Выберите короткий исходный ролик.'); return; }
  state.uploading[slot] = true;
  const status = $('uploadStatus'+slot);
  status.classList.remove('failed');
  status.textContent = 'Читаем видео и готовим предпросмотр…';
  showError('');
  refresh();
  try {
    const body = new FormData(); body.append('file', file);
    const source = await api('/api/upload', body);
    state.sources[slot] = source;
    $('drop'+slot).hidden = true; $('loaded'+slot).hidden = false; $('cropControl'+slot).hidden = false;
    $('name'+slot).textContent = source.name;
    $('meta'+slot).textContent = `${source.info.duration.toFixed(1)} с · ${source.info.width} × ${source.info.height} · ${mb(source.info.size)} МБ`;
    const video = $('sourceVideo'+slot); video.src = source.preview; video.style.objectPosition = `50% ${$('crop'+slot).value}%`;
    video.onloadedmetadata = () => { video.currentTime = Math.min(3, video.duration / 2); };
    status.textContent = source.info.hdr ? 'HDR исходник · экспорт с преобразованием в SDR' : '';
    markChanged();
  } catch (error) {
    status.textContent = error.message; status.classList.add('failed');
  } finally { state.uploading[slot] = false; $('file'+slot).value = ''; refresh(); }
}
for (let slot=0; slot<2; slot++) {
  const input = $('file'+slot), drop = $('drop'+slot);
  input.addEventListener('change', () => upload(slot, input.files[0]));
  drop.addEventListener('keydown', e => { if (e.key==='Enter'||e.key===' ') { e.preventDefault(); input.click(); } });
  drop.addEventListener('dragover', e => {e.preventDefault(); if (!state.running) drop.classList.add('dragover');});
  drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
  drop.addEventListener('drop', e => {e.preventDefault(); drop.classList.remove('dragover'); upload(slot,e.dataTransfer.files[0]);});
  $('loaded'+slot).addEventListener('dragover', e => e.preventDefault());
  $('loaded'+slot).addEventListener('drop', e => {e.preventDefault(); upload(slot,e.dataTransfer.files[0]);});
  $('crop'+slot).addEventListener('input', () => {
    $('cropValue'+slot).textContent = `${Math.round(+$('crop'+slot).value)}%`;
    $('sourceVideo'+slot).style.objectPosition = `50% ${$('crop'+slot).value}%`;
    markChanged();
  });
}
document.querySelectorAll('.replace').forEach(b => b.addEventListener('click', () => $('file'+b.dataset.slot).click()));
$('mode').addEventListener('change', () => {
  const smart = $('mode').value === 'smart';
  $('smartOptions').hidden = !smart;
  $('modeHelp').textContent = smart ? 'Находит движение, убирает длинные остановки и подгоняет ролик под длительность эталона.' : 'Точки монтажа и ускорения из проекта Premiere. Для видео с похожим порядком движений.';
  markChanged();
});
$('sensitivity').addEventListener('input', () => {$('sensitivityValue').textContent = `${$('sensitivity').value}%`; markChanged();});
$('transition').addEventListener('change', () => {
  $('transitionHelp').textContent = {
    lens:'Мягкий Lens Blur между моделью, руками и финальным фоном.',
    morph:'Преобразование формы через оптический поток. На разных ракурсах возможны искажения; обработка дольше.',
    cut:'Мгновенная смена планов без размытия и деформации.'
  }[$('transition').value];
  markChanged();
});
function selectTab(result) {
  if (result && !state.result) return;
  $('mainVideo').pause();
  $('mainVideo').src = result ? `/result/${state.result.id}` : '/reference';
  $('mainVideo').setAttribute('aria-label', result ? 'Готовое видео' : 'Видео эталона');
  $('referenceTab').setAttribute('aria-selected', String(!result));
  $('resultTab').setAttribute('aria-selected', String(result));
  $('viewerLabel').textContent = result ? (state.stale ? 'Предыдущая версия · нужен новый монтаж' : 'Ваш готовый ролик') : 'Оригинальный ролик';
  $('videoSize').textContent = result ? `${mb(state.result.report.result.size)} МБ` : '2,95 МБ';
}
$('referenceTab').onclick = () => selectTab(false);
$('resultTab').onclick = () => selectTab(true);
document.querySelectorAll('[role=tab]').forEach(button => button.addEventListener('keydown', e => {
  if (['ArrowLeft','ArrowRight'].includes(e.key) && state.result) {
    e.preventDefault(); const result = e.key==='ArrowRight'; selectTab(result); $(result?'resultTab':'referenceTab').focus();
  }
}));
$('mainVideo').addEventListener('loadedmetadata', () => { if (!state.result || $('referenceTab').getAttribute('aria-selected')==='true') $('mainVideo').currentTime = 2; });
async function pollJob() {
  try {
    const job = await api(`/api/jobs/${state.job}`);
    showError('');
    $('progressBar').value = job.progress;
    $('progressValue').textContent = `${job.progress}%`;
    $('progressStage').textContent = job.stage;
    $('stageText').textContent = job.stage;
    if (job.status === 'running') { pollTimer = setTimeout(pollJob, 750); return; }
    state.running = false;
    $('renderOverlay').hidden = true; $('progressArea').hidden = true;
    if (job.status === 'done') {
      state.result = job;
      state.stale = false;
      $('resultTab').disabled = false;
      $('resultActions').hidden = false;
      $('outputPath').textContent = job.output;
      $('successText').textContent = `Сохранено · ${mb(job.report.result.size)} МБ · 21,93 с`;
      selectTab(true);
    } else if (job.status === 'error') showError(job.error);
    else showError('Экспорт отменён. Можно запустить заново.');
    if (job.status !== 'done' && state.result && !state.stale) $('resultActions').hidden = false;
    refresh();
    window.batchController?.completed(job);
  } catch (error) {
    // Keep the job active on transient polling failures; do not launch a duplicate render.
    showError('Связь с обработкой прервана. Проверяем повторно…');
    pollTimer = setTimeout(pollJob, 2500);
  }
}
$('renderButton').onclick = async () => {
  if (state.running || state.externalLocked) return;
  state.running = true; showError(''); refresh();
  try {
    const job = await api('/api/render', {
      sources: state.sources.map(s=>s.id), mode:$('mode').value, transition:$('transition').value,
      crops:[+$('crop0').value/100,+$('crop1').value/100], sensitivity:+$('sensitivity').value, bitrate_kbps:+$('bitrate').value,
      ...window.batchController?.exportContext()
    });
    state.job = job.id;
    $('mainVideo').pause();
    $('renderOverlay').hidden = false; $('progressArea').hidden = false; $('resultActions').hidden = true;
    $('progressBar').value = 0; $('progressValue').textContent = '0%';
    $('cancelButton').disabled = false; $('cancelButton').textContent = 'Отменить экспорт';
    pollJob();
  } catch(error) {state.running=false; showError(error.message); refresh();}
};
$('cancelButton').onclick = async () => {
  try {
    await api(`/api/jobs/${state.job}/cancel`, {});
    $('cancelButton').disabled=true; $('cancelButton').textContent='Отменяем…';
  } catch(error) {showError(error.message);}
};
$('saveButton').onclick = async () => {
  try {
    const result=await api(`/api/save/${state.result.id}`, {});
    if (result.download) {const link=document.createElement('a');link.href=result.download;link.download='';link.click();}
    if (result.saved) $('outputPath').textContent=result.saved;
  } catch(error) {showError(error.message);}
};
$('folderButton').onclick = async () => {try {await api('/api/folder',window.batchController?.folderContext()||{});} catch(error){showError(error.message);}};
$('helpButton').onclick = () => $('helpDialog').showModal();
$('closeHelp').onclick = () => $('helpDialog').close();
$('helpDialog').addEventListener('click', e => {if(e.target===$('helpDialog')) {const r=$('helpDialog').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('helpDialog').close();}});
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());
refresh();

function editorSnapshot() {
  return {sources:[...state.sources], result:state.result, stale:state.stale,
    settings:{mode:$('mode').value, transition:$('transition').value,
      crops:[+$('crop0').value/100,+$('crop1').value/100], sensitivity:+$('sensitivity').value, bitrate_kbps:+$('bitrate').value}};
}
function loadEditor(snapshot) {
  state.sources=[...snapshot.sources];state.result=snapshot.result||null;state.stale=!!snapshot.stale;
  for(let i=0;i<2;i++){
    const source=state.sources[i],video=$('sourceVideo'+i);
    video.pause();
    $('drop'+i).hidden=!!source;$('loaded'+i).hidden=!source;$('cropControl'+i).hidden=!source;
    $('uploadStatus'+i).textContent='';
    if(source){
      $('name'+i).textContent=source.name;
      $('meta'+i).textContent=`${source.info.duration.toFixed(1)} с · ${source.info.width} × ${source.info.height}`;
      video.src=source.preview;video.onloadedmetadata=()=>{video.currentTime=Math.min(3,video.duration/2);};
    }else{video.removeAttribute('src');video.load();}
    $('crop'+i).value=snapshot.settings.crops[i]*100;
    $('cropValue'+i).textContent=`${Math.round(snapshot.settings.crops[i]*100)}%`;
    video.style.objectPosition=`50% ${snapshot.settings.crops[i]*100}%`;
  }
  $('mode').value=snapshot.settings.mode;$('transition').value=snapshot.settings.transition;
  $('bitrate').value=snapshot.settings.bitrate_kbps ?? 2500;
  updateBitrateMetrics();
  $('sensitivity').value=snapshot.settings.sensitivity;$('sensitivityValue').textContent=snapshot.settings.sensitivity+'%';
  $('smartOptions').hidden=snapshot.settings.mode!=='smart';
  $('modeHelp').textContent=snapshot.settings.mode==='smart'?'Поиск пауз по движению с подгонкой длительности под эталон.':'Точки монтажа и ускорения из проекта Premiere. Для видео с похожим порядком движений.';
  $('transitionHelp').textContent={lens:'Мягкий Lens Blur между планами.',morph:'Оптический поток. На разных ракурсах возможны искажения.',cut:'Мгновенная смена планов.'}[snapshot.settings.transition];
  $('resultTab').disabled=!state.result;$('resultActions').hidden=!state.result||state.stale;
  $('renderOverlay').hidden=true;$('progressArea').hidden=true;showError('');
  if(state.result){$('outputPath').textContent=state.result.output;$('successText').textContent=`Сохранено · ${mb(state.result.report.result.size)} МБ · 21,93 с`;}
  selectTab(!!state.result);refresh();
}
