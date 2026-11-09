"""Vocal stem -> raw polyphonic MIDI with basic-pitch (both singers mixed together).
usage: transcribe_notes.py vocals.wav raw.mid
Prints a pitch histogram: two humps = two singers, one = solo."""
import sys, numpy as np
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
wav, out = sys.argv[1], sys.argv[2]
model_out, midi, notes = predict(wav, minimum_frequency=80, maximum_frequency=1100, onset_threshold=0.5, frame_threshold=0.3, minimum_note_length=100)
midi.write(out)
notes = sorted(notes, key=lambda n: n[0])
p = np.array([n[2] for n in notes])
print(len(notes), "notes; pitch range", p.min(), p.max())
h = np.bincount(p, minlength=100)
for k in range(p.min(), p.max()+1): print(k, '#'*(h[k]//5))
