"""Score-informed split of a 2-voice vocal stem using each singer's transcribed notes."""
import sys, numpy as np, soundfile as sf, librosa, pretty_midi
vox, m1, m2, o1, o2 = sys.argv[1:6]
y, sr = sf.read(vox, always_2d=True); y = y.T.astype(np.float32)          # (ch, n)
NF, HOP = 4096, 1024
X = np.stack([librosa.stft(c, n_fft=NF, hop_length=HOP) for c in y])      # (ch, bins, frames)
mag = np.abs(X).mean(0); nb, nfr = mag.shape
freqs = librosa.fft_frequencies(sr=sr, n_fft=NF); ft = librosa.frames_to_time(np.arange(nfr), sr=sr, hop_length=HOP, n_fft=NF)
PAD = 0.12
def roll(mid):
    p = np.full(nfr, np.nan)
    for n in pretty_midi.PrettyMIDI(mid).instruments[0].notes:
        p[(ft >= n.start - PAD) & (ft < n.end + PAD)] = n.pitch
    return p
P = [roll(m1), roll(m2)]
cents = np.linspace(-0.8, 0.8, 17)
def refine(p, t):
    best, bf = -1, None
    for c in cents:
        f0 = librosa.midi_to_hz(p + c); hs = f0 * np.arange(1, 11); hs = hs[hs < sr / 2]
        s = mag[np.searchsorted(freqs, hs), t].sum()
        if s > best: best, bf = s, f0
    return bf
def hmask(f0):
    m = np.zeros(nb, np.float32)
    for h in range(1, 60):
        fh = h * f0
        if fh > 11000: break
        bw = max(12.0, 0.012 * fh)
        m += np.exp(-0.5 * ((freqs - fh) / bw) ** 2)
    return np.clip(m, 0, 1)
M = np.zeros((2, nb, nfr), np.float32)
act = [~np.isnan(P[0]), ~np.isnan(P[1])]
# frames with no note at all: give to the nearest singer in time
last = np.full(nfr, -1); nxt = np.full(nfr, -1)
who = np.where(act[0] & ~act[1], 0, np.where(act[1] & ~act[0], 1, -1))
for t in range(nfr):
    if act[0][t] and act[1][t]:
        H = [hmask(refine(P[k][t], t)) for k in (0, 1)]
        tot = H[0] + H[1] + 1e-6; res = 1 - np.clip(tot, 0, 1)
        for k in (0, 1): M[k, :, t] = np.clip(H[k] / tot * np.clip(tot, 0, 1) + 0.5 * res, 0, 1)
    elif act[0][t]: M[0, :, t] = 1
    elif act[1][t]: M[1, :, t] = 1
idle = ~(act[0] | act[1]); solo = np.where(who >= 0)[0]
if len(solo):
    for t in np.where(idle)[0]:
        j = solo[np.argmin(np.abs(solo - t))]
        if abs(j - t) * HOP / sr < 1.5: M[who[j], :, t] = 1
        else: M[:, :, t] = 0.5
for k, out in ((0, o1), (1, o2)):
    ych = [librosa.istft(X[c] * M[k], hop_length=HOP, n_fft=NF, length=y.shape[1]) for c in range(len(y))]
    sf.write(out, np.stack(ych, 1), sr, subtype='PCM_16')
both = (act[0] & act[1]).mean(); print(f"frames: both singing {both:.0%}, singer1 only {(act[0]&~act[1]).mean():.0%}, singer2 only {(act[1]&~act[0]).mean():.0%}")
