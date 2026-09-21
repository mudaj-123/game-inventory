const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage({ viewport: {width:390,height:844} });
  const errors=[]; page.on('pageerror', e=>{errors.push(e.message);console.error('Page error:',e.message);});
  await page.goto('http://127.0.0.1:18085');
  await page.fill('#login-username','browser-admin');
  await page.fill('#login-password','test-password');
  await page.click('#login-form button');
  await page.locator('#admin-button').waitFor({state:'visible'});
  await page.click('[data-mode-button="IN"]');
  await page.fill('#scanner-input','00007777'); await page.press('#scanner-input','Enter');
  await page.locator('#unknown-form').waitFor({state:'visible'});
  await page.fill('#unknown-game-name','浏览器验收游戏'); await page.selectOption('#unknown-platform','PS5');
  await page.click('#unknown-form button[type="submit"]');
  await page.locator('#unknown-form').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('库存 1'));
  await page.fill('#scanner-input','00007777'); await page.press('#scanner-input','Tab');
  await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('库存 2'));
  let dropped = false;
  await page.route('**/api/scans', async route => {
    if (!dropped) { dropped = true; await route.fetch(); await route.abort(); }
    else await route.continue();
  });
  await page.fill('#scanner-input','00007777'); await page.press('#scanner-input','Enter');
  await page.locator('#retry-scan').waitFor({state:'visible'});
  await page.click('#retry-scan');
  await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('库存 3'));
  await page.click('#exit-scan'); await page.click('#admin-button');
  await page.waitForFunction(()=>document.querySelector('#product-list').textContent.includes('库存 3'));
  await page.screenshot({path:'/tmp/game-inventory-admin.png',fullPage:true});
  if(errors.length) throw new Error(errors.join('\n'));
  console.log('Browser login, unknown resolution, Enter/Tab scans, lost-response idempotent retry and admin dashboard passed');
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
