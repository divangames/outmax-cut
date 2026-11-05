/* Run against an isolated profile: this test changes defaults and exports fixture copies. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=process.cwd(),url=process.env.OUTMAX_URL||'http://127.0.0.1:8768';
const artifacts=path.join(root,'analysis/qa16');fs.mkdirSync(artifacts,{recursive:true});
const ffprobe=path.join(root,'vendor/bin/ffprobe.exe');
const inspect=file=>JSON.parse(execFileSync(ffprobe,['-v','error','-select_streams','v:0','-show_streams','-of','json',file],{encoding:'utf8'})).streams[0];
const previewReady=page=>page.waitForFunction(()=>state.preview!==null&&!autoPreview.loading,null,{timeout:120000});
const slide=(page,id,value)=>page.locator('#'+id).evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));},String(value));
const format=(page,name)=>page.locator(`#exportFormats input[value=${name}]`);

(async()=>{
 const browser=await chromium.launch({headless:process.env.OUTMAX_HEADLESS==='1'});
 const page=await browser.newPage({viewport:{width:1340,height:950}});
 const errors=[],previewRequests=[],metrics={};
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/preview'))previewRequests.push(request.postDataJSON());});
 try{
  await page.goto(url);await page.evaluate(()=>preferencesReady);
  assert.equal(await page.locator('#previewButton').count(),0);
  assert.equal(await page.locator('#mode').inputValue(),'smart');
  await page.locator('#mode').selectOption('template');
  await page.locator('#bitrate').selectOption('750');
  await slide(page,'sensitivity',67);await page.locator('#sensitivity').dispatchEvent('change');
  await page.evaluate(()=>preferenceWrite);
  await page.reload();await page.evaluate(()=>preferencesReady);
  assert.equal(await page.locator('#mode').inputValue(),'template');
  assert.equal(await page.locator('#bitrate').inputValue(),'750');
  assert.equal(await page.locator('#sensitivity').inputValue(),'67');
  await page.locator('#mode').selectOption('smart');
  await page.locator('#file0').setInputFiles(path.join(root,'analysis/features/inputs/90001/90001_model.mp4'));
  await page.locator('#loaded0').waitFor({timeout:60000});
  const started=Date.now();
  await page.locator('#file1').setInputFiles(path.join(root,'analysis/features/inputs/90001/90001_hands.mov'));
  await page.locator('#loaded1').waitFor({timeout:60000});
  await previewReady(page);metrics.initialPreviewMs=Date.now()-started;
  assert.equal(await page.locator('#previewTab').getAttribute('aria-selected'),'true');
  assert.equal(await page.locator('#mode').isEnabled(),true);
  const initial=await page.evaluate(()=>state.preview.id);
  const proxyUrl=await page.evaluate(()=>state.sources[1].preview);
  const proxy=await page.request.get(url+proxyUrl);
  const proxyFile=path.join(artifacts,'source-proxy.mp4');fs.writeFileSync(proxyFile,await proxy.body());
  assert.equal(inspect(proxyFile).avg_frame_rate,'30/1');
  const before=previewRequests.length;
  await page.evaluate(()=>{for(let i=0;i<30;i++){const input=document.getElementById('cropX0');input.value=50+i;input.dispatchEvent(new Event('input',{bubbles:true}));}});
  assert.equal(await page.locator('#mode').isEnabled(),true);
  await previewReady(page);
  assert.equal(await page.evaluate(()=>state.preview.settings.crops_x[0]),.79);
  assert.equal(previewRequests.length-before,1,'Slider drag should be debounced into one preview');
  await page.locator('#resetCrop0').click();await previewReady(page);
  assert.equal(await page.locator('#cropX0').inputValue(),'50');
  assert.equal(await page.locator('#crop0').inputValue(),'82.4');
  assert.equal(await page.evaluate(()=>state.preview.id),initial,'Returning to original settings should reuse the cache');
  await format(page,'marketplace').check();await format(page,'vertical').check();
  const variants={standard:[480,480],marketplace:[360,480],vertical:[270,480]};
  for(const name of ['marketplace','vertical','standard']){
   const start=Date.now();await page.locator('#outputFormat').selectOption(name);await previewReady(page);
   const dimensions=await page.evaluate(()=>[state.preview.report.result.width,state.preview.report.result.height]);
   assert.deepEqual(dimensions,variants[name]);metrics[name+'PreviewMs']=Date.now()-start;
  }
  await page.locator('#previewTab').click();
  await page.locator('#mainVideo').evaluate(v=>{v.muted=true;return v.play();});
  await page.waitForFunction(()=>document.getElementById('mainVideo').getVideoPlaybackQuality().totalVideoFrames>=120,null,{timeout:15000});
  metrics.playback=await page.locator('#mainVideo').evaluate(v=>{const q=v.getVideoPlaybackQuality();v.pause();return {frames:q.totalVideoFrames,dropped:q.droppedVideoFrames,time:v.currentTime};});
  assert(metrics.playback.frames>=90,'Preview is not decoding at a useful frame rate');
  assert(metrics.playback.dropped/metrics.playback.frames<.1,'Too many preview frames were dropped');
  metrics.seekMs=await page.locator('#mainVideo').evaluate(v=>new Promise(resolve=>{const start=performance.now();v.addEventListener('seeked',()=>resolve(performance.now()-start),{once:true});v.currentTime=12;}));
  assert(metrics.seekMs<2000,'Seeking the small preview is too slow');
  await page.screenshot({path:path.join(artifacts,'single-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(artifacts,'single-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1340,height:950});
  await page.locator('#bitrate').selectOption('500');
  await page.locator('#articleNumber').fill('90011');
  const singleOutput=path.join(artifacts,'single-'+Date.now());await page.locator('#batchOutputPath').fill(singleOutput);
  // Export remains available during automatic preview; starting it cancels obsolete work.
  await slide(page,'cropX0',31);
  await page.waitForFunction(()=>autoPreview.loading,null,{timeout:5000});
  assert(await page.locator('#renderButton').isEnabled());
  await page.locator('#renderButton').click();
  await page.waitForFunction(()=>!state.running&&state.result?.variants?.length===3,null,{timeout:240000});
  assert.equal(await page.locator('#resultTab').getAttribute('aria-selected'),'true');
  for(const [name,dims] of Object.entries({standard:[1080,1080],marketplace:[900,1200],vertical:[1080,1920]})){
   const stream=inspect(path.join(singleOutput,'90011',`90011_${dims[0]}x${dims[1]}.mp4`));
   assert.deepEqual([stream.width,stream.height],dims);assert(+stream.nb_frames>0);assert.equal(stream.avg_frame_rate,'30/1');
  }
  await page.locator('#resultFormat').selectOption('vertical');
  await page.waitForFunction(()=>document.getElementById('mainVideo').videoHeight===1920,null,{timeout:10000});
  const saved=await page.evaluate(()=>api('/api/save/'+state.result.id,{format:'vertical'}));
  assert(saved.download.includes('format=vertical'));
  const range=await page.request.get(url+saved.download,{headers:{Range:'bytes=0-1023'}});assert.equal(range.status(),206);
  await slide(page,'cropX0',32);await previewReady(page);
  assert.equal(await page.evaluate(()=>state.preview.settings.crops_x[0]),.32);
  assert.equal(await page.locator('#resultActions').isVisible(),false);
  await page.locator('#batchMode').click();
  await page.evaluate(folder=>api('/api/shell/enqueue',{paths:[folder]}),path.join(root,'analysis/features/inputs'));
  await page.waitForFunction(()=>document.querySelectorAll('.batch-row').length===2,null,{timeout:60000});
  const rows=page.locator('.batch-row');
  await rows.nth(0).locator('.batch-item-open').click();
  assert.equal(await page.locator('#mode').inputValue(),'smart');assert.equal(await page.locator('#bitrate').inputValue(),'500');assert.equal(await page.locator('#sensitivity').inputValue(),'67');
  await format(page,'marketplace').check();
  await rows.nth(1).locator('.batch-item-open').click();
  assert.equal(await format(page,'marketplace').isChecked(),false);
  await format(page,'vertical').check();await format(page,'standard').uncheck();
  await rows.nth(0).locator('.batch-item-open').click();assert(await format(page,'marketplace').isChecked());assert.equal(await format(page,'vertical').isChecked(),false);
  await previewReady(page);
  await page.screenshot({path:path.join(artifacts,'batch-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(await page.locator('#resetCrop0').isVisible());await page.screenshot({path:path.join(artifacts,'batch-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1340,height:950});
  const batchOutput=path.join(artifacts,'batch-'+Date.now());await page.locator('#batchOutputPath').fill(batchOutput);
  await page.locator('#batchRenderButton').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('.batch-item-status')].every(el=>el.textContent==='Сохранён'),null,{timeout:240000});
  for(const [article,filenames] of [['90001',['90001_1080x1080.mp4','90001_900x1200.mp4']],['90002',['90002.mp4']]]){
   for(const filename of filenames)assert(fs.existsSync(path.join(batchOutput,article,filename)));
   assert(fs.existsSync(path.join(batchOutput,article,'Руки + Ноги',article+'_ноги.mp4')));
  }
  assert.equal(await page.locator('#resultTab').getAttribute('aria-selected'),'true');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'browser.json'),JSON.stringify({metrics,errors,previews:previewRequests.length,singleOutput,batchOutput},null,2));
  console.log('PASS auto preview, cache/debounce, 30fps playback/seek, persistent settings, reset, responsive layout, 3 single formats, independent batch formats, full exports, byte ranges');
  console.log(JSON.stringify(metrics));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
