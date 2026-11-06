/* The worker runs on the server; this view is optional and never starts rendering. */
(() => {
  const button=document.createElement('button');button.id='automationButton';button.className='text-button';button.textContent='Автосборка';button.setAttribute('aria-haspopup','dialog');$('settingsButton').before(button);
  const dialog=document.createElement('dialog');dialog.id='automationDialog';dialog.setAttribute('aria-labelledby','automationTitle');
  dialog.innerHTML='<div class="automation-heading"><h2 id="automationTitle">Автосборка в один клик</h2><button id="closeAutomation" class="secondary-button">Закрыть</button></div><p>В Проводнике: правая кнопка по видео или папке → «Собрать видео автоматически». Пара находится рядом с файлом, папки обрабатываются с подпапками. Неоднозначные товары откладываются для проверки.</p><label class="dialog-field">Пресет для следующей автосборки<select id="autoPreset"></select></label><p id="autoPresetNote" class="field-help"></p><div class="automation-controls"><button id="autoRefresh" class="secondary-button">Обновить</button><button id="autoCancel" class="secondary-button">Остановить автосборку</button><span id="autoStatus" role="status"></span></div><div id="autoRuns"></div>';
  document.body.append(dialog);let timer=null,lastSignature='';const expanded=new Set();
  const editor=document.createElement('button');editor.id='autoOpenEditor';editor.className='secondary-button';editor.textContent='Открыть редактор';$('autoRefresh').before(editor);
  editor.onclick=async()=>{await batchWorkspace.activateEditor();motion.closeDialog(dialog);};
  const labels={queued:'В очереди',running:'Собирается',cancelling:'Останавливается',done:'Готово',done_with_review:'Есть товары для проверки',review:'Нужна проверка',skipped:'Пропущено',cancelled:'Остановлено',interrupted:'Прервано',error:'Ошибка'};
  async function paint(data){
    button.textContent=data.active?'Автосборка · идёт обработка':'Автосборка';
    if(!!state.automationRunning!==data.active){state.automationRunning=data.active;if(data.active)window.autoPreview?.cancel();refresh();if(!data.active&&!state.backgroundMode)window.autoPreview?.schedule();}
    if(!dialog.open)return;
    $('autoCancel').disabled=!data.active;$('autoStatus').textContent=data.active?'Работа продолжается в фоне':'Все текущие запуски завершены';
    const signature=JSON.stringify(data);if(signature===lastSignature)return;lastSignature=signature;
    const open=new Set([...$('autoRuns').querySelectorAll('details[open]')].map(element=>element.dataset.id)),focus=document.activeElement?.dataset.action;
    $('autoRuns').replaceChildren();
    if(!data.runs.length){const empty=document.createElement('p');empty.textContent='Запусков пока нет. Команда Проводника появляется после установки этой версии.';$('autoRuns').append(empty);}
    for(const [index,run] of data.runs.slice(0,10).entries()){
      const section=document.createElement('details');section.className='automatic-run';section.dataset.id=run.id;section.open=open.has(run.id)||index===0;
      const summary=document.createElement('summary');summary.textContent=(labels[run.status]||run.status)+' · '+new Date(run.created*1000).toLocaleString('ru-RU');
      const description=document.createElement('p');description.textContent=run.stage;const preset=document.createElement('p');preset.className='field-help';preset.textContent='Пресет: '+run.preset;
      const folder=document.createElement('button');folder.className='text-button';folder.textContent='Открыть папку готовых';folder.dataset.action=run.id+'-folder';folder.onclick=()=>api('/api/folder',{path:run.output}).catch(error=>showError(error.message));section.append(summary,description,preset,folder);
      const items=expanded.has(run.id)?run.items:run.items.slice(0,50);
      for(const item of items){
        const row=document.createElement('div');row.className='automatic-item';row.dataset.status=item.status;
        const title=document.createElement('strong');title.textContent=item.name+' · '+(labels[item.status]||item.status)+(item.progress!=null&&item.status==='running'?' · '+item.progress+'%':'');
        const message=document.createElement('p');message.textContent=item.message;row.append(title,message);
        if(item.outputs?.length){const files=document.createElement('p');files.className='field-help';files.textContent=item.outputs.map(path=>path.split(/[\\/]/).at(-1)).join(', ');row.append(files);}
        if(item.status==='review'){
          const review=document.createElement('button');review.className='secondary-button';review.textContent='Проверить в редакторе';review.dataset.action=run.id+'-'+item.name;
          review.onclick=async()=>{try{await batchWorkspace.activateEditor();await api('/api/shell/enqueue',{paths:item.paths,action:'review'});motion.closeDialog(dialog);batchWorkspace.notify('Товар добавлен для ручной проверки.');}catch(error){showError(error.message);}};row.append(review);
        }section.append(row);
      }
      if(run.items.length>items.length){const more=document.createElement('button');more.className='text-button';more.textContent='Показать остальные товары · '+(run.items.length-items.length);more.onclick=()=>{expanded.add(run.id);lastSignature='';poll();};section.append(more);}
      $('autoRuns').append(section);
    }
    if(focus)[...$('autoRuns').querySelectorAll('[data-action]')].find(element=>element.dataset.action===focus)?.focus({preventScroll:true});
  }
  async function poll(){clearTimeout(timer);try{await paint(await api('/api/automation'+(dialog.open?'':'?summary=1')));}catch(error){if(dialog.open)$('autoStatus').textContent=error.message;}finally{timer=setTimeout(poll,dialog.open?1000:2500);}}
  async function open(){
    const data=await api('/api/presets');$('autoPreset').replaceChildren();
    for(const preset of data.presets)$('autoPreset').add(new Option(preset.name,preset.id));
    if(!data.presets.length)$('autoPreset').add(new Option('Последние настройки экспорта',''));
    $('autoPreset').value=data.last_id||data.presets.at(-1)?.id||'';$('autoPreset').disabled=!data.presets.length;
    $('autoPresetNote').textContent=data.presets.length?'Используется последний сохранённый или применённый пресет. Ручные границы других исходников не копируются.':'Если экспортов ещё не было, используются стандартные настройки.';
    lastSignature='';motion.openDialog(dialog);await poll();
  }
  $('autoPreset').onchange=()=>api('/api/automation/preset',{id:$('autoPreset').value}).catch(error=>showError(error.message));
  $('closeAutomation').onclick=()=>motion.closeDialog(dialog);$('autoRefresh').onclick=poll;$('autoCancel').onclick=()=>api('/api/automation/cancel',{}).then(poll).catch(error=>showError(error.message));button.onclick=()=>open().catch(error=>showError(error.message));
  window.automationUI={open};preferencesReady.then(poll);
  dialog.addEventListener('close',()=>{if(state.backgroundMode&&nativeApp)api('/api/automation/hide',{}).catch(()=>{});else if(!state.automationRunning)window.autoPreview?.schedule();});
})();
