/* Regression: format choices made on an excluded item apply to every queued product. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),cp=require('node:child_process');
const root=process.cwd(),out=path.join(root,'analysis/qa194'),url=process.env.OUTMAX_URL||'http://127.0.0.1:8774';
const formats=['standard','marketplace','vertical'];
const digest=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
(async()=>{
 const browser=await chromium.launch({headless:false}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const row=name=>page.locator('.batch-row').filter({has:page.locator('.batch-item-open strong',{hasText:name})});
 try{
  await page.goto(url);await page.evaluate(()=>workspaceReady);
  await page.evaluate(input=>api('/api/shell/enqueue',{paths:[input],action:'add'}),path.join(out,'test-inputs'));
  await page.waitForFunction(()=>batchController.items.length===4&&!batchController.locked,null,{timeout:180000});
  await row('47433').locator('.batch-item-open').click();
  await row('47664').locator('.batch-item-check').uncheck();
  const originals=await page.evaluate(()=>batchController.items.map(i=>({id:i.id,name:i.name,sources:i.snapshot.sources.map(s=>s?.location),settings:i.snapshot.settings})));
  assert.equal(originals.find(i=>i.name.endsWith('47433')).sources[0],undefined);
  const active=originals.find(i=>i.name.endsWith('47467'));
  await page.evaluate(id=>batchController.apply({crops:[.3,.6],zooms:[1.1,1.2],mode:'template'},[id],['crops','zooms','mode']),active.id);
  await page.locator('#exportFormats input[value=marketplace]').check();
  await page.locator('#exportFormats input[value=vertical]').check();
  assert(await page.locator('#formatScopeNote').isVisible());
  let items=await page.evaluate(()=>batchController.items.map(i=>({name:i.name,settings:i.snapshot.settings})));
  for(const item of items)assert.deepEqual(item.settings.formats,formats);
  assert.deepEqual(items.find(i=>i.name.endsWith('47467')).settings.crops,[.3,.6]);
  assert.deepEqual(items.find(i=>i.name.endsWith('47469')).settings.crops,[.824,.5]);
  await page.getByRole('button',{name:'Сбросить разрешения экспорта',exact:true}).click();
  assert(await page.evaluate(()=>batchController.items.every(i=>JSON.stringify(i.snapshot.settings.formats)==='["standard"]')));
  await page.locator('#exportFormats input[value=marketplace]').check();await page.locator('#exportFormats input[value=vertical]').check();
  await page.evaluate(input=>api('/api/shell/enqueue',{paths:[input],action:'add'}),path.join(out,'late-inputs'));
  await page.waitForFunction(()=>batchController.items.length===5&&!batchController.locked,null,{timeout:90000});
  assert.deepEqual(await page.evaluate(()=>batchController.items.find(i=>i.name.endsWith('45555')).snapshot.settings.formats),formats);
  await page.evaluate(()=>batchWorkspace.flush());await page.reload();await page.evaluate(()=>workspaceReady);
  assert(await page.evaluate(()=>batchController.items.every(i=>i.snapshot.settings.formats.length===3)));
  // Simulate an older saved queue: visible choices are three, another item's snapshot is square-only.
  await page.evaluate(()=>{const item=batchController.items.find(i=>i.name.endsWith('47469'));item.snapshot.settings.formats=['standard'];});
  await page.locator('#batchOutputPath').fill(path.join(out,'exports'));
  const sent=page.waitForRequest(r=>r.url().endsWith('/api/batch/render'));
  await page.locator('#batchRenderButton').click();
  const payload=(await sent).postDataJSON();assert.equal(payload.items.length,2);
  for(const item of payload.items)assert.deepEqual(item.formats,formats);
  await page.waitForFunction(()=>!batchController.locked,null,{timeout:600000});
  const results=await page.evaluate(()=>batchController.items.filter(i=>i.status==='done').map(i=>({name:i.name,result:i.snapshot.result})));
  assert.equal(results.length,2);
  for(const {name,result} of results){
   const article=name.split('/').at(-1);assert.equal(result.variants.length,3);
   assert.deepEqual(result.variants.map(v=>[v.report.result.width,v.report.result.height]),[[1080,1080],[900,1200],[1080,1920]]);
   for(const variant of result.variants){
    const probe=JSON.parse(cp.execFileSync(path.join(root,'vendor/bin/ffprobe.exe'),['-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',variant.output],{encoding:'utf8'}));
    assert.deepEqual([probe.streams[0].width,probe.streams[0].height],[variant.report.result.width,variant.report.result.height]);
   }
   assert.equal(fs.readdirSync(path.join(out,'exports',article,'Руки + Ноги')).length,2);
  }
  for(const article of ['47433','45555','47664'])assert(!fs.existsSync(path.join(out,'exports',article)));
  for(const record of JSON.parse(fs.readFileSync(path.join(out,'test-inputs.json'),'utf8'))){assert.equal(digest(record.copy),record.sha256);assert.equal(digest(record.original),record.sha256);}
  assert.match(await page.locator('#batchSummary').textContent(),/Файлов: 6/);
  await row('47467').locator('.batch-item-open').click();await page.locator('#resultFormat').selectOption('vertical');
  await page.waitForFunction(()=>$('mainVideo').readyState>=2);
  await page.locator('#exportFormats').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(root,'ui/whats-new/1.9.4-formats.png'),animations:'disabled'});
  await page.getByRole('button',{name:'Что нового',exact:true}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('#releaseHistory details:first-child img')].every(i=>i.complete&&i.naturalWidth>0));
  assert.match(await page.locator('.release-entry').first().locator('summary').textContent(),/^1.9.4/);
  await page.locator('#closeWhatsNew').click();
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,'phone.png'),fullPage:true,animations:'disabled'});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({exports:6,dimensions:[[1080,1080],[900,1200],[1080,1920]],nativeInputsPreserved:true,excludedPreserved:true,archiveCopies:true,independentCrops:true,inheritance:true,reset:true,restore:true,releaseMenu:true,mobile:true,errors},null,2));
  console.log('PASS: 6 actual MP4 exports, three verified dimensions, native source bytes preserved, excluded complete/incomplete items untouched, archive copies, independent crops, new imports, reset, restore, release image and narrow layout.');
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),animations:'disabled'});console.log(await page.evaluate(()=>({error:$('batchError').textContent,summary:$('batchSummary').textContent,items:batchController.items.map(i=>({name:i.name,status:i.status,error:i.error,formats:i.snapshot.settings.formats}))})));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
