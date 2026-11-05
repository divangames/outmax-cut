const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const root=process.cwd(),url=process.env.OUTMAX_URL||'http://127.0.0.1:8768';
const folder=path.join(root,'analysis/qa16');
const manifest=JSON.parse(fs.readFileSync(path.join(folder,'real-inputs.json'),'utf8'));
const inspect=file=>JSON.parse(execFileSync(path.join(root,'vendor/bin/ffprobe.exe'),['-v','error','-select_streams','v:0','-show_streams','-of','json',file],{encoding:'utf8'})).streams[0];
const ready=page=>page.waitForFunction(()=>state.preview!==null&&!autoPreview.loading,null,{timeout:180000});

(async()=>{
 const browser=await chromium.launch({headless:process.env.OUTMAX_HEADLESS==='1'});
 const page=await browser.newPage({viewport:{width:1340,height:950}});
 const errors=[],progress=[],metrics=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async response=>{if(response.url().includes('/api/imports/'))try{progress.push(await response.json());}catch{}});
 try{
  await page.goto(url);await page.evaluate(()=>preferencesReady);
  assert.equal(await page.locator('#outputFormat option[value=vertical]').isDisabled(),true);
  await page.locator('#batchMode').click();
  const started=Date.now();await page.evaluate(input=>api('/api/shell/enqueue',{paths:[input]}),manifest.root);
  await page.waitForFunction(()=>document.querySelectorAll('.batch-row').length===6,null,{timeout:180000});
  const importMs=Date.now()-started;
  assert(progress.some(task=>task.status==='running'&&task.progress>0&&task.progress<100));
  assert.equal(progress.at(-1).errors.length,0);
  const rows=page.locator('.batch-row');
  for(let i=0;i<6;i++){
   const start=Date.now();await rows.nth(i).locator('.batch-item-open').click();await ready(page);
   const job=await page.evaluate(()=>state.preview);
   assert.deepEqual(job.source_ids,await page.evaluate(()=>state.sources.map(source=>source.id)));
   const stream=inspect(job.output);assert.equal(stream.avg_frame_rate,'30/1');assert.equal(+stream.nb_frames,job.report.frames);
   await page.waitForFunction(()=>{const v=document.getElementById('mainVideo');return v.readyState>=3&&!v.seeking&&v.currentTime>=.09;},null,{timeout:10000});
   const item={article:await rows.nth(i).locator('strong').textContent(),previewMs:Date.now()-start};
   if(i<2){
    await page.locator('#mainVideo').evaluate(v=>{v.muted=true;return v.play();});
    await page.waitForFunction(()=>document.getElementById('mainVideo').currentTime>=4,null,{timeout:15000});
    item.playback=await page.locator('#mainVideo').evaluate(v=>{const quality=v.getVideoPlaybackQuality();v.pause();return {frames:quality.totalVideoFrames,dropped:quality.droppedVideoFrames};});
    assert(item.playback.dropped/item.playback.frames<.1);
   }
   metrics.push(item);console.log(JSON.stringify(item));
  }
  await rows.nth(0).locator('.batch-item-open').click();await ready(page);
  await page.locator('#exportFormats input[value=marketplace]').check();await page.locator('#exportFormats input[value=vertical]').check();
  await page.locator('#outputFormat').selectOption('vertical');await ready(page);
  await page.locator('#cropX0').evaluate(el=>{el.value=27;el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>autoPreview.loading,null,{timeout:10000});
  await page.locator('#resetCrop0').click();await ready(page);
  assert.equal(await page.evaluate(()=>state.preview.settings.crops_x[0]),.5);
  await page.screenshot({path:path.join(folder,'real-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(folder,'real-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1340,height:950});
  await page.locator('#batchSelectAll').uncheck();
  await rows.nth(0).locator('.batch-item-check').check();await rows.nth(1).locator('.batch-item-check').check();
  await rows.nth(1).locator('.batch-item-open').click();
  await page.locator('#exportFormats input[value=vertical]').check();
  const output=path.join(folder,'real-export-'+Date.now());await page.locator('#batchOutputPath').fill(output);
  await page.locator('#batchRenderButton').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('.batch-item-status')].slice(0,2).every(el=>el.textContent==='Сохранён'),null,{timeout:480000});
  for(const [article,dimensions] of [['45555',[[1080,1080],[900,1200],[1080,1920]]],['47433',[[1080,1080],[1080,1920]]]]){
   for(const [width,height] of dimensions){
    const result=inspect(path.join(output,article,`${article}_${width}x${height}.mp4`));
    assert.deepEqual([result.width,result.height],[width,height]);assert(+result.nb_frames>0);assert.equal(result.avg_frame_rate,'30/1');
   }
  }
  assert.equal(await page.locator('#resultTab').getAttribute('aria-selected'),'true');
  assert.equal(await page.locator('#resultFormat option').count(),2);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(folder,'real-browser.json'),JSON.stringify({importMs,metrics,errors,output},null,2));
  console.log('PASS: all 12 supplied clips imported, 6 real auto previews, 30fps playback, cancellation/reset, five full exports, no JS errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
