"""Whisper (faster-whisper medium) word timings on the vocal stem; used ONLY for timing, never for lyric text.
usage: asr_words.py vocals.wav lyrics_plain.txt words.json
lyrics_plain.txt (one phrase per line) is the initial prompt: it steers recognition but can leak into the output,
so never copy text from words.json into the lyrics."""
import sys, json
from faster_whisper import WhisperModel
m = WhisperModel("medium", device="cpu", compute_type="int8")
prompt = open(sys.argv[2]).read().replace("\n", "，")
segs, info = m.transcribe(sys.argv[1], language="zh", word_timestamps=True, initial_prompt=prompt,
                          vad_filter=True, condition_on_previous_text=False)
out = []
for s in segs:
    for w in s.words: out.append((w.start, w.end, w.word))
    print(f"{s.start:6.1f}-{s.end:6.1f} {s.text}", flush=True)
json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False)
