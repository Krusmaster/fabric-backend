// n244: how the browser tests open a page. Usage: const { open, settle, reloadSettled } = require('./browser_nav');
//
// 'networkidle' (no request for 500 ms) is a timing guess, not a state of the page. On CI's loaded runner (pytest -n auto,
// several Chromiums at once) it timed out at Playwright's 30 s on the home page in three of nine runs on 22 November 2026:
// six seconds after 'load' the home page fetches /check's engine ahead (14 MB of Pyodide, site.js, data-check-prefetch),
// so a page that has not gone quiet by then waits for that whole download as well.
//
// open():   for a test that reads the page's own elements. It waits for 'load' (the HTML, its scripts, styles and
//           images), for the element the test reads, and for the web fonts (layout is measured), not for the network.
// settle(): for a test whose assertion is about the network or storage itself (no third-party request, nothing stored
//           before consent, no failed request when the page closes): it keeps 'networkidle', with more time on CI.
const NAV_TIMEOUT = process.env.CI ? 120000 : 30000;

async function fontsReady(page) {
  await page.evaluate(() => document.fonts.ready.then(() => true));
}

async function open(page, url, ready) {
  if (!ready) throw new Error('open(): name the element the test reads');
  await page.goto(url, { waitUntil: 'load', timeout: NAV_TIMEOUT });
  await page.waitForSelector(ready, { state: 'attached', timeout: NAV_TIMEOUT });
  await fontsReady(page);
}

async function settle(page, url) {
  await page.goto(url, { waitUntil: 'networkidle', timeout: NAV_TIMEOUT });
}

async function reloadSettled(page) {
  await page.reload({ waitUntil: 'networkidle', timeout: NAV_TIMEOUT });
}

module.exports = { open, settle, reloadSettled, NAV_TIMEOUT };
