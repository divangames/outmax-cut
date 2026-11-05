/* Latest settings win. Preview never owns editor locks or export progress. */
(() => {
  let generation=0,timer=null,job=null;
  const status=message=>{$('autoPreviewStatus').textContent=message;};
  function cancel(){
    generation++;clearTimeout(timer);timer=null;
    if(job){const id=job;job=null;api(`/api/jobs/${id}/cancel`,{}).catch(()=>{});}
    controller.loading=false;
  }
  function schedule(delay=450){
    cancel();
    if(state.sources.some(source=>!source)){
      status('Превью появится автоматически после добавления двух видео.');return;
    }
    if(state.result&&!state.stale){status('Результат готов в полном качестве.');return;}
    if(state.preview){status('Превью готово · 30 кадров/с');return;}
    if(state.running||state.externalLocked||state.uploading.some(Boolean))return;
    status('Обновляем превью…');
    const version=generation;
    timer=setTimeout(()=>render(version),delay);
  }
  async function render(version){
    if(version!==generation||state.running||state.externalLocked||state.uploading.some(Boolean))return;
    controller.loading=true;
    try{
      const snapshot=editorSnapshot();
      const task=await api('/api/preview',{sources:snapshot.sources.map(source=>source.id),...snapshot.settings});
      if(version!==generation){api(`/api/jobs/${task.id}/cancel`,{}).catch(()=>{});return;}
      job=task.id;
      for(;;){
        const result=await api(`/api/jobs/${task.id}`);
        if(version!==generation)return;
        if(result.status==='done'){
          job=null;state.preview=result;$('previewTab').disabled=false;
          status(task.cached?'Превью из кэша · 30 кадров/с':'Превью готово · 30 кадров/с');
          const player=$('mainVideo'),liveVersion=window.livePreview?.version;
          const playback=player.getAttribute('src')?.startsWith('/result/')?{time:player.currentTime,paused:player.paused,onRestored:()=>window.livePreview?.finish(liveVersion)}:null;
          if(playback)window.livePreview?.suspend(playback.time);
          if(player.dataset.userSourceView!=='true')selectTab(false,true,playback);
          window.batchController?.previewCompleted();
          return;
        }
        if(result.status!=='running'&&result.status!=='queued'){
          job=null;status(result.status==='error'?'Не удалось обновить превью: '+result.error:'Обновление превью остановлено.');return;
        }
        status(`Превью · ${result.progress}% · ${result.stage}`);
        await new Promise(resolve=>setTimeout(resolve,250));
      }
    }catch(error){
      if(version===generation)status('Не удалось загрузить превью: '+error.message);
    }finally{
      if(version===generation)controller.loading=false;
    }
  }
  const controller=window.autoPreview={schedule,cancel,loading:false};
  // Multiple players decoding at once can starve the main preview on modest PCs.
  const players=[$('mainVideo'),$('sourceVideo0'),$('sourceVideo1')];
  players.forEach(player=>player.addEventListener('play',()=>players.filter(other=>other!==player).forEach(other=>other.pause())));
  preferencesReady.then(()=>schedule(100));
})();
