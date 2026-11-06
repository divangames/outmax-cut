const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const base='http://127.0.0.1:8790',config=await (await fetch(base+'/api/config')).json();assert(config.native);
 const html=await (await fetch(base+'/')).text(),token=/name="outmax-token" content="([^"]+)"/.exec(html)[1];
 const current=await (await fetch(base+'/api/session')).json(),expected=current.session.single.settings.zooms;
 const changed=structuredClone(current.session);changed.single.settings.zooms=[1.67,1.23];
 await fetch(base+'/api/session',{method:'POST',headers:{'Content-Type':'application/json','X-Outmax-Token':token},body:JSON.stringify(changed)});
 const command=`Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class OutmaxCloseQA{[DllImport("user32.dll")]public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);}'
 $owner=(Get-NetTCPConnection -LocalPort 8790 | Select-Object -First 1).OwningProcess
 $target=Get-Process -Id $owner
 if($target.MainWindowTitle -ne 'OUTMAX Cut' -or $target.MainWindowHandle -eq 0){throw 'Unexpected native test window'}
 [OutmaxCloseQA]::PostMessage($target.MainWindowHandle,0x0010,[IntPtr]::Zero,[IntPtr]::Zero)`;
 execFileSync('powershell.exe',['-NoProfile','-Command',command],{windowsHide:true,timeout:15000});
 for(let attempt=0;attempt<80;attempt++){try{await fetch('http://127.0.0.1:8790/api/config');}catch{break;}await new Promise(resolve=>setTimeout(resolve,100));}
 let exited=false;try{await fetch('http://127.0.0.1:8790/api/config');}catch{exited=true;}assert(exited,'Native close blocked the UI');
 const data=JSON.parse(fs.readFileSync(path.resolve('analysis/qa180/native-profile/OutmaxCut/queue.json'),'utf8'));assert.deepEqual(data.payload.single.settings.zooms,expected);
 console.log('PASS native WebView2 close exits without deadlock and captures live UI state before exit');
})().catch(error=>{console.error(error);process.exitCode=1;});

