const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
const root = process.env.OUTMAX_ROOT || process.cwd();
const targetUrl = process.env.OUTMAX_URL || 'http://127.0.0.1:8765';
(async () => {
  const browser = await chromium.launch({headless:false});
  const page = await browser.newPage({viewport:{width:1340,height:900}});
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  try {
    await page.goto(targetUrl);
    await page.getByRole('heading',{name:'Редактор видео'}).waitFor();
    await page.waitForFunction(()=>{const v=document.getElementById('mainVideo');return v.readyState>=3&&!v.seeking&&v.currentTime>=1.9;});
    await page.evaluate(()=>document.fonts.ready);
    // Native video-control spinner has a fade after seeked; allow that chrome to settle.
    await page.waitForTimeout(900);
    assert(await page.getByRole('button',{name:'Собрать видео',exact:true}).isDisabled());
    await page.screenshot({path:path.join(root,'analysis/ui-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(root,'analysis/ui-mobile.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
    await page.setViewportSize({width:1340,height:900});
    await page.getByRole('button',{name:'Как это работает'}).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({state:'hidden'});
    await page.locator('#articleNumber').fill('99001');
    await page.locator('#file0').setInputFiles(path.join(root,'видео','2026-10-01 16.09.54.MOV'));
    await page.locator('#loaded0').waitFor({timeout:120000});
    await page.locator('#file1').setInputFiles(path.join(root,'видео','2026-09-30 14.45.00.MOV'));
    await page.locator('#loaded1').waitFor({timeout:120000});
    await page.waitForFunction(()=>[0,1].every(i=>{const v=document.getElementById('sourceVideo'+i);return v.readyState>=3&&!v.seeking;}));
    if (process.env.OUTMAX_TEST_SMART) {
      await page.getByLabel('Режим сборки').selectOption('smart');
      await page.getByLabel('Переход между планами').selectOption('morph');
    }
    assert.equal(await page.locator('#sourceCount').textContent(),'2 из 2');
    await page.screenshot({path:path.join(root,'analysis/ui-loaded.png'),fullPage:true});
    await page.getByRole('button',{name:'Собрать видео',exact:true}).click();
    await page.locator('#progressArea').waitFor();
    await page.locator('#resultActions').waitFor({timeout:240000});
    assert.equal(await page.getByRole('tab',{name:'Результат'}).getAttribute('aria-selected'),'true');
    await page.waitForFunction(()=>document.getElementById('mainVideo').readyState>=3);
    await page.locator('#mainVideo').evaluate(v=>new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=12;}));
    await page.waitForTimeout(900);
    await page.screenshot({path:path.join(root,'analysis/ui-result.png'),fullPage:true});
    console.log('Result:',await page.locator('#outputPath').textContent());
    await page.getByRole('tab',{name:'Эталон',exact:true}).click();
    assert.equal(await page.getByRole('tab',{name:'Эталон',exact:true}).getAttribute('aria-selected'),'true');
    await page.getByLabel('Режим сборки').selectOption('smart');
    await page.locator('#smartOptions').waitFor();
    await page.locator('#resultActions').waitFor({state:'hidden'});
    assert.match(await page.locator('#readyHint').textContent(),/изменены/);
    await page.screenshot({path:path.join(root,'analysis/ui-stale.png'),fullPage:true});
    await page.getByRole('button',{name:'Собрать заново',exact:true}).click();
    await page.locator('#progressArea').waitFor();
    await page.getByRole('button',{name:'Отменить экспорт',exact:true}).click();
    await page.locator('#progressArea').waitFor({state:'hidden',timeout:20000});
    assert(await page.getByRole('button',{name:'Собрать заново',exact:true}).isEnabled());
    assert.deepEqual(errors,[]);
    console.log('PASS: upload, reference, export, playback, responsive layout, help, mode, cancellation; no JS errors');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
