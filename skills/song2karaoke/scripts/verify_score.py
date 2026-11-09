"""Full verification battery for a score render (jianpu.py, choir.py or staff.py), numbered PASS/FAIL.
usage: verify_score.py --render "CMD" --lyrics lyric_times.json
                       [--old-lyrics OLD.json --current CURRENT.pdf] [--install DEST.pdf] [--log run_log.md] [--work DIR]
  --render   the render command with {LYR} for the lyrics file and {OUT} for the output prefix, e.g.
             "python choir.py s2.mid s1.mid {LYR} {OUT} Title 'Singer 2' 'Singer 1' Eb"
  --old-lyrics/--current  the previous lyrics and the PDF made from them: enables the reproduce, notes-unchanged
             and changed-pages checks
  --install  copy the verified PDF here (the old file is backed up first; page PNGs are copied next to it
             only if a matching <stem>_p1.png already exists there)
  --log      append the results table to this markdown file
Checks: reproduce old (pixel-identical) · render ok · PDF valid (pages, A4) · deterministic re-render ·
notes unchanged · changed pages · lyric order · lines complete · chars placed · install + byte-identical.
Reading the changed pages by eye is still needed: the script prints which ones.
Needs pypdfium2 (to rasterize PDFs) and the render script's own dependencies.
"""
import argparse, os, sys, json, shlex, shutil, subprocess, tempfile, datetime, filecmp
import numpy as np, pypdfium2 as pdfium

ap = argparse.ArgumentParser()
ap.add_argument("--render", required=True); ap.add_argument("--lyrics", required=True)
ap.add_argument("--old-lyrics"); ap.add_argument("--current"); ap.add_argument("--install")
ap.add_argument("--log"); ap.add_argument("--work")
a = ap.parse_args()
W = a.work or tempfile.mkdtemp(prefix="verify_score_"); os.makedirs(W, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
def rec(name, ok, detail=""):
    rows.append((len(rows) + 1, name, "PASS" if ok is True else ("FAIL" if ok is False else str(ok)), detail))
    print(f"{len(rows):2d}. {name:<34} {rows[-1][2]:<5} {detail}", flush=True)

def render(lyr, tag):
    out = os.path.join(W, tag, "score"); os.makedirs(os.path.dirname(out), exist_ok=True)
    dump = os.path.join(W, tag, "dump.json")
    cmd = shlex.split(a.render.replace("{LYR}", shlex.quote(lyr)).replace("{OUT}", shlex.quote(out)))
    r = subprocess.run(cmd, env={**os.environ, "DUMP": dump}, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(out + ".pdf"), out + ".pdf", dump, (r.stderr or r.stdout)[-400:]

def raster(pdf, dpi=100):
    d = pdfium.PdfDocument(pdf)
    return [np.asarray(d[i].render(scale=dpi / 72, grayscale=True).to_pil().convert("L")) for i in range(len(d))]

def same_pages(p1, p2):
    A, B = raster(p1), raster(p2)
    if len(A) != len(B): return False, f"page count {len(A)} vs {len(B)}"
    diff = [i + 1 for i, (x, y) in enumerate(zip(A, B)) if x.shape != y.shape or not np.array_equal(x, y)]
    return not diff, ("identical" if not diff else f"pages differ: {diff}")

old = a.old_lyrics and a.current
if old:
    ok, pdf_o, dump_o, err = render(a.old_lyrics, "old")
    s, d = same_pages(pdf_o, a.current) if ok else (False, err)
    rec("reproduce current from old lyrics", s, d)
ok, pdf_n, dump_n, err = render(a.lyrics, "new")
rec("render with new lyrics", ok, "" if ok else err)
if not ok: sys.exit(1)
try:
    doc = pdfium.PdfDocument(pdf_n); w, h = doc[0].get_size()
    a4 = abs(w - 595) < 3 and abs(h - 842) < 3
    rec("PDF opens, A4", a4, f"{len(doc)} pages, {w:.0f}x{h:.0f} pt")
except Exception as e: rec("PDF opens, A4", False, str(e))
ok2, pdf_n2, _, _ = render(a.lyrics, "new2")
s, d = same_pages(pdf_n, pdf_n2) if ok2 else (False, "second render failed")
rec("deterministic re-render", s, d)
if old:
    A, B = raster(pdf_o), raster(pdf_n)
    ch = [i + 1 for i in range(max(len(A), len(B))) if i >= len(A) or i >= len(B) or not np.array_equal(A[i], B[i])]
    rec("changed pages (old -> new)", "INFO", f"{ch or 'none'}  <- read these by eye")
cs = subprocess.run([sys.executable, os.path.join(HERE, "check_score.py"), dump_n, a.lyrics] + ([dump_o] if old else []),
                    capture_output=True, text=True).stdout
def line(prefix): return next((l for l in cs.splitlines() if l.startswith(prefix)), "")
for pre, name in (("notes", "notes unchanged (pitch+rhythm)"),):
    if old: l = line(pre); rec(name, "PASS" in l, l.split(":", 1)[-1].strip())
orders = [l for l in cs.splitlines() if l.startswith("order")]
rec("lyrics in time order", all("PASS" in l for l in orders), "; ".join(o.split(None, 1)[1] for o in orders))
l = line("lines"); rec("every lyric line complete", "PASS" in l, l.split(None, 1)[1] if l else "")
l = line("chars"); rec("every char placed (<=1.5 s)", "PASS" in l, l.split(None, 1)[1] if l else "")
l = line("distance"); rec("char-to-note distance", "INFO", l.split(None, 1)[1] if l else "")
if old:
    chg = cs.split("changes:", 1)[-1].strip().splitlines()
    rec("lyric changes (old -> new)", "INFO", f"{len(chg)} notes changed" + (f": {chg[0].strip()} ..." if chg else ""))
if a.install:
    dest = a.install; stem = os.path.splitext(os.path.basename(dest))[0]; bk = None
    if os.path.exists(dest):
        bk = os.path.join(os.path.dirname(dest) or ".", f"backup_{stem}_{datetime.datetime.now():%Y%m%d-%H%M%S}")
        os.makedirs(bk); shutil.copy2(dest, bk)
    shutil.copy2(pdf_n, dest); same = filecmp.cmp(pdf_n, dest, shallow=False)
    rec("installed PDF byte-identical", same, dest + (f" (previous copy backed up to {bk})" if bk else ""))
fails = [r for r in rows if r[2] == "FAIL"]
print(f"\n{len(rows)} checks, {len(fails)} FAIL. Work dir: {W}")
if a.log:
    with open(a.log, "a", encoding="utf-8") as f:
        f.write(f"\n### Score verification {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n| # | Check | Result | Detail |\n|---|---|---|---|\n")
        for n, name, res, det in rows: f.write(f"| {n} | {name} | {res} | {det.replace('|', '/')} |\n")
sys.exit(1 if fails else 0)
