/* Manual source in/out points stay local to one product. */
(() => {
  const track=document.querySelector('.timeline-track'),timeline=document.querySelector('.timeline');
  let trims=[null,null],base=null,locked=false;
  const handles=[0,1].map(slot=>{
    const button=document.createElement('button');button.className='cut-handle';button.type='button';button.dataset.slot=slot;
    button.setAttribute('role','slider');button.setAttribute('aria-label',slot?'Склейка рук с возвратом к началу':'Склейка модели с руками');button.title=button.getAttribute('aria-label');button.disabled=true;track.append(button);return button;
  });
  const details=document.createElement('details');details.className='trim-settings';
  details.innerHTML='<summary>Точки монтажа <span id="trimMode">Автоматически</span></summary><p>Перетащите границы на шкале или задайте время в исходниках. Скорость ×1,25. Ручные границы относятся только к этому товару.</p><div class="trim-fields"></div><button id="resetTrims" class="text-button"><svg aria-hidden="true"><use href="#i-reset"/></svg> Автоматические границы</button><p id="trimError" role="alert" hidden></p>';
  timeline.append(details);
  for(let slot=0;slot<2;slot++){
    const group=document.createElement('fieldset');group.innerHTML=`<legend>${slot?'Руки':'Модель'}</legend><label>Начало, с<input id="trimStart${slot}" type="number" min="0" step="0.033333" aria-label="Начало ${slot?'рук':'модели'}, секунды"></label><label>Конец, с<input id="trimEnd${slot}" type="number" min="0" step="0.033333" aria-label="Конец ${slot?'рук':'модели'}, секунды"></label><button type="button" class="icon-button reset-trim" title="Автоматические границы ${slot?'рук':'модели'}" aria-label="Сбросить границы ${slot?'рук':'модели'}"><svg><use href="#i-reset"/></svg></button>`;
    details.querySelector('.trim-fields').append(group);
    group.querySelectorAll('input').forEach(input=>input.step='any');
    group.querySelector('button').onclick=()=>{trims[slot]=null;changed();};
    for(const edge of ['Start','End'])$('trim'+edge+slot).onchange=()=>setTrim(slot,[+$('trimStart'+slot).value,+$('trimEnd'+slot).value]);
  }
  const round=value=>{const base=Math.floor(value),fraction=value-base;return base+(fraction>.5||(Math.abs(fraction-.5)<1e-9&&base%2)?1:0);};
  function plan(report=base){
    if(!report)return null;
    const bounds=(report.auto_bounds||report.content_bounds).map((range,s)=>trims[s]||range),segments=[];
    for(let s=0;s<2;s++){
      const selected=$('mode').value==='smart'?(report.activity_ranges?.[s]||report.segments.filter(segment=>segment.source===s&&!segment.loop).map(segment=>[segment.start,segment.end])):[bounds[s]];
      let ranges=selected.map(([a,b])=>[Math.max(a,bounds[s][0]),Math.min(b,bounds[s][1])]).filter(([a,b])=>b-a>=1/30);
      if(!ranges.length)ranges=[[...bounds[s]]];
      ranges[0][0]=bounds[s][0];ranges[ranges.length-1][1]=bounds[s][1];
      for(const [start,end] of ranges)segments.push({source:s,start,end,speed:1.25,frames:Math.max(1,round((end-start)/1.25*30)),label:s?'Руки':'Модель'});
    }
    segments.push({source:0,start:segments[0].start,end:segments[0].start,frames:18,loop:true,label:'Пустой фон перед появлением модели'});
    const model_frames=segments.filter(s=>s.source===0&&!s.loop).reduce((n,s)=>n+s.frames,0),hands_frames=segments.filter(s=>s.source===1).reduce((n,s)=>n+s.frames,0),frames=model_frames+hands_frames+18;
    return {...report,segments,content_bounds:bounds,model_frames,hands_frames,frames,result:{...report.result,duration:frames/30}};
  }
  function paint(){
    const report=plan();
    handles.forEach(button=>button.disabled=locked||!report||state.sources.some(source=>!source));
    details.querySelectorAll('input,button').forEach(input=>input.disabled=locked||!report||state.sources.some(source=>!source));
    $('trimMode').textContent=trims.some(Boolean)?'Вручную':'Автоматически';
    if(!report)return;
    const values=[report.model_frames,report.hands_frames,18],clips=[document.querySelector('.clip-model'),document.querySelector('.clip-hands'),document.querySelector('.clip-end')];
    clips.forEach((clip,i)=>{clip.style.flex=values[i];if(i<2)clip.querySelector('span').textContent=(values[i]/30).toFixed(2).replace('.',',')+' с';});
    handles.forEach((button,s)=>{
      button.style.left=(s===0?report.model_frames:report.model_frames+report.hands_frames)/report.frames*100+'%';
      button.setAttribute('aria-valuemin',report.content_bounds[s][0]+1/24);button.setAttribute('aria-valuemax',state.sources[s]?.info.duration||0);button.setAttribute('aria-valuenow',report.content_bounds[s][1]);button.setAttribute('aria-valuetext',report.content_bounds[s][1].toFixed(2)+' с исходника');
      $('trimStart'+s).value=report.content_bounds[s][0].toFixed(3);$('trimEnd'+s).value=report.content_bounds[s][1].toFixed(3);
      $('trimStart'+s).max=state.sources[s]?.info.duration||0;$('trimEnd'+s).max=state.sources[s]?.info.duration||0;
    });
    document.querySelector('.timeline-label>span').textContent=report.result.duration.toFixed(2)+' с · ×1,25';
    const stamp=seconds=>Math.floor(seconds/60)+':'+String(Math.floor(seconds)%60).padStart(2,'0');
    const ticks=document.querySelector('.timeline-times');ticks.firstElementChild.textContent='0:00';ticks.children[1].textContent=stamp(report.result.duration/2);ticks.lastElementChild.textContent=stamp(Math.ceil(report.result.duration));
    timeline.setAttribute('aria-label','Монтаж: модель '+(report.model_frames/30).toFixed(2)+' с, руки '+(report.hands_frames/30).toFixed(2)+' с, возврат 0,6 с');
  }
  function changed(){paint();markChanged();$('trimError').hidden=true;}
  function setTrim(slot,range){
    const duration=state.sources[slot]?.info.duration;
    if(locked||!base)return;
    if(!range.every(Number.isFinite)||range[0]<0||range[1]>duration+.001||range[1]-range[0]<1/24){$('trimError').textContent='Границы должны находиться внутри исходника. Оставьте хотя бы один кадр.';$('trimError').hidden=false;return;}
    trims[slot]=range;changed();
  }
  handles.forEach((button,slot)=>{
    let drag=null;
    button.onpointerdown=event=>{
      if(button.disabled||event.button!==0)return;event.preventDefault();button.setPointerCapture(event.pointerId);
      const report=plan();drag={x:event.clientX,frames:report.frames,width:track.getBoundingClientRect().width,range:[...report.content_bounds[slot]]};
    };
    button.onpointermove=event=>{
      if(!drag)return;
      const end=Math.max(drag.range[0]+1/24,Math.min(state.sources[slot].info.duration,drag.range[1]+Math.round((event.clientX-drag.x)/drag.width*drag.frames)*1.25/30));
      setTrim(slot,[drag.range[0],end]);
    };
    button.onpointerup=button.onpointercancel=()=>{drag=null;};
    button.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)||button.disabled)return;
      event.preventDefault();const range=[...plan().content_bounds[slot]],direction=['ArrowLeft','ArrowDown'].includes(event.key)?-1:1;
      range[1]=event.key==='Home'?range[0]+1/24:event.key==='End'?state.sources[slot].info.duration:Math.max(range[0]+1/24,Math.min(state.sources[slot].info.duration,range[1]+direction*(event.shiftKey?10:1)/24));setTrim(slot,range);
    };
  });
  $('resetTrims').onclick=()=>{trims=[null,null];changed();};
  window.timelineEditor={get trims(){return structuredClone(trims);},plan,setTrim,reset(slot){if(locked)return;if(slot===undefined)trims=[null,null];else trims[slot]=null;changed();},load(value){trims=structuredClone(value);base=null;paint();},sourceChanged(slot){trims[slot]=null;base=null;paint();},acceptReport(report){base=report;paint();},refreshLocks(value){locked=value;paint();}};
  paint();
})();
