"""Fix octave errors (notes >9 semitones from the local median), drop blips <0.12s, write per-singer MIDI + MusicXML.
usage: clean_export.py in_dir out_dir KEY TITLE
  KEY   major key in music21 spelling (E- for Eb, F#, C, ...) - the jianpu '1=' key - or "auto" to estimate it
reads  in_dir/two_singers.mid (1 instrument for a solo song, 2 for a duet)
writes out_dir/two_singers.mid, out_dir/singer1.mid [, singer2.mid], out_dir/two_singers.musicxml
"""
import sys, numpy as np, pretty_midi, music21 as m21
d, dst, key, title = sys.argv[1:5]
pm = pretty_midi.PrettyMIDI(f"{d}/two_singers.mid"); tempo = pm.get_tempo_changes()[1][0]
for inst in pm.instruments:
    ps = np.array([n.pitch for n in inst.notes]); fixed = 0
    for i, n in enumerate(inst.notes):
        med = np.median(ps[max(0, i - 8):i + 9])
        while n.pitch - med > 9: n.pitch -= 12; fixed += 1
        while med - n.pitch > 9: n.pitch += 12; fixed += 1
    inst.notes = [n for n in inst.notes if n.end - n.start > 0.12]
    ps = [n.pitch for n in inst.notes]
    print(inst.name, len(ps), "notes, octave-fixed", fixed, "range",
          pretty_midi.note_number_to_name(min(ps)), "-", pretty_midi.note_number_to_name(max(ps)))
pm.write(f"{dst}/two_singers.mid")
for k, inst in enumerate(pm.instruments, 1):
    s = pretty_midi.PrettyMIDI(initial_tempo=tempo); s.instruments.append(inst); s.write(f"{dst}/singer{k}.mid")
sc = m21.converter.parse(f"{dst}/two_singers.mid", quantizePost=True, quarterLengthDivisors=(4, 3))
if key == "auto":
    k = sc.analyze('key')
    # jianpu "1=" names the major key (do); a minor result means its relative major (c minor -> Eb)
    maj = k.relative if k.mode == "minor" else k
    key = maj.tonic.name; print("detected key", k, "-> using", maj, "(confirm with the user)")
names = ["Singer 1 (lower)", "Singer 2 (higher)"] if len(sc.parts) > 1 else ["Singer"]
for p, name in zip(sc.parts, names):
    p.partName = name
    for ks in p.recurse().getElementsByClass(m21.key.KeySignature): p.remove(ks, recurse=True)
    p.measure(1).insert(0, m21.key.Key(key))
sc.insert(0, m21.metadata.Metadata()); sc.metadata.title = f"{title} - vocal transcription"
sc.write('musicxml', f"{dst}/two_singers.musicxml")
print("tempo", round(tempo, 1), "key", key)
