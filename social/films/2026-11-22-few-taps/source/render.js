// Renders film.html to a silent MP4, one screenshot per frame (30 fps).
// Usage, from the repository root:
//   node social/films/2026-11-22-few-taps/source/render.js out.mp4
// Needs Playwright with Chromium, and ffmpeg on the PATH.
const {chromium}=require('playwright');const {spawn}=require('child_process');
(async()=>{const out=process.argv[2]||'film.mp4';const b=await chromium.launch();
const p=await b.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
await p.goto('file://'+__dirname+'/film.html');await p.evaluate(()=>document.fonts.ready);
const dur=await p.evaluate(()=>DUR);const fps=30;const n=Math.round(dur*fps);
const ff=spawn('ffmpeg',['-v','error','-y','-f','image2pipe','-framerate',String(fps),'-c:v','png','-i','-','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',out],{stdio:['pipe','inherit','inherit']});
for(let i=0;i<n;i++){await p.evaluate(t=>render(t),i/fps);const buf=await p.screenshot({type:'png'});if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r));}
ff.stdin.end();await new Promise(r=>ff.on('close',r));await b.close();console.log('frames',n,out);})();
