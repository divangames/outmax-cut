/* Durable batch workspace, reusable presets and scoped bulk editing. */
(() => {
  const B=batchController,shared=['mode','transition','crops','crops_x','zooms','sensitivity','bitrate_kbps','format','formats','format_catalog'];
  let initializing=true,saveTimer,lastSaved='',saving=Promise.resolve(),presets=[],clipboard=null;
  const toolbar=document.createElement('div');toolbar.className='queue-workspace-tools';
  toolbar.innerHTML='<label class="queue-search">Поиск<input id="queueSearch" type="search" placeholder="Артикул или имя файла"></label><label>Показать<select id="queueFilter"><option value="all">Все товары</option><option value="ready">Готовые к сборке</option><option value="incomplete">Без доступной пары</option><option value="changed">Настройки изменены</option><option value="running">В обработке</option><option value="done">Сохранённые</option><option value="error">С ошибками</option><option value="review">Нужна проверка видео</option><option value="selected">Выделенные</option><option value="excluded">Исключённые</option></select></label><button class="icon-button" id="resetQueueFilter" title="Сбросить поиск и фильтр" aria-label="Сбросить поиск и фильтр"><svg><use href="#i-reset"/></svg></button><button class="secondary-button" id="applySelectedButton">Настройки выделенным</button><span id="queueSaveStatus" role="status"></span>';
  document.querySelector('.queue-columns').before(toolbar);
  const historyButton=document.createElement('button');historyButton.id='queueHistory';historyButton.className='secondary-button';historyButton.textContent='Сохранённые пакеты';toolbar.append(historyButton);
  const presetBar=document.createElement('div');presetBar.className='preset-bar';
  presetBar.innerHTML='<label>Пресет<select id="presetSelect"><option value="">Выберите пресет…</option></select></label><button id="applyPreset" class="secondary-button">Применить</button><button id="savePreset" class="secondary-button">Сохранить пресет</button><button id="managePresets" class="text-button">Управление</button>';
  document.querySelector('.controls .settings').before(presetBar);
  const dialog=document.createElement('dialog');dialog.id='workspaceDialog';dialog.className='workspace-dialog';dialog.setAttribute('aria-label','Действие с очередью');document.body.append(dialog);
  function notify(message){$('queueSaveStatus').textContent=message;}
  function ask(title,fields=[],submit='Применить'){
    return new Promise(resolve=>{
      if(dialog.open)motion.closeDialog(dialog);dialog.replaceChildren();
      const heading=document.createElement('h2');heading.textContent=title;dialog.append(heading);
      const form=document.createElement('form');dialog.append(form);
      for(const field of fields){
        const label=document.createElement('label');label.className=field.type==='checkbox'?'dialog-check':'dialog-field';
        const input=document.createElement(field.type==='select'?'select':'input');input.name=field.id;
        if(field.type==='select'){for(const [value,text] of field.options)input.add(new Option(text,value));input.value=field.value||'';}
        else {input.type=field.type||'text';if(input.type==='checkbox')input.checked=field.checked!==false;else{input.value=field.value??'';input.required=field.required!==false;input.maxLength=field.maxLength||48;}}
        if(field.type==='checkbox'){label.append(input,document.createTextNode(field.label));}else{const text=document.createElement('span');text.textContent=field.label;label.append(text,input);}form.append(label);
      }
      const actions=document.createElement('div');actions.className='dialog-actions';const cancel=document.createElement('button'),apply=document.createElement('button');cancel.type='button';cancel.className='secondary-button';cancel.textContent='Отмена';apply.type='submit';apply.className='primary-button';apply.textContent=submit;actions.append(cancel,apply);form.append(actions);
      let settled=false;const finish=value=>{if(settled)return;settled=true;motion.closeDialog(dialog);resolve(value);};
      cancel.onclick=()=>finish(null);dialog.oncancel=event=>{event.preventDefault();finish(null);};
      form.onsubmit=event=>{event.preventDefault();const result={};for(const field of fields){const input=form.elements.namedItem(field.id);result[field.id]=field.type==='checkbox'?input.checked:input.value;}finish(result);};motion.openDialog(dialog);
    });
  }
  function report(title,text){
    if(dialog.open)motion.closeDialog(dialog);dialog.replaceChildren();const heading=document.createElement('h2'),pre=document.createElement('pre'),close=document.createElement('button');heading.textContent=title;pre.className='workspace-report';pre.textContent=text;close.className='secondary-button';close.textContent='Закрыть';close.onclick=()=>motion.closeDialog(dialog);dialog.oncancel=null;dialog.append(heading,pre,close);motion.openDialog(dialog);
  }
  function filter(){
    const query=$('queueSearch').value.toLocaleLowerCase('ru').trim(),status=$('queueFilter').value;
    for(const item of B.items){
      const findings=(item.snapshot.result?.variants||[]).some(v=>v.report?.quality?.findings?.length);
      const matches=status==='all'||status==='ready'&&B.ready(item)&&!['done','running','queued'].includes(item.status)||status==='incomplete'&&!B.ready(item)||status==='selected'&&item.selected||status==='excluded'&&!item.selected||status==='review'&&findings||item.status===status;
      const words=[item.name,...item.candidates.map(s=>s.name)].join(' ').toLocaleLowerCase('ru');const row=document.querySelector(`.batch-row[data-id="${item.id}"]`);if(row)row.hidden=!(matches&&words.includes(query));
    }
  }
  async function flush(){
    if(initializing||state.backgroundMode)return;
    const payload=B.persistPayload(),value=JSON.stringify(payload);if(value===lastSaved)return saving;
    notify('Сохраняем очередь…');
    saving=saving.catch(()=>{}).then(()=>api('/api/session',payload)).then(()=>{lastSaved=value;notify('Очередь сохранена');}).catch(error=>{notify('Не удалось сохранить очередь: '+error.message);throw error;});
    return saving;
  }
  function schedule(){filter();if(initializing)return;clearTimeout(saveTimer);saveTimer=setTimeout(()=>flush().catch(()=>{}),300);}
  window.addEventListener('queuechange',schedule);$('batchOutputPath').addEventListener('input',schedule);
  $('queueSearch').oninput=filter;$('queueFilter').onchange=filter;$('resetQueueFilter').onclick=()=>{$('queueSearch').value='';$('queueFilter').value='all';filter();};
  $('mainVideo').addEventListener('pause',()=>{if(!initializing)flush().catch(()=>{});});
  setInterval(()=>{if(!initializing&&!document.hidden)flush().catch(()=>{});},5000);
  window.addEventListener('pagehide',()=>{if(!initializing&&!state.backgroundMode)fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json','X-Outmax-Token':token},body:JSON.stringify(B.persistPayload()),keepalive:true}).catch(()=>{});});
  function paintPresets(){const previous=$('presetSelect').value;$('presetSelect').replaceChildren(new Option('Выберите пресет…',''));for(const preset of presets)$('presetSelect').add(new Option(preset.name,preset.id));$('presetSelect').value=presets.some(p=>p.id===previous)?previous:'';B.refreshLocks();}
  $('presetSelect').onchange=()=>B.refreshLocks();
  async function ensureFormats(settings){
    const missing=(settings.format_catalog||[]).filter(item=>!formatSpecs[item.id]);if(!missing.length)return;
    const catalog=structuredClone(formatCatalog);
    for(const item of missing){const entry={...item};if(catalog.some(p=>p.name.toLowerCase()===entry.name.toLowerCase()))entry.name=entry.name.slice(0,35)+' (пресет)';catalog.push(entry);}
    const saved=await api('/api/settings',{video_formats:catalog});formatCatalog=saved.video_formats;formatManager.renderChoices();
  }
  async function apply(settings,ids=null,keys=shared){
    if(B.locked)return;await ensureFormats(settings);settings={...settings,format_catalog:structuredClone(formatCatalog)};
    if(B.mode)B.apply(settings,ids||[B.current?.id].filter(Boolean),keys);
    else {const snapshot=editorSnapshot();for(const key of keys)if(settings[key]!==undefined)snapshot.settings[key]=structuredClone(settings[key]);snapshot.preview=null;snapshot.stale=!!snapshot.result;loadEditor(snapshot);}
    schedule();
  }
  async function usePreset(id,ids=null){const preset=presets.find(p=>p.id===id);if(!preset)return;await api('/api/automation/preset',{id});$('presetSelect').value=id;return apply(preset.settings,ids);}
  async function chooseFields(settings,ids){
    if(B.locked||!ids.length)return;
    const groups=[['frame','Положение кадра',['crops','crops_x']],['zoom','Масштаб',['zooms']],['mode','Режим монтажа',['mode']],['transition','Переход',['transition']],['formats','Форматы экспорта',['formats','format','format_catalog']],['pauses','Удаление пауз',['sensitivity']],['bitrate','Битрейт',['bitrate_kbps']],['trims','Ручные границы исходников',['trims']]];
    const result=await ask('Применить настройки · товаров '+ids.length,groups.map(([id,label])=>({id,label,type:'checkbox',checked:id!=='trims'})));
    if(result)await apply(settings,ids,groups.filter(([id])=>result[id]).flatMap(([, ,keys])=>keys));
  }
  async function savePreset(){
    if(B.locked)return;B.remember();const selected=presets.find(p=>p.id===$('presetSelect').value);
    const result=await ask('Сохранить пресет',[{id:'name',label:'Название',value:selected?.name||''},{id:'replace',label:'Обновить выбранный пресет',type:'checkbox',checked:!!selected}],'Сохранить');
    if(!result)return;const response=await api('/api/presets',{id:result.replace?selected?.id:undefined,name:result.name,settings:editorSnapshot().settings});presets=response.presets;paintPresets();$('presetSelect').value=presets.find(p=>p.name===result.name.trim())?.id||'';B.refreshLocks();notify('Пресет сохранён');
  }
  async function managePresets(){
    const selected=presets.find(p=>p.id===$('presetSelect').value)||presets[0];if(!selected){await savePreset();return;}
    const result=await ask('Управление пресетами',[{id:'preset',label:'Пресет',type:'select',value:selected.id,options:presets.map(p=>[p.id,p.name])},{id:'action',label:'Действие',type:'select',options:[['rename','Переименовать'],['delete','Удалить']]},{id:'name',label:'Новое название (для переименования)',value:selected.name,required:false}]);
    if(!result)return;const preset=presets.find(p=>p.id===result.preset);const response=await api('/api/presets',{id:preset.id,action:result.action==='delete'?'delete':'save',name:result.name,settings:preset.settings});presets=response.presets;paintPresets();
  }
  const itemsPayload=items=>items.map(item=>({item_id:item.id,name:item.name,sources:item.snapshot.sources.map(source=>source?.id||null),...item.snapshot.settings}));
  async function verify(items=B.items){
    if(B.locked)return;B.remember();const response=await api('/api/batch/preflight',{output:$('batchOutputPath').value,items:itemsPayload(items)}),ids=[...new Set(items.flatMap(i=>i.candidates.map(s=>s.id)))];
    const warnings=response.items.filter(item=>item.status==='error').map(item=>B.items.find(i=>i.id===item.id)?.name+': '+item.error);
    if(ids.length){const task=await api('/api/sources/check',{sources:ids});for(;;){const status=await api('/api/imports/'+task.id);notify(`Проверка исходников · ${status.processed}/${status.total}`);if(status.status!=='running'){warnings.push(...status.errors.map(error=>error.file+': '+error.error));break;}await new Promise(resolve=>setTimeout(resolve,250));}}
    report('Проверка исходников',warnings.length?warnings.join('\n\n'):'Исходники доступны, видеодорожки читаются, пары и настройки проверены. Проверка не запускает экспорт.');
  }
  async function exportNew(items=B.items.filter(item=>item.selected)){
    if(B.locked)return;B.remember();B.setExportFormats(selectedFormats());const checked=await api('/api/batch/preflight',{output:$('batchOutputPath').value,items:itemsPayload(items)});const ids=checked.items.filter(item=>item.status==='ready').map(item=>item.id);
    if(ids.length)await B.export({ids});else notify('Нет новых товаров для экспорта.');
    const skipped=checked.items.filter(item=>item.status!=='ready');if(skipped.length)notify('Пропущено готовых или требующих исправления товаров: '+skipped.length);
  }
  async function imported(command,items){
    if(!command)return;
    if(command.action==='new'){const keep=new Set(items.map(item=>item.id));for(const item of [...B.items])if(!keep.has(item.id))B.remove(item.id);}
    if(['model','hands'].includes(command.action))for(const item of items){const source=item.candidates[0];item.snapshot.sources=command.action==='model'?[source,null]:[null,source];item.selected=false;item.status='changed';} 
    if(items.length&&B.current&&['model','hands'].includes(command.action))B.open(items[0].id);
    if(command.action==='preset'){const preset=presets.find(p=>p.id===command.preset);if(!preset){notify('Пресет удалён. Выберите другой.');return;}await usePreset(preset.id,items.map(item=>item.id));}
    if(command.action==='quick'&&B.lastSettings)await apply(B.lastSettings,items.map(item=>item.id));
    if(['quick','preset','new-only'].includes(command.action))await exportNew(items);
    if(command.action==='check')await verify(items);B.render();schedule();
  }
  async function shellCommand(command){
    if(command.action==='settings')$('settingsButton').click();
    if(command.action==='results')await api('/api/folder',{path:$('batchOutputPath').value});
    if(command.action==='resume'){await B.restore(await api('/api/session'));notify('Сохранённая очередь восстановлена.');}
  }
  async function archive(){await flush();return api('/api/session/archive',{});}
  async function history(){
    const data=await api('/api/session/archives');if(!data.archives.length){report('Сохранённые пакеты','Текущая очередь сохраняется автоматически. Перед созданием нового пакета предыдущая очередь попадает в этот список.');return;}
    const result=await ask('Открыть сохранённый пакет',[{id:'archive',label:'Пакет',type:'select',options:data.archives.map(item=>[item.id,item.name+' · товаров '+item.count])}],'Открыть');
    if(result){await archive();await B.restore(await api('/api/session?archive='+result.archive));schedule();}
  }
  async function activateEditor(){
    if(state.backgroundMode){initializing=true;state.backgroundMode=false;const active=state.automationRunning;state.automationRunning=false;
      try{await B.restore(await api('/api/session'));}finally{state.automationRunning=active;initializing=false;if(active)window.autoPreview?.cancel();refresh();schedule();}}
    if(!state.automationRunning)window.autoPreview?.schedule();
  }
  $('queueHistory').onclick=()=>history().catch(error=>showError(error.message));
  $('applySelectedButton').onclick=()=>chooseFields(editorSnapshot().settings,B.items.filter(item=>item.selected).map(item=>item.id)).catch(error=>showError(error.message));
  $('savePreset').onclick=()=>savePreset().catch(error=>showError(error.message));$('managePresets').onclick=()=>managePresets().catch(error=>showError(error.message));
  $('applyPreset').onclick=()=>usePreset($('presetSelect').value).catch(error=>showError(error.message));
  window.batchWorkspace={ask,report,notify,flush,archive,history,activateEditor,apply,usePreset,chooseFields,savePreset,verify,exportNew,imported,shellCommand,get presets(){return presets;},get copied(){return clipboard;},copy(item){B.remember();clipboard=structuredClone(item.snapshot.settings);notify('Настройки скопированы');},paste(item){if(clipboard)return chooseFields(clipboard,[item.id]);}};
  window.workspaceReady=preferencesReady.then(async()=>{const savedPresets=await api('/api/presets');presets=savedPresets.presets;paintPresets();$('presetSelect').value=savedPresets.last_id||presets.at(-1)?.id||'';B.refreshLocks();const saved=await api('/api/session');if(saved.session)await B.restore(saved);if(saved.missing?.length)notify('Не найдены исходники: '+saved.missing.length+'. Замените их в роликах.');}).catch(error=>notify('Восстановление очереди: '+error.message)).finally(()=>{initializing=false;filter();schedule();});
})();
