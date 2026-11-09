"""Two-part jianpu score (choir style): upper & lower voice in bracketed systems with lyrics.
usage: choir.py upper.mid lower.mid lyrics.json out_prefix title upper_label lower_label key_label
  key_label: tonic as shown in "1=..." (e.g. ♭E, Eb, F#, C); it also sets which octave gets plain digits.
  env DUMP=path.json: also write every note with its attached lyric (for check_score.py).
"""
import sys, json, numpy as np, pretty_midi
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Arc
from matplotlib.font_manager import FontProperties
CJK = FontProperties(fname="/System/Library/Fonts/Supplemental/Songti.ttc")

up_mid, lo_mid, LYR, outp, title, up_lab, lo_lab, keylab = sys.argv[1:9]
pm0 = pretty_midi.PrettyMIDI(up_mid)
tempo = pm0.get_tempo_changes()[1][0]
g = 60 / tempo / 4
allst = [n.start for f in (up_mid, lo_mid) for n in pretty_midi.PrettyMIDI(f).instruments[0].notes]
off = np.median([(s / g) % 1 for s in allst]) * g
U = lambda t: int(round((t - off) / g))
RES, GAP = 2, 3
chars_all = json.load(open(LYR))
class N: pass

def load_part(mid):
    notes = sorted(pretty_midi.PrettyMIDI(mid).instruments[0].notes, key=lambda n: n.start)
    ev = []
    for n in notes:
        s = int(round(U(n.start) / RES)) * RES; e = int(round(U(n.end) / RES)) * RES
        if e - s < RES: e = s + RES
        if ev and s <= ev[-1][0]:
            if e - s > ev[-1][1] - ev[-1][0]: ev[-1] = [ev[-1][0], e, n.pitch]
            continue
        ev.append([s, e, n.pitch])
    for i in range(len(ev) - 1):
        if ev[i][1] > ev[i + 1][0]: ev[i][1] = ev[i + 1][0]
        elif ev[i + 1][0] - ev[i][1] <= GAP: ev[i][1] = ev[i + 1][0]
    notes = []
    for s, e, p in ev:
        x = N(); x.start = s * g + off; x.end = e * g + off; x.pitch = p; x.ly = None; notes.append(x)
    groups = []
    for c in chars_all:
        if groups and groups[-1][-1]['line'] == c['line'] and c['t'] - groups[-1][-1]['t'] < 3: groups[-1].append(c)
        else: groups.append([c])
    dur = lambda n: U(n.end) - U(n.start)
    def split(nt):
        s, e = U(nt.start), U(nt.end); L = e - s
        if L < 2: return None
        mid = s + (L // 2 if L < 4 else (L // 2) // 2 * 2)
        n2 = N(); n2.start = mid * g + off; n2.end = nt.end; n2.pitch = nt.pitch; n2.ly = nt.ly
        nt.end = n2.start; notes.append(n2); return n2
    for grp in groups:
        cand = [k for k, n in enumerate(notes) if grp[0]['t'] - 0.8 <= n.start <= grp[-1]['t'] + 0.8 and n.ly is None]
        if len(cand) < 0.5 * len(grp): continue
        I, J = len(grp), len(cand)
        D = np.full((I + 1, J + 1), 1e9); D[0, :] = 0; B = {}
        for i in range(1, I + 1):
            D[i, 0] = D[i - 1, 0] + 1.0; B[(i, 0)] = 'c'
            for j in range(1, J + 1):
                D[i, j], B[(i, j)] = min((D[i-1, j-1] + abs(grp[i-1]['t'] - notes[cand[j-1]].start), 'm'),
                                         (D[i, j-1], 'n'), (D[i-1, j] + 1.0, 'c'))
        i, j = I, int(np.argmin(D[I])); asg = [None] * I
        while i > 0:
            op = B[(i, j)] if j > 0 else 'c'
            if op == 'm': asg[i-1] = notes[cand[j-1]]; asg[i-1].ly = grp[i-1]['ch']; i -= 1; j -= 1
            elif op == 'n': j -= 1
            else: i -= 1
        for i in range(I):
            if asg[i] is not None: continue
            prev = next((k for k in range(i - 1, -1, -1) if asg[k] is not None), None)
            nxt = next((k for k in range(i + 1, I) if asg[k] is not None), None)
            P = asg[prev] if prev is not None else None; Q = asg[nxt] if nxt is not None else None
            if P is Q: Q = None
            ch = [x for x in (P, Q) if x is not None and dur(x) >= 2]
            if ch:
                tgt = max(ch, key=dur); n2 = split(tgt)
                if tgt is P: n2.ly = grp[i]['ch']; asg[i] = n2
                else: n2.ly = tgt.ly; tgt.ly = grp[i]['ch']; asg[i] = tgt; asg[nxt] = n2
            elif P is not None: P.ly += grp[i]['ch']; asg[i] = P
            elif Q is not None: Q.ly = grp[i]['ch'] + Q.ly; asg[i] = Q
        notes.sort(key=lambda n: n.start)
    return notes

parts = [load_part(up_mid), load_part(lo_mid)]
import os
if os.environ.get("DUMP"):
    json.dump([[{"s": n.start, "e": n.end, "p": n.pitch, "ly": n.ly} for n in pt] for pt in parts],
              open(os.environ["DUMP"], "w"), ensure_ascii=False)
alln = parts[0] + parts[1]
on = np.array([U(n.start) for n in alln]); en = np.array([U(n.end) for n in alln])
best = None
for ph in range(16):
    sc = 2 * np.sum((on - ph) % 16 == 0) + np.sum((on - ph) % 4 == 0) - 1.5 * np.sum(((on - ph) // 16) != ((en - 1 - ph) // 16))
    if best is None or sc > best[0]: best = (sc, ph)
ph = best[1]
first_bar = (on.min() - ph) // 16; last_bar = (en.max() - 1 - ph) // 16
base = first_bar * 16 + ph; nslots = (last_bar - first_bar + 1) * 16
pall = np.array([n.pitch for n in alln])
def key_pc(lab):
    """'♭E' / 'Eb' / 'bb' / 'F#' / '1=C' -> pitch class 0-11"""
    s = lab.strip().replace("♭", "b").replace("♯", "#")
    i = next((k for k, c in enumerate(s) if c in "ABCDEFG"), None)
    if i is None:
        i = next(k for k, c in enumerate(s) if c in "abcdefg"); s = s[:i] + s[i].upper() + s[i + 1:]
    rest = s[:i] + s[i + 1:]
    return ({"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[s[i]] + rest.count("#") - rest.count("b")) % 12
pc = key_pc(keylab)
# middle register: the tonic octave that leaves the fewest notes needing octave dots
tonic = min((pc + 12 * o for o in range(3, 8)), key=lambda t: np.sum((pall < t) | (pall >= t + 12)))

def build_bars(notes):
    pitch = [None] * nslots; onset = [False] * nslots; eid = [None] * nslots
    for n in notes:
        s, e = U(n.start) - base, U(n.end) - base
        for u in range(max(s, 0), min(e, nslots)): pitch[u] = n.pitch; onset[u] = False
        if 0 <= s < nslots: onset[s] = True; eid[s] = n
    def beat_runs(b):
        runs = []
        for u in range(b * 4, b * 4 + 4):
            p, o = pitch[u], onset[u]
            if runs and not o and runs[-1]['p'] == p: runs[-1]['len'] += 1; continue
            runs.append({'p': p, 'len': 1, 'onset': o or p is None, 'n': eid[u] if o else None})
        return runs
    nbeats = nslots // 4; beats = [beat_runs(b) for b in range(nbeats)]; cells = []; skip = set()
    for b, runs in enumerate(beats):
        els = []
        for i, r in enumerate(runs):
            if (b, i) in skip: continue
            if r['p'] is None: els.append({'t': 'rest', 'len': r['len']})
            elif not r['onset'] and r['len'] == 4: els.append({'t': 'dash', 'len': 4})
            else: els.append({'t': 'note', 'p': r['p'], 'len': r['len'], 'tie': not r['onset'],
                              'ly': r['n'].ly if r['n'] is not None else None})
        if (len(els) == 1 and els[0]['t'] == 'note' and els[0]['len'] == 4 and b + 1 < nbeats
                and beats[b+1][0]['p'] == els[0]['p'] and not beats[b+1][0]['onset'] and beats[b+1][0]['len'] == 2):
            els[0]['dot'] = True; skip.add((b + 1, 0))
        # a rest beat made of several rest runs -> single 0
        if all(e['t'] == 'rest' for e in els): els = [{'t': 'rest', 'len': 4}]
        cells.append(els)
    return [cells[i:i + 4] for i in range(0, len(cells), 4)]

BU, BL = build_bars(parts[0]), build_bars(parts[1])
empty = lambda bar: all(all(e['t'] == 'rest' for e in c) for c in bar)
items, i = [], 0      # ('bar', upper_bar, lower_bar, idx) | ('mrest', n, idx)
while i < len(BU):
    if empty(BU[i]) and empty(BL[i]):
        j = i
        while j < len(BU) and empty(BU[j]) and empty(BL[j]): j += 1
        if j - i >= 4: items.append(('mrest', j - i, i)); i = j; continue
    items.append(('bar', BU[i], BL[i], i)); i += 1
bar_time = lambda bi: (base + bi * 16) * g + off
mmss = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"

# ---------------- drawing ----------------
PW, PH = 8.27, 11.69; LM, RM = 0.75, 0.45; FS = 14
DEG = {0: ('1', ''), 1: ('1', '#'), 2: ('2', ''), 3: ('3', 'b'), 4: ('3', ''), 5: ('4', ''),
       6: ('4', '#'), 7: ('5', ''), 8: ('5', '#'), 9: ('6', ''), 10: ('7', 'b'), 11: ('7', '')}
ROW_GAP, LY_OFF, SYS_H = 0.92, 0.42, 2.05
tie_prev = [None, None]

def draw_beat(ax, els, cx0, cw, y, part):
    n = len(els); xs = [cx0 + (j + 0.5) * cw / max(n, 1) for j in range(n)]; lv = []
    for e, x in zip(els, xs):
        L = e['len']; nl = 0 if L >= 4 else (1 if L in (2, 3) else 2)
        if e['t'] == 'dash':
            ax.text(x, y, '–', ha='center', va='center', fontsize=FS); lv.append(0); continue
        if e['t'] == 'rest':
            ax.text(x, y, '0', ha='center', va='center', fontsize=FS); tie_prev[part] = None
        else:
            d, acc = DEG[(e['p'] - tonic) % 12]; octv = (e['p'] - tonic) // 12
            ax.text(x, y, d, ha='center', va='center', fontsize=FS, fontweight='bold')
            if e.get('ly'):
                ax.text(x, y - LY_OFF, e['ly'], ha='center', va='center', fontproperties=CJK,
                        fontsize=12 if len(e['ly']) == 1 else 8.5)
            if acc: ax.text(x - 0.09, y + 0.08, '♯' if acc == '#' else '♭', ha='center', va='center', fontsize=8)
            for o in range(octv): ax.plot(x, y + 0.19 + 0.07 * o, 'k.', ms=3.2)
            for o in range(-octv): ax.plot(x, y - 0.16 - 0.055 * nl - 0.07 * o, 'k.', ms=3.2)
            if e.get('tie') and tie_prev[part] is not None:
                px, py = tie_prev[part]
                if abs(py - y) < 1e-6 and x > px:
                    ax.add_patch(Arc(((px + x) / 2, y + 0.19), x - px, 0.16, theta1=0, theta2=180, lw=0.8))
            tie_prev[part] = (x, y)
        if L == 3 or e.get('dot'): ax.plot(x + 0.1, y, 'k.', ms=3.2)
        lv.append(nl)
    for level in (1, 2):
        j = 0
        while j < n:
            if lv[j] >= level:
                k2 = j
                while k2 + 1 < n and lv[k2 + 1] >= level: k2 += 1
                half = cw / max(n, 1) * 0.38; yy = y - 0.14 - 0.055 * (level - 1)
                ax.plot([xs[j] - half, xs[k2] + half], [yy, yy], color='k', lw=0.9); j = k2 + 1
            else: j += 1

def draw_system(ax, sys_items, y):
    y1, y2 = y, y - ROW_GAP
    width = PW - LM - RM
    bwt = lambda els: max(1.4, len(els) * 1.15)
    wts = [[7.0] if it[0] == 'mrest' else [max(bwt(a), bwt(b)) for a, b in zip(it[1], it[2])] for it in sys_items]
    tot = sum(sum(w) for w in wts)
    if len(sys_items) < 4: tot = max(tot, tot * 4 / len(sys_items) * 0.85)
    unit = width / tot; xcur = LM
    # bracket + labels + time
    top, bot = y1 + 0.3, y2 - 0.25
    ax.plot([LM - 0.12, LM - 0.12], [bot, top], color='k', lw=3)
    ax.plot([LM - 0.12, LM - 0.02], [top, top + 0.06], color='k', lw=1.2)
    ax.plot([LM - 0.12, LM - 0.02], [bot, bot - 0.06], color='k', lw=1.2)
    ax.text(LM - 0.22, y1, up_lab, ha='right', va='center', fontsize=7.5, color='0.35')
    ax.text(LM - 0.22, y2, lo_lab, ha='right', va='center', fontsize=7.5, color='0.35')
    ax.text(LM, top + 0.12, mmss(bar_time(sys_items[0][-1])), fontsize=7, color='0.45', ha='left')
    for yy in (y1, y2): ax.plot([LM, LM], [yy - 0.2, yy + 0.22], color='k', lw=0.9)
    for k, it in enumerate(sys_items):
        x0 = xcur; bw = sum(wts[k]) * unit; xcur += bw
        if it[0] == 'mrest':
            for yy in (y1, y2):
                ax.plot([x0 + bw * 0.15, x0 + bw * 0.85], [yy + 0.02, yy + 0.02], color='k', lw=4)
            ax.text(x0 + bw / 2, (y1 + y2) / 2 + 0.05, f"interlude  {it[1]} bars", ha='center', va='center', fontsize=9, color='0.25')
            tie_prev[0] = tie_prev[1] = None
        else:
            for part, (bar, yy) in enumerate(((it[1], y1), (it[2], y2))):
                for bi, els in enumerate(bar):
                    draw_beat(ax, els, x0 + sum(wts[k][:bi]) * unit, wts[k][bi] * unit, yy, part)
        for yy in (y1, y2): ax.plot([x0 + bw, x0 + bw], [yy - 0.2, yy + 0.22], color='k', lw=0.9)
    if sys_items is systems[-1]:
        for yy in (y1, y2): ax.plot([xcur - 0.04, xcur - 0.04], [yy - 0.2, yy + 0.22], color='k', lw=2.5)

systems = [items[k:k + 4] for k in range(0, len(items), 4)]
pages, k, first_cap, cap = [], 0, 4, 5
while k < len(systems):
    c = first_cap if not pages else cap; pages.append(systems[k:k + c]); k += c
with PdfPages(outp + ".pdf") as pdf:
    for pi, pg in enumerate(pages):
        fig = plt.figure(figsize=(PW, PH), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, PW); ax.set_ylim(0, PH); ax.axis('off')
        y = PH - 0.6
        if pi == 0:
            ax.text(PW / 2, y - 0.2, title, ha='center', va='center', fontsize=26, fontproperties=CJK)
            ax.text(PW / 2, y - 0.62, "二声部", ha='center', va='center', fontsize=12, fontproperties=CJK, color='0.3')
            ax.text(LM - 0.15, y - 1.0, f"1={keylab}  4/4", ha='left', va='center', fontsize=13, fontweight='bold')
            ax.text(LM - 0.15, y - 1.3, f"♩={tempo:.0f}", ha='left', va='center', fontsize=11)
            ax.text(PW - RM, y - 1.0, f"upper: {up_lab}", ha='right', va='center', fontsize=9)
            ax.text(PW - RM, y - 1.22, f"lower: {lo_lab}", ha='right', va='center', fontsize=9)
            ax.text(PW - RM, y - 1.44, "auto-transcribed from audio", ha='right', va='center', fontsize=8, color='0.4')
            y -= 2.3
        else:
            y -= 0.5
        for s in pg:
            draw_system(ax, s, y); y -= SYS_H
        ax.text(PW - RM, 0.35, f"{pi + 1}/{len(pages)}", ha='right', fontsize=9)
        pdf.savefig(fig); fig.savefig(f"{outp}_p{pi + 1}.png", dpi=150); plt.close(fig)
print("tonic", tonic, "bars", len(BU), "systems", len(systems), "pages", len(pages))
