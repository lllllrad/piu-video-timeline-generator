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
 const chartRequests=[],windowChartRequests=[];
 page.on('request',request=>{const url=new URL(request.url());if(url.pathname==='/api/chart')chartRequests.push(url.href);if(url.pathname==='/api/window'&&['notes','holds'].includes(url.searchParams.get('kind')))windowChartRequests.push(url.href);});
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#row-count')?.textContent.includes('saved records'));
 const meta=await page.request.get(`${base}/api/meta`).then(r=>r.json());
 const start=meta.start_seconds+Math.min(40,Math.max(0,meta.end_seconds-meta.start_seconds-10));
 const end=Math.min(meta.end_seconds,start+10),span=end-start;
 const head=start+span*.2,other=start+span*.6;
 const seekLimits=await page.locator('#video-seek').evaluate(e=>[Number(e.min),Number(e.max)]);
 if(seekLimits[0]!==meta.start_seconds||seekLimits[1]!==meta.end_seconds)throw Error('Player seek is not segment bounded');
 await page.locator('video').evaluate((v,start)=>{v.currentTime=start-2;},meta.start_seconds);
 await page.waitForFunction(start=>document.querySelector('video').currentTime>=start,meta.start_seconds);
 await page.locator('video').evaluate(async(v,end)=>{v.currentTime=end-.2;await v.play();},meta.end_seconds);
 await page.waitForFunction(end=>document.querySelector('video').paused&&Math.abs(document.querySelector('video').currentTime-end)<.01,meta.end_seconds);
 await page.locator('#play-toggle').click();await page.waitForFunction(start=>document.querySelector('video').currentTime<start+2&&!document.querySelector('video').paused,meta.start_seconds);
 await page.locator('#play-toggle').click();
 if(await page.locator('video').evaluate(v=>v.controls))throw Error('Native recording controls are still enabled');
 await page.locator('#playback-rate').selectOption('0.5');
 if(await page.locator('video').evaluate(v=>v.playbackRate)!==.5)throw Error('Custom playback speed failed');
 await page.locator('#playback-rate').selectOption('1');
 await page.locator('#mute').click();if(!(await page.locator('video').evaluate(v=>v.muted)))throw Error('Custom mute failed');
 await page.locator('#volume').evaluate(e=>{e.value='.35';e.dispatchEvent(new Event('input'));});
 if(Math.abs(await page.locator('video').evaluate(v=>v.volume)-.35)>.001)throw Error('Custom volume failed');
 await page.locator('#video-seek').evaluate((e,t)=>{e.value=String(t);e.dispatchEvent(new Event('input'));e.dispatchEvent(new Event('change'));},meta.start_seconds+1);
 await page.waitForFunction(t=>Math.abs(document.querySelector('video').currentTime-t)<.01,meta.start_seconds+1);
 await page.locator('#fullscreen').click();await page.waitForFunction(()=>!!document.fullscreenElement);
 await page.locator('#fullscreen').click();await page.waitForFunction(()=>!document.fullscreenElement);
 await page.locator('#chart').focus();await page.keyboard.press('Space');
 await page.waitForFunction(()=>!document.querySelector('video').paused);
 await page.waitForTimeout(400);
 if(Math.abs(await page.locator('#playhead').evaluate(e=>parseFloat(e.style.top))-38)>2)throw Error('Playback does not follow the fixed judgment line');
 await page.keyboard.press('Space');await page.waitForFunction(()=>document.querySelector('video').paused);
 const beforeFrame=await page.locator('video').evaluate(v=>v.currentTime);
 await page.keyboard.press('ArrowRight');await page.waitForFunction(t=>document.querySelector('video').currentTime>t,beforeFrame);

 await page.locator('#from').fill(String(start));await page.locator('#to').fill(String(end));await page.locator('#load').click();
 await page.waitForFunction(()=>!document.querySelector('#load').hasAttribute('aria-busy'));
 await page.locator('#chart').hover();await page.mouse.wheel(0,160);
 await page.waitForFunction(t=>Number((/** @type {HTMLInputElement} */(document.querySelector('#from'))).value)>t&&!document.querySelector('#load').hasAttribute('aria-busy'),start)
 .catch(async failure=>{await page.screenshot({path:'.local/editor/artifacts/player-failure.png',fullPage:true});throw Error(failure.message+JSON.stringify({from:await page.locator('#from').inputValue(),to:await page.locator('#to').inputValue(),error:await page.locator('#error').textContent(),errors}));});
 const scrolled=Number(await page.locator('#from').inputValue());
 const chartHeight=await page.locator('#chart').evaluate(e=>e.clientHeight);
 const scrolledTime=await page.locator('video').evaluate(v=>v.currentTime);
 if(Math.abs(scrolledTime-(scrolled+span*8/(chartHeight-30)))>.01)throw Error('Chart scroll did not seek to its judgment line');
 const wheelSpan=Number(await page.locator('#to').inputValue())-Number(await page.locator('#from').inputValue());
 if(Math.abs(wheelSpan-span)>.00001)throw Error('Chart scrolling changed zoom');
 await page.locator('#chart-position').focus();await page.keyboard.press('End');
 await page.waitForFunction(end=>Number((/** @type {HTMLInputElement} */(document.querySelector('#to'))).value)>end-1&&!document.querySelector('#load').hasAttribute('aria-busy'),meta.end_seconds);
 await page.waitForFunction(end=>Math.abs(document.querySelector('video').currentTime-end)<.01&&document.querySelector('video').paused,meta.end_seconds);
 await page.locator('#chart-position').focus();await page.keyboard.press('Home');
 await page.waitForFunction(start=>Math.abs(document.querySelector('video').currentTime-start)<.01&&document.querySelector('video').paused,meta.start_seconds);

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
 const targets=await page.request.get(`${base}/api/chart`).then(r=>r.json());
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
 const reportPage=await browser.newPage({viewport:{width:1280,height:900}});
 const reportRequests=[];reportPage.on('request',request=>reportRequests.push(request.url()));
 await reportPage.goto(`${base}/report.html`);
 if(await reportPage.locator('h2').first().textContent()!=='Analysis summary')throw Error('Standalone report has no summary');
 if(!(await reportPage.locator('#editor').getAttribute('href')).startsWith('/?source='))throw Error('Report editor link lost current server address');
 await reportPage.screenshot({path:'.local/editor/artifacts/report.png',fullPage:true});
 const localPath=meta.signature.path.slice(meta.signature.path.indexOf('/.local/')).replace(/report-data\.json$/,'report.html');
 await reportPage.goto('file:///workspace'+localPath);
 if(!(await reportPage.locator('body').textContent()).includes('This report opens without an editor server'))throw Error('File report did not open independently');
 if(reportRequests.some(url=>url.includes('/api/')))throw Error('Standalone report depends on editor APIs');
 await reportPage.setViewportSize({width:600,height:900});
 if(await reportPage.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Standalone report overflows compact viewport');
 await reportPage.screenshot({path:'.local/editor/artifacts/report-compact.png',fullPage:true});
 await reportPage.close();
 const catalog=await page.request.get(`${base}/api/library`).then(r=>r.json());
 const switchPage=await browser.newPage({viewport:{width:1600,height:1050}});
 await switchPage.goto(base);await switchPage.waitForFunction(()=>document.querySelector('#row-count')?.textContent.includes('saved records'));
 const currentSource=await switchPage.locator('#source-picker').inputValue();
 const currentSegment=await switchPage.locator('#segment-picker').inputValue();
 const sourceEntry=catalog.sources.find(item=>item.id===currentSource);
 const alternateSegment=sourceEntry.segments.find(item=>String(item.number)!==currentSegment);
 if(alternateSegment){
  await switchPage.locator('#segment-picker').selectOption(String(alternateSegment.number));
  await switchPage.locator('#open-play').click();
  await switchPage.waitForFunction(()=>document.body.getAttribute('aria-busy')==='false',null,{timeout:180000});
  if(!(await switchPage.locator('#subtitle').textContent()).includes(`Segment ${alternateSegment.number} ·`))throw Error('Segment picker did not switch plays');
 }
 const otherSource=catalog.sources.find(item=>item.id!==currentSource);
 if(otherSource){
  await switchPage.locator('#source-picker').selectOption(otherSource.id);
  await switchPage.locator('#open-play').click();
  await switchPage.waitForFunction(()=>document.body.getAttribute('aria-busy')==='false',null,{timeout:180000});
  const query=new URL(switchPage.url()).search;
  const switchedMeta=await switchPage.request.get(`${base}/api/meta${query}`).then(r=>r.json());
  if(switchedMeta.source_id!==otherSource.id||!(await switchPage.locator('video').getAttribute('src')).includes(`source=${encodeURIComponent(otherSource.id)}`))throw Error('Video picker did not bind recording and evidence to the new source');
 }
 await switchPage.screenshot({path:'.local/editor/artifacts/library.png',fullPage:true});
 await switchPage.close();

 if(chartRequests.length!==1||windowChartRequests.length)throw Error('Chart navigation refetched note objects: '+JSON.stringify({chartRequests,windowChartRequests}));
 const response=await page.request.get(`${base}/media`,{headers:{Range:'bytes=0-15'}});
 const forbidden=await page.request.put(`${base}/api/review?id=abc`,{data:{}});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const result={errors,automaticSelectionChecked:!!target,review:identity,rangeStatus:response.status(),rangeBytes:(await response.body()).length,unauthorizedWrite:forbidden.status(),overflow};
 if(errors.length||response.status()!==206||forbidden.status()!==403||overflow)throw Error(JSON.stringify(result));
 writeFileSync('.local/editor/artifacts/browser-result.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}
