# ChessTeach

**A prototyping project by my son, who teaches chess to children.**

ChessTeach is a teaching-oriented chess board, originally built for a
Raspberry Pi connected to a TV. Instead of a full chess client, it focuses on
what a coach needs in front of children: load prepared positions (FEN) and
games (PGN) instantly, step through them, and explain using arrows, highlights,
markings and engine analysis.

> The user interface is in German, because the lessons are held in German.

## Features

- **Positions (FEN)** and **games (PGN)** organised in **lessons** and
  **exercises** (tabs: *Positionen*, *Partien*)
- **Replay PGN games** move by move (⏮ ◀ ▶ ⏭) with a clickable German move list
- **Flip the board** (black at the bottom)
- **Free edit mode** (*Figuren* tab + *Bearbeiten* toggle): place or remove any
  pieces (any number, any colour) and move pieces freely — no rule checks, no
  engine — ideal for teaching piece movement
- Make moves (click piece → click target), undo, reset
- **Stockfish analysis** — best move + evaluation, drawn as an arrow
- Draw **arrows** (right-drag), **mark squares**, highlight **threats** and
  **legal moves**
- Toggle **coordinates** (a–h / 1–8) with a clean frame around the board
- Remembers **window size/position**, **fullscreen** and the **last position**
- Clean, child-friendly standard tournament pieces

## Requirements

- Python 3.9+
- [`python-chess`](https://github.com/niklasf/python-chess)
- [`Pillow`](https://python-pillow.org/) (with ImageTk)
- `tkinter`
- [`Stockfish`](https://stockfishchess.org/) (for analysis)

On Raspberry Pi OS / Debian:

```bash
sudo apt install -y python3-tk stockfish
python3 -m venv venv && source venv/bin/activate
pip install chess pillow
```

## Run

```bash
python chessteach/chessteach.py
```

To start it fullscreen automatically on a Raspberry Pi desktop, add a
`~/.config/autostart/chessteach.desktop` file with:

```ini
[Desktop Entry]
Type=Application
Name=ChessTeach
Exec=/usr/bin/python3 /path/to/chessteach/chessteach.py
Terminal=false
X-GNOME-Autostart-enabled=true
```

## Data format

All content lives in `chessteach/stellungen.json`:

```json
{
  "positions": {
    "lessons": [
      {"title": "Mate in 1", "exercises": [
        {"title": "Queen mate", "fen": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"}
      ]}
    ],
    "exercises": [
      {"title": "Start position", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}
    ]
  },
  "games": {
    "lessons": [
      {"title": "Quick mates", "exercises": [
        {"title": "Scholar's mate", "pgn": "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"}
      ]}
    ],
    "exercises": [
      {"title": "Italian Game", "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6"}
    ]
  }
}
```

Lessons are expandable groups; exercises are single entries. New lessons and
exercises can also be added from within the app.

## Controls

| Action              | Input                              |
|---------------------|------------------------------------|
| Move a piece        | click piece → click target square  |
| Draw an arrow       | right-drag on the board            |
| Mark a square       | enable *Markieren*, then click     |
| Flip board          | *Brett drehen* checkbox            |
| Free edit mode      | *Bearbeiten* checkbox + *Figuren* tab |
| Fullscreen          | `F11`                              |
| Exit fullscreen     | `Esc`                              |
| Undo / previous move| `Ctrl+Z` or `←`                    |
| Next move           | `→`                                |

## Credits

- Chess logic: [python-chess](https://github.com/niklasf/python-chess)
- Chess pieces: Cburnett set (as shipped with [PyChess](https://github.com/pychess/pychess))
- Engine: [Stockfish](https://stockfishchess.org/)
