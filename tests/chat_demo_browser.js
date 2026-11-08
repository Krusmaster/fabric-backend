// Round n92: the chat demo on the start page; n93: its pictures, Connect to /start, the button on every ordinary page and
// the memory within the tab. Prints JSON facts for tests/test_browser.py: at 375 x 812 and 1280 x 800, light and dark,
// the whole flow once by mouse and once by keyboard; what loads before and after the first click; the storage before and
// after; the pictures inside their bubbles and Larger picture; a page change with the chat open and closed; a link inside
// the chat; Start over; a corrupt stored value; blocked storage; Mascots: off; reduced motion; the plan failing to load;
// no JavaScript; every page with its button (CHAT_PAGES, from test_browser.py) and what the button may cover. With
// SHOTS=<dir> it also saves screenshots there.
// Everything runs under the pages' own content security policies (the start page's connect-src: /check's engine files and
// /demo/plan.json on this host, server.py home_headers; the other pages' connect-src 'self'); nothing is bypassed. Only
// "blocked storage" adds an init script, which makes sessionStorage throw as a browser that refuses storage does.
const { chromium } = require('playwright');
const path = require('path');

const [base, exe] = process.argv.slice(2);
const SHOTS = process.env.SHOTS || '';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// waitForFunction evaluates a string in newer Playwright, which the start page's CSP (no 'unsafe-eval') refuses: poll
async function until(page, fn, arg, what) {
  for (let i = 0; i < 300; i++) { if (await page.evaluate(fn, arg)) return; await wait(50); }
  throw new Error('timeout: ' + (what || arg));
}

async function shot(page, name) {
  if (!SHOTS) return;
  await wait(600);                                    // after the chat's own short animations
  await page.screenshot({ path: path.join(SHOTS, name + '.png') });
}

// the picks on screen now, by label
const picks = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-picks .kgc-pick')].map((b) => b.getAttribute('data-pick')));
async function waitPick(page, label) {
  await until(page, (l) => [...document.querySelectorAll('.kgc-picks .kgc-pick')].some((b) => b.getAttribute('data-pick') === l), label);
}
const lastText = (page, sel) => page.evaluate((s) => { const all = document.querySelectorAll(s); return all.length ? all[all.length - 1].innerText : ''; }, sel);
const wins = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-msg.win .kgc-bub')].map((b) => b.innerText.replace(/\s+/g, ' ').trim()));
const KEY = 'krusgraph.chat';
const PAGES = JSON.parse(process.env.CHAT_PAGES || '[]');
const stored = (page) => page.evaluate((k) => { try { return sessionStorage.getItem(k); } catch (e) { return 'blocked'; } }, KEY);
const chatState = (page) => page.evaluate(() => {
  const box = document.getElementById('kgcBox'), a = document.activeElement;
  const r = box ? box.getBoundingClientRect() : null;
  return { loaded: !!window.KrusgraphChat, box: !!box, open: !!box && !box.hidden, still: !!box && box.classList.contains('kgc-still'),
           msgs: document.querySelectorAll('.kgc-msg').length, pics: document.querySelectorAll('.kgc-pic').length,
           you: [...document.querySelectorAll('.kgc-you')].map((x) => x.textContent),
           focusInChat: !!(box && box.contains(a)), focus: a ? (a.id || a.tagName) : '', bits: document.querySelectorAll('.kgc-bit').length,
           anims: document.getAnimations().filter((x) => x.effect && x.effect.target && x.effect.target.closest && x.effect.target.closest('.kgc'))
             .map((x) => (x.animationName || x.transitionProperty || 'animation') + '@' + (x.effect.target.getAttribute('class') || x.effect.target.tagName)),
           launchShown: !!document.getElementById('kgcLaunch') && !document.getElementById('kgcLaunch').hidden,
           rect: r && !box.hidden ? { right: Math.round(innerWidth - r.right), bottom: Math.round(innerHeight - r.bottom), width: Math.round(r.width), height: Math.round(r.height) } : null };
});
// what each picture in the chat shows, and whether it stays inside its bubble and is readable without zoom
const pictures = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-log .kgc-pic')].map((fig) => {
  const svg = fig.querySelector('svg'), bub = fig.closest('.kgc-bub'), sr = svg.getBoundingClientRect(), br = bub.getBoundingClientRect();
  const pad = parseFloat(getComputedStyle(bub).paddingRight) + parseFloat(getComputedStyle(bub).borderRightWidth);
  const scale = sr.width / svg.viewBox.baseVal.width;
  const nodes = [...svg.querySelectorAll('.kgc-n')];
  const label = (g) => g.querySelector(':scope > text');
  const fit = nodes.every((g) => { const t = label(g).getBBox(), r = g.querySelector(':scope > rect').getBBox(); return t.x >= r.x + 2 && t.x + t.width <= r.x + r.width - 2; });
  const fonts = nodes.map((g) => parseFloat(getComputedStyle(label(g)).fontSize) * scale);
  const boxes = nodes.map((g) => g.querySelector(':scope > rect').getBBox());
  const overlap = boxes.some((a, i) => boxes.some((b, j) => i < j && a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height));
  const groups = [...svg.querySelectorAll('.kgc-grp rect')].map((r) => r.getBBox());
  const inGroup = (name) => { const g = nodes.find((n) => label(n).textContent === name); if (!g) return null; const r = g.querySelector(':scope > rect').getBBox();
    return groups.some((b) => r.x >= b.x && r.x + r.width <= b.x + b.width && r.y >= b.y && r.y + r.height <= b.y + b.height); };
  return { role: svg.getAttribute('role'), desc: svg.getAttribute('aria-label') || '', names: nodes.map((g) => label(g).textContent),
           keys: svg.querySelectorAll('.kgc-key').length, nokey: nodes.filter((g) => g.classList.contains('nokey')).map((g) => label(g).textContent),
           edges: svg.querySelectorAll('.kgc-e').length, kinds: ['new', 'off', 'iface', 'faint'].reduce((o, k) => (o[k] = svg.querySelectorAll('.kgc-e.' + k).length, o), {}),
           groupNames: [...svg.querySelectorAll('.kgc-grp text')].map((t) => t.textContent), outside: inGroup('audit_log'),
           inside: sr.left >= br.left - 0.5 && sr.right <= br.right - pad + 0.5, width: Math.round(sr.width), fit, overlap,
           minFont: Math.round(Math.min.apply(null, fonts) * 10) / 10, zoom: !!fig.querySelector('.kgc-zoom'),
           textBeside: bub.innerText.replace(/\s+/g, ' ').replace('Larger picture', '').trim().length };
}));
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
  // n154: Fix data issues and Write dbt tests are links to the docs of what exists today, with that in one line
  f.further = await page.evaluate(() => ['Fix data issues', 'Draft a dbt project'].map((l) => {
    const a = document.querySelector(`.kgc-pick[data-pick="${l}"]`);
    return a ? { tag: a.tagName, href: a.getAttribute('href'), planned: a.classList.contains('planned'), why: (a.querySelector('small') || {}).textContent || '' } : null;
  }));
  await shot(page, `chat-further@${v}`);
  for (const label of ['Create a semantic model', 'Create an ontology', 'Draft data products']) {
    await waitPick(page, label);
    await page.click(`.kgc-pick[data-pick="${label}"]`);
  }
  await waitPick(page, 'Check my tables');
  f.results = await wins(page);
  f.end = await lastText(page, '.kgc-msg.onto .kgc-bub');
  f.endLinks = await page.evaluate(() => [...document.querySelectorAll('.kgc-picks a')].map((a) => ({ href: a.getAttribute('href'), target: a.getAttribute('target') })));
  f.endPicks = await picks(page);
  f.endWhy = await page.evaluate(() => { const a = document.querySelector('.kgc-pick[data-pick="Connect to my Fabric"] small'); return a ? a.textContent : ''; });
  f.pics = await pictures(page);
  f.logOverflowX = await page.evaluate(() => { const l = document.querySelector('.kgc-log'); return l.scrollWidth - l.clientWidth; });
  f.pageOverflowX = await page.evaluate(() => document.scrollingElement.scrollWidth - innerWidth);
  await shot(page, `chat-end@${v}`);
  for (let i = 0; SHOTS && i < f.pics.length; i++) {
    const el = (await page.$$('.kgc-log .kgc-pic'))[i];
    await el.scrollIntoViewIfNeeded();
    await wait(200);
    await el.screenshot({ path: path.join(SHOTS, `chat-pic${i}@${v}.png`) });
  }
  // Larger picture: inside the chat, at its full width, no sideways scroll; Esc returns to the button that opened it
  const zoom = (await page.$$('.kgc-log .kgc-zoom'))[4];
  await zoom.scrollIntoViewIfNeeded();
  await zoom.click();
  await page.waitForSelector('.kgc-big');
  f.big = await page.evaluate(() => {
    const big = document.querySelector('.kgc-big'), svg = big.querySelector('svg'), body = big.querySelector('.kgc-big-body');
    const box = document.getElementById('kgcBox').getBoundingClientRect(), r = big.getBoundingClientRect();
    return { focus: document.activeElement.className, width: Math.round(svg.getBoundingClientRect().width), overflowX: body.scrollWidth - body.clientWidth,
             covers: Math.abs(r.width - box.width) < 3, text: body.innerText.replace(/\s+/g, ' ').trim(), logInert: document.querySelector('.kgc-log').hasAttribute('inert') };
  });
  await shot(page, `chat-larger@${v}`);
  await page.keyboard.press('Escape');
  f.bigClosed = await page.evaluate(() => ({ big: !!document.querySelector('.kgc-big'), open: !document.getElementById('kgcBox').hidden,
    focus: document.activeElement.className, pic: document.activeElement.getAttribute('data-pic') }));
  f.allText = await page.evaluate(() => document.getElementById('kgcBox').innerText);
  f.notes = await page.evaluate(() => [...document.querySelectorAll('.kgc-note')].map((n) => n.textContent));
  f.box = await page.evaluate(() => { const r = document.getElementById('kgcBox').getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; });
  f.overflowX = await page.evaluate(() => { const l = document.querySelector('.kgc-log'); return l.scrollWidth - l.clientWidth; });
  await page.click('.kgc-close');
  f.afterClose = await page.evaluate(() => ({ hidden: document.getElementById('kgcBox').hidden, launchShown: !document.getElementById('kgcLaunch').hidden,
    focus: document.activeElement.id, expanded: document.getElementById('kgcLaunch').getAttribute('aria-expanded') }));
}

async function flowByKeyboard(page, f, v) {
  // Tab to the button from the last link or button of the page before it (the footer's), then only Tab, Enter and Escape
  await page.evaluate(() => { const ls = [...document.querySelectorAll('footer a[href], footer button')].filter((x) => x.offsetParent); ls[ls.length - 1].focus(); });
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
    await until(page, (l) => document.activeElement && document.activeElement.getAttribute('data-pick') === l, label, 'focus on ' + label);
    steps.push(label);
    await page.keyboard.press('Enter');
  };
  await enterOn('Check the tables');
  await enterOn('Yes, add the link');
  // n154: Tab reaches the link to what exists for fixing data (Enter would follow it; the flow goes on here)
  await until(page, (l) => document.activeElement && document.activeElement.getAttribute('data-pick') === l, 'Create a semantic model', 'focus on Create a semantic model');
  for (let i = 0; i < 10; i++) {
    if ((await focusInfo(page)).pick === 'Fix data issues') break;
    await page.keyboard.press('Tab');
  }
  f.furtherFocused = await page.evaluate(() => ({ pick: document.activeElement.getAttribute('data-pick'), tag: document.activeElement.tagName,
                                                   href: document.activeElement.getAttribute('href') }));
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
  await until(page, (l) => document.activeElement && document.activeElement.getAttribute('data-pick') === l, 'Check my tables', 'focus on Check my tables');
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
        await page.goto(base + '/use-cases', { waitUntil: 'load' });
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
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
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
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
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
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
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
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
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
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
    out.noJs = await page.evaluate(() => { const b = document.getElementById('kgcLaunch'); return { exists: !!b, shown: !!(b && b.getBoundingClientRect().width), padded: document.body.classList.contains('has-kgc') }; });
    await page.goto(base + '/docs', { waitUntil: 'load' });
    out.noJsDocs = await page.evaluate(() => { const b = document.getElementById('kgcLaunch'); return { exists: !!b, shown: !!(b && b.getBoundingClientRect().width) }; });
    await ctx.close();
  }

  // ------------------------------------------------------------------ n93: the memory within the tab
  // the steps up to the link, by mouse
  async function stepsToLink(page) {
    await page.click('#kgcLaunch');
    await waitPick(page, 'Check the tables');
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await waitPick(page, 'Yes, add the link');
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await waitPick(page, 'Create a semantic model');
  }
  const ownRequests = (page, list) => page.on('request', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/static/chat') || u.pathname === '/demo/plan.json') list.push(u.pathname); });

  // a page change with the chat open, then closed: at 1280 it comes back as it was, where it was, without animation, without
  // the focus; at 375 it stays closed until the button is pressed
  for (const [w, h] of [[1280, 800], [375, 812]]) {
    for (const scheme of ['light', 'dark']) {
      const v = `${w}-${scheme}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme });
      const page = await ctx.newPage();
      const f = { errors: [] };
      page.on('console', (m) => { if (m.type() === 'error') f.errors.push(m.text()); });
      page.on('pageerror', (e) => f.errors.push(String(e)));
      await page.goto(base + '/use-cases', { waitUntil: 'load' });
      await stepsToLink(page);
      await wait(1200);
      f.before = await chatState(page);
      f.storedOpen = await stored(page);
      // by the menu at 1280; at 375 the chat covers the page and its menu, so the next page is opened directly
      let reqs = [];
      ownRequests(page, reqs);
      if (w === 1280) await page.click('.site-nav a[href="/docs"]'); else await page.goto(base + '/docs');
      await page.waitForURL('**/docs');
      await page.waitForLoadState('load');
      await wait(w === 1280 ? 800 : 1500);
      if (w === 1280) await until(page, () => !!document.getElementById('kgcBox') && !document.getElementById('kgcBox').hidden, null, 'restored');
      f.after = await chatState(page);
      f.afterRequests = reqs.slice();
      f.afterPics = w === 1280 ? await pictures(page) : [];
      await shot(page, `chat-restored@${v}`);
      if (w === 1280) {
        // the page beside it still takes Esc and the keyboard: Esc on the page does not close the chat
        await page.focus('main');
        await page.keyboard.press('Escape');
        f.escOnPage = (await chatState(page)).open;
        await page.click('.kgc-close');
        f.closedStored = await stored(page);
        reqs = [];
        ownRequests(page, reqs);
        await page.click('.site-nav a[href="/pricing"]');
        await page.waitForURL('**/pricing');
        await page.waitForLoadState('load');
        await wait(1200);
        f.closedNext = await chatState(page);
        f.closedRequests = reqs.slice();
      }
      // the button opens it with its steps, the focus on Close
      await page.click('#kgcLaunch');
      await until(page, () => document.querySelectorAll('.kgc-you').length >= 2, null, 'steps back');
      await wait(300);
      f.reopened = await chatState(page);
      out[`pagechange@${v}`] = f;
      await ctx.close();
    }
  }

  // a link inside the chat closes it, and its steps are there at the next open: Connect to my Fabric goes to /start
  for (const [w, h] of [[1280, 800], [375, 812]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    const f = {};
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
    await stepsToLink(page);
    for (const label of ['Create a semantic model', 'Create an ontology', 'Draft data products']) {
      await waitPick(page, label);
      await page.click(`.kgc-pick[data-pick="${label}"]`);
    }
    await waitPick(page, 'Connect to my Fabric');
    await page.click('.kgc-pick[data-pick="Connect to my Fabric"]');
    await page.waitForURL('**/start');
    await page.waitForLoadState('load');
    await wait(1200);
    f.url = new URL(page.url()).pathname;
    f.title = await page.title();
    f.stored = JSON.parse(await stored(page));
    f.after = await chatState(page);
    await page.click('#kgcLaunch');
    await until(page, () => document.querySelectorAll('.kgc-msg.win').length === 4, null, 'results back');
    await wait(300);
    f.reopened = await chatState(page);
    f.endPicks = await picks(page);
    out[`link@${w}`] = f;
    await ctx.close();
  }

  // Start over: the steps go, the chat begins again, the focus on its first choice
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(base + '/pricing', { waitUntil: 'load' });
    await stepsToLink(page);
    const f = { before: JSON.parse(await stored(page)) };
    await page.click('.kgc-restart');
    await waitPick(page, 'Check the tables');
    await wait(300);
    f.after = await chatState(page);
    f.stored = JSON.parse(await stored(page));
    f.focus = await page.evaluate(() => document.activeElement.getAttribute('data-pick'));
    await shot(page, 'chat-start-over@1280-light');
    await page.goto(base + '/docs', { waitUntil: 'load' });
    await until(page, () => !!document.getElementById('kgcBox') && !document.getElementById('kgcBox').hidden, null, 'restored after start over');
    await wait(300);
    f.next = await chatState(page);
    out.startOver = f;
    await ctx.close();
  }

  // a corrupt or foreign value under the key: ignored, nothing of it shown or run; the chat starts as on a first visit
  {
    const values = ['not json', 'x'.repeat(5000), '[1,2,3]', 'null', '{"open":"yes","steps":[]}', '{"open":true,"steps":"scan"}',
      '{"open":true,"steps":["<img src=x onerror=window.__kgcx=1>"]}', '{"open":true,"steps":["scan","scan"]}',
      '{"open":true,"steps":["scan","<b>x</b>"]}', '{"open":true,"steps":["toString"]}', '{"open":true,"steps":["__proto__"]}'];
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(String(e)));
    const res = [];
    for (const val of values) {
      await page.goto(base + '/check', { waitUntil: 'load' });              // no chat there to write over the value
      await page.evaluate(([k, x]) => sessionStorage.setItem(k, x), [KEY, val]);
      await page.goto(base + '/docs', { waitUntil: 'load' });
      await wait(900);
      const r = { value: val.slice(0, 60), state: await chatState(page) };
      await page.click('#kgcLaunch');
      await waitPick(page, 'Check the tables');
      await wait(200);
      r.opened = await chatState(page);
      r.injected = await page.evaluate(() => ({ img: document.querySelectorAll('#kgcBox img').length + [...document.querySelectorAll('#kgcBox b')].filter((x) => x.textContent === 'x').length, flag: !!window.__kgcx }));
      r.storedAfter = await stored(page);
      res.push(r);
    }
    // the same shape with extra keys: what is known is used, the rest ignored
    await page.goto(base + '/check', { waitUntil: 'load' });
    await page.evaluate((k) => sessionStorage.setItem(k, '{"open":true,"steps":["scan","yes"],"html":"<b>x</b>","x":1}'), KEY);
    await page.goto(base + '/docs', { waitUntil: 'load' });
    await until(page, () => !!document.getElementById('kgcBox') && !document.getElementById('kgcBox').hidden, null, 'restored with extra keys');
    await wait(300);
    out.corrupt = { results: res, extra: await chatState(page), extraInjected: await page.evaluate(() => [...document.querySelectorAll('#kgcBox b')].filter((x) => x.textContent === 'x').length), errors };
    await ctx.close();
  }

  // storage refused (sessionStorage throws): the chat works as in n92 and forgets on the next page
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await ctx.addInitScript(() => {
      Object.defineProperty(window, 'sessionStorage', { configurable: true, get() { throw new DOMException('refused', 'SecurityError'); } });
    });
    const page = await ctx.newPage();
    const f = { errors: [] };
    page.on('console', (m) => { if (m.type() === 'error') f.errors.push(m.text()); });
    page.on('pageerror', (e) => f.errors.push(String(e)));
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
    await stepsToLink(page);
    await page.click('.kgc-pick[data-pick="Create a semantic model"]');
    await waitPick(page, 'Create an ontology');
    f.results = await wins(page);
    f.pics = (await pictures(page)).length;
    await page.click('.kgc-restart');
    await waitPick(page, 'Check the tables');
    f.afterStartOver = await chatState(page);
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await waitPick(page, 'Yes, add the link');
    await page.click('.site-nav a[href="/docs"]');
    await page.waitForURL('**/docs');
    await page.waitForLoadState('load');
    await wait(1200);
    f.next = await chatState(page);
    await page.click('#kgcLaunch');
    await waitPick(page, 'Check the tables');
    f.reopened = await chatState(page);
    out.blocked = f;
    await ctx.close();
  }

  // reduced motion and Mascots: off on a restored chat: no animation, the pictures stay
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.goto(base + '/use-cases', { waitUntil: 'load' });
    await page.click('[data-mascot-toggle]');
    await stepsToLink(page);
    await page.click('.site-nav a[href="/use-cases"]');
    await page.waitForURL('**/use-cases');
    await until(page, () => !!document.getElementById('kgcBox') && !document.getElementById('kgcBox').hidden, null, 'restored, reduced');
    await wait(300);
    out.restoredReduced = { state: await chatState(page), pics: await pictures(page),
      figures: await page.evaluate(() => [...document.querySelectorAll('#kgcBox svg.mascot')].filter((x) => x.getBoundingClientRect().width).length),
      svgShown: await page.evaluate(() => [...document.querySelectorAll('#kgcBox .kgc-svg')].filter((x) => x.getBoundingClientRect().width > 100).length) };
    await shot(page, 'chat-restored-mascots-off@1280-light');
    await ctx.close();
  }

  // every page: the button where it belongs, and at the bottom of each page it covers no text or control; no fixed or
  // sticky part of a page sits under it
  {
    const res = {};
    for (const [w, h] of [[375, 812], [1280, 800]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await ctx.newPage();
      const errors = [];
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', (e) => errors.push(String(e)));
      for (const p of PAGES.concat(['/check', '/demo'])) {
        await page.goto(base + p, { waitUntil: 'load' });
        await wait(150);
        res[`${p}@${w}`] = await page.evaluate(async () => {
          const b = document.getElementById('kgcLaunch');
          const shown = !!b && !b.hidden && b.getBoundingClientRect().width > 0;
          if (!shown) return { button: !!b, shown, path: location.pathname, chat: !!window.KrusgraphChat };
          window.scrollTo({ top: document.scrollingElement.scrollHeight, behavior: 'instant' });
          await new Promise((r) => setTimeout(r, 200));
          const br = b.getBoundingClientRect();
          const hit = (r) => r.width && r.height && r.left < br.right && r.right > br.left && r.top < br.bottom && r.bottom > br.top;
          // what would be seen there without the button: an element only counts where it shows (not where a parent clips it)
          b.style.visibility = 'hidden';
          const seen = (el) => {
            const r = el.getBoundingClientRect(), x0 = Math.max(r.left, br.left), x1 = Math.min(r.right, br.right), y0 = Math.max(r.top, br.top), y1 = Math.min(r.bottom, br.bottom);
            for (const fx of [0.1, 0.5, 0.9]) for (const fy of [0.2, 0.5, 0.8]) {
              const at = document.elementFromPoint(x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy);
              if (at && (at === el || el.contains(at))) return true;
            }
            return false;
          };
          const covers = [...document.querySelectorAll('a, button, input, select, textarea, label, p, li, td, th, h1, h2, h3, h4, dt, dd, code, pre, img, svg, figcaption, summary')]
            .filter((el) => el !== b && !b.contains(el) && !el.closest('#kgcLaunch') && getComputedStyle(el).visibility !== 'hidden' && hit(el.getBoundingClientRect()) && seen(el))
            .map((el) => el.tagName + ':' + (el.textContent || '').trim().slice(0, 30));
          b.style.visibility = '';
          const fixed = [...document.querySelectorAll('body *')].filter((el) => el !== b && !b.contains(el) && /fixed|sticky/.test(getComputedStyle(el).position) &&
            getComputedStyle(el).display !== 'none' && hit(el.getBoundingClientRect())).map((el) => el.tagName + '.' + el.className);
          return { button: true, shown, path: location.pathname, covers, fixed, chat: !!window.KrusgraphChat, text: b.innerText.trim() };
        });
      }
      res[`errors@${w}`] = errors;
      await ctx.close();
    }
    out.pages = res;
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
