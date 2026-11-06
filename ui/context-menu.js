/* One accessible menu, with commands scoped to the right-clicked product or frame. */
(() => {
  const B=batchController,W=batchWorkspace,menu=document.createElement('div');menu.id='contextMenu';menu.className='context-menu';menu.setAttribute('role','menu');menu.hidden=true;document.body.append(menu);
  let origin=null,stack=[],anchor={x:0,y:0};
  const action=(label,run,disabled=false)=>({label,run,disabled}),group=(label,children)=>({label,children});
  function close(restore=false){menu.hidden=true;menu.replaceChildren();if(restore)origin?.focus({preventScroll:true});}
  function paint(entries){
    menu.replaceChildren();
    if(stack.length){const back=document.createElement('button');back.type='button';back.setAttribute('role','menuitem');back.textContent='Назад';back.onclick=()=>paint(stack.pop());menu.append(back);}
    for(const entry of entries){
      if(entry===null){const line=document.createElement('div');line.className='menu-separator';line.setAttribute('role','separator');menu.append(line);continue;}
      const button=document.createElement('button');button.type='button';button.setAttribute('role','menuitem');button.textContent=entry.label;button.disabled=entry.disabled;
      if(entry.children){button.className='has-submenu';button.setAttribute('aria-haspopup','menu');}
      button.onclick=async()=>{
        if(entry.children){stack.push(entries);paint(entry.children);return;}
        close();try{await entry.run();}catch(error){showError(error.message);W.notify(error.message);}
      };menu.append(button);
    }
    menu.hidden=false;menu.style.left=Math.max(6,Math.min(anchor.x,innerWidth-menu.offsetWidth-6))+'px';menu.style.top=Math.max(6,Math.min(anchor.y,innerHeight-menu.offsetHeight-6))+'px';menu.querySelector('button:not(:disabled)')?.focus({preventScroll:true});
  }
  async function copyText(text){try{await navigator.clipboard.writeText(text);}catch{const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();}W.notify('Скопировано');}
  const selected=()=>B.items.filter(item=>item.selected).map(item=>item.id);
  const sourceFolder=async(item,slot,copy=false)=>{const source=item.snapshot.sources[slot];if(!source)return;const data=await api('/api/source-location',{id:source.id,open:!copy});if(copy)await copyText(data.path);};
  const resultFolder=async item=>{const result=item.snapshot.result;await api('/api/folder',{path:result?result.output.replace(/[\\/][^\\/]+$/,''):$('batchOutputPath').value});};
  function reset(item,keys){B.apply(editorDefaults(),[item.id],keys);}
  function rowMenu(item){
    const edit=B.locked,hasPair=B.ready(item);
    return [
      action('Открыть превью',()=>B.open(item.id),edit),
      action(item.selected?'Исключить из экспорта':'Включить в экспорт',()=>{if(B.locked)return;item.selected=!item.selected;B.render();},edit),
      action('Модель ↔ Руки',()=>B.swap(item.id),edit),null,
      action('Скопировать настройки',()=>W.copy(item)),action('Вставить настройки…',()=>W.paste(item),edit||!W.copied),
      action('Применить настройки выделенным…',()=>{B.remember();return W.chooseFields(item.snapshot.settings,selected());},edit||!selected().length),
      action('Сохранить как пресет…',()=>{B.open(item.id);return W.savePreset();},edit),
      group('Применить пресет',W.presets.length?W.presets.map(p=>action(p.name,()=>W.apply(p.settings,[item.id]),edit)):[action('Пресетов пока нет',()=>{},true)]),
      group('Сбросить',[action('Положение кадра',()=>reset(item,['crops','crops_x']),edit),action('Масштаб',()=>reset(item,['zooms']),edit),action('Монтажные границы',()=>reset(item,['trims']),edit),action('Все настройки',()=>reset(item,Object.keys(editorDefaults())),edit)]),null,
      group('Переместить',[action('В начало',()=>B.move(item.id,'first'),edit),action('Выше',()=>B.move(item.id,-1),edit),action('Ниже',()=>B.move(item.id,1),edit),action('В конец',()=>B.move(item.id,'last'),edit)]),
      action('Экспортировать этот товар',()=>B.export({ids:[item.id],repeat:!!item.snapshot.result}),edit||!hasPair),
      action('Экспортировать выделенные',()=>B.export({ids:selected(),repeat:B.items.some(i=>i.selected&&i.snapshot.result)}),edit||!selected().length),
      action('Повторить только ошибочные',()=>B.export({ids:B.items.filter(i=>i.status==='error').map(i=>i.id),repeat:true}),edit||!B.items.some(i=>i.status==='error')),
      action('Экспортировать только новые',()=>W.exportNew(B.items.filter(i=>i.selected)),edit),
      action('Проверить исходники',()=>W.verify([item]),edit),null,
      group('Открыть папку',[action('Исходник модели',()=>sourceFolder(item,0),!item.snapshot.sources[0]),action('Исходник рук',()=>sourceFolder(item,1),!item.snapshot.sources[1]),action('Результаты товара',()=>resultFolder(item))]),
      group('Скопировать',[action('Артикул',()=>copyText(item.name.split(/[\\/]/).at(-1))),action('Путь модели',()=>sourceFolder(item,0,true),!item.snapshot.sources[0]),action('Путь рук',()=>sourceFolder(item,1,true),!item.snapshot.sources[1]),action('Путь результата',()=>copyText(item.snapshot.result?.output||''),!item.snapshot.result)]),
      action('Отчёт обработки и проверка видео',async()=>{const result=item.snapshot.result;if(!result){W.report('Отчёт','Товар ещё не экспортирован.');return;}const log=await api('/api/job-log',{id:result.id});W.report('Отчёт · '+item.name,JSON.stringify(log,null,2));}),null,
      action('Убрать из очереди',()=>B.remove(item.id),edit)
    ];
  }
  function cursor(){
    const player=$('mainVideo'),raw=player.dataset.sourceSlot;
    if(raw!==undefined)return {slot:+raw,time:player.currentTime};
    const plan=timelineEditor.plan();if(!plan)return null;let frame=Math.floor(player.currentTime*30);
    for(const segment of plan.segments){if(frame<segment.frames)return {slot:segment.source,time:segment.start+(segment.loop?0:frame*1.25/30)};frame-=segment.frames;}return null;
  }
  function mark(edge){const point=cursor(),plan=timelineEditor.plan();if(!point||!plan)return;const range=[...plan.content_bounds[point.slot]];range[edge]=Math.min(state.sources[point.slot].info.duration,point.time);timelineEditor.setTrim(point.slot,range);}
  let loopCheck=null;
  $('mainVideo').addEventListener('loadstart',()=>loopCheck=null);
  $('mainVideo').addEventListener('timeupdate',()=>{if(loopCheck&&$('mainVideo').currentTime>=loopCheck.end)$('mainVideo').currentTime=loopCheck.start;});
  async function loopSeam(){const plan=timelineEditor.plan();if(!plan)return;const boundaries=[plan.model_frames/30,(plan.model_frames+plan.hands_frames)/30],now=$('mainVideo').currentTime,boundary=boundaries.reduce((a,b)=>Math.abs(b-now)<Math.abs(a-now)?b:a);loopCheck={start:Math.max(0,boundary-1),end:Math.min($('mainVideo').duration,boundary+1)};$('mainVideo').currentTime=loopCheck.start;await $('mainVideo').play();}
  const capture=()=>{const canvas=document.createElement('canvas'),source=livePreview.active?document.querySelector('.live-preview-canvas'):$('mainVideo');canvas.width=source.videoWidth||source.width;canvas.height=source.videoHeight||source.height;if(!canvas.width)throw new Error('Дождитесь кадра видео.');canvas.getContext('2d').drawImage(source,0,0,canvas.width,canvas.height);return canvas;};
  async function saveFrame(){const result=await api('/api/frame',{data:capture().toDataURL('image/png')});if(result.download){const link=document.createElement('a');link.href=result.download;link.download='кадр.png';link.click();}if(result.saved)W.notify('Кадр сохранён');}
  async function compare(){
    const point=cursor();if(!point)return;const image=capture().toDataURL(),video=document.createElement('video');video.controls=true;video.muted=true;video.playsInline=true;video.src=state.sources[point.slot].preview;video.onloadedmetadata=()=>{video.currentTime=point.time;video.pause();};
    W.report('Исходник и кадрирование','');const dialog=$('workspaceDialog'),layout=document.createElement('div');layout.className='source-comparison';for(const [name,media]of [['Исходник',video],['Кадрирование',Object.assign(document.createElement('img'),{src:image,alt:'Текущий кадр с настройками'})]]){const cell=document.createElement('div'),label=document.createElement('p');label.textContent=name;cell.append(label,media);layout.append(cell);}dialog.querySelector('pre').replaceWith(layout);dialog.addEventListener('close',()=>video.pause(),{once:true});
  }
  function playerMenu(){
    const player=$('mainVideo'),point=cursor(),edit=B.locked,plan=timelineEditor.plan();
    return [action(player.paused?'Воспроизвести':'Пауза',()=>{loopCheck=null;return player.paused?player.play():player.pause();}),
      action('Предыдущий кадр',()=>{loopCheck=null;player.pause();player.currentTime=Math.max(0,player.currentTime-1/30);}),action('Следующий кадр',()=>{loopCheck=null;player.pause();player.currentTime=Math.min(player.duration-1/30,player.currentTime+1/30);}),null,
      action('Установить начало текущего плана здесь',()=>mark(0),edit||!plan),action('Установить конец текущего плана здесь',()=>mark(1),edit||!plan),action('Вернуть автоматические границы',()=>timelineEditor.reset(),edit||!plan),
      action(loopCheck?'Отключить повтор склейки':'Повторять участок вокруг склейки',()=>{if(loopCheck){loopCheck=null;return;}return loopSeam();},!plan),null,
      group('Формат просмотра',selectedFormats().map(id=>action(`${formatNames[id]} · ${formatSpecs[id].join(' × ')}`,()=>{$('outputFormat').value=id;$('outputFormat').dispatchEvent(new Event('change'));},edit))),
      action('Сбросить положение и масштаб плана',()=>{if(point)$('resetCrop'+point.slot).click();},edit||!point),action('Сравнить с исходником',compare,!point),action('Сохранить текущий кадр PNG',saveFrame,player.readyState<2)
    ];
  }
  function backgroundMenu(){return [action('Выбрать все готовые',()=>B.selectAll(true),B.locked),action('Снять выделение',()=>B.selectAll(false),B.locked),action('Выделить ошибочные',()=>{if(B.locked)return;for(const item of B.items)item.selected=item.status==='error';B.render();},B.locked),action('Применить текущие настройки выделенным…',()=>W.chooseFields(editorSnapshot().settings,selected()),B.locked),action('Проверить очередь',()=>W.verify(),B.locked),action('Экспортировать только новые',()=>W.exportNew(),B.locked),action('Сохранить пакет отдельно',()=>W.archive()),action('Открыть сохранённый пакет…',()=>W.history(),B.locked)];}
  document.addEventListener('contextmenu',event=>{
    const row=event.target.closest('.batch-row'),viewer=event.target.closest('#viewer,.timeline'),queue=event.target.closest('#batchList');if(!row&&!viewer&&!queue)return;
    if(event.target.matches('input[type=number],input[type=text],textarea'))return;
    event.preventDefault();origin=document.activeElement;anchor={x:event.clientX,y:event.clientY};stack=[];
    const item=row&&B.items.find(item=>item.id===row.dataset.id);paint(item?rowMenu(item):viewer?playerMenu():backgroundMenu());
  });
  menu.addEventListener('keydown',event=>{const buttons=[...menu.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(document.activeElement);if(event.key==='Escape'){event.preventDefault();close(true);}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}else if(event.key==='ArrowRight'&&document.activeElement.getAttribute('aria-haspopup')){event.preventDefault();document.activeElement.click();}else if(event.key==='ArrowLeft'&&stack.length){event.preventDefault();paint(stack.pop());}else if(event.key==='Tab')close();});
  document.addEventListener('pointerdown',event=>{if(!menu.contains(event.target))close();});window.addEventListener('resize',()=>close());
})();
