/* Explicit zoom and consistent, accessible reset controls. */
(() => {
  const icon='<svg aria-hidden="true"><use href="#i-reset"/></svg>';
  function resetButton(label,action){const button=document.createElement('button');button.type='button';button.className='icon-button setting-reset';button.title=label;button.setAttribute('aria-label',label);button.innerHTML=icon;button.onclick=event=>{event.preventDefault();action();};return button;}
  for(let slot=0;slot<2;slot++){
    const label=document.createElement('label');label.htmlFor='zoom'+slot;label.innerHTML=`Масштаб <output id="zoomValue${slot}">100%</output>`;
    const slider=document.createElement('input');slider.id='zoom'+slot;slider.type='range';slider.min=100;slider.max=300;slider.step=1;slider.value=100;slider.setAttribute('aria-label','Масштаб '+(slot?'рук':'модели'));
    $('resetCrop'+slot).before(label,slider);
    slider.oninput=()=>{$('zoomValue'+slot).textContent=slider.value+'%';markChanged();};
    $('resetCrop'+slot).innerHTML=icon;$('resetCrop'+slot).classList.add('icon-button');$('resetCrop'+slot).title='Сбросить положение и масштаб '+(slot?'рук':'модели');$('resetCrop'+slot).setAttribute('aria-label',$('resetCrop'+slot).title);
  }
  const defaults={mode:'smart',transition:'lens',sensitivity:40,bitrate:2500,outputFormat:'standard',cropX0:50,cropX1:50,crop0:82.4,crop1:50,zoom0:100,zoom1:100};
  function installResets(){
    for(const [id,value] of Object.entries(defaults)){
      const input=$(id),label=document.querySelector(`label[for="${id}"]`);if(!label||label.querySelector('.setting-reset'))continue;
      label.append(resetButton('Сбросить: '+(input.getAttribute('aria-label')||label.childNodes[0].textContent.trim()),()=>{
        if(id==='outputFormat'&&!selectedFormats().includes('standard'))syncFormats([...selectedFormats(),'standard']);
        input.value=value;input.dispatchEvent(new Event(input.type==='range'?'input':'change',{bubbles:true}));
        if(input.type==='range')input.dispatchEvent(new Event('change',{bubbles:true}));
      }));
    }
    const legend=$('exportFormats').querySelector('legend');if(legend&&!legend.querySelector('button'))legend.append(resetButton('Сбросить разрешения экспорта',()=>changeExportFormats(['standard'])));
  }
  const preferenceLabel=$('saveProcessingLog').closest('label');preferenceLabel.append(resetButton('Сбросить сохранение лога',()=>{$('saveProcessingLog').checked=false;$('saveProcessingLog').dispatchEvent(new Event('change'));}));
  const folderLabel=document.querySelector('label[for="batchOutputPath"]');let defaultOutput='';preferencesReady.then(()=>api('/api/config')).then(config=>{defaultOutput=config.output;});
  folderLabel.append(resetButton('Сбросить папку экспорта',()=>{$('batchOutputPath').value=defaultOutput;$('batchOutputPath').dispatchEvent(new Event('input',{bubbles:true}));}));
  window.editorExtras={installResets,refreshLocks(locked){document.querySelectorAll('.setting-reset').forEach(button=>button.disabled=locked);$('saveFormats').disabled=locked;$('addFormat').disabled=locked;$('formatRows').querySelectorAll('input,button').forEach(input=>input.disabled=locked);}};
  installResets();refresh();
})();
