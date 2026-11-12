/* Batch state stays independent for each product, sharing the single-clip editor. */
(() => {
  const defaults = () => editorDefaults();
  const batch = {mode:false,items:[],active:null,single:null,importing:false,importId:null,
    cancelImport:false,running:false,id:null,native:false,loading:false,collecting:false};
  const rows=new Map();
  let lastEditLock, paintFrame;
  const text=(el,value)=>{if(el.textContent!==String(value))el.textContent=String(value);};
  const current = () => batch.items.find(item=>item.id===batch.active);
  const ready = item => item.snapshot.sources.every(source=>source&&!source.missing) && item.snapshot.sources[0].id!==item.snapshot.sources[1].id;
  const incompleteText = item => {
    const [model,hands]=item.snapshot.sources.map(source=>source&&!source.missing);
    if(!model&&!hands)return item.candidates.some(source=>!source.missing)?'Выберите модель и руки':'Нет видео ног и рук';
    if(!model)return 'Нет видео ног';
    if(!hands)return 'Нет видео рук';
    return 'Выберите разные видео';
  };
  const locked = () => state.running||state.automationRunning||state.uploading.some(Boolean)||batch.running||batch.importing||batch.collecting;
  const error = message => {$('batchError').textContent=message;$('batchError').hidden=!message;if(!batch.mode)showError(message);};
  function remember(){
    if(batch.loading||batch.running||!batch.mode||!current())return;
    const item=current();
    item.snapshot=editorSnapshot();
    for(const source of item.snapshot.sources.filter(Boolean)){
      if(!item.candidates.some(c=>c.id===source.id))item.candidates.push(source);
    }
    if(item.snapshot.stale)item.status='changed';
  }
  function refreshLocks(){
    const editLocked=locked();
    if($('batchSelectAll'))$('batchSelectAll').disabled=editLocked||!batch.items.length;
    ['singleMode','batchMode'].forEach(id=>$(id).disabled=editLocked);
    ['swapDetailButton','applySettingsButton','batchModelSelect','batchHandsSelect'].forEach(id=>$(id).disabled=editLocked);
    ['chooseOutputButton','batchOutputPath','selectAllButton'].forEach(id=>$(id).disabled=editLocked);
    $('generalSettingsButton').disabled=editLocked||!batch.items.length;
    $('applySettingsButton').disabled=editLocked||batch.items.length<2;
    $('importFolderButton').disabled=editLocked;
    $('folderDrop').setAttribute('aria-disabled',String(editLocked));
    if(lastEditLock!==editLocked){for(const row of rows.values())row.querySelectorAll('[data-edit]').forEach(el=>el.disabled=editLocked);lastEditLock=editLocked;}
    const count=batch.items.filter(item=>item.selected&&ready(item)).length;
    if($('applySelectedButton'))$('applySelectedButton').disabled=editLocked||!batch.items.some(item=>item.selected);
    if($('savePreset'))$('savePreset').disabled=editLocked;
    if($('applyPreset'))$('applyPreset').disabled=editLocked||!$('presetSelect').value;
    $('batchRenderButton').disabled=editLocked||!count||!$('batchOutputPath').value.trim();
    $('batchRenderButton').textContent=`Собрать выбранные${count?' · '+count:''}`;
  }
  function switchMode(enabled){
    if(locked())return;
    if(batch.mode===enabled)return;
    if(enabled){batch.single=editorSnapshot();batch.mode=true;}
    else{remember();batch.mode=false;}
    $('singleMode').setAttribute('aria-pressed',String(!enabled));$('batchMode').setAttribute('aria-pressed',String(enabled));
    document.body.classList.toggle('batch-mode',enabled);
    if($('formatScopeNote'))$('formatScopeNote').hidden=!enabled;
    motion.visible($('batchPanel'),enabled);
    window.workspaceLayout?.(enabled);
    $('pageTitle').textContent=enabled?'Пакетная обработка':'Редактор видео';
    $('singleArticleRow').hidden=enabled;
    $('pageSubtitle').textContent=enabled?'Проверьте пары, настройте каждый товар и запустите очередь.':'Исходники → монтаж → экспорт';
    if(enabled){
      if(batch.active){batch.loading=true;openItem(batch.active);batch.loading=false;}else {$('editorWorkspace').hidden=true;$('batchDetail').hidden=true;}
    }else{
      $('editorWorkspace').hidden=false;$('batchDetail').hidden=true;
      batch.loading=true;loadEditor(batch.single);batch.loading=false;
    }
    motion.reveal($('editorWorkspace'));
    refreshLocks();
  }
  function detailSelectors(item){
    for(let i=0;i<2;i++){
      const select=$(i===0?'batchModelSelect':'batchHandsSelect');
      select.replaceChildren(new Option('Выберите исходник…',''));
      item.candidates.forEach(c=>select.add(new Option(c.name,c.id)));
      select.value=item.snapshot.sources[i]?.id||'';
    }
    $('batchDetailTitle').textContent='Артикул '+item.name.split('/').filter(Boolean).at(-1);
    $('batchDetailNote').textContent=item.detection+' Настройки относятся только к этому ролику.';
  }
  function openItem(id){
    if(state.running||state.uploading.some(Boolean)||batch.importing)return;
    remember();batch.active=id;
    const item=current();if(!item)return;
    $('editorWorkspace').hidden=false;$('batchDetail').hidden=false;
    batch.loading=true;loadEditor(item.snapshot);batch.loading=false;
    detailSelectors(item);
    if(!item.snapshot.result&&!item.snapshot.preview)window.previewSource?.(item.snapshot.sources.findIndex(source=>source&&!source.missing));
    for(const [key,row] of rows)row.classList.toggle('selected',key===id);
    refreshLocks();
  }
  function openAndView(id){
    openItem(id);
    motion.reveal($('editorWorkspace'));
    if(innerWidth<900)$('batchDetail').scrollIntoView({block:'nearest',behavior:'instant'});
  }
  const statusText = item => ({
    ready:'Готов к сборке',changed:'Настройки изменены',queued:'В очереди',running:`Обработка · ${item.progress||0}%`,
    done:'Сохранён',error:'Ошибка · можно повторить',cancelled:'Отменён'
  }[item.status] || 'Готов к сборке');
  function updateRows(){
    for(const item of batch.items){
      const row=rows.get(item.id);
      if(!row)continue;
      const findings=(item.snapshot.result?.variants||[]).flatMap(v=>v.report?.quality?.findings||[]);
      const statusKey=[item.status,item.progress,item.error,ready(item),incompleteText(item),item.selected,findings.length].join('|');
      if(row.dataset.statusKey===statusKey)continue;
      row.dataset.statusKey=statusKey;
      row.querySelector('.batch-item-check').checked=item.selected;
      text(row.querySelector('.batch-item-status'),ready(item)?statusText(item)+(findings.length?' · проверить':''):incompleteText(item));
      row.querySelector('.batch-item-status').title=ready(item)?'':'Товар будет пропущен при сборке, пока не выбраны два доступных видео: модель и руки.';
      row.querySelector('.batch-item-status').dataset.status=ready(item)?item.status:'incomplete';
      text(row.querySelector('.batch-item-error'),item.error||'');
      motion.progress(row.querySelector('.batch-item-progress'),item.progress||0);
      row.querySelector('.batch-item-progress').hidden=item.status!=='running';
    }
    $('batchCount').textContent=String(batch.items.length);
    const selectAll=$('batchSelectAll');
    if(selectAll){const count=batch.items.filter(i=>i.selected).length;selectAll.checked=!!count&&count===batch.items.length;selectAll.indeterminate=!!count&&count<batch.items.length;selectAll.disabled=locked()||!batch.items.length;}
    if(!batch.running){
      const count=batch.items.filter(i=>i.selected&&ready(i)).length;
      const completed=batch.items.filter(i=>i.status==='done'&&!i.snapshot.stale).length;
      $('batchSummary').textContent=batch.items.length?`Выбрано ${count} из ${batch.items.length} · сохранено ${completed}`:'Пока нет роликов для экспорта.';
    }
    refreshLocks();
    window.dispatchEvent(new Event('queuechange'));
  }
  function patchRow(row,item){
    const visualKey=[item.selected,item.name,...item.snapshot.sources.map(s=>`${s?.id}:${!!s?.missing}`),...item.snapshot.settings.crops,...item.snapshot.settings.crops_x,item.snapshot.settings.format].join('|');
    if(row.dataset.visualKey===visualKey)return;
    row.dataset.visualKey=visualKey;
    row.classList.toggle('selected',item.id===batch.active);
    const check=row.querySelector('.batch-item-check');check.checked=item.selected;
    const open=row.querySelector('.batch-item-open');text(open.querySelector('strong'),item.name.split('/').filter(Boolean).at(-1));
    open.title=item.name+' · '+item.detection;
    for(let i=0;i<2;i++){
      const source=item.snapshot.sources[i],cell=row.querySelectorAll('.pair-preview')[i];
      const signature=[source?.id,source?.missing,item.snapshot.settings.crops[i],item.snapshot.settings.crops_x[i],item.snapshot.settings.format].join(':');
      if(cell.dataset.signature===signature)continue;
      cell.dataset.signature=signature;cell.replaceChildren();
      const label=document.createElement('span');label.textContent=source&&!source.missing?source.name:(i===0?'Нет видео ног':'Нет видео рук');
      cell.title=(i===0?'Модель':'Руки')+' · '+label.textContent+(source?.missing?' · '+source.name:'');
      if(source&&!source.missing){const img=document.createElement('img');img.loading='lazy';img.decoding='async';img.src=source.poster;img.alt='';img.width=48;img.height=48;img.style.objectPosition=`${item.snapshot.settings.crops_x[i]*100}% ${item.snapshot.settings.crops[i]*100}%`;const [w,h]=formatSpecs[item.snapshot.settings.format];img.style.aspectRatio=`${w}/${h}`;img.style.height='auto';cell.append(img);}
      else {const empty=document.createElement('span');empty.className='no-source';empty.textContent='—';cell.append(empty);}
      cell.append(label);
    }
  }
  function makeRow(item){
    const row=document.createElement('article');row.className='batch-row';row.dataset.id=item.id;
    row.innerHTML='<input type="checkbox" data-edit class="batch-item-check"><button class="batch-item-open"><strong></strong></button><div class="batch-pair"><button class="pair-preview"></button><button class="pair-preview"></button></div><button class="text-button batch-swap" data-edit title="Поменять роли местами" aria-label="Поменять роли местами">⇄</button><div class="batch-state"><span class="batch-item-status"></span><progress class="batch-item-progress" max="100" hidden></progress><small class="batch-item-error"></small></div><button class="batch-remove text-button" data-edit aria-label="Убрать из очереди" title="Убрать из очереди">×</button>';
    const check=row.querySelector('input');check.setAttribute('aria-label','Выбрать '+item.name);
    check.onchange=()=>{item.selected=check.checked;updateRows();};
    row.querySelector('.batch-item-open').onclick=()=>openAndView(item.id);
    row.querySelectorAll('.pair-preview').forEach((cell,i)=>{cell.onclick=()=>{openAndView(item.id);window.previewSource?.(i);};});
    row.querySelector('.batch-swap').onclick=()=>swap(item);
    row.querySelector('.batch-remove').onclick=()=>{
      if(locked())return;
      const index=batch.items.indexOf(item),hadFocus=row.contains(document.activeElement);
      batch.items.splice(index,1);
      if(batch.active===item.id){batch.active=null;$('batchDetail').hidden=true;$('editorWorkspace').hidden=true;}
      renderList();
      if(hadFocus)(rows.get(batch.items[Math.min(index,batch.items.length-1)]?.id)?.querySelector('.batch-remove')||$('importFolderButton')).focus({preventScroll:true});
    };
    row.querySelectorAll('[data-edit]').forEach(el=>el.disabled=locked());
    return row;
  }
  function renderList(){
    const list=$('batchList'),ids=new Set(batch.items.map(item=>item.id));
    motion.reconcile(list,()=>{
      for(const [id,row] of rows)if(!ids.has(id)){motion.remove(row,list);rows.delete(id);}
      list.querySelector('.batch-empty')?.remove();
      for(const item of batch.items){
        let row=rows.get(item.id);
        if(!row){row=makeRow(item);rows.set(item.id,row);list.append(row);}
        patchRow(row,item);
      }
      batch.items.forEach((item,index)=>{const row=rows.get(item.id);if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);});
      if(!batch.items.length){const empty=document.createElement('p');empty.className='batch-empty';empty.textContent='Добавьте папки с артикулами';list.append(empty);}
    });
    updateRows();
  }
  function scheduleCurrent(){
    if(paintFrame)return;
    paintFrame=requestAnimationFrame(()=>{paintFrame=null;const item=current();if(item&&rows.has(item.id))patchRow(rows.get(item.id),item);updateRows();});
  }
  function changedItem(item){
    item.snapshot.preview=null;
    item.snapshot.stale=!!item.snapshot.result;item.status='changed';item.error=null;
    item.detection='Порядок и настройки заданы вручную.';
    if(item.id===batch.active){batch.loading=true;loadEditor(item.snapshot);batch.loading=false;detailSelectors(item);}
    renderList();
  }
  function swap(item){
    if(locked())return;
    remember();item.snapshot.sources.reverse();item.snapshot.settings.trims=[null,null];
    // Crop follows the role, so the model still uses its legs framing.
    changedItem(item);
  }
  async function addGroups(groups){
    await preferencesReady;
    const newItems=groups.map(group=>({
      ...group,id:crypto.randomUUID(),selected:group.sources.every(Boolean),status:'ready',
      snapshot:{sources:group.sources.map(id=>group.candidates.find(c=>c.id===id)||null),
        settings:{...defaults(),formats:[...selectedFormats()],format:$('outputFormat').value},result:null,stale:false}
    }));
    for(let i=0;i<newItems.length;i+=40){batch.items.push(...newItems.slice(i,i+40));renderList();await new Promise(resolve=>setTimeout(resolve,0));}
    if(!batch.active&&newItems.length)openItem(newItems[0].id);
  }
  function beginImport(){
    batch.importing=true;batch.cancelImport=false;error('');
    $('batchImportNotice').textContent='';
    $('batchImportStatus').hidden=false;$('cancelImportButton').disabled=false;
    $('batchImportText').textContent='Ищем видео и готовим предпросмотр…';refreshLocks();
    $('batchImportProgress').removeAttribute('value');
  }
  function endImport(){
    batch.importing=false;batch.importId=null;$('batchImportStatus').hidden=true;
    refreshLocks();
    if(!batch.active&&batch.items.length)openItem(batch.items[0].id);
  }
  async function pollImport(){
    try{
      const task=await api(`/api/imports/${batch.importId}`);
      $('batchImportText').textContent=`${task.processed} из ${task.total} · ${importLabel(task)}${task.current?' · '+task.current:''}`;
      $('batchImportProgress').value=task.progress||0;
      if(task.status==='running'){setTimeout(pollImport,700);return;}
      if(task.command?.action==='new')await window.batchWorkspace?.archive();
      const before=new Set(batch.items.map(item=>item.id));await addGroups(task.groups);endImport();
      await window.batchWorkspace?.imported(task.command,batch.items.filter(item=>!before.has(item.id)));
      if(task.skipped)$('batchImportNotice').textContent=`Готовые экспорты OUTMAX пропущены: ${task.skipped}.`;
      if(task.errors.length)error('Не удалось прочитать:\n'+task.errors.map(e=>e.file+': '+e.error).join('\n'));
    }catch(e){error(e.message);endImport();}
  }
  async function chooseInput(){
    if(locked())return;
    try{
      if(batch.native){
        const choice=await api('/api/choose-folder',{});
        if(!choice.path)return;
        beginImport();
        const task=await api('/api/batch/import',{path:choice.path});batch.importId=task.id;pollImport();
      }else $('folderInput').click();
    }catch(e){error(e.message);endImport();}
  }
  async function importFiles(files){
    if(locked())return;
    beginImport();
    const generated=new Set();
    for(const item of files.filter(item=>/\.json$/i.test(item.file.name)&&item.file.size<1024**2)){
      try{
        const data=JSON.parse(await item.file.text());
        if(data && (data.generator==='OUTMAX Cut'||(data.frames===658&&data.fps===30&&data.transition_note&&data.settings&&data.segments))){
          generated.add(item.relative.replace(/\.json$/i,'').toLowerCase());
        }
      }catch{}
    }
    const allVideos=files.filter(item=>/\.(mp4|mov|m4v|mkv|avi|webm)$/i.test(item.file.name));
    const videos=allVideos.filter(item=>{
      const parts=item.relative.replaceAll('\\','/').split('/');
      const match=/^([0-9]+)(?:_[0-9]+x[0-9]+(?:_[a-zA-Z0-9_-]+)?)?(?:_v[0-9]+)?\.mp4$/i.exec(item.file.name);
      const archive=parts.slice(0,-1).join('/')+'/Руки + Ноги/';
      const articleExport=match&&parts.at(-2)===match[1]&&['ноги','руки'].every(role=>
        allVideos.some(candidate=>candidate.relative.replaceAll('\\','/').startsWith(archive+match[1]+'_'+role+'.')));
      return !articleExport&&!generated.has(item.relative.replace(/\.[^.]+$/,'').toLowerCase());
    });
    const skipped=allVideos.length-videos.length;
    if(!videos.length){error('В папках нет исходных видео. Готовые экспорты OUTMAX пропускаются.');endImport();return;}
    if(videos.length>1000){error('За один импорт можно добавить до 1000 видео.');endImport();return;}
    const ids=[],failures=[];
    try{
      for(let i=0;i<videos.length;i++){
        if(batch.cancelImport)break;
        $('batchImportText').textContent=`Готовим исходники · ${i+1} из ${videos.length}`;
        const {file,relative}=videos[i];
        if(file.size>2*1024**3){failures.push(relative+': файл больше 2 ГБ');continue;}
        const form=new FormData();form.append('file',file);form.append('relative',relative);
        try{ids.push((await prepareSource('/api/upload',form,task=>{
          $('batchImportText').textContent=`${i+1} из ${videos.length} · ${relative} · ${importLabel(task)}`;
          $('batchImportProgress').value=(i+(task.transfer?task.progress/100*.1:.1+task.progress/100*.9))/videos.length*100;
          if(batch.cancelImport&&task.id&&task.status==='running')api(`/api/imports/${task.id}/cancel`,{}).catch(()=>{});
        })).id);}catch(e){failures.push(relative+': '+e.message);}
      }
      const grouped=await api('/api/batch/group',{sources:ids});await addGroups(grouped.groups);endImport();
      if(skipped)$('batchImportNotice').textContent=`Готовые экспорты OUTMAX пропущены: ${skipped}.`;
      if(failures.length)error('Не удалось прочитать:\n'+failures.join('\n'));
    }catch(e){error(e.message);}finally{endImport();}
  }
  async function walk(entry){
    if(entry.isFile)return [{file:await new Promise((resolve,reject)=>entry.file(resolve,reject)),relative:entry.fullPath.replace(/^\//,'')}];
    if(!entry.isDirectory)return [];
    const reader=entry.createReader();let children=[],part;
    do{part=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));children.push(...part);}while(part.length);
    const result=[];for(const child of children)result.push(...await walk(child));return result;
  }
  async function pollBatch(){
    try{
      const run=await api(`/api/batches/${batch.id}`);
      let sum=0,finished=0;
      const itemsById=new Map(batch.items.map(item=>[item.id,item]));
      for(const job of run.jobs){
        const item=itemsById.get(job.item_id);if(!item)continue;
        item.status=job.status;item.progress=job.progress;item.error=job.error;
        if(['done','error','cancelled'].includes(job.status)){sum+=100;finished++;}else sum+=job.progress;
        if(job.status==='done'&&item.snapshot.result?.id!==job.id){
          item.snapshot.result=job;item.snapshot.stale=false;
          if(item.id===batch.active){batch.loading=true;loadEditor(item.snapshot);batch.loading=false;}
        }
      }
      motion.progress($('batchProgress'),sum/run.jobs.length);
      $('batchSummary').textContent=`Обработано ${finished} из ${run.jobs.length} · сохранено ${run.jobs.filter(j=>j.status==='done').length}`;
      const fileCount=run.jobs.reduce((count,job)=>count+job.variants.filter(v=>v.status==='done').length,0),fileTotal=run.jobs.reduce((count,job)=>count+job.variants.length,0);
      const progress=run.jobs.reduce((sum,job)=>sum+(['done','error','cancelled'].includes(job.status)?100:job.progress),0)/run.jobs.length;
      const elapsed=(Date.now()-(batch.startedAt||Date.now()))/1000,eta=progress>3?Math.round(elapsed/progress*(100-progress)):null;
      $('batchSummary').textContent+=` · файлов ${fileCount}/${fileTotal}${eta?' · ≈ '+Math.ceil(eta/60)+' мин':''}`;
      updateRows();
      if(run.status==='running'){setTimeout(pollBatch,900);return;}
      batch.running=false;state.externalLocked=false;$('batchCancelButton').hidden=true;
      $('batchSummary').textContent=run.status==='cancelled'?'Очередь отменена. Готовые файлы сохранены.':run.status==='done_with_errors'?'Очередь завершена с ошибками. Их причины указаны у роликов.':`Готово. Сохранено ${run.jobs.length} роликов.${fileCount!==run.jobs.length?' Файлов: '+fileCount+'.':''}`;
      refresh();refreshLocks();
      window.autoPreview?.schedule();
    }catch(e){error('Не удалось обновить очередь. Повторяем проверку…');setTimeout(pollBatch,2000);}
  }
  async function exportSelected(options={}){
    if(locked())return;
    remember();const chosen=batch.items.filter(i=>(options.ids?options.ids.includes(i.id):i.selected)&&ready(i));if(!chosen.length)return;
    batch.running=true;state.externalLocked=true;error('');refresh();
    window.autoPreview?.cancel();
    try{
      const run=await api('/api/batch/render',{output:$('batchOutputPath').value.trim(),
        items:chosen.map(i=>({item_id:i.id,name:i.name,sources:i.snapshot.sources.map(s=>s.id),...i.snapshot.settings,_repeat:!!options.repeat}))});
      batch.id=run.id;batch.startedAt=Date.now();batch.lastSettings=structuredClone(chosen[0].snapshot.settings);$('batchProgress').hidden=false;motion.progress($('batchProgress'),0);
      $('batchCancelButton').hidden=false;$('batchCancelButton').disabled=false;pollBatch();
      window.dispatchEvent(new Event('queuechange'));
    }catch(e){batch.running=false;state.externalLocked=false;error(e.message);refresh();}
  }
  window.batchController={
    refreshLocks,
    get items(){return batch.items;},get current(){return current();},get mode(){return batch.mode;},get locked(){return locked();},get lastSettings(){return batch.lastSettings;},
    ready,remember,open:openAndView,render:renderList,switchMode,export:exportSelected,
    persistPayload(){
      remember();const payload={items:structuredClone(batch.items),single:batch.mode?structuredClone(batch.single):editorSnapshot(),active:batch.active,mode:batch.mode,output:$('batchOutputPath').value,batch_id:batch.running?batch.id:null,lastSettings:batch.lastSettings};
      for(const snapshot of [...payload.items.map(item=>item.snapshot),payload.single].filter(Boolean)){snapshot.preview=null;if(snapshot.result)snapshot.result={id:snapshot.result.id};}
      return payload;
    },
    async restore(data){
      const saved=data.session;if(!saved)return;
      const hydrate=snapshot=>{
        if(!snapshot)return {sources:[null,null],settings:defaults()};
        snapshot.sources=snapshot.sources.map(source=>source?data.sources[source.id]||{...source,missing:true}:null);
        snapshot.result=snapshot.result?data.jobs[snapshot.result.id]||null:null;snapshot.preview=null;
        snapshot.settings.formats=(snapshot.settings.formats||['standard']).filter(id=>formatSpecs[id]);if(!snapshot.settings.formats.length)snapshot.settings.formats=['standard'];
        if(!snapshot.settings.formats.includes(snapshot.settings.format))snapshot.settings.format=snapshot.settings.formats[0];return snapshot;
      };
      batch.items=saved.items.map(item=>({...item,status:['queued','running'].includes(item.status)?'cancelled':item.status,candidates:item.candidates.map(source=>data.sources[source.id]||{...source,missing:true}),snapshot:hydrate(item.snapshot)}));
      batch.active=batch.items.some(item=>item.id===saved.active)?saved.active:batch.items[0]?.id||null;batch.lastSettings=saved.lastSettings;
      if(saved.output)$('batchOutputPath').value=saved.output;
      const single=hydrate(saved.single);if(saved.mode)switchMode(true);else{batch.loading=true;loadEditor(single);batch.loading=false;}
      batch.single=single;renderList();if(saved.mode&&batch.active){batch.loading=true;openItem(batch.active);batch.loading=false;}
      if(saved.batch_id)try{const run=await api('/api/batches/'+saved.batch_id);if(run.status==='running'){batch.running=true;state.externalLocked=true;batch.id=saved.batch_id;batch.startedAt=Date.now();$('batchCancelButton').hidden=false;$('batchProgress').hidden=false;refresh();pollBatch();}}catch{}
    },
    apply(settings,ids,keys){
      if(locked())return;remember();
      for(const item of batch.items.filter(item=>ids.includes(item.id))){for(const key of keys)if(settings[key]!==undefined)item.snapshot.settings[key]=structuredClone(settings[key]);item.snapshot.preview=null;item.snapshot.stale=!!item.snapshot.result;item.status='changed';item.error=null;}
      if(ids.includes(batch.active)){batch.loading=true;loadEditor(current().snapshot);batch.loading=false;}renderList();
    },
    setExportFormats(formats){
      if(!batch.mode||batch.loading||locked())return;remember();
      for(const item of batch.items){
        const snapshot=item.snapshot,settings=snapshot.settings;
        if(JSON.stringify(settings.formats)===JSON.stringify(formats))continue;
        settings.formats=[...formats];settings.format_catalog=structuredClone(formatCatalog);
        if(!formats.includes(settings.format)){settings.format=formats[0];snapshot.preview=null;}
        snapshot.stale=!!snapshot.result;item.status='changed';item.error=null;
      }
      renderList();
    },
    swap(id){if(!locked()){const item=batch.items.find(item=>item.id===id);if(item)swap(item);}},
    move(id,direction){if(locked())return;remember();const index=batch.items.findIndex(item=>item.id===id);if(index<0)return;const target=direction==='first'?0:direction==='last'?batch.items.length-1:Math.max(0,Math.min(batch.items.length-1,index+direction));const [item]=batch.items.splice(index,1);batch.items.splice(target,0,item);renderList();},
    remove(id){if(locked())return;remember();batch.items=batch.items.filter(item=>item.id!==id);if(batch.active===id){batch.active=null;if(batch.items.length)openItem(batch.items[0].id);else{$('batchDetail').hidden=true;$('editorWorkspace').hidden=true;}}renderList();},
    clear(){if(locked())return;remember();batch.items=[];batch.active=null;$('editorWorkspace').hidden=true;$('batchDetail').hidden=true;renderList();},
    formatsChanged(){
      remember();
      for(const snapshot of [...batch.items.map(item=>item.snapshot),batch.single].filter(Boolean)){
        snapshot.settings.format_catalog=structuredClone(formatCatalog);
        snapshot.settings.formats=(snapshot.settings.formats||['standard']).filter(id=>formatSpecs[id]);
        if(!snapshot.settings.formats.length)snapshot.settings.formats=['standard'];
        if(!snapshot.settings.formats.includes(snapshot.settings.format))snapshot.settings.format=snapshot.settings.formats[0];
        snapshot.preview=null;snapshot.stale=!!snapshot.result;
      }
      for(const item of batch.items)item.status='changed';renderList();
    },
    selectAll(checked){if(locked())return;batch.items.forEach(item=>item.selected=checked&&ready(item));updateRows();},
    changed(){if(batch.mode&&!batch.loading){remember();scheduleCurrent();}},
    previewCompleted(){if(batch.mode&&!batch.loading){remember();scheduleCurrent();}},
    completed(job){if(!batch.mode||!current())return;remember();if(!job.preview){current().status=job.status;current().error=job.error;}renderList();},
    exportContext(){return batch.mode&&current()?{folder:current().name,output:$('batchOutputPath').value.trim(),item_id:current().id}:{output:$('batchOutputPath').value.trim()};},
    folderContext(){return {path:$('batchOutputPath').value.trim()};}
  };
  $('singleMode').onclick=()=>switchMode(false);$('batchMode').onclick=()=>switchMode(true);
  $('importFolderButton').onclick=e=>{e.stopPropagation();chooseInput();};
  $('folderDrop').onclick=e=>{if(e.target===$('folderInput'))return;chooseInput();};
  $('folderDrop').onkeydown=e=>{if(e.target===$('folderDrop')&&['Enter',' '].includes(e.key)){e.preventDefault();chooseInput();}};
  $('folderInput').onchange=()=>{importFiles([...$('folderInput').files].map(file=>({file,relative:file.webkitRelativePath||file.name})));$('folderInput').value='';};
  $('folderDrop').ondragover=e=>{e.preventDefault();if(!locked())$('folderDrop').classList.add('dragover');};
  $('folderDrop').ondragleave=()=>$('folderDrop').classList.remove('dragover');
  $('folderDrop').ondrop=async e=>{
    e.preventDefault();$('folderDrop').classList.remove('dragover');if(locked())return;
    const entries=[...e.dataTransfer.items].map(item=>item.webkitGetAsEntry?.()).filter(Boolean);
    batch.collecting=true;refreshLocks();
    try{const files=[];for(const entry of entries)files.push(...await walk(entry));batch.collecting=false;await importFiles(files);}
    catch(err){error(err.message);}finally{batch.collecting=false;refreshLocks();}
  };
  $('cancelImportButton').onclick=async()=>{
    batch.cancelImport=true;$('cancelImportButton').disabled=true;
    if(batch.importId)try{await api(`/api/imports/${batch.importId}/cancel`,{});}catch(e){error(e.message);}
  };
  $('chooseOutputButton').onclick=async()=>{
    try{const result=await api('/api/choose-folder',{});if(result.path)$('batchOutputPath').value=result.path;
      else if(result.browser){$('batchOutputPath').focus();error('В браузерном режиме введите полный путь к папке. В Windows-приложении доступен выбор мышью.');}refreshLocks();
    }catch(e){error(e.message);}
  };
  $('batchOutputPath').oninput=refreshLocks;
  $('openBatchFolder').onclick=async()=>{try{await api('/api/folder',{path:$('batchOutputPath').value.trim()});}catch(e){error(e.message);}};
  $('selectAllButton').onclick=()=>{batch.items.forEach(item=>item.selected=ready(item));renderList();};
  $('swapDetailButton').onclick=()=>{if(current())swap(current());};
  for(let i=0;i<2;i++)$(i===0?'batchModelSelect':'batchHandsSelect').onchange=e=>{
    if(locked()||!current())return;remember();const item=current();
    const chosen=item.candidates.find(c=>c.id===e.target.value)||null;
    if(chosen&&item.snapshot.sources[1-i]?.id===chosen.id)item.snapshot.sources[1-i]=null;
    item.snapshot.sources[i]=chosen;item.snapshot.settings.trims=[null,null];changedItem(item);
  };
  $('generalSettingsButton').onclick=()=>{
    if(locked()||!batch.items.length)return;
    openAndView(current()?.id||batch.items[0].id);
    $('batchDetailNote').textContent='Задайте параметры ниже и нажмите «Применить к остальным роликам». Будут скопированы режим, переход, кадрирование, удаление пауз и битрейт для всех товаров очереди.';
  };
  $('applySettingsButton').onclick=()=>{
    if(locked()||!current())return;remember();const settings=structuredClone(current().snapshot.settings);
    const others=batch.items.filter(item=>item.id!==batch.active);
    for(const item of others){const trims=item.snapshot.settings.trims||[null,null];item.snapshot.settings={...structuredClone(settings),trims};item.snapshot.preview=null;item.snapshot.stale=!!item.snapshot.result;item.status='changed';item.error=null;}
    batch.loading=true;loadEditor(current().snapshot);batch.loading=false;renderList();
    $('batchDetailNote').textContent=`Настройки применены к остальным роликам: ${others.length}. Масштаб и форматы скопированы; ручные границы каждого товара сохранены.`;
  };
  $('batchRenderButton').onclick=exportSelected;
  $('batchCancelButton').onclick=async()=>{
    try{await api(`/api/batches/${batch.id}/cancel`,{});$('batchCancelButton').disabled=true;}catch(e){error(e.message);}
  };
  api('/api/config').then(config=>{batch.native=config.native;$('batchOutputPath').value=config.output;refreshLocks();}).catch(e=>error(e.message));
  async function pollShell(){
    try{
      if(!locked()){
        const task=await api('/api/shell/import',{});
        if((task.command||task.id)&&state.backgroundMode)await window.batchWorkspace?.activateEditor();
        if(task.command)await window.batchWorkspace?.shellCommand(task.command);
        if(task.id){
          switchMode(true);beginImport();batch.importId=task.id;pollImport();
        }
      }
    }catch(e){switchMode(true);error(e.message);}
    finally{setTimeout(pollShell,1500);}
  }
  pollShell();
})();
