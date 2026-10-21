/* Arrange the existing controls into the approved desktop layout; keep their IDs/state. */
(() => {
  const main=document.querySelector('main'),controls=document.querySelector('.controls'),preview=document.querySelector('.preview-panel');
  const nav=document.querySelector('.workflow-switch'),batch=$('batchPanel'),detail=$('batchDetail');
  const dock=document.createElement('section');dock.className='output-dock';dock.setAttribute('aria-label','Экспорт');main.append(dock);
  const output=document.querySelector('.batch-output');dock.append(output,$('singleArticleRow'),$('renderButton'),document.querySelector('.batch-actions'));
  const sidebar=document.createElement('div');sidebar.className='batch-sidebar';main.insertBefore(sidebar,dock);
  const advanced=document.createElement('div');advanced.id='advancedPanel';advanced.hidden=true;
  const advancedButton=document.createElement('button');advancedButton.className='secondary-button advanced-toggle';advancedButton.id='advancedButton';advancedButton.textContent='Дополнительно';advancedButton.setAttribute('aria-controls','advancedPanel');advancedButton.setAttribute('aria-expanded','false');
  controls.append(advancedButton,advanced);
  for(const id of ['cropControl0','cropControl1','modeHelp','transitionHelp'])advanced.append($(id));
  advancedButton.onclick=()=>{const show=advanced.hidden;motion.visible(advanced,show);advancedButton.setAttribute('aria-expanded',String(show));};
  controls.append(document.querySelector('.export-area'));
  for(const id of ['progressArea','errorMessage','resultActions'])preview.append($(id));
  const sourceOptions=document.createElement('details');sourceOptions.className='source-options';
  const sourceSummary=document.createElement('summary');sourceSummary.textContent='Исходники и роли';sourceOptions.append(sourceSummary,$('batchDetailNote'),document.querySelector('.batch-source-selects'),$('swapDetailButton'));detail.append(sourceOptions);
  controls.prepend(nav);
  const heading=document.createElement('div');heading.className='queue-columns';heading.innerHTML='<input id="batchSelectAll" type="checkbox" aria-label="Выбрать все ролики"><span>Артикул</span><span>Модель</span><span>Руки</span><span>Статус</span><span></span>';
  $('batchList').before(heading);batch.append($('folderDrop'));
  const sourceTabs=document.createElement('div');sourceTabs.className='tabs source-tabs';sourceTabs.setAttribute('role','group');sourceTabs.setAttribute('aria-label','Просмотр исходника');
  sourceTabs.innerHTML='<button id="previewModel" aria-pressed="true">Модель</button><button id="previewHands" aria-pressed="false">Руки</button>';
  $('viewer').after(sourceTabs);
  window.previewSource=slot=>{
    const source=state.sources[slot];if(!source)return;
    $('mainVideo').pause();$('mainVideo').dataset.sourceSlot=String(slot);$('mainVideo').style.objectFit='cover';$('mainVideo').style.objectPosition=`50% ${$('crop'+slot).value}%`;$('mainVideo').src=source.preview;$('mainVideo').onloadeddata=()=>{$('mainVideo').currentTime=Math.min(3,source.info.duration/2);};$('mainVideo').setAttribute('aria-label',slot?'Исходник рук':'Исходник модели');
    $('viewerLabel').textContent=source.name;$('videoDuration').textContent=source.info.duration.toFixed(2)+' с';$('videoSize').textContent=mb(source.info.size)+' МБ';
    $('referenceTab').setAttribute('aria-selected','false');$('resultTab').setAttribute('aria-selected','false');
    $('previewModel').setAttribute('aria-pressed',String(!slot));$('previewHands').setAttribute('aria-pressed',String(!!slot));motion.reveal($('viewer'));
  };
  $('previewModel').onclick=()=>previewSource(0);$('previewHands').onclick=()=>previewSource(1);
  window.workspaceLayout=enabled=>{
    if(enabled){main.prepend(nav);sidebar.append(detail,$('editorWorkspace'));$('editorWorkspace').prepend(preview);controls.append($('applySettingsButton'));}
    else {controls.prepend(nav);main.insertBefore($('editorWorkspace'),sidebar);$('editorWorkspace').prepend(controls);main.insertBefore(detail,sidebar);detail.append($('applySettingsButton'));}
  };
  $('batchSelectAll').onchange=()=>window.batchController.selectAll($('batchSelectAll').checked);
  workspaceLayout(false);
})();
