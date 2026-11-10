// @ts-check
/** Runs entirely inside the Playwright container; only test drafts and screenshots persist. */
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {mkdirSync,writeFileSync} from 'node:fs';
execFileSync('npm',['install','--prefix','/tmp/piu-browser','--no-save','--ignore-scripts','playwright@1.64.1'],{stdio:'inherit',env:{...process.env,npm_config_cache:'/tmp/npm-cache'}});
const {chromium}=await import(pathToFileURL('/tmp/piu-browser/node_modules/playwright/index.mjs').href);
const base=process.argv[2]||'http://127.0.0.1:4180';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.waitForFunction(()=>document.querySelector('#row-count')?.textContent.includes('saved records'));
 const meta=await page.request.get(`${base}/api/meta`).then(r=>r.json());
 const start=meta.start_seconds,end=Math.min(meta.end_seconds,start+10),span=end-start;
 const head=start+span*.2,other=start+span*.6;
 await page.locator('#from').fill(String(start));await page.locator('#to').fill(String(end));await page.locator('#load').click();
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
 await page.locator('#save').click();await page.waitForFunction(()=>document.querySelector('#save-state')?.textContent.includes('revision 1'));
 const identity=await page.locator('#reviews').inputValue(),saved=await page.request.get(`${base}/api/review?id=${identity}`).then(r=>r.json());
 if(saved.notes.length!==1||saved.notes[0].start_seconds!==head+.001||saved.ticks[0].count!==3||saved.scroll[0].multiplier!==.5)throw Error('Stored review differs from keyboard edits');
 await page.locator('#channel').selectOption('motion');
 await page.waitForTimeout(200);
 if(await page.locator('#observations button').count())await page.locator('#observations button').first().click();
 await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
 mkdirSync('.local/editor/artifacts',{recursive:true});
 await page.screenshot({path:'.local/editor/artifacts/desktop.png',fullPage:true});
 await page.setViewportSize({width:1100,height:900});await page.screenshot({path:'.local/editor/artifacts/compact.png',fullPage:true});
 const response=await page.request.get(`${base}/media`,{headers:{Range:'bytes=0-15'}});
 const forbidden=await page.request.put(`${base}/api/review?id=abc`,{data:{}});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const result={errors,review:identity,rangeStatus:response.status(),rangeBytes:(await response.body()).length,unauthorizedWrite:forbidden.status(),overflow};
 if(errors.length||response.status()!==206||forbidden.status()!==403||overflow)throw Error(JSON.stringify(result));
 writeFileSync('.local/editor/artifacts/browser-result.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}
