// Round n92: the chat demo on the start page. Prints JSON facts for tests/test_browser.py: at 375 x 812 and 1280 x 800,
// light and dark, the whole flow once by mouse and once by keyboard; what loads before and after the first click; the
// storage before and after; Mascots: off; reduced motion; the plan failing to load; no JavaScript. With SHOTS=<dir> it
// also saves screenshots there.
// Everything runs under the start page's own content security policy (connect-src: /check's engine files and
// /demo/plan.json on this host, server.py home_headers); nothing is bypassed.
const { chromium } = require('playwright');
const path = require('path');

const [base, exe] = process.argv.slice(2);
const SHOTS = process.env.SHOTS || '';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function shot(page, name) {
  if (!SHOTS) return;
  await wait(600);                                    // after the chat's own short animations
  await page.screenshot({ path: path.join(SHOTS, name + '.png') });
}

// the picks on screen now, by label
const picks = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-picks .kgc-pick')].map((b) => b.getAttribute('data-pick')));
async function waitPick(page, label) {
  await page.waitForFunction((l) => [...document.querySelectorAll('.kgc-picks .kgc-pick')].some((b) => b.getAttribute('data-pick') === l), label, { timeout: 15000 });
}
const lastText = (page, sel) => page.evaluate((s) => { const all = document.querySelectorAll(s); return all.length ? all[all.length - 1].innerText : ''; }, sel);
const wins = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-msg.win .kgc-bub')].map((b) => b.innerText.replace(/\s+/g, ' ').trim()));
const storage = (page) => page.evaluate(() => {
  const ls = {}; try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); } } catch (e) { /* none */ }
  const ss = {}; try { for (let i = 0; i < sessionStorage.length; i++) { const k = sessionStorage.key(i); ss[k] = sessionStorage.getItem(k); } } catch (e) { /* none */ }
  return { local: ls, session: ss, cookie: document.cookie };
});
const focusInfo = (page) => page.evaluate(() => {
  const a = document.activeElement, box = document.getElementById('kgcBox');
  return { inChat: !!(box && box.contains(a)), pick: a && a.getAttribute('data-pick'), id: a && a.id, cls: a && a.className,
           outline: a ? getComputedStyle(a).outlineStyle + ' ' + getComputedStyle(a).outlineWidth : '' };
});

async function flowByMouse(page, f, v) {
  await page.click('#kgcLaunch');
  await page.waitForSelector('#kgcBox:not([hidden])');
  await waitPick(page, 'Check the tables');
  f.firstPicks = await picks(page);
  f.firstLinks = await page.evaluate(() => [...document.querySelectorAll('.kgc-picks a')].map((a) => ({ href: a.getAttribute('href'), target: a.getAttribute('target') })));
  await shot(page, `chat-open@${v}`);
  await page.click('.kgc-pick[data-pick="Check the tables"]');
  await waitPick(page, 'Yes, add the link');
  f.facts = await page.evaluate(() => [...document.querySelectorAll('.kgc-facts b')].map((b) => b.textContent));
  f.links = await page.evaluate(() => [...document.querySelectorAll('.kgc-links li')].map((li) => li.innerText.trim()));
  f.question = await lastText(page, '.kgc-msg.thinker .kgc-bub');
  await shot(page, `chat-question@${v}`);
  await page.click('.kgc-pick[data-pick="Yes, add the link"]');
  await waitPick(page, 'Create a semantic model');
  f.linkAdded = await lastText(page, '.kgc-msg.win .kgc-bub');
  f.nextPicks = await picks(page);
  // a planned choice runs nothing: no steps, no result, only what exists today
  const before = await page.evaluate(() => ({ steps: document.querySelectorAll('.kgc-steps').length, wins: document.querySelectorAll('.kgc-msg.win').length, msgs: document.querySelectorAll('.kgc-msg').length }));
  for (const label of ['Fix data issues', 'Create a dbt flow']) {
    await page.click(`.kgc-pick[data-pick="${label}"]`);
    await page.click(`.kgc-pick[data-pick="${label}"]`, { force: true });          // a second click does nothing more
  }
  await wait(1500);
  const after = await page.evaluate(() => ({ steps: document.querySelectorAll('.kgc-steps').length, wins: document.querySelectorAll('.kgc-msg.win').length, msgs: document.querySelectorAll('.kgc-msg').length,
    disabled: [...document.querySelectorAll('.kgc-pick.planned')].map((b) => b.getAttribute('aria-disabled')),
    said: [...document.querySelectorAll('.kgc-msg.onto .kgc-bub')].slice(-2).map((b) => b.innerText.replace(/\s+/g, ' ').trim()),
    youSaid: [...document.querySelectorAll('.kgc-you')].map((x) => x.textContent) }));
  f.planned = { before, after };
  await shot(page, `chat-planned@${v}`);
  for (const label of ['Create a semantic model', 'Create an ontology', 'Draft data products']) {
    await waitPick(page, label);
    await page.click(`.kgc-pick[data-pick="${label}"]`);
  }
  await waitPick(page, 'Try your own files');
  f.results = await wins(page);
  f.end = await lastText(page, '.kgc-msg.onto .kgc-bub');
  f.endLinks = await page.evaluate(() => [...document.querySelectorAll('.kgc-picks a')].map((a) => ({ href: a.getAttribute('href'), target: a.getAttribute('target') })));
  f.endPicks = await picks(page);
  await shot(page, `chat-end@${v}`);
  f.allText = await page.evaluate(() => document.getElementById('kgcBox').innerText);
  f.box = await page.evaluate(() => { const r = document.getElementById('kgcBox').getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; });
  f.overflowX = await page.evaluate(() => { const l = document.querySelector('.kgc-log'); return l.scrollWidth - l.clientWidth; });
  await page.click('.kgc-close');
  f.afterClose = await page.evaluate(() => ({ hidden: document.getElementById('kgcBox').hidden, launchShown: !document.getElementById('kgcLaunch').hidden,
    focus: document.activeElement.id, expanded: document.getElementById('kgcLaunch').getAttribute('aria-expanded') }));
}

async function flowByKeyboard(page, f, v) {
  // Tab to the button from the last link of the page before it, then only Tab, Enter and Escape
  await page.evaluate(() => { const ls = [...document.querySelectorAll('main a[href], main button')].filter((x) => x.id !== 'kgcLaunch' && x.offsetParent); ls[ls.length - 1].focus(); });
  await page.keyboard.press('Tab');
  f.tabbedToLaunch = await page.evaluate(() => document.activeElement.id);
  f.launchFocus = (await focusInfo(page)).outline;
  await shot(page, `chat-launch-focus@${v}`);
  await page.keyboard.press('Enter');
  await page.waitForSelector('#kgcBox:not([hidden])');
  f.openFocus = await focusInfo(page);
  await waitPick(page, 'Check the tables');
  await page.keyboard.press('Tab');
  f.firstTab = await focusInfo(page);
  await shot(page, `chat-pick-focus@${v}`);
  const steps = [];
  const enterOn = async (label) => {
    await page.waitForFunction((l) => document.activeElement && document.activeElement.getAttribute('data-pick') === l, label, { timeout: 15000 });
    steps.push(label);
    await page.keyboard.press('Enter');
  };
  await enterOn('Check the tables');
  await enterOn('Yes, add the link');
  // the planned choice by keyboard: Tab to it, Enter, and nothing runs
  await page.waitForFunction(() => document.activeElement && document.activeElement.getAttribute('data-pick') === 'Create a semantic model', null, { timeout: 15000 });
  for (let i = 0; i < 10; i++) {
    if ((await focusInfo(page)).pick === 'Fix data issues') break;
    await page.keyboard.press('Tab');
  }
  f.plannedFocused = (await focusInfo(page)).pick;
  const n0 = await page.evaluate(() => document.querySelectorAll('.kgc-steps').length);
  await page.keyboard.press('Enter');
  await wait(800);
  f.plannedByKeyboard = { steps: (await page.evaluate(() => document.querySelectorAll('.kgc-steps').length)) - n0, focus: (await focusInfo(page)).pick,
                          said: await lastText(page, '.kgc-msg.onto .kgc-bub') };
  // Escape closes, the focus goes back to the button; Enter opens again where it was
  await page.keyboard.press('Escape');
  f.escape = await page.evaluate(() => ({ hidden: document.getElementById('kgcBox').hidden, focus: document.activeElement.id }));
  await page.keyboard.press('Enter');
  await page.waitForSelector('#kgcBox:not([hidden])');
  f.reopenedKept = await page.evaluate(() => document.querySelectorAll('.kgc-msg').length);
  await page.keyboard.press('Tab');
  for (let i = 0; i < 12; i++) {
    if ((await focusInfo(page)).pick === 'Create a semantic model') break;
    await page.keyboard.press('Tab');
  }
  await enterOn('Create a semantic model');
  await enterOn('Create an ontology');
  await enterOn('Draft data products');
  await page.waitForFunction(() => document.activeElement && document.activeElement.getAttribute('data-pick') === 'Try your own files', null, { timeout: 15000 });
  f.keyboardSteps = steps;
  f.keyboardResults = await wins(page);
  f.keyboardEndFocus = (await focusInfo(page)).pick;
  // Tab never leaves the chat at phone width
  const out = [];
  for (let i = 0; i < 25; i++) { await page.keyboard.press('Tab'); const fi = await focusInfo(page); if (!fi.inChat) out.push(fi.id || fi.cls); }
  for (let i = 0; i < 25; i++) { await page.keyboard.press('Shift+Tab'); const fi = await focusInfo(page); if (!fi.inChat) out.push(fi.id || fi.cls); }
  f.tabOutside = out;
  await page.keyboard.press('Escape');
  f.escapeEnd = await page.evaluate(() => ({ hidden: document.getElementById('kgcBox').hidden, focus: document.activeElement.id }));
}

(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = {};
  for (const [w, h] of [[375, 812], [1280, 800]]) {
    for (const scheme of ['light', 'dark']) {
      for (const mode of ['mouse', 'keyboard']) {
        const v = `${w}-${scheme}-${mode}`;
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme });
        const page = await ctx.newPage();
        const f = { errors: [], requests: [] };
        page.on('console', (m) => { if (m.type() === 'error') f.errors.push(m.text()); });
        page.on('pageerror', (e) => f.errors.push(String(e)));
        let clicked = false;
        page.on('request', (r) => { const u = new URL(r.url()); if (clicked) f.requests.push(u.origin === base ? u.pathname + (u.pathname.startsWith('/static/chat') ? '' : u.search) : r.url()); else f.before = (f.before || []).concat(u.pathname); });
        await page.goto(base + '/', { waitUntil: 'load' });
        await wait(1500);                                   // the chat never opens by itself
        f.onLoad = await page.evaluate(() => ({ box: !!document.getElementById('kgcBox'), launch: !!document.getElementById('kgcLaunch') && !document.getElementById('kgcLaunch').hidden,
          text: document.getElementById('kgcLaunch').innerText.trim(), chatScript: !!window.KrusgraphChat,
          css: [...document.querySelectorAll('link[rel=stylesheet]')].map((l) => new URL(l.href).pathname) }));
        f.storeBefore = await storage(page);
        // at the bottom of the page the button covers none of the footer's text or controls
        f.bottomCovers = await page.evaluate(async () => {
          window.scrollTo({ top: document.scrollingElement.scrollHeight, behavior: 'instant' });
          await new Promise((r) => setTimeout(r, 200));
          const b = document.getElementById('kgcLaunch').getBoundingClientRect();
          return [...document.querySelectorAll('footer a, footer button, footer p, footer span, main a, main button:not(#kgcLaunch)')].filter((el) => {
            const r = el.getBoundingClientRect();
            return r.width && r.height && r.left < b.right && r.right > b.left && r.top < b.bottom && r.bottom > b.top;
          }).map((el) => el.textContent.trim().slice(0, 40));
        });
        if (mode === 'mouse') await shot(page, `home-bottom@${v}`);
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
        clicked = true;
        if (mode === 'mouse') await flowByMouse(page, f, v); else await flowByKeyboard(page, f, v);
        f.storeAfter = await storage(page);
        f.cookies = (await ctx.cookies()).map((c) => c.name);
        out[v] = f;
        if (w === 375 && mode === 'mouse') {
          // open again at phone width: the page behind does not scroll and is inert
          await page.click('#kgcLaunch');
          await page.waitForSelector('#kgcBox:not([hidden])');
          const y0 = await page.evaluate(() => window.scrollY);
          await page.mouse.move(180, 20);                      // above the chat, over the page behind it
          await page.mouse.wheel(0, 600);
          await page.mouse.move(180, 400);                     // in the chat's log: it scrolls, the page does not
          await page.mouse.wheel(0, -2000);
          await wait(300);
          out[`phone@${scheme}`] = await page.evaluate((y) => {
            const de = getComputedStyle(document.documentElement).overflow, bo = getComputedStyle(document.body).overflow;
            const r = document.getElementById('kgcBox').getBoundingClientRect();
            return { scrolled: window.scrollY - y, htmlOverflow: de, bodyOverflow: bo, mainInert: document.querySelector('main').hasAttribute('inert'),
                     modal: document.getElementById('kgcBox').getAttribute('aria-modal'), top: r.top, height: r.height, width: r.width, vh: innerHeight, vw: innerWidth };
          }, y0);
          await page.keyboard.press('Escape');
          out[`phone@${scheme}`].afterClose = await page.evaluate(() => ({ inert: document.querySelectorAll('[inert]').length, lock: document.documentElement.classList.contains('kgc-lock') }));
        }
        await ctx.close();
      }
    }
  }

  // Mascots: off (the footer's switch): no figures, the button and every word stay
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(base + '/', { waitUntil: 'load' });
    await page.click('[data-mascot-toggle]');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    const f = {};
    f.launchText = await page.evaluate(() => document.getElementById('kgcLaunch').innerText.trim());
    f.launchFig = await page.evaluate(() => getComputedStyle(document.querySelector('#kgcLaunch .kgc-fig')).display);
    await page.click('#kgcLaunch');
    await waitPick(page, 'Check the tables');
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await waitPick(page, 'Yes, add the link');
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await waitPick(page, 'Create a semantic model');
    await page.click('.kgc-pick[data-pick="Create a semantic model"]');
    await waitPick(page, 'Create an ontology');
    f.figuresShown = await page.evaluate(() => [...document.querySelectorAll('#kgcBox .kgc-fig, #kgcBox svg.mascot')].filter((x) => getComputedStyle(x).display !== 'none' && x.getBoundingClientRect().width).length);
    f.results = await wins(page);
    f.question = await page.evaluate(() => [...document.querySelectorAll('.kgc-msg.thinker .kgc-bub')].map((b) => b.innerText).find((t) => t.includes('ship_to_id')) || '');
    await shot(page, 'chat-mascots-off@1280-light');
    out.mascotsOff = f;
    await ctx.close();
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, colorScheme: 'dark' });
    const page = await ctx.newPage();
    await page.goto(base + '/', { waitUntil: 'load' });
    await page.click('[data-mascot-toggle]');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.click('#kgcLaunch');
    await waitPick(page, 'Check the tables');
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await waitPick(page, 'Yes, add the link');
    await shot(page, 'chat-mascots-off@375-dark');
    out.mascotsOffPhone = await page.evaluate(() => [...document.querySelectorAll('#kgcBox svg.mascot')].filter((x) => x.getBoundingClientRect().width).length);
    await ctx.close();
  }

  // Reduce motion: no animation or transition runs, in the button or the chat, and the steps finish at once
  for (const w of [375, 1280]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 375 ? 812 : 800 }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.goto(base + '/', { waitUntil: 'load' });
    const f = {};
    f.launchTransition = await page.evaluate(() => getComputedStyle(document.getElementById('kgcLaunch')).transitionDuration);
    await page.hover('#kgcLaunch');
    f.launchTransform = await page.evaluate(() => getComputedStyle(document.getElementById('kgcLaunch')).transform);
    await page.click('#kgcLaunch');
    await waitPick(page, 'Check the tables');
    const t0 = Date.now();
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await waitPick(page, 'Yes, add the link');
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await waitPick(page, 'Create a semantic model');
    f.ms = Date.now() - t0;
    f.animations = await page.evaluate(() => document.getAnimations().map((a) => (a.animationName || a.transitionProperty || 'anim') + '@' + (a.effect && a.effect.target ? a.effect.target.className.baseVal || a.effect.target.className : '')));
    f.bits = await page.evaluate(() => document.querySelectorAll('.kgc-bit').length);
    await shot(page, `chat-reduced@${w}`);
    out[`reduced@${w}`] = f;
    await ctx.close();
  }

  // the plan cannot be fetched: a short text and a link to the check page's example
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.route('**/demo/plan.json', (r) => r.abort());
    await page.goto(base + '/', { waitUntil: 'load' });
    await page.click('#kgcLaunch');
    await page.waitForSelector('.kgc-msg');
    out.planFails = await page.evaluate(() => ({ text: document.querySelector('.kgc-log').innerText.replace(/\s+/g, ' ').trim(),
      links: [...document.querySelectorAll('.kgc-picks a')].map((a) => a.getAttribute('href')), buttons: document.querySelectorAll('.kgc-picks button').length }));
    await ctx.close();
  }

  // without JavaScript: no button, and the page is as before
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto(base + '/', { waitUntil: 'load' });
    out.noJs = await page.evaluate(() => { const b = document.getElementById('kgcLaunch'); return { exists: !!b, shown: !!(b && b.getBoundingClientRect().width), padded: document.body.classList.contains('has-kgc') }; });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
