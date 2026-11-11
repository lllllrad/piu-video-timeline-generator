// @ts-check
/** Runs entirely inside the Playwright container; only test drafts and screenshots persist. */
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {mkdirSync,writeFileSync} from 'node:fs';
execFileSync('npm',['install','--prefix','/tmp/piu-browser','--no-save','--ignore-scripts','playwright@1.64.1'],{stdio:'inherit',env:{...process.env,npm_config_cache:'/tmp/npm-cache'}});
const {chromium}=await import(pathToFileURL('/tmp/piu-browser/node_modules/playwright/index.mjs').href);
const base=process.argv[2]||'http://127.0.0.1:4180';
function latch(){let release=()=>{};const promise=new Promise(resolve=>{release=()=>resolve(undefined);});return {promise,resolve:release};}
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#row-count')?.textContent.includes('saved records'));
 const meta=await page.request.get(`${base}/api/meta`).then(r=>r.json());
 const start=meta.start_seconds+Math.min(40,Math.max(0,meta.end_seconds-meta.start_seconds-10));
 const end=Math.min(meta.end_seconds,start+10),span=end-start;
 const head=start+span*.2,other=start+span*.6;
 await page.locator('#chart').focus();await page.keyboard.press('Space');
 await page.waitForFunction(()=>!document.querySelector('video').paused);
 await page.keyboard.press('Space');await page.waitForFunction(()=>document.querySelector('video').paused);
 const beforeFrame=await page.locator('video').evaluate(v=>v.currentTime);
 await page.keyboard.press('ArrowRight');await page.waitForFunction(t=>document.querySelector('video').currentTime>t,beforeFrame);

 await page.locator('#from').fill(String(start));await page.locator('#to').fill(String(end));await page.locator('#load').click();
 await page.waitForFunction(()=>!document.querySelector('#load').hasAttribute('aria-busy'));
 await page.locator('#chart').focus();await page.keyboard.press('Shift+ArrowRight');
 await page.waitForFunction(()=>!document.querySelector('#load').hasAttribute('aria-busy'));
 if(Number(await page.locator('#from').inputValue())<=start&&meta.end_seconds-start>span)throw Error('Keyboard interval navigation failed');
 await page.locator('#zoom').selectOption('5');
 await page.waitForFunction(()=>!document.querySelector('#load').hasAttribute('aria-busy'));
 if(Math.abs(Number(await page.locator('#to').inputValue())-Number(await page.locator('#from').inputValue())-Math.min(5,meta.end_seconds-start))>.00001)throw Error('Interval zoom failed');
 await page.locator('#from').fill(String(start));await page.locator('#to').fill(String(end));await page.locator('#load').click();
 await page.waitForFunction(()=>!document.querySelector('#load').hasAttribute('aria-busy'));
 const targets=await page.request.get(`${base}/api/window?kind=notes&start=${start}&end=${end}&limit=500`).then(r=>r.json());
 const target=targets.rows.find(n=>n.status==='estimated'&&n.target_seconds>start&&n.target_seconds<end&&n.lane!=null);
 if(target){
  const box=await page.locator('#chart').boundingBox();
  await page.locator('#chart').click({position:{x:64+(target.lane+.5)*(box.width-64)/meta.layout.lanes.length,y:30+(target.target_seconds-start)/span*(box.height-30)}});
  await page.waitForFunction(id=>document.querySelector('#selected-evidence').textContent.includes(id),target.id);
  if(!(await page.locator('#evidence-panel').getAttribute('open')!==null))throw Error('Chart selection did not reveal evidence');
  await page.locator('#ghosts').uncheck();
  await page.locator('#evidence-panel').evaluate(e=>e.removeAttribute('open'));
  await page.locator('#chart').click({position:{x:64+(target.lane+.5)*(box.width-64)/meta.layout.lanes.length,y:30+(target.target_seconds-start)/span*(box.height-30)}});
  if(await page.locator('#evidence-panel').getAttribute('open')!==null)throw Error('Hidden automatic evidence intercepted a chart click');
  await page.locator('#ghosts').check();
 }
 await page.locator('#new').click();await page.locator('#head').fill(String(head));await page.locator('#apply-note').click();
 const first=await page.locator('#manual-notes').inputValue();
 await page.locator('#new-note').focus();await page.keyboard.press('Enter');
 await page.locator('#head').fill(String(other));await page.locator('#apply-note').focus();await page.keyboard.press('Enter');
 const second=await page.locator('#manual-notes').inputValue();
 if(await page.locator('#manual-notes option').count()!==3)throw Error('Consecutive keyboard creation failed');
 await page.locator('#manual-notes').selectOption(first);await page.locator('#head').fill(String(head+.001));
 await page.locator('#apply-note').focus();await page.keyboard.press('Enter');
 await page.locator('#manual-notes').selectOption(second);await page.locator('#remove-note').focus();await page.keyboard.press('Enter');
 await page.locator('#tick-time').evaluate(e=>e.closest('details').open=true);
 await page.locator('#tick-time').fill(String(head+.013));await page.locator('#tick-count').fill('3');await page.locator('#tick-form button').click();
 await page.locator('#scroll-time').evaluate(e=>e.closest('details').open=true);
 await page.locator('#scroll-time').fill(String(head+.02));await page.locator('#scroll-ratio').fill('.5');await page.locator('#scroll-form button').click();
 await page.locator('#comment').fill('Container browser smoke test draft; not independently reviewed chart truth.');await page.locator('#comment').blur();
 await page.locator('#chart').focus();await page.keyboard.press('Control+s');await page.waitForFunction(()=>document.querySelector('#save-state')?.textContent.includes('revision 1'));
 const identity=await page.locator('#reviews').inputValue(),saved=await page.request.get(`${base}/api/review?id=${identity}`).then(r=>r.json());
 if(saved.notes.length!==1||saved.notes[0].start_seconds!==head+.001||saved.ticks[0].count!==3||saved.scroll[0].multiplier!==.5)throw Error('Stored review differs from keyboard edits');
 await page.locator('#chart').focus();await page.keyboard.press('Control+z');
 await page.locator('#comment').fill('Container browser smoke test draft; save/undo verified, not independently reviewed truth.');await page.locator('#comment').blur();
 await page.locator('#chart').focus();await page.keyboard.press('Control+s');
 await page.waitForFunction(()=>document.querySelector('#save-state')?.textContent.includes('revision 2'));
 const reachedServer=latch(),releaseResponse=latch();let delaySave=true;
 await page.route('**/api/review?*',async route=>{
  if(route.request().method()!=='PUT'||!delaySave){await route.continue();return;}
  delaySave=false;const response=await route.fetch();reachedServer.resolve();
  await releaseResponse.promise;await route.fulfill({response});
 });
 await page.locator('#chart').focus();await page.keyboard.press('Control+s');await reachedServer.promise;
 const pendingComment='Container browser smoke test draft; edited while saving, not independently reviewed truth.';
 await page.locator('#comment').fill(pendingComment);releaseResponse.resolve();
 await page.waitForFunction(()=>!document.querySelector('#save').hasAttribute('disabled'));
 if(await page.locator('#comment').inputValue()!==pendingComment||await page.locator('#save-state').textContent()!=='Unsaved changes')throw Error('Save response discarded in-flight edits');
 await page.locator('#chart').focus();await page.keyboard.press('Control+s');
 await page.waitForFunction(()=>document.querySelector('#save-state')?.textContent.includes('revision 4'));
 const finalSaved=await page.request.get(`${base}/api/review?id=${identity}`).then(r=>r.json());
 if(finalSaved.comment!==pendingComment)throw Error('In-flight edits did not persist on the next revision');


 await page.locator('#channel').selectOption('motion');
 await page.waitForTimeout(200);
 if(await page.locator('#observations button').count())await page.locator('#observations button').first().click();
 await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
 mkdirSync('.local/editor/artifacts',{recursive:true});
 const workspace=await page.evaluate(()=>({height:document.documentElement.scrollHeight,viewport:innerHeight}));
 if(workspace.height>workspace.viewport+1)throw Error('Desktop workspace scrolls the recording out of view');
 await page.screenshot({path:'.local/editor/artifacts/desktop.png',fullPage:true});
 await page.setViewportSize({width:1100,height:900});await page.screenshot({path:'.local/editor/artifacts/compact.png',fullPage:true});
 const response=await page.request.get(`${base}/media`,{headers:{Range:'bytes=0-15'}});
 const forbidden=await page.request.put(`${base}/api/review?id=abc`,{data:{}});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const result={errors,automaticSelectionChecked:!!target,review:identity,rangeStatus:response.status(),rangeBytes:(await response.body()).length,unauthorizedWrite:forbidden.status(),overflow};
 if(errors.length||response.status()!==206||forbidden.status()!==403||overflow)throw Error(JSON.stringify(result));
 writeFileSync('.local/editor/artifacts/browser-result.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}
