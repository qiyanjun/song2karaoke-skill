"""Place user-provided timed lyrics: align each entry to Whisper char timings inside its own time window;
fall back to vocal onsets when Whisper heard nothing usable. Output text is the user's text only."""
import sys, json, re, numpy as np, librosa
words = json.load(open(sys.argv[1])); vox = sys.argv[3]
ent = []
for l in open(sys.argv[2]):
    l = l.strip()
    if not l: continue
    ts, txt = l.split(" ", 1); m, s = ts.split(":"); ent.append((int(m) * 60 + int(s), txt.split()))
A = []
for s, e, w in words:
    w = re.sub(r"[\s，。,.!?！？、]", "", w)
    for k, c in enumerate(w): A.append((s + (e - s) * (k + 0.5) / len(w), c))
at = np.array([t for t, _ in A]); ac = [c for _, c in A]
y, sr = librosa.load(vox, sr=22050, mono=True)
ons = librosa.onset.onset_detect(y=y, sr=sr, units='time', backtrack=False, delta=0.08)
def sw(L, idx):
    n, m = len(L), len(idx); H = np.zeros((n + 1, m + 1)); T = np.zeros((n + 1, m + 1), int)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = H[i-1, j-1] + (2 if L[i-1] == ac[idx[j-1]] else -0.5); u = H[i-1, j] - 1; l = H[i, j-1] - 1
            b = max(0, d, u, l); H[i, j] = b; T[i, j] = 0 if b == 0 else (1 if b == d else (2 if b == u else 3))
    i, j = np.unravel_index(H.argmax(), H.shape); pairs = []
    while i > 0 and j > 0 and T[i, j]:
        if T[i, j] == 1: pairs.append((i - 1, idx[j - 1])); i -= 1; j -= 1
        elif T[i, j] == 2: i -= 1
        else: j -= 1
    return pairs[::-1]
def times_from(pr, L):
    tt = {i: at[j] for i, j in pr}; ks = sorted(tt)
    step = np.median(np.diff([tt[q] for q in ks])) if len(ks) > 2 else 0.4
    return [float(np.interp(i, ks, [tt[q] for q in ks])) if ks[0] <= i <= ks[-1] else
            float(tt[ks[0]] - step * (ks[0] - i) if i < ks[0] else tt[ks[-1]] + step * (i - ks[-1])) for i in range(len(L))]
out = []; lid = 0; used = np.zeros(len(A), bool)
for k, (t0, halves) in enumerate(ent):
    t1 = ent[k + 1][0] if k + 1 < len(ent) else t0 + 12
    res = [None] * len(halves); hows = [None] * len(halves)
    for h, L in enumerate(halves):          # pass 1: whisper per half
        idx = [j for j in range(len(A)) if t0 - 1.0 <= at[j] < t1 + 0.5 and not used[j]]
        pr = sw(L, idx) if idx else []
        if len(pr) >= 0.5 * len(L):
            res[h] = times_from(pr, L); hows[h] = f"whisper {len(pr)}/{len(L)}"
            for _, j in pr: used[j] = True
    for h, L in enumerate(halves):          # pass 2: onsets inside the remaining gap
        if res[h] is not None: continue
        lo = max([res[q][-1] + 0.2 for q in range(h) if res[q]] + [t0 - 0.5])
        hi = min([res[q][0] - 0.2 for q in range(h + 1, len(halves)) if res[q]] + [t1])
        o = ons[(ons >= lo) & (ons < hi)]
        if len(o) >= len(L): res[h] = list(map(float, o[:len(L)])); hows[h] = "vocal onsets"
        else: res[h] = list(np.linspace(lo, max(lo, min(hi - 0.5, lo + 0.45 * len(L))), len(L))); hows[h] = "even spacing"
    for h, L in enumerate(halves):
        for i, c in enumerate(L): out.append({"t": float(res[h][i]), "ch": c, "line": lid + h, "pos": i})
    print(f"{t0//60}:{t0%60:02d}  " + "  |  ".join(f"{L} [{hw}]" for L, hw in zip(halves, hows)))
    lid += len(halves)
json.dump(sorted(out, key=lambda c: c["t"]), open(sys.argv[4], "w"), ensure_ascii=False)
