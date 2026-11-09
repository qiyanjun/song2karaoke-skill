"""Check a jianpu score's lyric placement using the note dump written by choir.py (env DUMP=...).
usage: check_score.py new_dump.json lyric_times.json [old_dump.json]

Checks (PASS/FAIL each):
  order     lyric notes in each part are in time order
  lines     every lyric line appears complete, in order, in at least one part (window: line +-1.5 s)
  chars     every character of lyric_times.json sits on a note of the same glyph within 1.5 s (either part)
  distance  median/max |char time - note start|; lists placements > 0.5 s (usually a gap in that singer's notes)
With old_dump.json (a dump of the previous score):
  notes     pitches and rhythm identical (a lyric fix must not move notes)
  changes   every note whose lyric changed, so you can confirm changes sit only where you edited
"""
import sys, json, numpy as np
new = json.load(open(sys.argv[1])); J = json.load(open(sys.argv[2]))
old = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
mm = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"; ok = lambda c: "PASS" if c else "FAIL"
name = lambda i: ["upper", "lower"][i] if len(new) == 2 else f"part{i+1}"
seq = lambda pt: [(n["s"], n["ly"]) for n in pt if n["ly"]]
fails = 0
for i, pt in enumerate(new):
    t = [s for s, _ in seq(pt)]; c = all(np.diff(t) > 0)
    print(f"order    {name(i)}: {ok(c)}"); fails += not c
lines = {}
for c in J: lines.setdefault(c["line"], []).append(c)
miss = []
for L in lines.values():
    L = sorted(L, key=lambda c: c["pos"]); want = "".join(c["ch"] for c in L)
    if not any(want in "".join(l for s, l in seq(pt) if L[0]["t"] - 1.5 <= s <= L[-1]["t"] + 1.5) for pt in new):
        miss.append(f"{mm(L[0]['t'])} {want}")
print(f"lines    {len(lines)-len(miss)}/{len(lines)} complete: {ok(not miss)}", *miss, sep="\n         " if miss else " ")
fails += bool(miss)
pool = [(s, ch) for pt in new for s, l in seq(pt) for ch in l]
un, dist, far = [], [], []
for c in J:
    ds = [abs(s - c["t"]) for s, ch in pool if ch == c["ch"] and abs(s - c["t"]) < 1.5]
    if not ds: un.append(f"{c['ch']}@{mm(c['t'])}"); continue
    dist.append(min(ds))
    if min(ds) > 0.5: far.append(f"{c['ch']}@{mm(c['t'])} ({min(ds):.2f}s)")
print(f"chars    {len(J)-len(un)}/{len(J)} placed within 1.5 s: {ok(not un)}", " ".join(un)); fails += bool(un)
print(f"distance median {np.median(dist):.2f}s, max {max(dist):.2f}s; >0.5 s: {', '.join(far) or 'none'}")
if old:
    same = all([(round(a["s"], 4), round(a["e"], 4), a["p"]) for a in o] == [(round(b["s"], 4), round(b["e"], 4), b["p"]) for b in n]
               for o, n in zip(old, new)) and len(old) == len(new)
    print(f"notes    identical to old score: {ok(same)}"); fails += not same
    print("changes:")
    for i, (o, n) in enumerate(zip(old, new)):
        for a, b in zip(o, n):
            if a["ly"] != b["ly"]: print(f"         {name(i)} {mm(a['s'])}  {a['ly']} -> {b['ly']}")
sys.exit(1 if fails else 0)
