"""Render a monophonic MIDI track as jianpu (numbered notation) PDF/PNG.
usage: jianpu.py in.mid out_prefix title subtitle tonic_midi key_label
"""
import sys, numpy as np, pretty_midi
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Arc
from matplotlib.font_manager import FontProperties
import json
CJK = FontProperties(fname="/System/Library/Fonts/Supplemental/Songti.ttc")

mid, outp, title, subtitle, tonic, keylab = sys.argv[1:7]
tonic = int(tonic)
pm = pretty_midi.PrettyMIDI(mid)
tempo = pm.get_tempo_changes()[1][0]
g = 60 / tempo / 4                      # one sixteenth in seconds
notes = sorted(pm.instruments[0].notes, key=lambda n: n.start)
off = np.median([(n.start / g) % 1 for n in notes]) * g
U = lambda t: int(round((t - off) / g))
RES = int(sys.argv[7]) if len(sys.argv) > 7 else 2    # grid in sixteenths (2 = eighth notes)
GAP = 3                                               # fill rests up to this many sixteenths

# ---- simplify: snap to grid, fill small gaps, resolve collisions ----
ev = []
for n in notes:
    s = int(round(U(n.start) / RES)) * RES; e = int(round(U(n.end) / RES)) * RES
    if e - s < RES: e = s + RES
    if ev and s <= ev[-1][0]:            # collides with previous onset: keep longer
        if e - s > ev[-1][1] - ev[-1][0]: ev[-1] = [ev[-1][0], e, n.pitch]
        continue
    ev.append([s, e, n.pitch])
for i in range(len(ev) - 1):
    if ev[i][1] > ev[i + 1][0]: ev[i][1] = ev[i + 1][0]
    elif ev[i + 1][0] - ev[i][1] <= GAP: ev[i][1] = ev[i + 1][0]
class N: pass
notes = []
for s, e, p in ev:
    x = N(); x.start = s * g + off; x.end = e * g + off; x.pitch = p; x.ly = None; notes.append(x)

# ---- attach lyrics: ordered DP of chars onto note onsets ----
LYR = sys.argv[8] if len(sys.argv) > 8 else None
if LYR:
    chars = json.load(open(LYR)); groups = []
    for c in chars:
        if groups and groups[-1][-1]['line'] == c['line'] and c['t'] - groups[-1][-1]['t'] < 3: groups[-1].append(c)
        else: groups.append([c])
    for grp in groups:
        cand = [k for k, n in enumerate(notes) if grp[0]['t'] - 0.8 <= n.start <= grp[-1]['t'] + 0.8 and n.ly is None]
        if len(cand) < 0.5 * len(grp): continue
        I, J = len(grp), len(cand); INF = 1e9
        D = np.full((I + 1, J + 1), INF); D[0, :] = 0; B = {}
        for i in range(1, I + 1):
            D[i, 0] = D[i - 1, 0] + 1.0; B[(i, 0)] = 'c'
            for j in range(1, J + 1):
                opts = [(D[i - 1, j - 1] + abs(grp[i - 1]['t'] - notes[cand[j - 1]].start), 'm'),
                        (D[i, j - 1], 'n'), (D[i - 1, j] + 1.0, 'c')]
                D[i, j], B[(i, j)] = min(opts)
        i, j = I, int(np.argmin(D[I])); asg = [None] * I
        while i > 0:
            op = B[(i, j)] if j > 0 else 'c'
            if op == 'm': asg[i - 1] = notes[cand[j - 1]]; asg[i - 1].ly = grp[i - 1]['ch']; i -= 1; j -= 1
            elif op == 'n': j -= 1
            else: i -= 1
        # chars left without a note: split the neighbouring note (same pitch re-articulation)
        def split(nt, first_half_gets=None, second_half_gets=None):
            s, e = U(nt.start), U(nt.end); L = e - s
            if L < 2: return None
            mid = s + (L // 2 if L < 4 else (L // 2) // 2 * 2)
            n2 = N(); n2.start = mid * g + off; n2.end = nt.end; n2.pitch = nt.pitch; n2.ly = nt.ly
            nt.end = n2.start; notes.append(n2)
            return n2
        dur = lambda n: U(n.end) - U(n.start)
        for i in range(I):
            if asg[i] is not None: continue
            prev = next((k for k in range(i - 1, -1, -1) if asg[k] is not None), None)
            nxt = next((k for k in range(i + 1, I) if asg[k] is not None), None)
            P = asg[prev] if prev is not None else None
            Q = asg[nxt] if nxt is not None else None
            if P is Q: Q = None
            choices = [x for x in (P, Q) if x is not None and dur(x) >= 2]
            if choices:
                tgt = max(choices, key=dur); n2 = split(tgt)
                if tgt is P:   # second half takes this char
                    n2.ly = grp[i]['ch']; asg[i] = n2
                else:          # first half takes this char, second half keeps the next char
                    n2.ly = tgt.ly; tgt.ly = grp[i]['ch']; asg[i] = tgt; asg[nxt] = n2
            elif P is not None: P.ly += grp[i]['ch']; asg[i] = P      # no room: share the note
            elif Q is not None: Q.ly = grp[i]['ch'] + Q.ly; asg[i] = Q
        notes.sort(key=lambda n: n.start)

# ---- choose bar phase (downbeat) that best fits the onsets ----
on = np.array([U(n.start) for n in notes]); en = np.array([U(n.end) for n in notes])
best = None
for ph in range(16):
    sc = 2 * np.sum((on - ph) % 16 == 0) + np.sum((on - ph) % 4 == 0)
    sc -= 1.5 * np.sum(((on - ph) // 16) != ((en - 1 - ph) // 16))
    if best is None or sc > best[0]: best = (sc, ph)
ph = best[1]
first_bar = (on.min() - ph) // 16
last_bar = (en.max() - 1 - ph) // 16
base = first_bar * 16 + ph
nslots = (last_bar - first_bar + 1) * 16
pitch = [None] * nslots; onset = [False] * nslots; eid = [None] * nslots
for n in notes:
    s, e = U(n.start) - base, U(n.end) - base
    for u in range(max(s, 0), min(e, nslots)): pitch[u] = n.pitch; onset[u] = False
    if 0 <= s < nslots: onset[s] = True; eid[s] = n

# ---- build per-beat element lists ----
DEG = {0: ('1', ''), 1: ('1', '#'), 2: ('2', ''), 3: ('3', 'b'), 4: ('3', ''), 5: ('4', ''),
       6: ('4', '#'), 7: ('5', ''), 8: ('5', '#'), 9: ('6', ''), 10: ('7', 'b'), 11: ('7', '')}
def beat_runs(b):
    runs = []
    for u in range(b * 4, b * 4 + 4):
        p, o = pitch[u], onset[u]
        if runs and not o and runs[-1]['p'] == p: runs[-1]['len'] += 1; continue
        runs.append({'p': p, 'len': 1, 'onset': o or p is None, 'n': eid[u] if o else None})
    return runs

nbeats = nslots // 4
beats = [beat_runs(b) for b in range(nbeats)]
cells = []      # per beat: list of elements
skip = set()
for b, runs in enumerate(beats):
    els = []
    for i, r in enumerate(runs):
        if (b, i) in skip: continue
        if r['p'] is None:
            els.append({'t': 'rest', 'len': r['len']})
        elif not r['onset'] and r['len'] == 4:
            els.append({'t': 'dash', 'len': 4})
        else:
            els.append({'t': 'note', 'p': r['p'], 'len': r['len'], 'tie': not r['onset'],
                        'ly': r['n'].ly if r['n'] is not None else None})
    # dotted quarter: full-beat note continued by an eighth in next beat
    if (len(els) == 1 and els[0]['t'] == 'note' and els[0]['len'] == 4 and b + 1 < nbeats
            and beats[b + 1][0]['p'] == els[0]['p'] and not beats[b + 1][0]['onset']
            and beats[b + 1][0]['len'] == 2):
        els[0]['dot'] = True; skip.add((b + 1, 0))
    cells.append(els)

# merge rest runs inside a beat, then split bars
bars = [cells[i:i + 4] for i in range(0, len(cells), 4)]
def empty(bar): return all(all(e['t'] == 'rest' for e in c) for c in bar)

# compress long empty stretches
items = []   # ('bar', bar, bar_index) or ('mrest', n, bar_index)
i = 0
while i < len(bars):
    if empty(bars[i]):
        j = i
        while j < len(bars) and empty(bars[j]): j += 1
        if j - i >= 2: items.append(('mrest', j - i, i)); i = j; continue
    items.append(('bar', bars[i], i)); i += 1
def bar_time(bi): return (base + bi * 16) * g + off

# ---- drawing ----
PW, PH = 8.27, 11.69
BARS_PER_LINE = 4
LM, RM = 0.55, 0.45
line_h = 0.95 if LYR else 0.62
FS = 15

def mmss(t): return f"{int(t // 60)}:{int(t % 60):02d}"

def draw_page(fig, page_items, first):
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, PW); ax.set_ylim(0, PH); ax.axis('off')
    y = PH - 0.6
    if first:
        ax.text(PW / 2, y - 0.25, title, ha='center', va='center', fontsize=28, fontproperties=CJK, fontweight='bold')
        ax.text(PW - RM, y - 0.15, subtitle, ha='right', va='center', fontsize=10)
        ax.text(PW - RM, y - 0.40, "auto-transcribed from audio", ha='right', va='center', fontsize=9, color='0.35')
        ax.text(LM, y - 0.15, f"1={keylab}   4/4", ha='left', va='center', fontsize=14)
        ax.text(LM, y - 0.45, f"♩={tempo:.0f}", ha='left', va='center', fontsize=13)
        y -= 1.25
    else:
        y -= 0.3
    width = PW - LM - RM
    lines = [page_items[k:k + BARS_PER_LINE] for k in range(0, len(page_items), BARS_PER_LINE)]
    prev_note_xy = [None]
    for ln in lines:
        bw = width / BARS_PER_LINE
        bwt = lambda els: max(1.4, len(els) * 1.15)           # beat weight: busy beats get more room
        wts = [[6.0] if it[0] == 'mrest' else [bwt(c) for c in it[1]] for it in ln]
        unit = width / sum(sum(w) for w in wts); xcur = LM
        ax.text(LM - 0.05, y + 0.32, mmss(bar_time(ln[0][2])), fontsize=7, color='0.45', ha='left')
        ax.plot([LM, LM], [y - 0.2, y + 0.22], color='k', lw=0.9)
        for k, it in enumerate(ln):
            x0 = xcur; bw = sum(wts[k]) * unit; xcur += bw
            if it[0] == 'mrest':
                ax.text(x0 + bw / 2, y, f"0   (rest {it[1]} bars)", ha='center', va='center', fontsize=11)
                ax.plot([x0 + bw * 0.15, x0 + bw * 0.85], [y + 0.25, y + 0.25], color='k', lw=2.5)
                prev_note_xy[0] = None
            else:
                cw = bw / 4
                for bi, els in enumerate(it[1]):
                    cx0 = x0 + sum(wts[k][:bi]) * unit; cw = wts[k][bi] * unit
                    n = len(els)
                    xs = [cx0 + (j + 0.5) * cw / max(n, 1) for j in range(n)]
                    lv = []
                    for e, x in zip(els, xs):
                        L = e['len']
                        lines_ = 0 if L >= 4 else (1 if L in (2, 3) else 2)
                        if e['t'] == 'dash':
                            ax.text(x, y, '–', ha='center', va='center', fontsize=FS); lv.append(0); continue
                        if e['t'] == 'rest':
                            ax.text(x, y, '0', ha='center', va='center', fontsize=FS)
                            prev_note_xy[0] = None
                        else:
                            d, acc = DEG[(e['p'] - tonic) % 12]
                            octv = (e['p'] - tonic) // 12
                            ax.text(x, y, d, ha='center', va='center', fontsize=FS)
                            if e.get('ly'):
                                ax.text(x, y - 0.48, e['ly'], ha='center', va='center', fontsize=12.5 if len(e['ly']) == 1 else 9, fontproperties=CJK)
                            if acc:
                                ax.text(x - 0.1, y + 0.08, '♯' if acc == '#' else '♭', ha='center', va='center', fontsize=9)
                            for o in range(octv):
                                ax.plot(x, y + 0.2 + 0.08 * o, 'k.', ms=3.5)
                            for o in range(-octv):
                                ax.plot(x, y - 0.17 - 0.06 * lines_ - 0.08 * o, 'k.', ms=3.5)
                            if e.get('tie') and prev_note_xy[0] is not None:
                                px, py = prev_note_xy[0]
                                if abs(py - y) < 1e-6 and x > px:
                                    ax.add_patch(Arc(((px + x) / 2, y + 0.2), x - px, 0.18, theta1=0, theta2=180, lw=0.8))
                            prev_note_xy[0] = (x, y)
                        if L == 3 or e.get('dot'):
                            ax.plot(x + 0.11, y, 'k.', ms=3.5)
                        lv.append(lines_)
                    # underlines (beams)
                    for level in (1, 2):
                        j = 0
                        while j < n:
                            if lv[j] >= level:
                                k2 = j
                                while k2 + 1 < n and lv[k2 + 1] >= level: k2 += 1
                                half = cw / max(n, 1) * 0.38
                                yy = y - 0.15 - 0.06 * (level - 1)
                                ax.plot([xs[j] - half, xs[k2] + half], [yy, yy], color='k', lw=0.9)
                                j = k2 + 1
                            else: j += 1
            ax.plot([x0 + bw, x0 + bw], [y - 0.2, y + 0.22], color='k', lw=0.9)
        y -= line_h
    return y

# paginate
lines_per_page_first, lines_per_page = (9, 11) if LYR else (14, 16)
chunks, k = [], 0
cap = lines_per_page_first * BARS_PER_LINE
while k < len(items):
    chunks.append(items[k:k + cap]); k += cap; cap = lines_per_page * BARS_PER_LINE
with PdfPages(outp + ".pdf") as pdf:
    for pi, ch in enumerate(chunks):
        fig = plt.figure(figsize=(PW, PH), dpi=150)
        draw_page(fig, ch, pi == 0)
        fig.text(0.5, 0.02, f"{pi + 1} / {len(chunks)}", ha='center', fontsize=8, color='0.4')
        pdf.savefig(fig); fig.savefig(f"{outp}_p{pi + 1}.png", dpi=150); plt.close(fig)
print("bars", len(bars), "items", len(items), "pages", len(chunks), "phase", ph)
