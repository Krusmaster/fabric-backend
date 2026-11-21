// DOCV1: open the "Where Krusgraph is heading" page at 390 and 1280 px, light and dark, from the files the test wrote
// (no server: every request is answered from that map or refused), and print the page's widths as JSON.
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const files = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const b = await chromium.launch();
  const out = [];
  for (const [w, scheme] of [[390, 'light'], [390, 'dark'], [1280, 'light']]) {
    const p = await b.newPage({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    const external = [];
    await p.route('**/*', r => {
      const u = new URL(r.request().url());
      if (u.host !== 'krusgraph.test') { external.push(u.href); return r.abort(); }
      const f = files[u.pathname];
      return f ? r.fulfill({ status: 200, contentType: f[0], body: f[1] }) : r.abort();
    });
    await p.goto('http://krusgraph.test' + files.__page__);
    await p.waitForTimeout(200);
    out.push(await p.evaluate(([w, scheme, external]) => {
      const box = document.querySelector('.hs-scroll'), svg = document.querySelector('.hs-svg');
      const t = svg.querySelector('text.hs-t');
      return { w, scheme, external, page: document.documentElement.scrollWidth, inner: window.innerWidth,
               box: box.getBoundingClientRect().right, svgWidth: svg.getBoundingClientRect().width,
               font: parseFloat(getComputedStyle(t).fontSize) * svg.getBoundingClientRect().width / 1040,
               ink: getComputedStyle(t).fill };
    }, [w, scheme, external]));
    await p.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
