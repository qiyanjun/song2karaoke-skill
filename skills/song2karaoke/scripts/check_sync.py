"""Verify a karaoke video against its sources: music alignment, lyric timing, and sung passages with no lyric.
usage: check_sync.py karaoke.mp4 original.(mp3|wav) background.wav vocals.wav lyric_times.json [workdir]

Prints:
  MUSIC   offset/correlation of the video audio vs the backing track and vs the original, plus drift per 30 s
  LYRICS  per line: median/max distance of each character to the nearest vocal onset, characters placed on silence
  GAPS    stretches (>=1 s) where the vocal stem is active but no lyric line is on screen
Exit code 1 if the music check fails (correlation < 0.98 or any drift), else 0.
Interpreting: sung Mandarin is legato, so median onset distances of 60-180 ms are normal; a line whose
median is > 300 ms or with several 'silent' characters is genuinely off. GAPS can be ad-libs ("啊"),
backing-vocal bleed, or a lyric missing from the user's text (common: repeated tag lines) - listen/transcribe before adding.
"""
import sys, os, json, subprocess, tempfile, numpy as np, librosa
from scipy.signal import correlate

vid, orig, bgf, voxf, lyr = sys.argv[1:6]
wd = sys.argv[6] if len(sys.argv) > 6 else tempfile.mkdtemp()
SR = 22050
def dec(src, name):
    out = os.path.join(wd, name)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(SR), out], check=True)
    return librosa.load(out, sr=SR)[0]
k, m, b, v = dec(vid, "k.wav"), dec(orig, "m.wav"), dec(bgf, "b.wav"), dec(voxf, "v.wav")
mm = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"

def lag(a, r):
    n = min(len(a), len(r)); c = correlate(a[:n], r[:n], mode="full", method="fft")
    i = np.argmax(np.abs(c)); return (i - (n - 1)) / SR * 1000, np.abs(c[i]) / np.sqrt(np.sum(a[:n] ** 2) * np.sum(r[:n] ** 2))
print("== MUSIC")
print(f"durations: video {len(k)/SR:.2f}s  original {len(m)/SR:.2f}s  background {len(b)/SR:.2f}s")
lb, cb = lag(k, b); lm, cm = lag(k, m); ls, cs = lag(b + v[:len(b)], m)
print(f"video vs background: offset {lb:+.1f} ms, corr {cb:.4f}")
print(f"video vs original:   offset {lm:+.1f} ms, corr {cm:.3f}  (lower corr expected: no vocals)")
print(f"background+vocals vs original: offset {ls:+.1f} ms, corr {cs:.3f}  (~25 ms = MP3 priming, inaudible)")
drift = []
for t in range(0, int(min(len(k), len(b)) / SR) - 30, 30):
    l, c = lag(k[t * SR:(t + 30) * SR], b[t * SR:(t + 30) * SR]); drift.append(l)
print("windowed offset vs background (ms per 30 s):", " ".join(f"{d:+.0f}" for d in drift))
music_ok = cb > 0.98 and all(abs(d - lb) < 5 for d in drift)
print("MUSIC", "PASS" if music_ok else "FAIL")

print("== LYRICS")
hop = 220; rms = librosa.feature.rms(y=v, hop_length=hop)[0]; tt = np.arange(len(rms)) * hop / SR
db = 20 * np.log10(rms + 1e-9); act = db > np.percentile(db, 95) - 25
ons = librosa.onset.onset_detect(y=v, sr=SR, units="time", delta=0.07)
chars = json.load(open(lyr)); lines = {}
for c in chars: lines.setdefault(c["line"], []).append(c)
def afrac(a, z): s = (tt >= a) & (tt < z); return act[s].mean() if s.any() else 0
alld = []
for lid in sorted(lines, key=lambda l: min(c["t"] for c in lines[l])):
    L = sorted(lines[lid], key=lambda c: c["pos"]); ts = [c["t"] for c in L]
    d = [np.min(np.abs(ons - t)) for t in ts]; alld += d
    sil = "".join(c["ch"] for c in L if afrac(c["t"] - 0.05, c["t"] + 0.25) < 0.2)
    flag = "  <-- CHECK" if (np.median(d) > 0.3 or len(sil) > 1 or not all(np.diff(ts) > 0)) else ""
    print(f"{mm(ts[0])} {''.join(c['ch'] for c in L):<16} onset med {np.median(d)*1000:4.0f}ms max {max(d)*1000:4.0f}ms"
          f" silent:{sil or '-'}{'' if all(np.diff(ts) > 0) else ' OUT-OF-ORDER'}{flag}")
alld = np.array(alld)
print(f"{len(chars)} chars / {len(lines)} lines; onset distance median {np.median(alld)*1000:.0f} ms, 90th pct {np.percentile(alld,90)*1000:.0f} ms")

print("== GAPS (vocals active, no lyric on screen, >=1 s)")
cov = np.zeros_like(act)
for L in lines.values():
    ts = sorted(c["t"] for c in L); cov |= (tt >= ts[0] - 0.4) & (tt <= ts[-1] + 1.5)
un = act & ~cov; seg = []; s = None
for i, u in enumerate(un):
    if u and s is None: s = i
    if not u and s is not None:
        if tt[i] - tt[s] > 0.3: seg.append([tt[s], tt[i]])
        s = None
mg = []
for a, z in seg:
    if mg and a - mg[-1][1] < 0.6: mg[-1][1] = z
    else: mg.append([a, z])
gaps = [(a, z) for a, z in mg if z - a >= 1.0]
for a, z in gaps: print(f"  {mm(a)} - {mm(z)} ({z-a:.1f}s)")
if not gaps: print("  none")
sys.exit(0 if music_ok else 1)
