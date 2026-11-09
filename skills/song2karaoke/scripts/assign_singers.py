"""Split the raw basic-pitch notes into two monophonic singers, quantized to a 16th grid at the song tempo.
usage: assign_singers.py vocals.wav raw.mid phrases.npy full_mix.(wav|mp3) outdir
writes outdir/singer1.mid (lower), outdir/singer2.mid (higher), outdir/two_singers.mid"""
import sys, numpy as np, librosa, pretty_midi
vox, raw, ph, mix, outdir = sys.argv[1:6]
P = np.load(ph)
y, sr = librosa.load(vox, sr=22050, mono=True); hop=256
f0, vf, _ = librosa.pyin(y, fmin=90, fmax=1000, sr=sr, hop_length=hop)
f0m = librosa.hz_to_midi(f0)
notes = sorted(pretty_midi.PrettyMIDI(raw).instruments[0].notes, key=lambda n:(n.start,-n.pitch))
# tempo from full mix
ym, _ = librosa.load(mix, sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=ym, sr=22050, units='time')
tempo=float(np.atleast_1d(tempo)[0]); print("tempo", round(tempo,1), "first beat", round(beats[0],2))
v = {1:[], 2:[]}   # 1 = lower singer (cluster 1), 2 = higher singer
low_cluster = 1 if np.nanmean(P[P[:,4]==1,2]) < np.nanmean(P[P[:,4]==0,2]) else 0
def pyin_med(n):
    i0,i1=int(n.start*sr/hop),int(n.end*sr/hop); x=f0m[i0:i1]; x=x[~np.isnan(x)]
    return np.median(x) if len(x)>2 else np.nan
for a,b,mp,poly,l in P:
    ns=[n for n in notes if n.start>=a-0.05 and n.start<b]
    singer = 1 if int(l)==low_cluster else 2
    if poly < 0.25:      # solo: keep notes agreeing with pyin f0 (removes harmonics/bleed)
        for n in ns:
            pm_=pyin_med(n)
            if not np.isnan(pm_) and abs(pm_-n.pitch)<=1.0: v[singer].append(n)
    else:                # duet: split simultaneous notes high/low, else voice-leading
        last={1:None,2:None}
        for n in ns:
            ov=[m for m in ns if m is not n and m.start<n.end-0.05 and m.end>n.start+0.05]
            if ov:
                s = 2 if n.pitch >= max(m.pitch for m in ov) else 1
            else:
                d={k:(abs(n.pitch-last[k]) if last[k] is not None else (0 if (k==2)==(n.pitch>=64) else 12)) for k in (1,2)}
                s=min(d,key=d.get)
            last[s]=n.pitch; v[s].append(n)
# monophonize each voice: if overlaps within voice, keep louder/longer, trim
def mono(lst):
    lst=sorted(lst,key=lambda n:n.start); out=[]
    for n in lst:
        if out and n.start < out[-1].end-0.03:
            p=out[-1]
            if (n.end-n.start)*n.velocity > (p.end-p.start)*p.velocity and n.start-p.start<0.05: out[-1]=n; continue
            p.end=n.start
            if p.end-p.start<0.08: out.pop()
        out.append(n)
    return out
# quantize to 16th grid anchored at beats
spb=60/tempo; g=spb/4; t0=beats[0]%g
def q(t): return t0+round((t-t0)/g)*g
pm=pretty_midi.PrettyMIDI(initial_tempo=tempo)
for k,name in ((1,"Singer 1 (lower)"),(2,"Singer 2 (higher)")):
    inst=pretty_midi.Instrument(program=52 if k==1 else 53, name=name)
    for n in mono(v[k]):
        s,e=q(n.start),q(n.end)
        if e<=s: e=s+g
        inst.notes.append(pretty_midi.Note(velocity=90,pitch=n.pitch,start=s,end=e))
    # fix overlaps after quantization
    for i in range(len(inst.notes)-1):
        if inst.notes[i].end>inst.notes[i+1].start: inst.notes[i].end=inst.notes[i+1].start
    inst.notes=[n for n in inst.notes if n.end>n.start]
    pm.instruments.append(inst)
    solo=pretty_midi.PrettyMIDI(initial_tempo=tempo); solo.instruments.append(inst)
    solo.write(f"{outdir}/singer{k}.mid")
    ps=[n.pitch for n in inst.notes]
    print(name, len(ps),"notes, range", pretty_midi.note_number_to_name(min(ps)),"-",pretty_midi.note_number_to_name(max(ps)))
pm.write(f"{outdir}/two_singers.mid")
