(() => {
  const button=document.createElement('button');button.id='whatsNewButton';button.className='text-button whats-new-button';button.setAttribute('aria-haspopup','dialog');button.innerHTML='Что нового <span class="new-badge">NEW</span>';$('helpButton').before(button);
  button.setAttribute('aria-label','Что нового');button.querySelector('.new-badge').setAttribute('aria-hidden','true');
  const dialog=document.createElement('dialog');dialog.id='whatsNewDialog';dialog.setAttribute('aria-labelledby','whatsNewTitle');dialog.innerHTML='<div class="whats-new-heading"><h2 id="whatsNewTitle">Что нового в OUTMAX Cut</h2><button class="secondary-button" id="closeWhatsNew">Закрыть</button></div><div id="releaseHistory"></div>';document.body.append(dialog);
  let loaded=false;
  button.onclick=async()=>{
    try{
      if(!loaded){const response=await fetch('/ui/whats-new.json');if(!response.ok)throw new Error('Не удалось открыть историю версий.');const releases=await response.json();
        releases.forEach((release,index)=>{
          const section=document.createElement('details');section.className='release-entry';section.open=index===0;
          const summary=document.createElement('summary');summary.textContent=`${release.version} · ${release.title}`;section.append(summary);
          const description=document.createElement('p');description.textContent=release.description;section.append(description);
          const list=document.createElement('ul');release.changes.forEach(change=>{const item=document.createElement('li');item.textContent=change;list.append(item);});section.append(list);
          for(const shot of release.screenshots){const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');image.src=shot.src;image.alt=shot.caption;image.loading='lazy';caption.textContent=shot.caption;figure.append(image,caption);section.append(figure);}
          $('releaseHistory').append(section);
        });loaded=true;
      }motion.openDialog(dialog);
    }catch(error){showError(error.message);}
  };
  $('closeWhatsNew').onclick=()=>motion.closeDialog(dialog);
})();
