const {chromium}=require('playwright');
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const root=process.cwd(),url=process.env.OUTMAX_URL||'http://127.0.0.1:8769';
async function wrap(page){
 assert.equal(await page.locator('#mainVideo').evaluate(v=>v.loop),true);
 await page.locator('#mainVideo').evaluate(v=>new Promise(resolve=>{
  v.muted=true;v.pause();v.currentTime=v.duration-.25;
  v.addEventListener('seeked',()=>{
   window.wraps=0;window.ends=0;
   v.ontimeupdate=()=>{if(v.currentTime<.5)window.wraps++;};
   v.onended=()=>window.ends++;
   v.play().then(resolve);
  },{once:true});
 }));
 await page.waitForFunction(()=>window.wraps>0&&!document.getElementById('mainVideo').paused,null,{timeout:10000});
 assert.equal(await page.evaluate(()=>window.ends),0);
 await page.locator('#mainVideo').evaluate(v=>v.pause());
}
(async()=>{
 const browser=await chromium.launch({headless:false});const page=await browser.newPage({viewport:{width:1340,height:950}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 try{
  await page.goto(url);await page.evaluate(()=>preferencesReady);
  await page.locator('#file0').setInputFiles(path.join(root,'analysis/qa17/45555-model.mp4'));
  await page.locator('#loaded0').waitFor();
  await page.locator('#file1').setInputFiles(path.join(root,'analysis/qa17/45555-hands.mp4'));
  await page.waitForFunction(()=>state.preview&&!autoPreview.loading,null,{timeout:120000});
  await page.waitForFunction(()=>document.getElementById('mainVideo').readyState>=3);
  await wrap(page);
  assert.equal(await page.evaluate(()=>state.preview.report.loop),true);
  assert.equal(await page.evaluate(()=>state.preview.report.black_opening_frame),false);
  await page.locator('#mainVideo').evaluate(v=>{v.currentTime=9;});
  await page.waitForFunction(()=>!document.getElementById('mainVideo').seeking);
  await page.screenshot({path:path.join(root,'analysis/qa17/loop-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(root,'analysis/qa17/loop-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1340,height:950});
  await page.locator('#bitrate').selectOption('500');await page.locator('#articleNumber').fill('99017');
  const output=path.join(root,'analysis/qa17/browser-export-'+Date.now());await page.locator('#batchOutputPath').fill(output);
  await page.locator('#renderButton').click();
  await page.waitForFunction(()=>state.result&&!state.running,null,{timeout:240000});
  await page.waitForFunction(()=>document.getElementById('mainVideo').readyState>=3);
  await wrap(page);
  await page.locator('#referenceTab').click();assert.equal(await page.locator('#mainVideo').evaluate(v=>v.loop),false);
  await page.locator('#resultTab').click();assert.equal(await page.locator('#mainVideo').evaluate(v=>v.loop),true);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(root,'analysis/qa17/browser.json'),JSON.stringify({errors,output,previewWrap:true,resultWrap:true},null,2));
  console.log('PASS: actual preview/result wrap and continue playing, no ended event, no black opening frame, responsive UI, no JS errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
