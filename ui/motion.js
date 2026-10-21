/* Interruptible compositor-only motion. No animation owns application state. */
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Map();
  const ease = 'cubic-bezier(.22,1,.36,1)';
  function stop(element) { animations.get(element)?.cancel(); animations.delete(element); }
  function animate(element, frames, duration=210) {
    stop(element);
    if (reduced.matches || document.hidden) return;
    const animation=element.animate(frames,{duration,easing:ease});
    animations.set(element,animation);
    animation.finished.catch(()=>{}).finally(()=>{if(animations.get(element)===animation)animations.delete(element);});
    return animation;
  }
  function reveal(element) {
    if(element.hidden || reduced.matches)return;
    const active=animations.has(element), style=active?getComputedStyle(element):null;
    animate(element,[{opacity:style?.opacity||0,transform:style?.transform||'translateY(5px)'},{opacity:1,transform:'none'}]);
  }
  function visible(element, show) {
    if(element.hidden===!show)return;
    stop(element); element.hidden=!show;
    if(show)reveal(element);
  }
  function rects(list) {
    const bounds=list.getBoundingClientRect(), positions=new Map();
    for(const row of list.children){
      if(!row.classList.contains('batch-row')||row.dataset.leaving)continue;
      const rect=row.getBoundingClientRect();
      if(rect.bottom>=bounds.top && rect.top<=bounds.bottom)positions.set(row,rect);
    }
    return positions;
  }
  const scrollGuards=new WeakMap();
  function holdScroll(list, top){
    scrollGuards.get(list)?.();
    let frame, timer;
    const events=['wheel','touchstart','pointerdown','keydown'];
    const cleanup=()=>{clearTimeout(timer);cancelAnimationFrame(frame);list.removeEventListener('scroll',restore);events.forEach(type=>list.removeEventListener(type,cleanup,true));scrollGuards.delete(list);};
    const restore=()=>{if(Math.abs(list.scrollTop-top)>.5){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{list.scrollTop=top;});}};
    list.addEventListener('scroll',restore,{passive:true});events.forEach(type=>list.addEventListener(type,cleanup,{capture:true,passive:true}));
    timer=setTimeout(cleanup,240);scrollGuards.set(list,cleanup);
  }
  function reconcile(list, mutate) {
    const before=reduced.matches?new Map():rects(list), scroll=list.scrollTop;
    holdScroll(list,scroll);mutate(); list.scrollTop=scroll;
    if(reduced.matches)return;
    const after=rects(list);
    // Read every position first, then write transforms: one layout, not one per row.
    for(const [row,rect] of after){
      const old=before.get(row);
      if(old){const dy=old.top-rect.top;if(Math.abs(dy)>.5)animate(row,[{transform:`translateY(${dy}px)`},{transform:'none'}],220);}
      else reveal(row);
    }
  }
  function remove(row,list) {
    if(!reduced.matches){
      const box=row.getBoundingClientRect(),bounds=list.getBoundingClientRect();
      if(box.bottom>=bounds.top&&box.top<=bounds.bottom){
        const ghost=row.cloneNode(true);ghost.dataset.leaving='true';ghost.inert=true;ghost.setAttribute('aria-hidden','true');
        Object.assign(ghost.style,{position:'absolute',top:`${box.top-bounds.top+list.scrollTop}px`,left:'0',width:`${box.width}px`,pointerEvents:'none',zIndex:2});
        list.append(ghost);
        const animation=animate(ghost,[{opacity:1,transform:'none'},{opacity:0,transform:'translateX(6px)'}],180);
        if(animation)animation.finished.catch(()=>{}).finally(()=>ghost.remove());else ghost.remove();
      }
    }
    stop(row);row.remove();
  }
  function progress(element,value) {
    const bounded=Math.max(0,Math.min(100,Number(value)||0));
    if(!element.parentElement.classList.contains('motion-progress')){
      const wrapper=document.createElement('span'),fill=document.createElement('span');
      wrapper.className='motion-progress';fill.className='progress-fill';fill.setAttribute('aria-hidden','true');
      element.before(wrapper);wrapper.append(element,fill);
    }
    if(element.value!==bounded)element.value=bounded;
    const fill=element.parentElement.lastElementChild;
    if(fill.dataset.value!==String(bounded)){fill.dataset.value=String(bounded);fill.style.transform=`scaleX(${bounded/100})`;}
  }
  function openDialog(dialog){if(!dialog.open)dialog.showModal();reveal(dialog);}
  function closeDialog(dialog){stop(dialog);dialog.close();}
  reduced.addEventListener('change',()=>{for(const el of [...animations.keys()])stop(el);document.querySelectorAll('[data-leaving]').forEach(el=>el.remove());});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const el of [...animations.keys()])stop(el);});
  window.motion={visible,reveal,reconcile,remove,progress,openDialog,closeDialog,reduced};
})();
