/**
 * Krusgraph Model editor screenshots for the website docs.
 *
 * Bundles harness.tsx (the editor's own views, fixtures from build_fixtures.py) with esbuild from
 * workload/Workload/node_modules, compiling the editor's .scss with the `sass` package, serves the bundle on 127.0.0.1
 * and saves one PNG per view with Playwright (1280x800 viewport, deviceScaleFactor 1, cropped to the content, at most
 * MAX_HEIGHT px) into fabric_backend/static/workload-shots/, each also as .webp (Chromium's own encoder). Nothing is
 * fetched from the network.
 *
 *   node workload/scripts/screens/shoot.js            # from the repository root
 */
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const HERE = __dirname;
const ROOT = path.resolve(HERE, "../../..");
const MODULES = path.join(ROOT, "workload/Workload/node_modules");
const OUT = path.join(ROOT, "fabric_backend/static/workload-shots");
const DIST = fs.mkdtempSync(path.join(os.tmpdir(), "krusgraph-screens-"));
const MAX_HEIGHT = 1400;
const SHOTS = [
  ["review", "model-review.png"],
  ["outputs", "model-outputs.png"],
  ["flow", "model-flow.png"],
  // the dry run's cards, one per output, as the preview shows them below the data flow (scrolled to the first card)
  ["preview", "model-preview-cards.png", "section.krusgraph-output[data-output]"],
];
const LABEL_HEIGHT = 31;
const WEBP_QUALITY = 0.9;

const esbuild = require(path.join(MODULES, "esbuild"));
const sass = require(path.join(MODULES, "sass"));
const { chromium } = require("playwright");

const scssPlugin = {
  name: "scss",
  setup(build) {
    build.onLoad({ filter: /\.scss$/ }, (args) => ({
      contents: sass.compile(args.path, { loadPaths: [path.dirname(args.path), MODULES] }).css,
      loader: "css",
    }));
  },
};

async function bundle() {
  await esbuild.build({
    entryPoints: { harness: path.join(HERE, "harness.tsx") },
    bundle: true,
    outdir: DIST,
    format: "iife",
    platform: "browser",
    target: "es2019",
    jsx: "transform",
    nodePaths: [MODULES],
    define: { "process.env.NODE_ENV": '"production"' },
    loader: { ".svg": "dataurl", ".png": "dataurl" },
    plugins: [scssPlugin],
    logLevel: "warning",
  });
  fs.copyFileSync(path.join(HERE, "index.html"), path.join(DIST, "index.html"));
}

function serve() {
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };
  const server = http.createServer((req, res) => {
    const file = path.join(DIST, path.normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^[/\\]+/, "") || "index.html");
    if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" }).end(fs.readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** The PNG next to itself as .webp (quality WEBP_QUALITY), encoded by Chromium's canvas: no other tool needed. */
async function toWebp(coder, png) {
  const b64 = fs.readFileSync(png).toString("base64");
  const data = await coder.evaluate(async ([src, q]) => {
    const img = new Image();
    img.src = src;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/webp", q);
  }, [`data:image/png;base64,${b64}`, WEBP_QUALITY]);
  if (!data.startsWith("data:image/webp;base64,")) throw new Error("this Chromium does not encode WebP");
  const out = png.replace(/\.png$/, ".webp");
  fs.writeFileSync(out, Buffer.from(data.split(",")[1], "base64"));
  return out;
}

async function main() {
  await bundle();
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/index.html`;
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const coder = await browser.newPage();                          // encodes each PNG as WebP with Chromium's canvas
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("request", (r) => {
    if (!r.url().startsWith(`http://127.0.0.1:`) && !r.url().startsWith("data:")) errors.push(`blocked request: ${r.url()}`);
  });
  await page.route(/^(?!http:\/\/127\.0\.0\.1:|data:)/, (route) => route.abort());
  for (const [view, file, start] of SHOTS) {
    await page.setViewportSize({ width: 1280, height: start ? MAX_HEIGHT : 800 });
    await page.goto(`${base}#${view}`);
    await page.waitForSelector(`#screen[data-view="${view}"] .krusgraph-view, #screen[data-view="${view}"] .krusgraph-flow`);
    await page.waitForTimeout(400);                                  // the map draws after the first render
    const target = path.join(OUT, file);
    let clip, height;
    if (start) {
      // scrolled as a reader would scroll the editor; the fixed label stays on top of the viewport. The viewport is as
      // tall as the label plus everything from `start` down (at most MAX_HEIGHT), so the page can scroll to `start`.
      const rest = await page.evaluate((sel) => {
        const screen = document.getElementById("screen").getBoundingClientRect().bottom + window.scrollY;
        return Math.ceil(screen - (document.querySelector(sel).getBoundingClientRect().top + window.scrollY));
      }, start);
      await page.setViewportSize({ width: 1280, height: Math.min(rest + LABEL_HEIGHT + 16, MAX_HEIGHT) });
      height = await page.evaluate(([sel, top]) => {
        const y = document.querySelector(sel).getBoundingClientRect().top + window.scrollY - top - 16;
        window.scrollTo(0, y);
        return Math.ceil(document.getElementById("screen").getBoundingClientRect().bottom);
      }, [start, LABEL_HEIGHT]);
      await page.waitForTimeout(100);
      clip = { x: 0, y: 0, width: 1280, height: Math.min(height, MAX_HEIGHT) };
      await page.screenshot({ path: target, clip });
    } else {
      height = await page.evaluate(() => Math.ceil(document.getElementById("screen").getBoundingClientRect().bottom));
      clip = { x: 0, y: 0, width: 1280, height: Math.min(height, MAX_HEIGHT) };
      await page.screenshot({ path: target, clip, fullPage: true });
    }
    const webp = await toWebp(coder, target);
    const kb = (f) => Math.round(fs.statSync(f).size / 1024);
    console.log(`${path.relative(ROOT, target)}: ${clip.width}x${clip.height} (content ${height} px), ${kb(target)} KB; .webp ${kb(webp)} KB`);
    if (!process.argv.includes("--keep-png")) fs.rmSync(target);   // n177: the site serves the .webp only
  }
  await browser.close();
  server.close();
  fs.rmSync(DIST, { recursive: true, force: true });
  if (errors.length) {
    console.error("page errors:\n" + errors.join("\n"));
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
