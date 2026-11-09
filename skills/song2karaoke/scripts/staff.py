"""Staff-notation (五线谱) score with lyrics, one staff per singer: PDF + page PNGs + MusicXML.
usage: staff.py lyrics.json out_prefix title key_label upper.mid[=Label] [lower.mid[=Label]]
  key_label  major key ("Eb", "♭E", "F#", "C" ...), as for choir.py
  env DUMP=path.json  also write every note with its attached lyric (for check_score.py)
Lyrics are attached to notes exactly as in choir.py/jianpu.py, so staff and jianpu scores agree.
Engraving: music21 -> MusicXML -> Verovio (SVG) -> resvg (PNG) -> Pillow (PDF). All pip-installable.
Runs of 2+ bars where every part rests are shown as one multi-bar rest.
"""
import sys, os, io, json, numpy as np, pretty_midi, music21 as m21, verovio, resvg_py
from PIL import Image, ImageDraw, ImageFont

LYR, outp, title, keylab = sys.argv[1:5]
specs = sys.argv[5:]
mids = [s.split("=", 1)[0] for s in specs]
labels = [s.split("=", 1)[1] if "=" in s else (f"Singer {len(specs) - i}" if len(specs) > 1 else "Singer")
          for i, s in enumerate(specs)]

# ---------- timing grid + lyric attachment (same algorithm as choir.py) ----------
pm0 = pretty_midi.PrettyMIDI(mids[0]); tempo = pm0.get_tempo_changes()[1][0]
g = 60 / tempo / 4
allst = [n.start for f in mids for n in pretty_midi.PrettyMIDI(f).instruments[0].notes]
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

parts = [load_part(m) for m in mids]
if os.environ.get("DUMP"):
    json.dump([[{"s": n.start, "e": n.end, "p": n.pitch, "ly": n.ly} for n in pt] for pt in parts],
              open(os.environ["DUMP"], "w"), ensure_ascii=False)
alln = [n for pt in parts for n in pt]
on = np.array([U(n.start) for n in alln]); en = np.array([U(n.end) for n in alln])
best = None
for ph in range(16):
    sc_ = 2 * np.sum((on - ph) % 16 == 0) + np.sum((on - ph) % 4 == 0) - 1.5 * np.sum(((on - ph) // 16) != ((en - 1 - ph) // 16))
    if best is None or sc_ > best[0]: best = (sc_, ph)
ph = best[1]
first_bar = (on.min() - ph) // 16; last_bar = (en.max() - 1 - ph) // 16
base = first_bar * 16 + ph; nbars = last_bar - first_bar + 1; total_ql = nbars * 4

# ---------- key ----------
def key_pc(lab):
    s = lab.strip().replace("♭", "b").replace("♯", "#")
    i = next((k for k, c in enumerate(s) if c in "ABCDEFG"), None)
    if i is None:
        i = next(k for k, c in enumerate(s) if c in "abcdefg"); s = s[:i] + s[i].upper() + s[i + 1:]
    rest = s[:i] + s[i + 1:]
    return ({"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[s[i]] + rest.count("#") - rest.count("b")) % 12
KEYNAME = {0: "C", 1: "D-", 2: "D", 3: "E-", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "A-", 9: "A", 10: "B-", 11: "B"}
key = m21.key.Key(KEYNAME[key_pc(keylab)])

# ---------- music21 score ----------
score = m21.stream.Score()
for pi, (pt, lab) in enumerate(zip(parts, labels)):
    p = m21.stream.Part(); p.partName = lab; p.partAbbreviation = lab
    med = np.median([n.pitch for n in pt]) if pt else 67
    p.insert(0, m21.clef.Treble8vbClef() if med < 60 else m21.clef.TrebleClef())
    p.insert(0, m21.key.Key(key.tonic, key.mode)); p.insert(0, m21.meter.TimeSignature("4/4"))
    for n in pt:
        s, e = U(n.start) - base, U(n.end) - base
        if e <= s or s < 0: continue
        x = m21.note.Note(n.pitch, quarterLength=(e - s) / 4)
        x.pitch.spellingIsInferred = True
        if n.ly:
            x.lyric = n.ly
        p.insert(s / 4, x)
    p.makeRests(refStreamOrTimeRange=[0.0, float(total_ql)], fillGaps=True, inPlace=True)
    pm_ = p.makeMeasures(); pm_.makeTies(inPlace=True)
    # spell black keys with flats in flat keys, sharps in sharp keys
    for nn in pm_.recurse().notes:
        a = nn.pitch.accidental
        if a is not None and ((key.sharps < 0 and a.alter > 0) or (key.sharps > 0 and a.alter < 0)):
            nn.pitch = nn.pitch.getEnharmonic()
    # accidentals by the standard rule: show one only where the pitch differs from the key signature or
    # from an earlier accidental on the same line/space in this bar; never on a tied continuation
    key_alter = {p.step: p.accidental.alter for p in key.alteredPitches}
    for m in pm_.getElementsByClass(m21.stream.Measure):
        state = {}
        for nn in m.notes:
            p = nn.pitch; alt = p.accidental.alter if p.accidental is not None else 0
            want = state.get((p.step, p.octave), key_alter.get(p.step, 0))
            show = alt != want and not (nn.tie is not None and nn.tie.type in ("stop", "continue"))
            if show and p.accidental is None: p.accidental = m21.pitch.Accidental("natural")
            if p.accidental is not None:
                if alt == 0 and not show: p.accidental = None
                else: p.accidental.displayStatus = show; p.accidental.displayType = "always" if show else "never"
            state[(p.step, p.octave)] = alt
    score.insert(0, pm_)

# bars where every part rests (condensed to multi-bar rests in the MusicXML below)
meas = [list(p.getElementsByClass(m21.stream.Measure)) for p in score.parts]
nm = min(len(m) for m in meas)
empty = [all(not list(m[i].notes) for m in meas) for i in range(nm)]
runs, i = [], 0
while i < nm:
    if empty[i]:
        j = i
        while j < nm and empty[j]: j += 1
        if j - i >= 2: runs.append((i, j - i))
        i = j
    else: i += 1

score.insert(0, m21.metadata.Metadata()); score.metadata.title = title
xml_path = outp + ".musicxml"
score.write("musicxml", xml_path)
import xml.etree.ElementTree as ET
tree = ET.parse(xml_path); root = tree.getroot()
for part in root.findall("part"):
    ms = part.findall("measure")
    for i, n in runs:
        m = ms[i]; att = m.find("attributes")
        if att is None: att = ET.Element("attributes"); m.insert(0, att)
        ms_ = ET.SubElement(att, "measure-style"); ET.SubElement(ms_, "multiple-rest").text = str(n)
for t in root.iter("text"):          # several characters sharing one note: smaller so they fit under it
    if t.text and len(t.text) > 1: t.set("font-size", "7.5" if len(t.text) == 2 else "6")
tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
# Verovio measures text with Latin font metrics, so CJK lyrics count as ~zero width and collide.
# For rendering only, pad each lyric with no-break spaces (symmetric, so the text stays centred).
PAD = float(os.environ.get("LYRIC_PAD", "1.6"))          # NBSPs per character on each side
for t in root.iter("text"):
    if t.text:
        k = sum(1 for c in t.text if ord(c) > 0x2E80); pad = "\u00a0" * int(round(PAD * k))
        t.text = pad + t.text + pad
render_xml = outp + ".render.musicxml"
tree.write(render_xml, encoding="UTF-8", xml_declaration=True)

# ---------- engrave ----------
W, H = 1654, 2339                      # A4 at 200 dpi
TOP = 250                              # px kept free at the top of every page (title block on page 1)
tk = verovio.toolkit()
tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 50, "header": "none", "footer": "none",
               "pageMarginTop": 120 + int(TOP * 2970 / H), "pageMarginBottom": 120, "pageMarginLeft": 110, "pageMarginRight": 110,
               "lyricSize": 4.5, "svgViewBox": True, "breaks": "auto", "spacingSystem": 14, "mmOutput": False})
tk.loadFile(render_xml)
npages = tk.getPageCount()
CJK = None
for f in ("/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
          "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
    if os.path.exists(f): CJK = f; break
font = (lambda s: ImageFont.truetype(CJK, s)) if CJK else (lambda s: ImageFont.load_default())
SYM = next((f for f in ("/System/Library/Fonts/Apple Symbols.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            if os.path.exists(f)), None)
def text_mixed(d, xy, txt, size, fill, anchor):
    """draw txt with ♭ ♯ ♩ in a symbol font; anchor 'lm' or 'rm'"""
    segs = [(c, ImageFont.truetype(SYM, size) if (SYM and c in "♭♯♩") else font(size)) for c in txt]
    w = sum(fo.getlength(c) for c, fo in segs); x = xy[0] - (w if anchor == "rm" else 0)
    for c, fo in segs: d.text((x, xy[1]), c, font=fo, fill=fill, anchor="lm"); x += fo.getlength(c)
imgs = []
for pg in range(1, npages + 1):
    png = bytes(resvg_py.svg_to_bytes(svg_string=tk.renderToSVG(pg), width=W, background="white"))
    im = Image.open(io.BytesIO(png)).convert("RGB")
    page = Image.new("RGB", (W, H), "white")
    page.paste(im, (0, 0))
    if pg == 1:
        d = ImageDraw.Draw(page)
        d.text((W // 2, 95), title, font=font(64), fill="black", anchor="mm")
        d.text((W // 2, 160), "五线谱" if len(parts) == 1 else "二声部 · 五线谱", font=font(26), fill=(80, 80, 80), anchor="mm")
        text_mixed(d, (90, 215), f"1={keylab}   4/4   ♩={tempo:.0f}", 28, "black", "lm")
        d.text((W - 90, 215), "  /  ".join(f"{l}" for l in labels) + "   ·   auto-transcribed from audio",
               font=font(20), fill=(100, 100, 100), anchor="rm")
    ImageDraw.Draw(page).text((W - 90, H - 60), f"{pg}/{npages}", font=font(22), fill="black", anchor="rm")
    page.save(f"{outp}_p{pg}.png"); imgs.append(page)
imgs[0].save(outp + ".pdf", save_all=True, append_images=imgs[1:], resolution=200)
os.remove(render_xml)
print("tempo", round(tempo, 1), "key", key, "bars", nbars, "pages", npages, "parts", labels)
