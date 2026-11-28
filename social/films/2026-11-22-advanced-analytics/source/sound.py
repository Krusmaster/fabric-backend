"""Synthesized sound for the advanced analytics film (no samples). Writes sound.wav (48 kHz, stereo).
Same instruments as ../2026-11-22-few-taps/source/sound.py; the cue times follow this film's scenes."""
import numpy as np, wave, sys
SR=48000; DUR=19.5; N=int(SR*DUR); t=np.arange(N)/SR
BEAT=2.6/4            # four beats per 2.6 s scene step (about 92 bpm)
def env(x,a,d): return np.where(x<0,0,np.minimum(x/a,1)*np.exp(-np.maximum(x-a,0)/d))
def note(f): return 440*2**((f-69)/12)
out=np.zeros(N)
# chord pad per scene: Am, F, C, G, (boom) C, F->C ending
chords=[(0,3.2,[48,55,60,64]),(3.2,6.0,[53,57,60]),(6.0,10.4,[57,60,64]),(10.4,13.8,[48,52,55,60,64]),(13.8,16.4,[55,59,62]),(16.4,19.5,[53,57,60,65])]
for a,b,ns in chords:
    m=(t>=a)&(t<b+0.3); x=t[m]-a
    g=np.minimum(x/0.25,1)*np.clip((b+0.3-t[m])/0.3,0,1)
    for n in ns:
        f=note(n); s=np.sin(2*np.pi*f*x)+0.3*np.sin(2*np.pi*2*f*x)+0.12*np.sin(2*np.pi*3*f*x)
        out[m]+=0.045*g*s*(0.8+0.2*np.sin(2*np.pi*0.5*x))
# plucked arpeggio from 5.2 s, eighth notes
for i in range(int((DUR-3.2)/(BEAT/2))):
    st=3.2+i*BEAT/2
    if 10.3<st<10.6 or 13.8<=st<16.4: continue
    ns=next(c[2] for c in chords if c[0]<=st<c[1]+1e-9) if st<19.5 else [60]
    n=ns[i%len(ns)]+12; x=t-st; m=(x>=0)&(x<0.6)
    out[m]+=0.06*np.sin(2*np.pi*note(n)*x[m])*env(x[m],0.004,0.18)
# kick on beats from 5.2 s, hats on off-beats from 9.2 s, louder after the boom
rng=np.random.default_rng(1); noise=rng.standard_normal(N)
for i in range(int((DUR-6.0)/BEAT)+1):
    st=6.0+i*BEAT
    if 13.8<=st<16.4: continue
    if st>18.6: break
    x=t-st; m=(x>=0)&(x<0.4)
    k=0.55 if st>=10.4 else 0.35
    out[m]+=k*np.sin(2*np.pi*(50+90*np.exp(-x[m]*30))*x[m])*env(x[m],0.002,0.09)
    if st>=10.4:
        h=st+BEAT/2; x=t-h; m=(x>=0)&(x<0.08)
        out[m]+=0.08*noise[m]*env(x[m],0.001,0.015)
# taps: send at 8.25 s, five steps from 10.2 s
for st in [1.25,1.55,1.85]+[7.6,8.4,9.2]:
    x=t-st; m=(x>=0)&(x<0.15)
    out[m]+=0.25*np.sin(2*np.pi*(1200+300*(st>10))*x[m])*env(x[m],0.001,0.02)
# typing ticks 6.3 to 7.6 s
for i in range(15):
    st=-1; x=t-st; m=(x>=0)&(x<0)
    out[m]+=0.05*noise[m]*env(x[m],0.0005,0.006)
# boom at 13.0 s, and a whoosh into it
x=t-10.4; m=(x>=0)&(x<1.6)
out[m]+=0.9*np.sin(2*np.pi*(45+110*np.exp(-x[m]*9))*x[m])*env(x[m],0.003,0.35)
w=(t>9.6)&(t<10.4); x=t[w]-9.6
out[w]+=0.12*noise[w]*(x/0.8)**2
# heartbeat in scene 5: lub-dub twice, in time with the line being drawn
for st in [14.25,14.45,15.15,15.35]:
    x=t-st; m=(x>=0)&(x<0.35)
    out[m]+=0.7*np.sin(2*np.pi*(48+40*np.exp(-x[m]*25))*x[m])*env(x[m],0.004,0.07)
# master: fade out, normalise
out*=np.clip((DUR-t)/2.0,0,1)*np.clip(t/0.4,0,1)
out=np.tanh(out*1.2)/np.tanh(1.2)
out/=np.max(np.abs(out))*1.05
st=np.stack([out,out],1)
st[:,0]=out*0.96+0.04*np.roll(out,240); st[:,1]=out*0.96+0.04*np.roll(out,-240)
with wave.open(sys.argv[1] if len(sys.argv)>1 else 'sound.wav','wb') as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((st*32767).astype('<i2').tobytes())
