const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('path');
const fs=require('fs');
const root=process.env.OUTMAX_ROOT||process.cwd();
const url=process.env.OUTMAX_URL||'http://127.0.0.1:8769';
(async()=>{
 const browser=await chromium.launch({headless:false});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);
  await page.locator('#settingsButton').click();
  await page.locator('#saveProcessingLog').check();
  await page.locator('#saveProcessingLog').isEnabled();
  await page.locator('#closeSettings').click();
  await page.getByRole('button',{name:'Пакетная сборка',exact:true}).click();
  await page.locator('#folderInput').setInputFiles(path.join(root,'analysis/batch-fixtures/Товары'));
  await page.waitForFunction(()=>document.querySelectorAll('.batch-row').length===3,{},{timeout:180000});
  const rows=page.locator('.batch-row');
  assert.match(await page.locator('#batchSummary').textContent(),/Выбрано 2 из 3/);
  await rows.nth(0).locator('.batch-item-open').click();
  assert.equal(await page.locator('#name0').textContent(),'2026-10-01 16.09.54.MOV');
  assert.equal(await page.locator('#name1').textContent(),'2026-09-30 14.45.00.MOV');
  await page.locator('#swapDetailButton').click();
  assert.equal(await page.locator('#name0').textContent(),'2026-09-30 14.45.00.MOV');
  await page.locator('#swapDetailButton').click();
  await page.getByLabel('Переход между планами').selectOption('cut');
  await page.locator('#crop0').fill('72');
  await page.locator('#crop0').dispatchEvent('input');
  await rows.nth(1).locator('.batch-item-open').click();
  await page.getByLabel('Режим сборки').selectOption('smart');
  await page.locator('#crop1').fill('35');
  await page.locator('#crop1').dispatchEvent('input');
  await rows.nth(0).locator('.batch-item-open').click();
  assert.equal(await page.locator('#transition').inputValue(),'cut');
  assert.equal(await page.locator('#crop0').inputValue(),'72');
  await page.getByRole('button',{name:'Один ролик',exact:true}).click();
  await page.getByRole('button',{name:'Пакетная сборка',exact:true}).click();
  assert.equal(await page.locator('#name0').textContent(),'2026-10-01 16.09.54.MOV');
  assert.equal(await page.locator('#transition').inputValue(),'cut');
  await rows.nth(2).locator('.batch-item-open').click();
  assert.equal(await page.locator('#batchModelSelect option').count(),2);
  assert(await page.locator('#renderButton').isDisabled());
  await rows.nth(0).locator('.batch-item-open').click();
  await page.locator('#batchOutputPath').fill(path.join(root,'analysis/batch-output'));
  await page.locator('#batchRenderButton').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(root,'analysis/batch-ready.png'),fullPage:true});
  await page.locator('#batchRenderButton').click();
  await page.locator('#batchCancelButton').waitFor();
  assert(await page.locator('#transition').isDisabled());
  await page.locator('#batchCancelButton').waitFor({state:'hidden',timeout:360000});
  assert.match(await page.locator('#batchSummary').textContent(),/Сохранено 2 роликов/);
  for(const sku of ['SKU-001','SKU-002']){
    const folder=path.join(root,'analysis/batch-output',sku.replace('SKU-',''));
    const reports=fs.readdirSync(folder).filter(f=>f==='монтаж.txt');
    assert(reports.length>=1);
    const report=JSON.parse(fs.readFileSync(path.join(folder,reports.at(-1)),'utf8'));
    assert.equal(report.frames,685);
    if(sku==='SKU-001'){assert.equal(report.settings.transition,'cut');assert.equal(report.settings.crops[0],.72);}
    else{assert.equal(report.settings.mode,'smart');assert.equal(report.settings.crops[1],.35);}
  }
  await rows.nth(1).locator('.batch-item-open').click();
  assert.equal(await page.locator('#resultTab').getAttribute('aria-selected'),'true');
  await page.waitForFunction(()=>document.getElementById('mainVideo').readyState>=3);
  await page.locator('#mainVideo').evaluate(v=>new Promise(r=>{v.addEventListener('seeked',r,{once:true});v.currentTime=12;}));
  await page.waitForTimeout(900);
  await page.screenshot({path:path.join(root,'analysis/batch-result.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(root,'analysis/batch-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: folder upload, image/name role detection, incomplete row, swap, independent settings, mode roundtrip, two real exports in separate folders, result preview, mobile. No JS errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
