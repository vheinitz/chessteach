#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChessTeach — Schach-Lehrbrett für Kinder
=========================================
- Stellungen (FEN) und Partien (PGN) in Lektionen/Übungen organisiert (Tabs)
- Partien nachspielen (PGN-Replay)
- Brett drehen
- Fenstergröße/-position und zuletzt geladene Stellung werden gemerkt
- Züge, Bedrohungen, Pfeile, Markierungen, Koordinaten, Stockfish-Analyse
"""

import os
import io
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import chess
import chess.pgn
import chess.engine
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Pfade & Konstanten
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PIECES_DIR = os.path.join(APP_DIR, "pieces")
DATA_FILE = os.path.join(APP_DIR, "stellungen.json")
CONFIG_DIR = os.path.expanduser("~/.config/chessteach")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STOCKFISH = "/usr/games/stockfish"

LIGHT = "#f0d9b5"
DARK = "#b58863"
SELECT_COLOR = "#ffeb3b"
LEGAL_COLOR = "#2e7d32"
CAPTURE_COLOR = "#c62828"
THREAT_COLOR = "#e53935"
MARK_COLOR = "#ffd54f"
ARROW_COLOR = "#1e88e5"
BESTMOVE_COLOR = "#8e24aa"
LAST_COLOR = "#f9a825"
CHECK_COLOR = "#d32f2f"

DEFAULT_DATA = {
    "positions": {
        "lessons": [
            {
                "title": "Matt in 1",
                "exercises": [
                    {"title": "Dame-Matt in 1", "fen": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"},
                    {"title": "Turm-Matt in 1", "fen": "6k1/5ppp/8/8/8/8/PPP2PPP/4R1K1 w - - 0 1"},
                ],
            },
            {
                "title": "Taktik-Grundlagen",
                "exercises": [
                    {"title": "Springer-Gabel (Sf7!)", "fen": "3q3k/6pp/8/4N3/8/8/5PPP/6K1 w - - 0 1"},
                    {"title": "Fesselung (Läufer)", "fen": "r1bqkbnr/pppp1ppp/2n5/1B6/8/8/PPPP1PPP/RNBQK1NR w KQkq - 0 1"},
                    {"title": "Spieß (Turm)", "fen": "3q4/8/3k4/8/8/8/PPP3P1/R5K1 w - - 0 1"},
                    {"title": "Abzugsschach", "fen": "r3k2r/p6p/8/8/4B3/8/PPPP1PPP/4R1K1 w - - 0 1"},
                ],
            },
        ],
        "exercises": [
            {"title": "Grundstellung", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"},
            {"title": "Rochade", "fen": "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"},
            {"title": "En passant", "fen": "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 1"},
            {"title": "Bauernumwandlung", "fen": "4k3/4P3/8/8/8/8/8/6K1 w - - 0 1"},
            {"title": "Patt", "fen": "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"},
        ],
    },
    "games": {
        "lessons": [
            {
                "title": "Kurze Matts",
                "exercises": [
                    {"title": "Schäfermatt", "pgn": "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"},
                    {"title": "Narrenmatt", "pgn": "1. f3 e5 2. g4 Qh4#"},
                ],
            }
        ],
        "exercises": [
            {"title": "Italienische Partie", "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d4 exd4 6. cxd4 Bb4+"},
        ],
    },
}


def san_de(board, move):
    """Englische SAN-Figuren in deutsche Figuren übersetzen."""
    return board.san(move).replace("N", "S").replace("B", "L").replace("Q", "D").replace("R", "T")


# ---------------------------------------------------------------------------
# Figuren
# ---------------------------------------------------------------------------
class PieceSet:
    def __init__(self, directory):
        self._pil = {}
        self._tk = {}
        for color in "wb":
            for piece in "KQRBNP":
                sym = piece if color == "w" else piece.lower()
                path = os.path.join(directory, color + piece.lower() + ".png")
                if os.path.exists(path):
                    self._pil[sym] = Image.open(path).convert("RGBA")

    def get(self, sym, size):
        size = max(4, int(size))
        key = (sym, size)
        if key not in self._tk:
            self._tk[key] = ImageTk.PhotoImage(self._pil[sym].resize((size, size), Image.LANCZOS))
        return self._tk[key]


PIECES = PieceSet(PIECES_DIR)


def draw_mini_board(canvas, x0, y0, size, fen):
    """Mini-Brett als Canvas-Items zeichnen."""
    sq = size // 8
    board = chess.Board(fen)
    for s in range(64):
        f, r = s % 8, s // 8
        color = LIGHT if (f + r) % 2 == 0 else DARK
        canvas.create_rectangle(x0 + f * sq, y0 + (7 - r) * sq,
                                x0 + (f + 1) * sq, y0 + (7 - r + 1) * sq,
                                fill=color, width=0)
    for s, piece in board.piece_map().items():
        f, r = s % 8, s // 8
        canvas.create_image(x0 + f * sq, y0 + (7 - r) * sq,
                            image=PIECES.get(piece.symbol(), sq), anchor="nw")


# ---------------------------------------------------------------------------
# Hauptbrett
# ---------------------------------------------------------------------------
class BoardCanvas(tk.Canvas):
    def __init__(self, parent, app):
        super().__init__(parent, highlightthickness=0, bg="#f2ede2")
        self.app = app
        self.sq = 60
        self.margin = 15
        self.off_x = 0
        self.off_y = 0
        self.bind("<Configure>", self.on_resize)
        self.bind("<Button-1>", self.on_left_click)
        self.bind("<Button-3>", self.on_right_press)
        self.bind("<B3-Motion>", self.on_right_motion)
        self.bind("<ButtonRelease-3>", self.on_right_release)

    # -- Geometrie ----------------------------------------------------------
    def on_resize(self, event):
        self.sq = max(16, int(min(event.width, event.height) / 8.5))
        self.margin = max(6, int(self.sq * 0.25))
        total = 8 * self.sq + 2 * self.margin
        self.off_x = (event.width - total) // 2
        self.off_y = (event.height - total) // 2
        self.redraw()

    def sq_origin(self, s):
        file = s % 8
        rank = s // 8
        if self.app.flipped:
            col, row = 7 - file, rank
        else:
            col, row = file, 7 - rank
        x0 = self.off_x + self.margin + col * self.sq
        y0 = self.off_y + self.margin + row * self.sq
        return x0, y0

    def square_of(self, x, y):
        col = (x - self.off_x - self.margin) // self.sq
        row = (y - self.off_y - self.margin) // self.sq
        if self.app.flipped:
            file, rank = 7 - col, row
        else:
            file, rank = col, 7 - row
        if 0 <= file < 8 and 0 <= rank < 8:
            return rank * 8 + file
        return None

    def center(self, sq):
        x0, y0 = self.sq_origin(sq)
        return x0 + self.sq / 2, y0 + self.sq / 2

    # -- Interaktion --------------------------------------------------------
    def on_left_click(self, event):
        sq = self.square_of(event.x, event.y)
        if sq is None:
            return
        if self.app.mark_mode:
            self.app.toggle_mark(sq)
            return
        self.app.board_click(sq)

    def on_right_press(self, event):
        sq = self.square_of(event.x, event.y)
        if sq is not None:
            self.app.arrow_start = sq
            self.app.arrow_cur = sq

    def on_right_motion(self, event):
        if self.app.arrow_start is not None:
            sq = self.square_of(event.x, event.y)
            if sq is not None:
                self.app.arrow_cur = sq
                self.redraw()
                self.draw_arrow(self.app.arrow_start, self.app.arrow_cur, ARROW_COLOR, draft=True)

    def on_right_release(self, event):
        if self.app.arrow_start is not None:
            sq = self.square_of(event.x, event.y)
            if sq is not None and sq != self.app.arrow_start:
                self.app.arrows.append((self.app.arrow_start, sq))
            self.app.arrow_start = None
            self.app.arrow_cur = None
            self.redraw()

    # -- Zeichnen -----------------------------------------------------------
    def redraw(self):
        self.delete("all")
        board = self.app.board
        sq = self.sq

        for s in range(64):
            x0, y0 = self.sq_origin(s)
            f, r = s % 8, s // 8
            color = LIGHT if (f + r) % 2 == 0 else DARK
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=color, width=0)

        if self.app.last_move:
            for s in [self.app.last_move.from_square, self.app.last_move.to_square]:
                x0, y0 = self.sq_origin(s)
                self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=LAST_COLOR, width=0, stipple="gray50")

        for s in self.app.marks:
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=MARK_COLOR, width=0, stipple="gray50")
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=MARK_COLOR, width=3)

        if self.app.show_threats:
            for s, piece in board.piece_map().items():
                if piece.color == board.turn and board.is_attacked_by(not board.turn, s):
                    x0, y0 = self.sq_origin(s)
                    self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=THREAT_COLOR, width=4)

        if board.is_check():
            king_sq = board.king(board.turn)
            if king_sq is not None:
                x0, y0 = self.sq_origin(king_sq)
                self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=CHECK_COLOR, width=5)

        if self.app.selected is not None:
            x0, y0 = self.sq_origin(self.app.selected)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=SELECT_COLOR, width=4)
            for move in board.legal_moves:
                if move.from_square == self.app.selected:
                    ts = move.to_square
                    tx, ty = self.center(ts)
                    if board.piece_at(ts):
                        self.create_oval(tx - sq/2 + 2, ty - sq/2 + 2,
                                         tx + sq/2 - 2, ty + sq/2 - 2,
                                         outline=CAPTURE_COLOR, width=4)
                    else:
                        rr = max(4, sq // 6)
                        self.create_oval(tx - rr, ty - rr, tx + rr, ty + rr, fill=LEGAL_COLOR)

        if self.app.show_coords:
            self.draw_coords()

        for s, piece in board.piece_map().items():
            x0, y0 = self.sq_origin(s)
            self.create_image(x0, y0, image=PIECES.get(piece.symbol(), sq), anchor="nw")

        for a, b in self.app.arrows:
            self.draw_arrow(a, b, ARROW_COLOR, draft=False)

        if self.app.best_move is not None:
            self.draw_arrow(self.app.best_move.from_square, self.app.best_move.to_square,
                            BESTMOVE_COLOR, draft=False, width=6)

    def draw_coords(self):
        sq = self.sq
        m = self.margin
        files = "abcdefgh"
        font = ("DejaVu Sans", max(8, int(sq * 0.22)), "bold")
        for i in range(8):
            file_idx = (7 - i) if self.app.flipped else i
            x = self.off_x + m + i * sq + sq / 2
            y = self.off_y + m + 8 * sq + m / 2
            self.create_text(x, y, text=files[file_idx], fill="#5d4037", font=font)
        for i in range(8):
            rank_idx = i if self.app.flipped else (7 - i)
            x = self.off_x + m / 2
            y = self.off_y + m + i * sq + sq / 2
            self.create_text(x, y, text=str(rank_idx + 1), fill="#5d4037", font=font)

    def draw_arrow(self, a, b, color, draft=False, width=5):
        import math
        x1, y1 = self.center(a)
        x2, y2 = self.center(b)
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        start = (x1 + ux * self.sq * 0.25, y1 + uy * self.sq * 0.25)
        end = (x2 - ux * self.sq * 0.18, y2 - uy * self.sq * 0.18)
        self.create_line(start[0], start[1], end[0], end[1],
                         fill=color, width=width, arrow="last",
                         arrowshape=(self.sq * 0.5, self.sq * 0.6, self.sq * 0.25))


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------
class ChessTeachApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ChessTeach — Schach-Lehrbrett")
        self.configure(bg="#eceff1")

        # Zustand
        self.board = chess.Board()
        self.loaded_fen = self.board.fen()
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = set()
        self.arrow_start = None
        self.arrow_cur = None
        self.best_move = None
        self.show_threats = False
        self.show_coords = True
        self.mark_mode = False
        self.flipped = False
        self.engine = None
        self._engine_lock = threading.Lock()
        self._closing = False

        # Partie-Replay
        self.game_base = chess.Board()
        self.game_moves = []
        self.game_index = 0

        # Daten & UI
        self.data = DEFAULT_DATA
        self.current_tab = "positions"
        self.expanded = {"positions": set(), "games": set()}
        self.selected_lesson = None
        self.list_canvases = {}
        self.list_hits = {}

        self.load_data()
        self.build_ui()
        self.load_config()
        self.update_status()
        self.update_content_field()

        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Left>", lambda e: self.undo())
        self.bind("<Right>", lambda e: self.game_next())
        self.bind("r", lambda e: self.reset())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- Daten --------------------------------------------------------------
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "positions" in raw:
                    self.data = raw
                else:  # alte flache Liste -> migrieren
                    self.data = {
                        "positions": {"lessons": [], "exercises": [
                            {"title": p.get("name", "?"), "fen": p["fen"]} for p in raw
                        ]},
                        "games": {"lessons": [], "exercises": []},
                    }
                self.data.setdefault("positions", {"lessons": [], "exercises": []})
                self.data.setdefault("games", {"lessons": [], "exercises": []})
            except Exception:
                self.data = DEFAULT_DATA
        else:
            self.data = DEFAULT_DATA

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # -- UI -----------------------------------------------------------------
    def build_ui(self):
        bar = ttk.Frame(self, padding=4)
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="↩", width=4, command=self.undo).pack(side="left", padx=1)
        ttk.Button(bar, text="⟲", width=4, command=self.reset).pack(side="left", padx=1)
        ttk.Button(bar, text="Neue Partie", command=self.new_game).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)

        self.flip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Brett drehen", variable=self.flip_var,
                        command=self.toggle_flip).pack(side="left", padx=2)

        # Replay-Knöpfe
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(bar, text="⏮", width=3, command=self.game_start).pack(side="left", padx=1)
        ttk.Button(bar, text="◀", width=3, command=self.game_prev).pack(side="left", padx=1)
        self.move_lbl = tk.Label(bar, text="Zug –", font=("DejaVu Sans", 11), width=10, anchor="center")
        self.move_lbl.pack(side="left", padx=2)
        ttk.Button(bar, text="▶", width=3, command=self.game_next).pack(side="left", padx=1)
        ttk.Button(bar, text="⏭", width=3, command=self.game_end).pack(side="left", padx=1)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        self.coord_btn = ttk.Checkbutton(bar, text="Koordinaten", command=self.toggle_coords)
        self.coord_btn.pack(side="left", padx=2)
        self.coord_btn.state(["selected"])
        self.threat_btn = ttk.Checkbutton(bar, text="Bedrohungen", command=self.toggle_threats)
        self.threat_btn.pack(side="left", padx=2)
        self.mark_btn = ttk.Checkbutton(bar, text="Markieren", command=self.toggle_mark_mode)
        self.mark_btn.pack(side="left", padx=2)
        ttk.Button(bar, text="Pfeile weg", command=self.clear_arrows).pack(side="left", padx=2)
        ttk.Button(bar, text="Mark. weg", command=self.clear_marks).pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        self.analyse_btn = ttk.Button(bar, text="🔍 Analyse", command=self.analyse)
        self.analyse_btn.pack(side="left", padx=2)

        self.status_lbl = tk.Label(bar, text="", font=("DejaVu Sans", 13, "bold"),
                                   fg="#1a237e", anchor="w")
        self.status_lbl.pack(side="left", padx=10, fill="x", expand=True)

        # Hauptbereich
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        board_frame = ttk.Frame(paned)
        paned.add(board_frame, weight=3)
        self.board_canvas = BoardCanvas(board_frame, self)
        self.board_canvas.pack(fill="both", expand=True)

        side = ttk.Frame(paned)
        paned.add(side, weight=2)

        self.notebook = ttk.Notebook(side)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Tab 1: Positionen
        pos_tab = ttk.Frame(self.notebook)
        self.notebook.add(pos_tab, text="Positionen")
        self.list_canvases["positions"] = self._make_list_canvas(pos_tab, "positions")

        # Tab 2: Partien
        game_tab = ttk.Frame(self.notebook)
        self.notebook.add(game_tab, text="Partien")
        self.list_canvases["games"] = self._make_list_canvas(game_tab, "games")
        ttk.Label(game_tab, text="Züge", font=("DejaVu Sans", 11, "bold")).pack(anchor="w")
        self.move_list = tk.Listbox(game_tab, height=8, font=("DejaVu Sans Mono", 10),
                                    exportselection=False)
        self.move_list.pack(fill="x", padx=2, pady=2)
        self.move_list.bind("<<ListboxSelect>>", self.on_move_list_select)

        # Eingabebereich
        add = ttk.LabelFrame(side, text="Neu", padding=4)
        add.pack(fill="x", padx=2, pady=4)
        ttk.Label(add, text="Titel").pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(add, textvariable=self.name_var).pack(fill="x")
        ttk.Label(add, text="FEN oder PGN").pack(anchor="w", pady=(4, 0))
        self.content_text = tk.Text(add, height=3, font=("DejaVu Sans Mono", 9), wrap="none")
        self.content_text.pack(fill="x")
        btns = ttk.Frame(add)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Laden", command=self.load_from_entry).pack(side="left", padx=2)
        ttk.Button(btns, text="Hinzufügen", command=self.add_node).pack(side="left", padx=2)
        ttk.Button(btns, text="Neue Lektion", command=self.new_lesson).pack(side="left", padx=2)

        self.render_tab("positions")
        self.render_tab("games")

    def _make_list_canvas(self, parent, tab):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, highlightthickness=0, bg="#fafafa", cursor="hand2")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind("<Button-1>", lambda e, t=tab: self.on_list_click(t, e))
        canvas.bind("<Configure>", lambda e, t=tab: self.render_tab(t))
        return canvas

    # -- Liste rendern ------------------------------------------------------
    def _section_header(self, canvas, x, y, text):
        canvas.create_text(x + 6, y + 12, text=text, anchor="w",
                           font=("DejaVu Sans", 11, "bold"), fill="#455a64")
        return y + 26

    def _node_preview_fen(self, node):
        if "fen" in node:
            return node["fen"]
        try:
            g = chess.pgn.read_game(io.StringIO(node.get("pgn", "")))
            if g:
                return g.board().fen()
        except Exception:
            pass
        return chess.STARTING_FEN

    def render_tab(self, tab):
        canvas = self.list_canvases[tab]
        canvas.delete("all")
        hits = []
        x, y = 6, 6
        size = 84
        ind = 26
        data = self.data.get(tab, {})

        lessons = data.get("lessons", []) or []
        exercises = data.get("exercises", []) or []

        if lessons:
            y = self._section_header(canvas, x, y, "Lektionen")
            for li, lesson in enumerate(lessons):
                exp = li in self.expanded[tab]
                sel = self.selected_lesson == (tab, li)
                bg = "#cfe0f0" if sel else "#e6ecef"
                canvas.create_rectangle(x, y, x + 400, y + 24, fill=bg, width=0)
                canvas.create_text(x + 10, y + 12, text="▾" if exp else "▸",
                                   anchor="w", font=("DejaVu Sans", 12), fill="#333")
                canvas.create_text(x + 30, y + 12, text=lesson.get("title", "?"),
                                   anchor="w", font=("DejaVu Sans", 12, "bold"), fill="#222")
                hits.append((y, y + 24, "lesson", li))
                y += 28
                if exp:
                    for node in lesson.get("exercises", []):
                        fen = self._node_preview_fen(node)
                        draw_mini_board(canvas, x + ind, y, size, fen)
                        canvas.create_text(x + ind + size + 8, y + size // 2,
                                           text=node.get("title", "?"), anchor="w",
                                           font=("DejaVu Sans", 12), fill="#222")
                        hits.append((y, y + size, "exercise", node))
                        y += size + 8

        if exercises:
            y += 6
            y = self._section_header(canvas, x, y, "Übungen")
            for node in exercises:
                fen = self._node_preview_fen(node)
                draw_mini_board(canvas, x, y, size, fen)
                canvas.create_text(x + size + 8, y + size // 2,
                                   text=node.get("title", "?"), anchor="w",
                                   font=("DejaVu Sans", 12), fill="#222")
                hits.append((y, y + size, "exercise", node))
                y += size + 8

        canvas.configure(scrollregion=(0, 0, max(420, canvas.winfo_width()), max(y + 8, canvas.winfo_height())))
        self.list_hits[tab] = hits

    def on_list_click(self, tab, event):
        cy = self.list_canvases[tab].canvasy(event.y)
        for y0, y1, kind, data in self.list_hits.get(tab, []):
            if y0 <= cy <= y1:
                if kind == "lesson":
                    li = data
                    self.selected_lesson = (tab, li)
                    if li in self.expanded[tab]:
                        self.expanded[tab].discard(li)
                    else:
                        self.expanded[tab].add(li)
                    self.render_tab(tab)
                else:
                    self.selected_lesson = None
                    node = data
                    if "fen" in node:
                        self.load_fen(node["fen"])
                    elif "pgn" in node:
                        self.load_pgn(node["pgn"])
                return

    def on_tab_changed(self, event):
        idx = self.notebook.index("current")
        self.current_tab = "positions" if idx == 0 else "games"
        self.render_tab(self.current_tab)

    # -- Laden --------------------------------------------------------------
    def load_fen(self, fen):
        try:
            self.board = chess.Board(fen)
        except Exception as e:
            messagebox.showerror("FEN-Fehler", str(e))
            return
        self.loaded_fen = fen
        self.game_moves = []
        self.game_index = 0
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = set()
        self.best_move = None
        self.update_content_field()
        self._sync_move_list()
        self.board_canvas.redraw()
        self.update_status()

    def load_pgn(self, pgn_text):
        g = chess.pgn.read_game(io.StringIO(pgn_text))
        if g is None:
            messagebox.showerror("PGN-Fehler", "PGN konnte nicht gelesen werden.")
            return
        self.game_base = g.board()
        self.game_moves = list(g.mainline_moves())
        self.game_index = len(self.game_moves)
        self.loaded_fen = self.game_base.fen()
        self._rebuild_game_board()
        self.selected = None
        self.arrows = []
        self.marks = set()
        self.best_move = None
        self._populate_move_list()
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def _rebuild_game_board(self):
        b = self.game_base.copy()
        for m in self.game_moves[:self.game_index]:
            b.push(m)
        self.board = b
        self.last_move = self.game_moves[self.game_index - 1] if self.game_index > 0 else None

    def game_replay_to(self, i):
        if not self.game_moves:
            return
        self.game_index = max(0, min(len(self.game_moves), i))
        self._rebuild_game_board()
        self.selected = None
        self.best_move = None
        self._sync_move_list_selection()
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def game_prev(self):
        self.game_replay_to(self.game_index - 1)

    def game_next(self):
        self.game_replay_to(self.game_index + 1)

    def game_start(self):
        self.game_replay_to(0)

    def game_end(self):
        self.game_replay_to(len(self.game_moves))

    def _populate_move_list(self):
        self.move_list.delete(0, "end")
        b = self.game_base.copy()
        for i, m in enumerate(self.game_moves):
            prefix = f"{i // 2 + 1}." if i % 2 == 0 else f"{i // 2 + 1}..."
            self.move_list.insert("end", f"{prefix} {san_de(b, m)}")
            b.push(m)

    def _sync_move_list(self):
        self.move_list.delete(0, "end")

    def _sync_move_list_selection(self):
        self.move_list.selection_clear(0, "end")
        if self.game_index > 0:
            self.move_list.selection_set(self.game_index - 1)
            self.move_list.see(self.game_index - 1)
            self.move_lbl.config(text=f"Zug {self.game_index}/{len(self.game_moves)}")
        else:
            self.move_lbl.config(text=f"Start")

    def on_move_list_select(self, event):
        sel = self.move_list.curselection()
        if sel:
            self.game_replay_to(sel[0] + 1)

    # -- Züge / Aktionen ----------------------------------------------------
    def board_click(self, sq):
        board = self.board
        piece = board.piece_at(sq)
        if self.selected is not None:
            for m in board.legal_moves:
                if m.from_square == self.selected and m.to_square == sq:
                    self.board.push(m)
                    self.last_move = m
                    self.selected = None
                    self.best_move = None
                    self.update_content_field()
                    self.board_canvas.redraw()
                    self.update_status()
                    return
        if piece and piece.color == board.turn:
            self.selected = sq
        else:
            self.selected = None
        self.board_canvas.redraw()

    def toggle_mark(self, sq):
        if sq in self.marks:
            self.marks.discard(sq)
        else:
            self.marks.add(sq)
        self.board_canvas.redraw()

    def undo(self):
        if self.game_moves:
            self.game_prev()
        elif self.board.move_stack:
            self.board.pop()
            self.last_move = self.board.peek() if self.board.move_stack else None
            self.selected = None
            self.best_move = None
            self.update_content_field()
            self.board_canvas.redraw()
            self.update_status()

    def reset(self):
        if self.game_moves:
            self.game_start()
        else:
            self.load_fen(self.loaded_fen)

    def new_game(self):
        self.load_fen(chess.STARTING_FEN)

    def toggle_flip(self):
        self.flipped = self.flip_var.get()
        self.board_canvas.redraw()

    def toggle_coords(self):
        self.show_coords = not self.show_coords
        self.board_canvas.redraw()

    def toggle_threats(self):
        self.show_threats = not self.show_threats
        self.board_canvas.redraw()

    def toggle_mark_mode(self):
        self.mark_mode = not self.mark_mode
        self.selected = None
        self.board_canvas.redraw()

    def clear_arrows(self):
        self.arrows = []
        self.best_move = None
        self.board_canvas.redraw()

    def clear_marks(self):
        self.marks = set()
        self.board_canvas.redraw()

    def load_from_entry(self):
        content = self.content_text.get("1.0", "end").strip()
        if not content:
            return
        try:
            chess.Board(content)
            self.load_fen(content)
            return
        except Exception:
            pass
        try:
            g = chess.pgn.read_game(io.StringIO(content))
            if g is not None:
                self.load_pgn(content)
                return
        except Exception:
            pass
        messagebox.showerror("Fehler", "Das ist weder eine gültige FEN noch eine gültige PGN.")

    def add_node(self):
        tab = self.current_tab
        title = self.name_var.get().strip() or "Ohne Namen"
        content = self.content_text.get("1.0", "end").strip()
        if not content:
            return
        if tab == "positions":
            try:
                chess.Board(content)
                node = {"title": title, "fen": content}
            except Exception:
                messagebox.showerror("FEN-Fehler", "Keine gültige FEN.")
                return
        else:
            try:
                g = chess.pgn.read_game(io.StringIO(content))
                if g is None:
                    raise ValueError
                node = {"title": title, "pgn": content}
            except Exception:
                messagebox.showerror("PGN-Fehler", "Keine gültige PGN.")
                return
        if self.selected_lesson and self.selected_lesson[0] == tab:
            li = self.selected_lesson[1]
            self.data[tab].setdefault("lessons", [] )[li].setdefault("exercises", []).append(node)
        else:
            self.data[tab].setdefault("exercises", []).append(node)
        self.save_data()
        self.render_tab(tab)

    def new_lesson(self):
        tab = self.current_tab
        title = simpledialog.askstring("Neue Lektion", "Titel der Lektion:", parent=self)
        if title:
            self.data[tab].setdefault("lessons", []).append({"title": title, "exercises": []})
            self.save_data()
            self.render_tab(tab)

    # -- Status / Content ---------------------------------------------------
    def update_status(self):
        b = self.board
        if b.is_checkmate():
            winner = "Weiß" if not b.turn else "Schwarz"
            txt = f"Schachmatt! {winner} gewinnt."
        elif b.is_stalemate():
            txt = "Patt — unentschieden."
        elif b.is_insufficient_material():
            txt = "Remis — zu wenig Material."
        elif b.is_check():
            txt = "Schach!"
        else:
            txt = "Weiß am Zug." if b.turn else "Schwarz am Zug."
        self.status_lbl.config(text=txt)

    def update_content_field(self):
        self.content_text.delete("1.0", "end")
        self.content_text.insert("1.0", self.board.fen())

    # -- Engine -------------------------------------------------------------
    def analyse(self):
        if self.best_move is not None:
            return
        fen = self.board.fen()
        self.analyse_btn.config(state="disabled", text="🔍 Analysiere…")
        threading.Thread(target=self._analyse_worker, args=(fen,), daemon=True).start()

    def _analyse_worker(self, fen):
        try:
            with self._engine_lock:
                if self.engine is None:
                    self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
                board = chess.Board(fen)
                info = self.engine.analyse(board, chess.engine.Limit(time=1.5))
            best = info.get("pv", [None])[0]
            score = info.get("score")
            self.after(0, self._apply_analysis, best, score, fen)
        except Exception as e:
            self.after(0, self._analysis_error, str(e))

    def _apply_analysis(self, best, score, fen):
        self.analyse_btn.config(state="normal", text="🔍 Analyse")
        if best is None or fen != self.board.fen():
            return
        self.best_move = best
        if score is not None:
            pov = score.pov(chess.WHITE)
            if pov.is_mate():
                self.status_lbl.config(text=f"Bewertung: Matt in {abs(pov.mate())} — Bester Zug: {san_de(self.board, best)}")
            else:
                self.status_lbl.config(text=f"Bewertung: {pov.score()/100:+.2f} — Bester Zug: {san_de(self.board, best)}")
        self.board_canvas.redraw()

    def _analysis_error(self, msg):
        self.analyse_btn.config(state="normal", text="🔍 Analyse")
        self.status_lbl.config(text=f"Analyse nicht möglich: {msg[:60]}")

    # -- Vollbild & Konfig --------------------------------------------------
    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not self.attributes("-fullscreen"))

    def exit_fullscreen(self):
        self.attributes("-fullscreen", False)

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = int(cfg.get("width", min(1560, sw - 60)))
        h = int(cfg.get("height", min(900, sh - 60)))
        x = int(cfg.get("x", (sw - w) // 2))
        y = int(cfg.get("y", (sh - h) // 2))
        x = max(0, min(x, sw - 100))
        y = max(0, min(y, sh - 100))
        self.geometry(f"{w}x{h}+{x}+{y}")
        if cfg.get("fullscreen"):
            self.after(100, lambda: self.attributes("-fullscreen", True))
        self.flipped = bool(cfg.get("flipped", False))
        self.flip_var.set(self.flipped)
        if cfg.get("last_fen"):
            try:
                self.board = chess.Board(cfg["last_fen"])
                self.loaded_fen = cfg["last_fen"]
                self.selected = None
                self.last_move = None
                self.arrows = []
                self.marks = set()
                self.best_move = None
                self.board_canvas.redraw()
            except Exception:
                pass

    def save_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        fs = bool(self.attributes("-fullscreen"))
        cfg = {
            "x": self.winfo_x(), "y": self.winfo_y(),
            "width": self.winfo_width(), "height": self.winfo_height(),
            "fullscreen": fs,
            "flipped": self.flipped,
            "last_fen": self.loaded_fen,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def on_close(self):
        self._closing = True
        try:
            if self.engine is not None:
                self.engine.quit()
        except Exception:
            pass
        self.save_config()
        self.destroy()


def main():
    app = ChessTeachApp()
    app.mainloop()


if __name__ == "__main__":
    main()
