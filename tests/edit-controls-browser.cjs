const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=process.cwd(),url=process.env.OUTMAX_URL||'http://127.0.0.1:8780',output=path.join(root,'analysis/qa170');
const slide=(page,id,value)=>page.locator('#'+id).evaluate((e,v)=>{e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));},String(value));
const ready=page=>page.waitForFunction(()=>state.preview&&!autoPreview.loading&&!livePreview.active&&$('mainVideo').readyState>=2,null,{timeout:120000});
const seek=(page,time)=>page.locator('#mainVideo').evaluate((v,t)=>new Promise(resolve=>{v.pause();if(Math.abs(v.currentTime-t)<.001&&!v.seeking)return resolve();v.addEventListener('seeked',resolve,{once:true});v.currentTime=t;}),time);
const live=page=>page.waitForFunction(()=>!document.querySelector('.live-preview-canvas').hidden&&document.querySelector('.live-preview-canvas').dataset.revision===String(livePreview.version));
const pixels=page=>page.evaluate(()=>{const c=document.querySelector('.live-preview-canvas');window.expectedPixels=c.getContext('2d').getImageData(0,0,c.width,c.height);return c.toDataURL();});
const compare=page=>page.evaluate(()=>{const a=window.expectedPixels,c=document.createElement('canvas');c.width=a.width;c.height=a.height;const ctx=c.getContext('2d');ctx.drawImage($('mainVideo'),0,0,c.width,c.height);const b=ctx.getImageData(0,0,c.width,c.height).data;let sum=0;for(let i=0;i<b.length;i++)if(i%4!==3)sum+=Math.abs(a.data[i]-b[i]);return sum/(b.length/4*3);});
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:false}),page=await browser.newPage({viewport:{width:1440,height:1040}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));let hold=false;const gates=[];
 await page.route('**/api/preview',async route=>{if(hold)await new Promise(resolve=>gates.push(resolve));await route.continue().catch(()=>{});});
 const release=()=>{hold=false;gates.splice(0).forEach(resolve=>resolve());};
 try{
  await page.goto(url);await page.evaluate(()=>preferencesReady);assert.equal(await page.locator('#referenceTab').count(),0);
  assert.equal(await page.locator('#mainVideo').getAttribute('src'),'/reference');
  await page.locator('#settingsButton').click();
  await page.locator('.remove-format').evaluateAll(buttons=>buttons.forEach(button=>button.click()));
  const preset=page.locator('.format-row[data-id=standard]');await preset.locator('.format-width').fill('480');await preset.locator('.format-height').click();assert.equal(await preset.locator('.format-height').inputValue(),'480');
  const market=page.locator('.format-row[data-id=marketplace]');await market.locator('.format-width').fill('450');await market.locator('.format-height').click();assert.equal(await market.locator('.format-height').inputValue(),'600');
  await page.locator('#addFormat').click();const customRow=page.locator('.format-row').last();const custom=await customRow.getAttribute('data-id');
  await customRow.locator('.format-name').fill('Карточка сайта');await customRow.locator('.format-width').fill('640');await customRow.locator('.format-height').fill('360');
  await page.locator('#saveFormats').click();await page.getByText('Размеры сохранены и доступны в экспорте.').waitFor();
  await page.screenshot({path:path.join(output,'settings.png')});await page.locator('#closeSettings').click();
  await page.reload();await page.evaluate(()=>preferencesReady);assert.equal(await page.locator(`#exportFormats input[value="${custom}"]`).count(),1);
  for(const [slot,name]of [[0,'45555-model.mp4'],[1,'45555-hands.mp4']]){await page.locator('#file'+slot).setInputFiles(path.join(root,'analysis/qa17',name));await page.locator('#loaded'+slot).waitFor();if(slot===0)assert.notEqual(await page.locator('#mainVideo').getAttribute('src'),'/reference');}
  await ready(page);await seek(page,4.25);hold=true;
  const start=Date.now();await slide(page,'zoom0',150);await live(page);const modelMs=Date.now()-start,modelBefore=await pixels(page);
  await slide(page,'zoom0',180);await live(page);assert.notEqual(await pixels(page),modelBefore);assert.equal(await page.locator('#mainVideo').evaluate(v=>v.currentTime),4.25);
  release();await ready(page);assert.equal(await page.locator('#mainVideo').evaluate(v=>v.currentTime),4.25);assert(await page.locator('#mainVideo').evaluate(v=>v.paused));
  const modelMAE=await compare(page);assert(modelMAE<12,modelMAE);
  const handsTime=await page.evaluate(()=>state.preview.report.model_frames/30+3);await seek(page,handsTime);hold=true;
  await slide(page,'zoom1',150);await live(page);const handsBefore=await pixels(page);await slide(page,'cropX1',15);await live(page);assert.notEqual(await pixels(page),handsBefore);
  const handsX=await pixels(page);await slide(page,'crop1',80);await live(page);assert.notEqual(await pixels(page),handsX);release();await ready(page);const handsMAE=await compare(page);assert(handsMAE<12,handsMAE);
  assert(Math.abs(await page.locator('#mainVideo').evaluate(v=>v.currentTime)-handsTime)<.001);
  await page.getByRole('button',{name:'Сбросить положение и масштаб рук',exact:true}).click();await ready(page);assert.equal(await page.locator('#zoom1').inputValue(),'100');
  await seek(page,2);hold=true;const handle=page.getByRole('slider',{name:'Склейка модели с руками',exact:true});const box=await handle.boundingBox(),oldEnd=await handle.getAttribute('aria-valuenow');
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2-36,box.y+box.height/2,{steps:8});await page.mouse.up();
  assert(Number(await handle.getAttribute('aria-valuenow'))<Number(oldEnd));assert.equal(await page.locator('#mainVideo').evaluate(v=>v.currentTime),2);
  const livePlan=await page.evaluate(()=>timelineEditor.plan().segments);release();await ready(page);
  assert.deepEqual(await page.evaluate(()=>state.preview.report.segments),livePlan);
  await page.locator('.trim-settings summary').click();await page.locator('#trimStart1').fill('0.5');await page.locator('#trimEnd1').fill('10');await page.locator('#trimStart1').click();await ready(page);
  assert.deepEqual(await page.evaluate(()=>state.preview.report.content_bounds[1]),[.5,10]);
  await page.screenshot({path:path.join(output,'single.png')});
  // Raw-source zoom retains its own cursor and native controls.
  await page.locator('#previewHands').click();await page.waitForFunction(()=>$('mainVideo').readyState>=2);await seek(page,3.4);await slide(page,'zoom1',160);await live(page);
  assert.equal(await page.locator('#mainVideo').getAttribute('data-source-slot'),'1');assert(Math.abs(await page.locator('#mainVideo').evaluate(v=>v.currentTime)-3.4)<.001);
  // Batch uses copies. Original supplied footage is never moved by this test.
  await page.locator('#batchMode').click();await page.evaluate(folder=>api('/api/shell/enqueue',{paths:[folder]}),path.join(output,'import'));
  await page.waitForFunction(()=>document.querySelectorAll('.batch-row').length===2,null,{timeout:30000});await ready(page);
  await seek(page,2);await slide(page,'zoom0',125);await slide(page,'zoom1',145);await ready(page);
  await page.locator('.trim-settings summary').evaluate(el=>el.parentElement.open=true);
  await page.locator('#trimEnd0').fill('8');await page.locator('#trimStart0').click();await ready(page);
  await page.locator(`#exportFormats input[value="${custom}"]`).check();await page.locator('#applySettingsButton').click();await ready(page);
  assert.equal(await page.locator('#zoom0').inputValue(),'125');assert.deepEqual(await page.evaluate(()=>timelineEditor.trims[0]),[.8,8]);
  await page.locator('.batch-item-open').nth(1).click();await ready(page);assert.deepEqual(await page.evaluate(()=>timelineEditor.trims),[null,null]);assert.equal(await page.locator('#zoom1').inputValue(),'145');
  await page.locator('.batch-item-open').nth(0).click();await ready(page);assert.equal(await page.evaluate(()=>timelineEditor.trims[0][1]),8);
  await page.locator('#batchOutputPath').fill(path.join(output,'export-'+Date.now()));await page.screenshot({path:path.join(output,'batch.png')});
  await page.locator('#batchRenderButton').click();await page.waitForFunction(()=>document.getElementById('batchSummary').textContent==='Готово. Сохранено 2 роликов.',null,{timeout:240000});
  const report=await page.evaluate(()=>({result:state.result,settings:editorSnapshot().settings}));assert.equal(report.result.variants.length,2);
  assert.deepEqual(report.result.variants.map(v=>[v.report.result.width,v.report.result.height]),[[480,480],[640,360]]);
  assert.equal(report.result.variants[1].report.settings.zooms[1],1.45);assert.equal(report.result.report.content_bounds[0][1],8);
  // Deleting a custom format updates all rows and their next exports.
  await page.locator('#settingsButton').click();await page.locator(`.format-row[data-id="${custom}"] .remove-format`).click();await page.locator('#saveFormats').click();await page.getByText('Размеры сохранены и доступны в экспорте.').waitFor();await page.locator('#closeSettings').click();
  assert.equal(await page.locator(`#exportFormats input[value="${custom}"]`).count(),0);await page.locator('.batch-item-open').nth(1).click();await ready(page);assert.deepEqual(await page.evaluate(()=>selectedFormats()),['standard']);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.locator('#settingsButton').click();await page.screenshot({path:path.join(output,'phone-settings.png')});assert(await page.locator('#settingsDialog').evaluate(e=>e.getBoundingClientRect().right<=innerWidth));
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({modelMs,modelMAE,handsMAE,report,errors},null,2));
  console.log('PASS: persistent custom/proportional formats, live zoom/pan in both scenes and raw sources, paused cursor, drag/manual cuts, independent batch trims, 4 real exports, format deletion, resets and narrow layout');console.log(JSON.stringify({modelMs,modelMAE,handsMAE}));
 }catch(error){await page.screenshot({path:path.join(output,'failure.png')});console.log('UI STATE',await page.evaluate(()=>({error:$('settingsError').textContent,invalid:[...document.querySelectorAll('input:invalid')].map(e=>({id:e.id,value:e.value,message:e.validationMessage})),trims:window.timelineEditor?.trims,preview:state.preview?.report?.content_bounds})));throw error;}finally{release();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
