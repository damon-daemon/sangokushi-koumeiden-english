# Sangokushi Koumeiden — English Translation

A fan translation of **Sangokushi Koumeiden** (三國志孔明伝, Koei) for the PlayStation into
English. It is the sequel to *Sangokushi Eiketsuden*: a story-driven tactics game in which you
follow Zhuge Liang (Kongming) from his first days in Liu Bei's service, through Chibi and the
founding of Shu, to the northern campaigns, with hex-map battles, councils, towns and shops in
between. The game was only released in Japan.

> **This is a full machine translation.** All of the game's text was translated from
> Japanese by an AI model, not by a human translator, and it has not been
> proofread by a fluent Japanese speaker. Expect occasional mistranslations, awkward
> phrasing and inconsistent terms. Corrections are welcome.

> **This is a beta.** All of the game's text is in English, but only the opening of the game
> (the prologue, Xinye, the Bowang battle and the start of the Xinye fire battle) has been played
> in order. A few later scenes were only checked by jumping to them. Expect some text that is
> squeezed, cut short or wrapped oddly later on.

This repository contains the English text and the tools that build the patch.
It does **not** contain the game, any of its data, or the Japanese script — you need
your own copy of the game.

## Screenshots

| | | |
|:-:|:-:|:-:|
| ![Dialogue](docs/screenshots/01_dialogue.png) | ![Narration](docs/screenshots/02_narration.png) | ![Choice](docs/screenshots/03_choice.png) |
| Event dialogue | Narration | Choices |
| ![Battle](docs/screenshots/04_battle.png) | ![Battle message](docs/screenshots/05_battle_message.png) | ![Sortie](docs/screenshots/06_sortie.png) |
| Battle | Battle messages | Choosing units for a battle |
| ![World map](docs/screenshots/07_world_map.png) | ![Town](docs/screenshots/08_town.png) | ![Items](docs/screenshots/09_items.png) |
| World map | Town | Items |

## What's translated

- All event text: every chapter's dialogue, narration, scene captions and choices
- Town people's lines and the officers' retreat lines in battle
- Officer, unit type, item and strategy names and descriptions, place and battle names
- Menus, battle messages, map commentary, shop, save and memory card messages
- Graphics: the stat plates and both settings screens, drawn at build time with an original
  English font
- A proportional English font (original drawings) with word wrap and paging

Long labels are shortened where the game's boxes are too small.

## Applying the patch (players)

1. Download the release zip (`Sangokushi_Koumeiden_English_v<version>.zip`) from the Releases
   page. It contains the patch `sangokushi_koumeiden_en_v<version>.xdelta`, a `.cue` file and
   a README.txt.
2. You need an unmodified image of the Japanese disc (serial `SLPS-00688`) in the usual two-track
   BIN/CUE form. Only track 1 is patched:

   | Track 1 | |
   |---|---|
   | Size  | 678,086,304 bytes |
   | CRC32 | `33EAE625` |
   | MD5   | `b49f73f3fe4936d58fb5a9adb99b1306` |
   | SHA-1 | `db5e32a8b879924862e72e3337be2c710da687e2` |

   Track 2 (CD audio, 37,810,752 bytes, CRC32 `40E86050`) is used unchanged.
3. Apply the patch to track 1 with an xdelta tool, e.g.
   [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher) or the command line:

   ```
   xdelta3 -d -s "Sangokushi Koumeiden (Japan) (Track 1).bin" sangokushi_koumeiden_en_v<version>.xdelta "Sangokushi Koumeiden (English v<version>) (Track 1).bin"
   ```

4. Put the zip's `Sangokushi Koumeiden (English v<version>).cue` next to the patched track 1
   and the original track 2, and open the `.cue` in your emulator.

## Building from source

Requirements: Python 3.10+, `xdelta3` (for the patch file).

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp "/path/to/Sangokushi Koumeiden (Japan) (Track 1).bin" sangokushi_koumeiden_track1.bin
cp "/path/to/Sangokushi Koumeiden (Japan) (Track 2).bin" sangokushi_koumeiden_track2.bin
.venv/bin/python tools/setup.py      # checks the disc, extracts script/ from it
.venv/bin/python tools/build.py      # writes build/sangokushi_koumeiden_en_track1.bin (+ track 2, .cue) and the .xdelta
```

`script/`, `extract/` and `build/` hold data from your disc and are never committed.
`.venv/bin/python tools/package.py <version>` then writes the release zip to `release/`.
No disc data is ever packaged.

## Repository layout

| Path | Contents |
|---|---|
| `tl/snr/` | English for the chapter text `SNR/SNR*M.E2`, by part and entry number |
| `tl/ip/`, `tl/dmes/` | English for the town people's lines `SNR/IP.E2` and the retreat lines `SNR/DMES.E2` |
| `tl/names/` | Speaker, place, item, NPC label and battle names |
| `tl/progstr/` | English for strings in the game program, by address |
| `tools/setup.py`, `tools/build.py` | Check the disc and extract; build the patched disc and the patch |
| `tools/tl.py`, `tools/text.py` | Translation checks, wrapping and paging |
| `tools/snr.py`, `tools/ip.py`, `tools/dmes.py` | Chapter text, town lines and retreat line file formats |
| `tools/iso.py` | Disc image |
| `tools/names.py`, `tools/tokens.py` | Speaker names; name tokens for officers, items, places and labels |
| `tools/progstr.py`, `tools/fmtlimit.py` | Program strings; format-string limits |
| `tools/vwf.py`, `tools/pixfont.py`, `tools/asm.py` | Proportional font, layout patches; small MIPS assembler |
| `tools/gfx.py` | Redrawn label graphics and settings screens |
| `tools/package.py` | Makes the release zip |
| `tools/dev/`, `tools/emu/` | Development helpers (disassembly, DuckStation automation) |
| `docs/screenshots/` | README screenshots |

## Known issues

- The title logo, the loading screen art, the Koei slogan logo and the movies are unchanged.
- The gold plate reads "G" because the plate is too small.
- Item names are shortened to fit the item list (e.g. "Repeating Xbow"); dialogue may use the
  full names.
- Most of the game after the first battles has not been seen in play. Its text may overflow in
  places.

Tested in DuckStation only. Bug reports with a screenshot and where it happened are welcome.

## Credits

- Translation and hacking: [damon-daemon](https://github.com/damon-daemon)
- Sangokushi Koumeiden © Koei Tecmo. This is an unofficial fan project, not affiliated with
  or endorsed by Koei Tecmo. Please support the official releases.

## License

The tools, fonts, documentation and English translation text in this repository
are released under the [MIT License](LICENSE). This covers only original work in
this repository: the game itself and all of its content (code, Japanese text,
graphics, audio) are copyright Koei Tecmo and are not included or licensed here.
