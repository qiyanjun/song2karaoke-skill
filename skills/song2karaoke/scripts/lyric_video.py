"""Karaoke-style lyric video: background audio + per-character timed lyrics, coloured by singer.
usage: lyric_video.py lyric_times.json singer1.mid singer2.mid audio.wav out.mp4 title
  solo song: pass "-" for singer2.mid (lines all in singer-1 colour, no legend)
macOS fonts: Hiragino Sans GB for CJK text; Apple Symbols for ♪ (Hiragino has no U+266A).
"""
import sys, json, subprocess, numpy as np, pretty_midi
from PIL import Image, ImageDraw, ImageFont

LYR, M1, M2, AUD, OUT, TITLE = sys.argv[1:7]
W, H, FPS = 1280, 720, 25
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
f_big, f_next, f_small, f_title = (ImageFont.truetype(FONT, s) for s in (64, 40, 22, 96))
f_sym = ImageFont.truetype("/System/Library/Fonts/Apple Symbols.ttf", 48)   # Hiragino has no U+266A ♪

def note_text(d, label, fill):
    """Draw centred `label + ♪` at y=330, the note glyph in a font that has it."""
    gap = 12 if label else 0
    wl, wn = f_next.getlength(label), f_sym.getlength("♪")
    x = W // 2 - (wl + gap + wn) / 2
    if label: d.text((x, 330), label, font=f_next, fill=fill, anchor="lm")
    d.text((x + wl + gap, 330), "♪", font=f_sym, fill=fill, anchor="lm")
COL = {1: (110, 190, 255), 2: (255, 140, 190), 3: (255, 210, 90)}       # singer1, singer2, both
NAME = {1: "Singer 1", 2: "Singer 2", 3: "合唱 (both)"}
WHITE, DIM = (240, 240, 240), (120, 120, 135)

chars = json.load(open(LYR))
lines = {}
for c in chars: lines.setdefault(c['line'], []).append(c)
lines = [sorted(v, key=lambda c: c['pos']) for _, v in sorted(lines.items(), key=lambda kv: min(c['t'] for c in kv[1]))]

def active(mid):
    return [(n.start, n.end) for n in pretty_midi.PrettyMIDI(mid).instruments[0].notes]
A1 = active(M1); A2 = active(M2) if M2 != "-" else []; SOLO = not A2
def cover(iv, a, b):
    return sum(max(0, min(e, b) - max(s, a)) for s, e in iv) / max(b - a, 1e-6)

L = []
for i, ln in enumerate(lines):
    ts = [c['t'] for c in ln]
    nxt = lines[i + 1][0]['t'] if i + 1 < len(lines) else ts[-1] + 3
    end = min(ts[-1] + 1.2, nxt - 0.05)
    c1, c2 = cover(A1, ts[0], end), cover(A2, ts[0], end)
    who = 1 if SOLO else (3 if min(c1, c2) > 0.35 else (1 if c1 >= c2 else 2))
    text = "".join(c['ch'] for c in ln)
    # pre-render white and coloured versions
    bw = int(f_big.getlength(text)) + 8
    img_w = Image.new("RGBA", (bw, 90), (0, 0, 0, 0)); img_c = img_w.copy()
    for img, col in ((img_w, WHITE), (img_c, COL[who])):
        d = ImageDraw.Draw(img); d.text((4, 6), text, font=f_big, fill=col + (255,), stroke_width=2, stroke_fill=(10, 10, 20, 255))
    xs = [4 + f_big.getlength(text[:k]) for k in range(len(text) + 1)]
    L.append(dict(text=text, ts=ts, start=ts[0] - 0.35, end=end, who=who, w=img_w, c=img_c, xs=xs))

# background: vertical gradient
yy = np.linspace(0, 1, H)[:, None, None]
bg = ((1 - yy) * np.array([18, 20, 38]) + yy * np.array([45, 22, 48])).repeat(W, 1).astype(np.uint8)
bg_img = Image.fromarray(bg)

def wipe_x(ln, t):
    ts, xs = ln['ts'], ln['xs']
    if t < ts[0]: return 0
    for k in range(len(ts)):
        t0 = ts[k]; t1 = ts[k + 1] if k + 1 < len(ts) else ts[k] + 0.6
        t1 = min(t1, t0 + 0.8)
        if t < t1: return xs[k] + (xs[k + 1] - xs[k]) * max(0, (t - t0) / max(t1 - t0, 1e-3))
        if k + 1 < len(ts) and t < ts[k + 1]: return xs[k + 1]
    return xs[-1] + 10

dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", AUD]))
ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                       "-i", "-", "-i", AUD, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-shortest", OUT], stdin=subprocess.PIPE)
first = L[0]['start']
for fi in range(int(dur * FPS) + 1):
    t = fi / FPS
    fr = bg_img.copy(); d = ImageDraw.Draw(fr)
    d.text((40, 30), TITLE, font=f_small, fill=(200, 200, 210))
    d.text((W - 40, 30), f"{int(t // 60)}:{int(t % 60):02d}", font=f_small, fill=(160, 160, 175), anchor="ra")
    # legend
    lx = 40
    for k in (() if SOLO else (1, 2, 3)):
        d.ellipse((lx, H - 44, lx + 14, H - 30), fill=COL[k]); d.text((lx + 22, H - 48), NAME[k], font=f_small, fill=(190, 190, 200)); lx += 190
    cur = next((ln for ln in L if ln['start'] <= t < ln['end']), None)
    upcoming = [ln for ln in L if ln['start'] > t]
    intro = t < first - 4
    if intro:
        d.text((W // 2, H // 2 - 40), TITLE, font=f_title, fill=WHITE, anchor="mm")
        d.text((W // 2, H // 2 + 50), "伴奏 · 歌词 (instrumental with lyrics)", font=f_small, fill=(180, 180, 195), anchor="mm")
    if cur:
        x0 = (W - cur['w'].width) // 2; y0 = 290
        fr.paste(cur['w'], (x0, y0), cur['w'])
        wx = int(wipe_x(cur, t))
        if wx > 0:
            cut = cur['c'].crop((0, 0, min(wx, cur['c'].width), cur['c'].height))
            fr.paste(cut, (x0, y0), cut)
        d.ellipse((x0 - 34, y0 + 38, x0 - 18, y0 + 54), fill=COL[cur['who']])
    nxt = upcoming[0] if upcoming else None
    if nxt and (nxt['start'] - t) < 12 and not intro:
        d.text((W // 2, 450), nxt['text'], font=f_next, fill=DIM, anchor="mm")
        gap = nxt['start'] - t
        if not cur and gap < 4:                 # count-in dots before a line
            for k in range(int(np.ceil(gap))):
                d.ellipse((W // 2 - 45 + k * 30, 360, W // 2 - 33 + k * 30, 372), fill=COL[nxt['who']])
        elif not cur and t > first:
            note_text(d, "间奏", (170, 170, 185))
    elif not cur and t > first:
        note_text(d, "", (170, 170, 185))
    ff.stdin.write(fr.tobytes())
ff.stdin.close(); ff.wait()
print("lines", len(L), "duration", round(dur, 1), "->", OUT)
