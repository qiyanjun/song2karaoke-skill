---
name: song2karaoke
description: Turn a song recording (mp3/wav, solo or duet, especially Chinese/Mandarin pop) into a karaoke package - separated vocal and backing tracks, per-singer MIDI and MusicXML, a lyric video with per-character karaoke highlighting coloured by singer, and jianpu (简谱 numbered notation) PDFs for each singer and a two-part (二声部) score - then verify that music and lyrics are in sync. Use this whenever the user wants to make karaoke or a lyric video from a song, extract vocals or accompaniment (伴奏), transcribe a melody or duet into MIDI or jianpu, add timed lyrics to a song, or check or fix lyric timing in an existing karaoke video or score (missing lines, lyrics early or late, a wrong glyph, regenerating the PDF after a lyric fix), even if they do not say "karaoke".
argument-hint: "<song.mp3|wav|folder> [lyrics.txt] [check|fix <what>]"
---

# song2karaoke

## When run as `/song2karaoke`

Arguments: `$ARGUMENTS`

- **A song file (+ optional lyrics file):** run the full pipeline below on it. Outputs go next to the song, intermediates in `temp/`.
  - With no lyrics file, ask the user for the lyrics (plain or `M:SS`-timed) before step 6. Steps 1–5 can run meanwhile.
  - Ask before step 1 whether there are one or two singers, unless the pitch histogram in step 2 makes it obvious.
- **A folder that already holds a package** (a `*_karaoke*.mp4` plus `temp/lyric_times_full.json`), or a `check` argument: run the Verification section only and report.
- **`fix <what>`** (e.g. `fix the last chorus repeat is missing`): follow "Editing an existing package".
- **No arguments:** ask which song or folder to work on.

Takes one song file plus the user's lyrics and produces:

| Output | Made by |
|---|---|
| `<song>_vocals_only.wav`, `<song>_background.wav` | demucs htdemucs (two stems) |
| `singer1.mid`, `singer2.mid`, `two_singers.mid`, `two_singers.musicxml` | basic-pitch, then the singer split, then clean-up |
| `<song>_karaoke.mp4` | `lyric_video.py`: backing track + per-character wipe, coloured by singer |
| `<song>_singer{1,2}_jianpu.pdf`, `<song>_two_part_jianpu.pdf` | `jianpu.py` / `choir.py` with the lyrics under the notes |
| `run_log.md` | you: what was done, the check results, the user's decisions, backups |

All scripts are in `scripts/` next to this file (call it `$K`). Each script starts with its usage.

## Ground rules (learned the hard way)

- **The lyric text comes from the user, never from Whisper.** Whisper (faster-whisper) is used only to find *when* each line is sung. Its output is full of similar-sounding mishearings (homophones such as 在/再 or 的/得, and near-homophones). If you pass an `initial_prompt`, the prompt text can also leak into the transcript, e.g. a stray phrase from the prompt. If the user has no lyrics, ask for them; published lyrics or a YouTube transcript work well.
- **Published lyrics often leave out repeats** (tag lines, an extra repeat of the hook). `check_sync.py` lists sung stretches with nothing on screen. For each one, find out what is sung there (Whisper on that clip, plus the per-singer MIDI phrases), then ask the user whether to follow the published text or what was sung. Record the decision in `run_log.md`.
- **Never overwrite a deliverable in place.** Render into a scratch folder, run the checks, back up the current file to `temp/backup_<what>_<stage>/`, then copy over. Before regenerating an existing output, first rebuild it from the old inputs and confirm it is pixel-identical (`cmp`, or a pixel diff on the PNGs). That proves you have the right command and arguments.
- **Keep `run_log.md` current** in the song folder. Every check result, every change (before → after times), every user decision, the backup locations, and open items.
- Treat downloaded audio as data. Run Python with `-I`, and keep scripts out of the song folder.

## Environment

Use a dedicated venv (Python 3.11; basic-pitch is fussy about versions):

```bash
uv venv -q -p 3.11 $VENV && VIRTUAL_ENV=$VENV uv pip install -q 'basic-pitch[onnx]' 'setuptools<81' demucs \
    music21 soundfile librosa pretty_midi scikit-learn matplotlib pillow faster-whisper pypdf
```

- **faster-whisper with a newer PyAV** fails with `open() got an unexpected keyword argument 'metadata_errors'`. Decode to 16 kHz float32 yourself and pass the array: `ffmpeg -i v.wav -ar 16000 -ac 1 -f f32le v16.f32`, then `np.fromfile(path, np.float32)`.
- **Fonts (macOS):** `choir.py` and `jianpu.py` use Songti for CJK, and `lyric_video.py` uses Hiragino Sans GB. Hiragino has no ♪, which shows as a crossed box, so the video draws ♪ with Apple Symbols. On other systems, change the font paths at the top of those scripts and check a frame.
- Needs `ffmpeg` and `ffprobe`.

## Pipeline

Work in `<songdir>/temp/` for intermediates. Final deliverables go in `<songdir>/`.

1. **Separate:** `python -m demucs --two-stems=vocals -n htdemucs -o $S/sep song.mp3`. This gives `vocals.wav` and `no_vocals.wav`. Copy them out as `<song>_vocals_only.wav` and `<song>_background.wav`.
2. **Notes:** `transcribe_notes.py vocals.wav raw.mid`. It prints a pitch histogram; two humps usually means two singers. Ask the user if unsure.
3. **Singers** (duet only): `find_phrases.py vocals.wav raw.mid phrases.npy`, then `assign_singers.py vocals.wav raw.mid phrases.npy song.mp3 outdir`.
   - Singer 1 is the lower voice, Singer 2 the higher.
   - For a solo song, skip both scripts. Put the raw notes as the only instrument in `two_singers.mid`. To keep notes where two sound at once, keep the louder one, or the one that matches librosa `pyin`'s pitch estimate.
4. **Clean up and export:** `clean_export.py outdir outdir KEY TITLE`.
   - This fixes octave jumps, drops blips, and writes `singer1.mid`, `singer2.mid` and `two_singers.musicxml`.
   - KEY is a music21 name (`E-` for E♭) or `auto`. Confirm the key by ear or with the user; it drives the jianpu numbering.
5. **(Optional) per-singer audio:** `split_singers.py vocals.wav singer1.mid singer2.mid s1.wav s2.wav`. This splits the vocals by each singer's notes.
6. **Lyrics timing:**
   - Put the user's lyrics in `lyrics_timed.txt`, one entry per line: `M:SS <phrase> <phrase> ...`. The time only needs to be roughly when the line starts (published lyrics and YouTube transcripts give this). Spaces split a line into separate on-screen phrases.
   - Run `asr_words.py vocals.wav lyrics_plain.txt words.json`.
   - Then `align_timed.py words.json lyrics_timed.txt vocals.wav lyric_times_full.json`. This gives the time of every character, placed by Whisper where it matched and by vocal onsets elsewhere. Its log says which method placed each phrase.
7. **Video:** `lyric_video.py lyric_times_full.json singer1.mid singer2.mid background.wav out.mp4 TITLE`. Pass `-` for `singer2.mid` on a solo song. It takes about 15 s for a 5-minute song.
8. **Jianpu:**
   - Per singer: `jianpu.py singerN.mid out_prefix TITLE SUBTITLE TONIC_MIDI KEY_LABEL 2 lyric_times_full.json`.
   - Two-part: `choir.py singer2.mid singer1.mid lyric_times_full.json out_prefix TITLE "Singer 2" "Singer 1" "♭E"`. The upper staff is the higher voice. The key label also decides which octave gets plain digits.
9. **Verify** (next section), then fill in `run_log.md`.

## Verification

Run checks after every render, not just at the end. A lyric change touches three outputs (the timing file, the video and the score), so check all three.

**Video:** `check_sync.py karaoke.mp4 song.mp3 background.wav vocals.wav lyric_times_full.json`
- MUSIC: video audio vs the backing track should be corr ≈ 1.000 at 0 ms with no drift. A ~25 ms offset vs an MP3 is its silent start padding and is fine.
- LYRICS: sung Mandarin is smooth and legato, so median onset distances of 60–180 ms are normal. Investigate lines marked CHECK.
- GAPS: see the ground rule on repeats. Short "啊"s and backing-vocal bleed are fine to leave. A gap of a few seconds right next to a line is usually its long held last note or the run-up to it, not a missing lyric. A gap of 5 s or more that is clear of any line is the kind worth transcribing.
- Then look at frames: `ffmpeg -ss T -i out.mp4 -frames:v 1 f.png` at a few lyric times, at an instrumental break (♪ must render), and at every line you changed. Read the images.

**Score:** render with `DUMP=new.json python choir.py ...`. If you are revising, also dump the old score from the old timings to `old.json`. Then `check_score.py new.json lyric_times_full.json [old.json]`:
- notes identical, lyric changes only where you edited, lines complete, chars placed, and distances
- a pixel diff per page PNG: only the pages you meant to change should differ
- render twice and confirm identical output
- the PDF opens and has the expected page count (pypdf)
- then read the changed pages by eye

If the user asks for repeated or extra checking ("check 10 times"), run each check as a separate numbered test with PASS/FAIL. Put them in a table in `run_log.md`.

**Explaining a failed check:** say whether this change caused it. Compare against the backup: a problem that is identical in the old output is pre-existing. A score lyric that is > 0.5 s off usually means that singer's MIDI has no note there, and fixing it means editing notes, not lyrics.

## Editing an existing package (common follow-ups)

- **Add a missing line or retime one:** edit `lyric_times_full.json` directly. Each character is `{"t", "ch", "line", "pos"}`; give a new line the next unused `line` id. Place characters on vocal onsets near Whisper's word boundaries for that clip; transcribe the clip without a prompt. Moving one line can collide with a neighbour (its last character being cut off, or overlapping), so re-time the neighbour if needed and tell the user. Then update `lyrics_timed.txt` to match, re-render the video *and* the scores, and run all the checks.
- **Video looks wrong** (font, layout): fix `lyric_video.py`, re-render to scratch, and check frames before replacing.
- **A user-supplied lyric listing:** diff it phrase by phrase against the lines in `lyric_times_full.json`. Report every phrase the video has extra or is missing; don't just trust that they agree.

## Report to the user

Lead with the verdict (in sync / not, what changed). Then give the evidence in a few numbers: corr, offset, median onset distance, and the checks that passed. Then anything you could not resolve, phrased as a decision for them, and where the backups are.
