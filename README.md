# song2karaoke

A [Claude Code](https://claude.com/claude-code) plugin that turns a song recording into a karaoke package, then checks that the music and lyrics actually line up.

Give it an mp3 or wav (solo or duet) and the lyrics. It produces:

- **Vocals and backing track:** separated with [demucs](https://github.com/facebookresearch/demucs) (htdemucs).
- **Per-singer MIDI and MusicXML:** notes from [basic-pitch](https://github.com/spotify/basic-pitch). Duets are split between the two singers by voice timbre and pitch.
- **A karaoke lyric video:** the backing track plays while each character fills in as it is sung, coloured by who sings it (singer 1, singer 2, or both).
- **Sheet music in your choice of format:** jianpu (简谱, numbered notation), staff notation (五线谱, five-line), or both. You get a PDF per singer and a two-part (二声部) score, with the lyrics under the notes. Staff scores also come as MusicXML for MuseScore, Finale or Dorico.
- **Sync checks:**
  - the video's audio against the original
  - each character's time against where the singing actually starts
  - sung passages that have no lyric on screen
  - a lyric-placement check for the scores

It was built for Mandarin pop duets. The pipeline itself works for any language Whisper handles, but the CJK fonts are set up for macOS (see below).

## Install

```text
/plugin marketplace add qiyanjun/song2karaoke-skill
/plugin install song2karaoke@song2karaoke
```

Then run it as a slash command:

```text
/song2karaoke ~/Music/duet.mp3 ~/Music/duet_lyrics.txt   # full pipeline (asks: jianpu, staff or both)
/song2karaoke ~/Music/duet.mp3 lyrics.txt --score staff  # staff notation only
/song2karaoke ~/Music/duet/ check                        # verify an existing package
/song2karaoke ~/Music/duet/ fix the last chorus repeat is missing
```

(If another skill already uses the name, the plugin's version is `/song2karaoke:song2karaoke`.)

Or just ask in plain words, for example:

> Make a karaoke video and a two-part jianpu score from `~/Music/duet.mp3`. Here are the lyrics with rough times: …

> Check whether `song_karaoke.mp4` is in sync with `song.mp3`.

> The last repeat of the chorus has no lyrics on screen, so add it and re-render the video and the score.

The skill's instructions are in [`skills/song2karaoke/SKILL.md`](skills/song2karaoke/SKILL.md), and every script in `skills/song2karaoke/scripts/` starts with its usage.

## Requirements

- `ffmpeg` and `ffprobe` on your PATH
- Python 3.11 in a virtual environment:

  ```bash
  uv venv -p 3.11 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt
  ```

- **Fonts:** on macOS the scripts use Songti, Hiragino Sans GB and Apple Symbols. On Linux or Windows, edit the font paths at the top of `jianpu.py`, `choir.py` and `lyric_video.py`, using any CJK font plus one that has the ♪ glyph.

## How it works

| Step | Script | Notes |
|---|---|---|
| Separate | `python -m demucs --two-stems=vocals -n htdemucs` | gives the vocals and the backing track |
| Notes | `transcribe_notes.py` | basic-pitch; prints a pitch histogram (two humps ≈ two singers) |
| Split singers | `find_phrases.py`, `assign_singers.py` | clusters phrases by voice timbre; splits overlapping notes high/low |
| Clean up | `clean_export.py` | octave fixes, MusicXML; `auto` key reports the major key (jianpu "1=") |
| Lyric timing | `asr_words.py`, `align_timed.py` | Whisper is used **only for timing**; the text always comes from your lyrics |
| Video | `lyric_video.py` | per-character wipe, singer colours, count-in dots; pass `-` as the second singer for a solo song |
| Scores | `jianpu.py`, `choir.py`, `staff.py` | single-part and two-part jianpu; staff notation via music21, Verovio and resvg (pip only, no MuseScore needed) |
| Verify | `check_sync.py`, `verify_score.py` | video: music sync, timing against the vocals, missing lines. Scores: about 12 numbered PASS/FAIL checks (reproduce, determinism, notes unchanged, changed pages, lyric placement, safe install) |

A few rules the skill follows:
- **Lyric text comes from you, never from speech recognition.** Whisper mishears song lyrics and sometimes repeats its prompt text into the output.
- **Published lyrics often leave out repeated lines.** `check_sync.py` lists sung passages that have no lyric on screen, and you decide whether to follow the published text or what was sung.
- **Outputs are never overwritten in place.** Each new render goes to a scratch folder and is checked, and the old file is backed up before it is replaced. Before regenerating an output, the old one is rebuilt from its old inputs first, to confirm the right command is being used.
- **Everything goes in a `run_log.md`** next to the song: the check results, the changes and your decisions.

## Copyright

This repository contains code only. Use it on recordings and lyrics you have the right to use. Don't commit song audio or lyrics to forks; the `.gitignore` already excludes audio, video and MIDI files.

## License

MIT. Third-party tools keep their own licenses: demucs (MIT), basic-pitch (Apache-2.0), faster-whisper (MIT), music21 (BSD-3), Verovio (LGPL-3.0), resvg (Apache-2.0/MIT), pypdfium2 (Apache-2.0/BSD-3).
