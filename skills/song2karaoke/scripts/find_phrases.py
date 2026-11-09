"""Cut the vocal stem into sung phrases and cluster them into 2 voice timbres (KMeans on MFCCs).
usage: find_phrases.py vocals.wav raw.mid phrases.npy
Prints each phrase: time, cluster, median pitch, poly (fraction of time 2+ notes sound = duet).
Only needed for 2-singer songs."""
import sys, numpy as np, librosa, pretty_midi
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
# vocal activity
rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
thr = np.percentile(rms, 60)*0.5
act = rms > thr
# phrases: merge gaps < 0.35s, drop < 0.6s
segs=[]; s=None
for i,a in enumerate(act):
    if a and s is None: s=i
    if not a and s is not None: segs.append([s,i]); s=None
if s is not None: segs.append([s,len(act)])
m=[]
for a,b in segs:
    if m and t[a]-t[m[-1][1]]<0.35: m[-1][1]=b
    else: m.append([a,b])
m=[(t[a],t[b]) for a,b in m if t[b]-t[a]>0.6]
# features per phrase
mf = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=512)
cen = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]
f0, vf, _ = librosa.pyin(y, fmin=90, fmax=1000, sr=sr, hop_length=512)
pm = pretty_midi.PrettyMIDI(sys.argv[2]); notes = pm.instruments[0].notes
feats=[]; info=[]
for a,b in m:
    i0,i1 = int(a*sr/512), int(b*sr/512)
    v = vf[i0:i1] & ~np.isnan(f0[i0:i1])
    mp = np.nanmedian(librosa.hz_to_midi(f0[i0:i1][v])) if v.sum()>3 else np.nan
    # polyphony fraction from basic-pitch
    ns=[n for n in notes if n.start<b and n.end>a]
    grid=np.arange(a,b,0.05); poly=np.mean([sum(n.start<=g<n.end for n in ns)>=2 for g in grid]) if len(grid) else 0
    feats.append(np.r_[mf[1:13,i0:i1].mean(1), mf[1:13,i0:i1].std(1)]); info.append((a,b,mp,poly))
X=StandardScaler().fit_transform(np.array(feats))
lab=KMeans(2,n_init=20,random_state=0).fit_predict(X)
for (a,b,mp,poly),l in zip(info,lab):
    print(f"{int(a//60)}:{a%60:05.2f}-{int(b//60)}:{b%60:05.2f}  dur={b-a:5.1f} cl={l} medpitch={mp:5.1f} poly={poly:.2f}")
np.save(sys.argv[3], np.array([(a,b,mp,poly,l) for (a,b,mp,poly),l in zip(info,lab)]))
