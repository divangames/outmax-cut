/* Render framing from the uncut source proxies at the montage's current time. */
(() => {
  const player=$('mainVideo'),stage=$('viewer'),canvas=document.createElement('canvas');
  canvas.className='live-preview-canvas';canvas.hidden=true;canvas.setAttribute('aria-hidden','true');
  stage.insertBefore(canvas,player);
  const context=canvas.getContext('2d'),buffers=[document.createElement('canvas'),document.createElement('canvas')];
  const sourceDrawers=[0,1].map(slot=>{
    const video=$('sourceVideo'+slot),surface=document.createElement('canvas');
    surface.className='source-framing-canvas';surface.hidden=true;surface.setAttribute('aria-hidden','true');video.before(surface);
    let scheduled=false;
    const draw=()=>{
      if(video.readyState<2||!state.sources[slot]){surface.hidden=true;video.classList.remove('live-frame');return;}
      const [w,h]=formatSpecs[$('outputFormat').value],scale=160/Math.max(w,h);
      cropped(video,slot,surface,Math.max(2,Math.floor(w*scale/2)*2),Math.max(2,Math.floor(h*scale/2)*2));
      surface.hidden=false;video.classList.add('live-frame');
      if(!video.paused&&!scheduled){scheduled=true;video.requestVideoFrameCallback(()=>{scheduled=false;draw();});}
    };
    for(const name of ['loadeddata','seeked','play','emptied'])video.addEventListener(name,draw);
    return draw;
  });
  const decoders=new Map();
  let report=null,sourceKey='',active=false,revision=0,editVersion=0,drawing=false,dirty=false,animation=0,frozenTime=null;
  const key=()=>state.sources.map(source=>source?.id||'').join('|');
  function stop(reset=false){
    active=false;revision++;frozenTime=null;cancelAnimationFrame(animation);canvas.hidden=true;player.classList.remove('live-frame');
    for(const video of decoders.values())video.pause();
    if(reset){report=null;sourceKey='';for(const video of decoders.values()){video.removeAttribute('src');video.load();}decoders.clear();}
  }
  function sample(index){
    let offset=0;
    for(const segment of report.segments){
      if(index<offset+segment.frames)return {slot:segment.source,time:segment.start+(segment.loop?0:(index-offset)*(segment.speed||report.speed||1.25)/30),moving:!segment.loop};
      offset+=segment.frames;
    }
    const first=report.segments[0];return {slot:first.source,time:first.start,moving:false};
  }
  function plan(){
    const index=Math.max(0,Math.min(report.frames-1,Math.floor((frozenTime??player.currentTime)*30+1e-6)));
    let incoming=sample(index);
    if(index===report.frames-1)return {layers:[sample(0)],fraction:0,blur:0};
    const model=report.model_frames,hands=report.hands_frames;
    for(const [boundary,length,kind] of [[model,Math.min(15,hands),$('transition').value],[model+hands,18,'lens']]){
      if(kind==='cut'||index<boundary||index>=boundary+length)continue;
      const previous=sample(boundary-1),step=boundary>=2&&sample(boundary-2).slot===previous.slot?Math.max(0,previous.time-sample(boundary-2).time):0;
      const limit=report.content_bounds[previous.slot][1]-1/30;
      const outgoing={slot:previous.slot,time:Math.min(limit,previous.time+(index-boundary+1)*step),moving:previous.time+(index-boundary+1)*step<limit};
      const fraction=length===1?1:(index-boundary)/(length-1);
      return {layers:[outgoing,incoming],fraction:fraction*fraction*(3-2*fraction),blur:kind==='lens'?22*Math.sin(Math.PI*fraction)**2:0};
    }
    return {layers:[incoming],fraction:0,blur:0};
  }
  function decoder(slot){
    const source=state.sources[slot];
    if(!source)return null;
    if(!decoders.has(source.id)){
      const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';video.src=source.preview;
      decoders.set(source.id,video);
    }
    return decoders.get(source.id);
  }
  function event(video,name){
    return new Promise(resolve=>{
      const finish=()=>{clearTimeout(timeout);video.removeEventListener(name,finish);video.removeEventListener('error',finish);resolve();};
      const timeout=setTimeout(finish,1000);video.addEventListener(name,finish,{once:true});video.addEventListener('error',finish,{once:true});
    });
  }
  async function frame(layer){
    const video=decoder(layer.slot);if(!video)return null;
    if(video.readyState<1)await event(video,'loadedmetadata');
    if(video.readyState<1)return null;
    const value=layer.time*30,base=Math.floor(value),fraction=value-base;
    const rounded=base+(fraction>.5||(fraction===.5&&base%2)?1:0);
    const time=Math.max(0,Math.min((rounded+.001)/30,video.duration-1/30));
    const moving=!player.paused&&layer.moving;
    if(!moving)video.pause();
    if(Math.abs(video.currentTime-time)>(moving?.08:1/120)){
      const seek=event(video,'seeked');video.currentTime=time;await seek;
    }else if(video.seeking)await event(video,'seeked');
    if(video.readyState<2)await event(video,'loadeddata');
    if(moving){video.playbackRate=report.speed||1.25;video.play().catch(()=>{});}
    return video.readyState>=2?video:null;
  }
  function cropped(video,slot,buffer,width,height){
    if(buffer.width!==width||buffer.height!==height){buffer.width=width;buffer.height=height;}
    const ctx=buffer.getContext('2d');
    ctx.drawImage(video,...framingBox(slot,video.videoWidth,video.videoHeight,width,height),0,0,width,height);
  }
  async function draw(){
    if(drawing||!active)return;
    drawing=true;
    do{
      dirty=false;const version=revision,rawSlot=player.dataset.sourceSlot;
      const current=rawSlot===undefined?plan():{layers:[{slot:+rawSlot}],fraction:0,blur:0};
      const videos=rawSlot===undefined?await Promise.all(current.layers.map(frame)):[player.readyState>=2?player:null];
      if(!active||version!==revision||videos.some(video=>!video))continue;
      const [w,h]=formatSpecs[$('outputFormat').value],scale=Math.min(1,480/Math.max(w,h)),width=Math.max(2,Math.floor(w*scale/2)*2),height=Math.max(2,Math.floor(h*scale/2)*2);
      if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
      videos.forEach((video,i)=>cropped(video,current.layers[i].slot,buffers[i],width,height));
      context.globalAlpha=1;context.filter='none';context.drawImage(buffers[0],0,0);
      if(videos.length===2){context.globalAlpha=current.fraction;context.drawImage(buffers[1],0,0);context.globalAlpha=1;}
      if(current.blur>.2){
        const copy=buffers[0].getContext('2d');copy.drawImage(canvas,0,0);context.filter=`blur(${current.blur*Math.min(width,height)/1080}px)`;context.drawImage(buffers[0],0,0);context.filter='none';
      }
      canvas.hidden=false;player.classList.add('live-frame');canvas.dataset.revision=String(editVersion);
    }while(dirty&&active);
    drawing=false;
    if(active&&!player.paused)animation=requestAnimationFrame(request);
  }
  function request(){if(!active)return;dirty=true;draw();}
  function edit(){
    sourceDrawers.forEach(draw=>draw());
    const currentKey=key();
    const selected=$('previewTab').getAttribute('aria-selected')==='true'?state.preview:$('resultTab').getAttribute('aria-selected')==='true'?resultVariant():null;
    if(selected?.report?.segments){report=selected.report;sourceKey=currentKey;}
    if(player.dataset.sourceSlot===undefined&&(!report||sourceKey!==currentKey))return;
    if(report)report=window.timelineEditor?.plan(report)||report;
    active=true;editVersion++;revision++;stage.style.setProperty('--video-ratio',formatSpecs[$('outputFormat').value][0]/formatSpecs[$('outputFormat').value][1]);request();
  }
  window.livePreview={edit,stop,get active(){return active;},get version(){return editVersion;},suspend(time){frozenTime=time;revision++;for(const video of decoders.values())video.pause();},finish(version){frozenTime=null;if(version===editVersion)stop();else request();}};
  $('outputFormat').addEventListener('change',()=>sourceDrawers.forEach(draw=>draw()));
  for(const name of ['loadeddata','seeked','timeupdate','play','pause'])player.addEventListener(name,()=>{if(active){revision++;request();}else if(player.dataset.sourceSlot!==undefined&&player.readyState>=2)edit();});
})();
