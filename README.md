# ChessTeach

A chess board for teaching children, written in Python/Tkinter. A prototype
made with my son, who teaches chess to children. It loads prepared
positions (FEN) and games (PGN) from a folder tree and lets the coach step
through them, draw arrows and markings, and show Stockfish analysis.

Status: prototype, in active development. The user interface is in German.

## Requirements

- Python 3 with `tkinter`
- [python-chess](https://github.com/niklasf/python-chess) (`pip install chess`)
- [Pillow](https://python-pillow.org/) with ImageTk
- Stockfish, expected at `/usr/games/stockfish` (path is hard-coded; this is
  where the Debian package installs it)

On Debian / Raspberry Pi OS:

```bash
sudo apt install -y python3-tk stockfish
python3 -m venv venv && source venv/bin/activate
pip install chess pillow
```

## Run

```bash
python3 chessteach/chessteach.py   # teaching board
python3 chessteach/coach.py        # separate app: play against Stockfish with coach hints
```

Tests (15, pytest):

```bash
cd chessteach && python3 -m pytest tests
```

Settings, window geometry, fullscreen state and the last position are stored
in `~/.config/chessteach/config.json` (`coach.py` uses `~/.config/coachmode/`).

## What it does

- Tabs on the right are built from the folders in `chessteach/lektionen/`;
  fixed tabs: *Figuren* (piece palette for free edit mode) and, if books are
  present, *Bücher*.
- Make moves by clicking piece and target square; step through games with the
  toolbar or arrow keys; move list with German notation.
- Free edit mode: place and remove pieces without rule checks.
- Stockfish analysis as arrows, with configurable think time and 1-5 move
  suggestions (multi-PV); optional engine reply for the side at the top.
- Repertoire training: replay a loaded PGN from the side at the bottom;
  right/wrong attempts are counted.
- Arrows (right-drag), square markings with switchable colours, highlighting
  of legal moves and of attacked pieces, board cover, coordinates on/off.
- Add positions/lessons from the *Neu* panel; mark exercises as done.
- Import/export of the `lektionen` folder from/to a USB drive (settings dialog).
- Book reader (*Bücher* tab, `buchleser.py`): reads `buecher/<name>/buch.json`,
  every move in the text is clickable and loads the game up to that move.

The toolbar uses icons; their meaning is shown as a tooltip. `F1` shows the
full key list.

## Data format

```text
lektionen/
└── 01_Grundlagen/              tab (title from _meta.txt or folder name)
    ├── _meta.txt               tab title (optional, first line)
    ├── 01_Das-Schachbrett/     lesson (subfolder)
    │   ├── _meta.txt           lesson title (optional)
    │   ├── 0001_Grundstellung.fen
    │   └── 0002_Reihen.fen
    ├── 02_Partien.pgn          .pgn directly in a tab: a lesson, one exercise per game
    └── 0003_Freie-Uebung.fen   standalone exercise
```

- Folders and files are sorted by name; a leading number is stripped from the
  displayed title.
- `.fen`: line 1 = title, line 2 = FEN. `.pgn`: title from the `[Event]` header.
- `F5` reloads the folder tree.

### Annotation commands in PGN comments

Commands inside `{ … }` are shown step by step while replaying, without
changing the position. Each move and each command is one step.

| Command          | Effect                         |
|------------------|--------------------------------|
| `[Sq e4,d5]`     | highlight squares              |
| `[Mk e4]`        | mark squares                   |
| `[Ar e2e4,g1f3]` | draw arrows                    |
| `[Rank 4]`       | highlight rank 4               |
| `[File e]`       | highlight file e               |
| `[Clear]`        | remove all annotations         |

```pgn
1. e4 { [Sq e4] [Ar f1b5] } e5 { [Mk e5] [Rank 4] } 2. Nf3 { [File e] }
```

## Keys

| Key            | Action                                           |
|----------------|--------------------------------------------------|
| `t` `z` `l` `u` | navigation mode: tabs, moves, lessons, exercises |
| `←` / `→`      | back / forward in the selected mode              |
| `Home` / `End` | start / end of the game                          |
| `Ctrl+Z`       | undo                                             |
| `n` / `r`      | new game / reset position                        |
| `a` / `g`      | analysis on/off / engine reply on/off            |
| `m` / `c`      | marking mode on/off / next marking colour        |
| `k` / `h`      | coordinates on/off / cover board                 |
| `d`            | mark current exercise/lesson as done             |
| `F1` / `F5`    | help / reload lessons                            |
| `F11` / `Esc`  | fullscreen on / off                              |

## Tools

Scripts in `chessteach/tools/` generate lesson content (each has usage notes in
its docstring):

- `partien_lektionen.py` – builds a lesson tab from a player's Lichess or
  chess.com games, using Stockfish. Output contains children's games and is
  excluded via `.gitignore`.
- `lichess_themen.py` – takes puzzles from the Lichess puzzle database as lessons.
- `buecher/pdf_buch.py` – converts a chess book PDF (with text layer) into the
  `buch.json` format of the book reader; currently only tuned for one Russian
  Nimzowitsch edition.

## Credits

- Chess logic: [python-chess](https://github.com/niklasf/python-chess)
- Engine: [Stockfish](https://stockfishchess.org/)
- Pieces: Cburnett set (as shipped with [PyChess](https://github.com/pychess/pychess))

## License

GPL-3.0, see [LICENSE](LICENSE); python-chess is GPL-3.0.
