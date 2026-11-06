/* Global format sizes are saved once; each export freezes its catalog. */
(() => {
  const presets=structuredClone(formatCatalog),dialog=$('settingsDialog');
  const section=document.createElement('section');section.className='format-settings';
  section.innerHTML='<h3>Размеры видео</h3><p>Стандартные форматы сохраняют пропорции. Для своего формата задайте название, ширину и высоту. Размеры — чётные числа от 32 до 8192 пикселей.</p><div id="formatRows"></div><div class="format-settings-actions"><button id="addFormat" class="secondary-button">Добавить свой размер</button><button id="saveFormats" class="primary-button">Сохранить размеры</button></div><p id="formatSaveStatus" role="status"></p>';
  $('settingsError').before(section);
  const gcd=(a,b)=>b?gcd(b,a%b):a;
  function rows(){
    $('formatRows').replaceChildren();formatCatalog.forEach(item=>addRow(item));
    $('formatSaveStatus').textContent='';
  }
  function addRow(item){
    const preset=presets.find(p=>p.id===item.id),row=document.createElement('div');row.className='format-row';row.dataset.id=item.id;
    row.innerHTML='<label class="format-name-label">Название<input class="format-name" maxlength="48" required></label><label>Ширина<input class="format-width" type="number" min="32" max="8192" step="2" required></label><span class="format-times" aria-hidden="true">×</span><label>Высота<input class="format-height" type="number" min="32" max="8192" step="2" required></label><div class="format-row-actions"></div>';
    row.querySelector('.format-name').value=item.name;row.querySelector('.format-name').readOnly=!!preset;
    const width=row.querySelector('.format-width'),height=row.querySelector('.format-height');width.value=item.width;height.value=item.height;
    if(preset){
      const divisor=gcd(preset.width,preset.height),unitW=preset.width/divisor,unitH=preset.height/divisor;
      for(const [input,other,unit,otherUnit] of [[width,height,unitW,unitH],[height,width,unitH,unitW]]){
        input.step=unit*2;
        input.min=Math.ceil(32/unit/2)*unit*2;
        input.addEventListener('input',()=>{if(+input.value>=32){const factor=Math.max(2,Math.round(+input.value/unit/2)*2);other.value=factor*otherUnit;}});
        input.addEventListener('change',()=>{if(+input.value>=32){const factor=Math.max(2,Math.round(+input.value/unit/2)*2);input.value=factor*unit;other.value=factor*otherUnit;}});
      }
    }
    const actions=row.querySelector('.format-row-actions'),reset=document.createElement('button');reset.className='icon-button';reset.type='button';
    reset.innerHTML='<svg><use href="#i-reset"/></svg>';reset.title='Сбросить размер '+item.name;reset.setAttribute('aria-label',reset.title);
    reset.onclick=()=>{const original=preset||formatCatalog.find(p=>p.id===item.id)||{width:1080,height:1080,name:item.name};width.value=original.width;height.value=original.height;row.querySelector('.format-name').value=original.name;};actions.append(reset);
    if(!preset){const remove=document.createElement('button');remove.className='icon-button remove-format';remove.type='button';remove.innerHTML='<svg><use href="#i-trash"/></svg>';remove.title='Удалить размер '+item.name;remove.setAttribute('aria-label',remove.title);remove.onclick=()=>row.remove();actions.append(remove);}
    $('formatRows').append(row);
  }
  function renderChoices(formats=selectedFormats(),preview=$('outputFormat').value){
    for(const key of Object.keys(formatSpecs)){delete formatSpecs[key];delete formatNames[key];}
    const field=$('exportFormats');field.replaceChildren();const legend=document.createElement('legend');legend.textContent='Разрешения экспорта';field.append(legend);
    $('outputFormat').replaceChildren();
    for(const item of formatCatalog){
      formatSpecs[item.id]=[item.width,item.height];formatNames[item.id]=item.name;
      const label=document.createElement('label'),input=document.createElement('input'),name=document.createElement('span'),size=document.createElement('span');
      input.type='checkbox';input.value=item.id;input.checked=formats.includes(item.id);name.className='format-choice-name';name.textContent=item.name;size.textContent=`${item.width} × ${item.height}`;label.append(input,name,size);field.append(label);
      $('outputFormat').add(new Option(`${item.name} · ${item.width} × ${item.height}`,item.id));
    }
    const valid=formats.filter(id=>formatSpecs[id]);syncFormats(valid.length?valid:['standard']);
    if(valid.includes(preview))$('outputFormat').value=preview;
    window.editorExtras?.installResets();updateFormat();refresh();
  }
  $('settingsButton').addEventListener('click',rows);
  $('addFormat').onclick=()=>{addRow({id:'custom_'+crypto.randomUUID().replaceAll('-','').slice(0,12),name:'Свой размер '+($('formatRows').children.length-2),width:1080,height:1080});$('formatRows').lastElementChild.querySelector('input').focus();};
  $('saveFormats').onclick=async()=>{
    if(state.running||state.externalLocked)return;
    const inputs=[...$('formatRows').querySelectorAll('input')];if(inputs.some(input=>!input.reportValidity()))return;
    const catalog=[...$('formatRows').children].map(row=>({id:row.dataset.id,name:row.querySelector('.format-name').value.trim(),width:+row.querySelector('.format-width').value,height:+row.querySelector('.format-height').value}));
    const button=$('saveFormats');button.disabled=true;
    try{
      const saved=await api('/api/settings',{video_formats:catalog});formatCatalog=structuredClone(saved.video_formats);
      renderChoices();window.batchController?.formatsChanged();markChanged();
      $('formatSaveStatus').textContent='Размеры сохранены и доступны в экспорте.';$('settingsError').hidden=true;
    }catch(error){$('settingsError').textContent=error.message;$('settingsError').hidden=false;}
    finally{button.disabled=false;}
  };
  window.formatManager={renderChoices,presets};
  preferencesReady.then(()=>{if(editorPreferences.video_formats)formatCatalog=structuredClone(editorPreferences.video_formats);renderChoices();rows();});
})();
