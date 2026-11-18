/** W13: bundles harness.tsx (the real editor and the host stand-in) into the folder given, as shoot.js does. */
const fs = require("fs");
const path = require("path");
const HERE = __dirname;
const MODULES = path.resolve(HERE, "../../Workload/node_modules");
const esbuild = require(path.join(MODULES, "esbuild"));
const sass = require(path.join(MODULES, "sass"));

async function bundle(out) {
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({
    entryPoints: { harness: path.join(HERE, "harness.tsx") },
    bundle: true, outdir: out, format: "iife", platform: "browser", target: "es2019", jsx: "transform",
    nodePaths: [MODULES], sourcemap: false,
    define: {
      "process.env.NODE_ENV": '"production"', "process.env.WORKLOAD_NAME": '"Org.Krusgraph"',
      "process.env.ITEM_NAMES": '"Model"', "process.env.KRUSGRAPH_ENGINE_URL": '""',
      "process.env.KRUSGRAPH_ENGINE_SCOPE": '"api://localdevinstance/e2e/Org.Krusgraph/Ab/user_impersonation"',
      "process.env.LOG_LEVEL": '""', "process.env.WORKLOAD_VERSION": '"e2e"',
    },
    loader: { ".svg": "dataurl", ".png": "dataurl", ".json": "json" },
    plugins: [{ name: "scss", setup(b) { b.onLoad({ filter: /\.scss$/ }, (a) => ({ contents: sass.compile(a.path, { loadPaths: [path.dirname(a.path), MODULES] }).css, loader: "css" })); } }],
    logLevel: "warning",
  });
  fs.copyFileSync(path.join(HERE, "index.html"), path.join(out, "index.html"));
  fs.copyFileSync(path.join(HERE, "frame.html"), path.join(out, "frame.html"));   // WB10: the editor in Fabric's sandbox
  // the app's static assets (icons, mascots, empty-state image), served at /assets as webpack's copy plugin does
  fs.cpSync(path.resolve(HERE, "../../Workload/app/assets"), path.join(out, "assets"), { recursive: true });
  // Fabric's own item icons, copied as webpack.config.js copies them (fabricIcons.json)
  const icons = require(path.resolve(HERE, "../../Workload/app/items/ModelItem/fabricIcons.json"));
  const into = path.join(out, icons.servedAt.replace(/^\/+/, ""));
  fs.mkdirSync(into, { recursive: true });
  for (const f of Object.keys(icons.files)) fs.copyFileSync(path.resolve(HERE, "../../Workload", icons.sourceDir, f), path.join(into, f));
}
module.exports = { bundle };
if (require.main === module) bundle(process.argv[2] || path.join(HERE, "dist")).then(() => console.log("bundled"));
