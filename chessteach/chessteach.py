#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChessTeach — Schach-Lehrbrett für Kinder
=========================================
- Lektionen als Verzeichnisstruktur: lektionen/<Tab>/<Lektion>/NNNN_Name.fen|.pgn
- Unterverzeichnisse mit _meta.txt (Titel), sonst Verzeichnisname
- .fen  = Zeile 1 Titel, Zeile 2 FEN
- .pgn  = Partie (Titel im [Event]-Header)
- Tabs werden dynamisch aus den Ordnern erzeugt
"""

import os
import io
import re
import json
import queue
import shutil
import threading
import time
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
DATA_DIR = os.path.join(APP_DIR, "lektionen")
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
SUGGEST_COLOR = "#1e88e5"
WINNABLE_COLOR = "#00a651"
HIGHLIGHT_COLOR = "#4fc3f7"
LINE_COLOR = "#ffb74d"
LAST_COLOR = "#f9a825"
CHECK_COLOR = "#d32f2f"


def square_color(s):
    """Farbe des Feldes s (0 = a1). a1 ist dunkel, h1 hell (weißes Feld unten rechts)."""
    return DARK if (s % 8 + s // 8) % 2 == 0 else LIGHT


FILE_EXTS = (".fen", ".pgn")


HELP_TEXT = """ChessTeach — Hilfe

Navigation: erst Modus wählen, dann ← / →
──────────────────────────────────────────
t   Tabs (Bibliothek rechts)
z   Züge (Partie/Stellung durchgehen)
l   Lektionen (aufklappen + erste Übung laden)
u   Übungen/Stellungen (nacheinander laden)
← / →   im gewählten Modus zurück / weiter

Weitere Tastatur
────────────────
Home / Ende   an den Anfang / ans Ende
n             Neue Partie
r             Stellung zurücksetzen
h             Brett verdecken
k             Koordinaten an/aus
m             Markieren an/aus
c             Markierungsfarbe wechseln
a             Analyse an/aus
F1            Diese Hilfe
F5            Lektionen neu laden
F11 / Esc     Vollbild an/aus
Strg+Z        Rückgängig

Maus
────
Linksklick        Figur auswählen, dann Zielfeld anklicken (Zug)
Rechtsklick+Ziehen  Pfeil zeichnen
„Markieren“ an → Linksklick markiert Felder (aktuelle Farbe)

Markierungsfarben (Wechsel mit c)
────────────────────────────────
gelb, rot, blau, grün, lila
(Liste in ~/.config/chessteach/config.json unter „mark_colors“)

Lernmodus: Befehle in PGN-Kommentaren
─────────────────────────────────────
[Sq e4,d5]   Quadrate hervorheben (blau)
[Mk e4]      Felder markieren
[Ar e2e4]    Pfeil zeichnen
[Rank 4]     Reihe 4 hervorheben (horizontal)
[File e]     Linie e hervorheben (vertikal)
[Clear]      alle Markierungen löschen
Jeder Zug und jedes [ … ] = ein Schritt (▶ / ◀).
"""


def sanitize(s):
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
          .replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue").replace("ß", "ss"))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s or "ohne-name"


def title_from_name(name):
    name = os.path.splitext(name)[0]
    name = re.sub(r"^\d+[_\-\s]*", "", name)
    name = name.replace("-", " ").replace("_", " ").replace("+", " ")
    return " ".join(name.split()).strip()


def truncate(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def read_text(path):
    for enc in ("utf-8", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""


def read_meta(directory):
    meta = os.path.join(directory, "_meta.txt")
    if os.path.exists(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        return line
        except Exception:
            pass
    return None


def next_number(directory, dirs_only=False):
    best = 0
    try:
        for fn in os.listdir(directory):
            m = re.match(r"^(\d+)", fn)
            if not m:
                continue
            full = os.path.join(directory, fn)
            if dirs_only != os.path.isdir(full):
                continue
            best = max(best, int(m.group(1)))
    except Exception:
        pass
    return best + 1


def load_node(path):
    """Liest eine .fen- oder .pgn-Datei -> dict {title, fen|pgn}."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fen":
        lines = []
        text = read_text(path)
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
        title = lines[0] if lines else title_from_name(os.path.basename(path))
        fen = lines[1] if len(lines) > 1 else ""
        return {"title": title, "fen": fen, "_path": path}
    # .pgn
    text = ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        pass
    title = title_from_name(os.path.basename(path))
    try:
        g = chess.pgn.read_game(io.StringIO(text))
        if g is not None:
            title = g.headers.get("Event") or title
    except Exception:
        pass
    return {"title": title, "pgn": text, "_path": path}


def find_usb_roots():
    """Eingehängte USB-Laufwerke suchen (ohne Root-Rechte)."""
    roots = []
    for base in ("/media", "/run/media", "/mnt"):
        if not os.path.isdir(base):
            continue
        try:
            for user in os.listdir(base):
                p1 = os.path.join(base, user)
                if not os.path.isdir(p1):
                    continue
                if base in ("/media", "/run/media"):
                    for vol in os.listdir(p1):
                        p2 = os.path.join(p1, vol)
                        if os.path.isdir(p2):
                            roots.append(p2)
                else:
                    roots.append(p1)
        except Exception:
            pass
    return sorted(set(roots))


def merge_dir(src, dst):
    """Kopiert den Inhalt von src nach dst (überschreibt gleichnamige Dateien, fügt Neues hinzu)."""
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)


def load_pgn_games(path):
    """Liest alle Partien/Stellungen aus einer PGN-Datei -> Liste von Knoten."""
    nodes = []
    games = []
    try:
        text = read_text(path)
        pgn_io = io.StringIO(text)
        while True:
            g = chess.pgn.read_game(pgn_io)
            if g is None:
                break
            games.append(g)
    except Exception:
        pass
    if not games:
        return nodes
    from collections import Counter
    event_counts = Counter((g.headers.get("Event") or "").strip() for g in games)
    used = Counter()
    for i, g in enumerate(games):
        try:
            h = g.headers
            white = (h.get("White") or "").strip()
            black = (h.get("Black") or "").strip()
            event = (h.get("Event") or "").strip()
            result = (h.get("Result") or "").strip()
            date = (h.get("Date") or "").strip()
            eco = (h.get("ECO") or "").strip()
            moves = list(g.mainline_moves())
            has_fen = h.get("SetUp") == "1" and bool(h.get("FEN"))

            if event and event_counts[event] > 1:
                used[event] += 1
                title = f"{event} {used[event]}"
            elif event:
                title = event
            elif white and black and white != "?" and black != "?":
                title = f"{white} – {black}"
            elif white and white != "?":
                title = white
            else:
                title = f"Partie {i + 1}"

            meta_parts = []
            if white and black and white != "?" and black != "?":
                meta_parts.append(f"{white} – {black}")
            if result and result != "*":
                meta_parts.append(result)
            if date and date not in ("????.??.??", ""):
                meta_parts.append(date[:4])
            elif eco:
                meta_parts.append(eco)
            meta = " · ".join(meta_parts)

            if has_fen and not moves:
                nodes.append({"title": title, "fen": h["FEN"], "meta": meta,
                              "_path": path, "_index": i, "_total": len(games)})
            else:
                try:
                    pgn_text = str(g)
                except Exception:
                    continue  # Spiel mit ungültigem Zug überspringen
                nodes.append({"title": title, "pgn": pgn_text, "meta": meta,
                              "_path": path, "_index": i, "_total": len(games),
                              "_preview_fen": g.board().fen()})
        except Exception:
            continue  # defektes Spiel überspringen
    return nodes


def san_de(board, move):
    return board.san(move).replace("N", "S").replace("B", "L").replace("Q", "D").replace("R", "T")


def mainline_moves(game):
    if hasattr(game, "mainline_moves"):
        return list(game.mainline_moves())
    moves = []
    node = game
    while node.variations:
        node = node.variations[0]
        moves.append(node.move)
    return moves


def symbol_to_piece(sym):
    color = chess.WHITE if sym[0] == "w" else chess.BLACK
    ptype = {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK,
             "B": chess.BISHOP, "N": chess.KNIGHT, "P": chess.PAWN}[sym[1].upper()]
    return chess.Piece(ptype, color)


def parse_annotation_comment(text):
    """Extrahiert [Befehl ...]-Markup aus einem PGN-Kommentar -> Liste von Schritten.

    Befehle (case-insensitiv):
      [Sq e4,d5]   Quadrate hervorheben
      [Mk e4]      Felder markieren (gelb)
      [Ar e2e4]    Pfeil von e2 nach e4
      [Rank 4]     Reihe 4 hervorheben (horizontal)
      [File e]     Linie e hervorheben (vertikal)
      [Clear]      alle Markierungen löschen
    """
    steps = []
    if not text:
        return steps
    for m in re.finditer(r"\[([A-Za-z]+)\s*([^\]]*)\]", text):
        cmd = m.group(1).lower()
        arg = m.group(2).strip()
        tokens = [t for t in re.split(r"[\s,]+", arg) if t]
        if cmd in ("x", "clear", "c"):
            steps.append(("clear",))
        elif cmd in ("a", "ar", "arrow", "pfeil"):
            for a in tokens:
                if len(a) >= 4:
                    try:
                        f = chess.parse_square(a[0:2])
                        t = chess.parse_square(a[2:4])
                        steps.append(("arrow", f, t))
                    except ValueError:
                        pass
        elif cmd in ("s", "sq", "hi", "highlight", "quadrat"):
            for s in tokens:
                try:
                    steps.append(("highlight", chess.parse_square(s)))
                except ValueError:
                    pass
        elif cmd in ("m", "mk", "mark", "feld"):
            for s in tokens:
                try:
                    steps.append(("mark", chess.parse_square(s)))
                except ValueError:
                    pass
        elif cmd in ("r", "rank", "reihe"):
            for r in tokens:
                if r.isdigit() and 1 <= int(r) <= 8:
                    steps.append(("rank", int(r) - 1))
        elif cmd in ("f", "file", "linie"):
            for f in tokens:
                f = f.lower()
                if len(f) == 1 and f in "abcdefgh":
                    steps.append(("file", "abcdefgh".index(f)))
    return steps


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
    sq = size // 8
    board = chess.Board(fen)
    for s in range(64):
        f, r = s % 8, s // 8
        color = square_color(s)
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
        return self.off_x + self.margin + col * self.sq, self.off_y + self.margin + row * self.sq

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

    def redraw(self):
        self.delete("all")
        board = self.app.board
        sq = self.sq

        for s in range(64):
            x0, y0 = self.sq_origin(s)
            color = square_color(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=color, width=0)

        if self.app.board_hidden:
            # Abgedeckt: nur die Felder zeichnen, Figuren/Markierungen ausblenden.
            cx = self.off_x + self.margin + 4 * sq
            cy = self.off_y + self.margin + 4 * sq
            self.create_text(cx, cy, text="Brett verdeckt",
                             fill="#9e9e9e",
                             font=("DejaVu Sans", max(14, sq // 2), "bold"))
            return

        if self.app.last_move:
            for s in [self.app.last_move.from_square, self.app.last_move.to_square]:
                x0, y0 = self.sq_origin(s)
                self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=LAST_COLOR, width=0, stipple="gray50")

        for s, color in self.app.marks.items():
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=color, width=0, stipple="gray50")
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=color, width=3)

        # Hervorgehobene Quadrate (Lernmodus)
        for s in self.app.highlights:
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=HIGHLIGHT_COLOR, width=0, stipple="gray50")
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=HIGHLIGHT_COLOR, width=3)

        # Reihen/Linien hervorheben (Lernmodus)
        for kind, idx in self.app.lines:
            if kind == "rank":
                row = idx if self.app.flipped else 7 - idx
                y0 = self.off_y + self.margin + row * sq
                self.create_rectangle(self.off_x + self.margin, y0,
                                      self.off_x + self.margin + 8 * sq, y0 + sq,
                                      fill=LINE_COLOR, width=0, stipple="gray50")
            else:
                col = 7 - idx if self.app.flipped else idx
                x0 = self.off_x + self.margin + col * sq
                self.create_rectangle(x0, self.off_y + self.margin,
                                      x0 + sq, self.off_y + self.margin + 8 * sq,
                                      fill=LINE_COLOR, width=0, stipple="gray50")

        if board.is_check() and not self.app.edit_mode:
            king_sq = board.king(board.turn)
            if king_sq is not None:
                x0, y0 = self.sq_origin(king_sq)
                self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=CHECK_COLOR, width=5)

        if self.app.selected is not None:
            x0, y0 = self.sq_origin(self.app.selected)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=SELECT_COLOR, width=4)
            legal = [] if self.app.edit_mode or not self.app.show_legal_moves else board.legal_moves
            for move in legal:
                if move.from_square == self.app.selected:
                    ts = move.to_square
                    tx, ty = self.center(ts)
                    if board.piece_at(ts):
                        atk, deff = self.app.defense_counts(ts)
                        color = WINNABLE_COLOR if atk > deff else THREAT_COLOR
                        m = sq * 0.14
                        self.create_oval(tx - sq/2 + m, ty - sq/2 + m,
                                         tx + sq/2 - m, ty + sq/2 - m,
                                         outline=color, width=5)
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

        for i, move in enumerate(self.app.best_moves):
            color = BESTMOVE_COLOR if i == 0 else SUGGEST_COLOR
            width = 6 if i == 0 else 4
            self.draw_arrow(move.from_square, move.to_square, color, draft=False, width=width)

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

        self.board = chess.Board()
        self.loaded_fen = self.board.fen()
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = {}
        self.arrow_start = None
        self.arrow_cur = None
        self.best_moves = []
        self.best_scores = []
        self.show_coords = True
        self.show_legal_moves = True
        self.board_hidden = False
        self.mark_colors = ["#ffd54f", "#f44336", "#2196f3", "#4caf50", "#9c27b0"]
        self.mark_color_index = 0
        self.current_node = None
        self.nav_mode = "moves"
        self.mark_mode = False
        self.flipped = False
        self.edit_mode = False
        self.palette_tool = None
        self.palette_buttons = {}
        self.engine = None
        self.engine_time = 1.5
        self.engine_multi = 1
        self.analyse_on = False
        self._analyse_thread = None
        self._result_queue = queue.Queue()
        self._engine_lock = threading.Lock()
        self._closing = False

        self.game_base = chess.Board()
        self.game_steps = []
        self.step_index = 0
        self.game_index = 0
        self.highlights = []
        self.lines = []
        self.move_step_index = []

        self.tabs = []
        self.current_tab_index = 0
        self.figures_index = 0
        self.expanded = {}
        self.selected_lesson = None
        self.tab_canvases = {}
        self.tab_hits = {}
        self.tab_del_hits = {}

        self.load_data()
        self.build_ui()
        self.load_config()
        self.update_status()
        self.update_content_field()

        self.bind("<F1>", lambda e: self.show_help())
        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.bind("<Control-z>", lambda e: self._prev_kb(e))
        self.bind("<Left>", lambda e: self._prev_kb(e))
        self.bind("<Right>", lambda e: self._next_kb(e))
        self.bind("<Home>", lambda e: self._goto_start_kb(e))
        self.bind("<End>", lambda e: self._goto_end_kb(e))
        self.bind("<F5>", lambda e: self._reload_db_kb(e))
        self.bind("r", lambda e: self._reset_kb(e))
        self.bind("n", lambda e: self._new_game_kb(e))
        self.bind("h", lambda e: self.toggle_cover_key())
        self.bind("k", lambda e: self._toggle_coords_kb(e))
        self.bind("m", lambda e: self._toggle_mark_kb(e))
        self.bind("c", lambda e: self._cycle_mark_color_kb(e))
        self.bind("a", lambda e: self._toggle_analyse_kb(e))
        self.bind("t", lambda e: self._set_nav_mode(e, "tabs"))
        self.bind("z", lambda e: self._set_nav_mode(e, "moves"))
        self.bind("l", lambda e: self._set_nav_mode(e, "lessons"))
        self.bind("u", lambda e: self._set_nav_mode(e, "exercises"))
        # Tab-Fokus-Traversal deaktivieren (kein Hängenbleiben in Eingabefeldern)
        self.bind_all("<Tab>", lambda e: "break")
        self.bind_all("<Shift-Tab>", lambda e: "break")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.board_canvas.focus_set()
        self.after(200, self._relayout)

    # -- Daten (Verzeichnisstruktur) ---------------------------------------
    def load_data(self):
        self.tabs = []
        if not os.path.isdir(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        entries = sorted(os.listdir(DATA_DIR))
        for tabname in entries:
            tabpath = os.path.join(DATA_DIR, tabname)
            if not os.path.isdir(tabpath) or tabname.startswith("."):
                continue
            tab = {"id": tabpath,
                   "title": read_meta(tabpath) or title_from_name(tabname),
                   "lessons": [], "exercises": []}
            for entry in sorted(os.listdir(tabpath)):
                epath = os.path.join(tabpath, entry)
                if os.path.isdir(epath):
                    lesson = {"id": epath,
                              "title": read_meta(epath) or title_from_name(entry),
                              "exercises": []}
                    for fn in sorted(os.listdir(epath)):
                        if fn.startswith("."):
                            continue
                        fpath = os.path.join(epath, fn)
                        if fn.lower().endswith(".pgn"):
                            lesson["exercises"].extend(load_pgn_games(fpath))
                        elif fn.lower().endswith(".fen"):
                            lesson["exercises"].append(load_node(fpath))
                    tab["lessons"].append(lesson)
                elif entry.lower().endswith(".pgn"):
                    tab["lessons"].append({"id": epath, "title": title_from_name(entry),
                                           "exercises": load_pgn_games(epath), "_is_file": True})
                elif entry.lower().endswith(".fen"):
                    tab["exercises"].append(load_node(epath))
            self.tabs.append(tab)
        # .pgn-Dateien auf oberster Ebene -> je ein Tab mit einer Lektion
        for fn in entries:
            fpath = os.path.join(DATA_DIR, fn)
            if os.path.isfile(fpath) and fn.lower().endswith(".pgn"):
                self.tabs.append({"id": fpath, "title": title_from_name(fn),
                                  "lessons": [{"id": fpath, "title": "Spiele",
                                               "exercises": load_pgn_games(fpath), "_is_file": True}],
                                  "exercises": []})

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
        self.edit_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Bearbeiten", variable=self.edit_var,
                        command=self.toggle_edit_mode).pack(side="left", padx=2)

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
        self.mark_btn = ttk.Checkbutton(bar, text="Markieren", command=self.toggle_mark_mode)
        self.mark_btn.pack(side="left", padx=2)
        self.cover_var = tk.BooleanVar(value=False)
        self.cover_btn = ttk.Checkbutton(bar, text="Brett verdecken", variable=self.cover_var,
                                         command=self.toggle_cover)
        self.cover_btn.pack(side="left", padx=2)
        ttk.Button(bar, text="Pfeile weg", command=self.clear_arrows).pack(side="left", padx=2)
        ttk.Button(bar, text="Mark. weg", command=self.clear_marks).pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(bar, text="⚙ Einstellungen", command=self.open_settings).pack(side="left", padx=2)
        self.analyse_var = tk.BooleanVar(value=False)
        self.analyse_btn = ttk.Checkbutton(bar, text="Analyse", variable=self.analyse_var,
                                           command=self.toggle_analyse)
        self.analyse_btn.pack(side="left", padx=2)

        self.nav_lbl = tk.Label(bar, text="Nav: Züge", font=("DejaVu Sans", 10), fg="#555555")
        self.nav_lbl.pack(side="left", padx=4)
        self.status_lbl = tk.Label(bar, text="", font=("DejaVu Sans", 13, "bold"),
                                   fg="#1a237e", anchor="w")
        self.status_lbl.pack(side="left", padx=10, fill="x", expand=True)

        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        self.board_frame = ttk.Frame(self.paned)
        self.paned.add(self.board_frame, weight=3)
        self.board_canvas = BoardCanvas(self.board_frame, self)
        self.board_canvas.pack(fill="both", expand=True)

        side = ttk.Frame(self.paned)
        self.paned.add(side, weight=2)

        self.notebook = ttk.Notebook(side)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # dynamische Tabs aus der Verzeichnisstruktur
        self.content_tab_frames = []
        for i, tab in enumerate(self.tabs):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=tab["title"])
            self.content_tab_frames.append(frame)
            self.tab_canvases[i] = self._make_list_canvas(frame, i)
            self.expanded[i] = set()
            self.render_tab(i)

        # Figuren-Palette (fester Tab)
        fig_tab = ttk.Frame(self.notebook)
        self.notebook.add(fig_tab, text="Figuren")
        self.figures_index = len(self.tabs)
        ttk.Label(fig_tab, text="Figur wählen, dann aufs Brett klicken.",
                  font=("DejaVu Sans", 11, "bold")).pack(anchor="w", padx=6, pady=(6, 0))
        for label, prefix in [("Weiß", "w"), ("Schwarz", "b")]:
            ttk.Label(fig_tab, text=label).pack(anchor="w", padx=6, pady=(8, 0))
            row = ttk.Frame(fig_tab)
            row.pack(anchor="w", padx=6)
            for ptype in "KQRBNP":
                tool = prefix + ptype
                piece_sym = ptype if prefix == "w" else ptype.lower()
                btn = tk.Button(row, image=PIECES.get(piece_sym, 44), width=48, height=48,
                                command=lambda s=tool: self.set_palette_tool(s))
                btn.pack(side="left", padx=1)
                self.palette_buttons[tool] = btn
        tools = ttk.Frame(fig_tab)
        tools.pack(anchor="w", padx=6, pady=10)
        self.remove_btn = tk.Button(tools, text="✕ Entfernen", width=11,
                                    command=lambda: self.set_palette_tool("remove"))
        self.remove_btn.pack(side="left", padx=2)
        self.palette_buttons["remove"] = self.remove_btn
        tk.Button(tools, text="Leeres Brett", command=self.clear_board).pack(side="left", padx=2)
        ttk.Label(fig_tab, text="Mit ausgewählter Figur: Klick setzt die Figur.\n"
                  "Mit ✕: Klick entfernt eine Figur.\n"
                  "Ohne Auswahl: Figur anklicken und frei verschieben.",
                  wraplength=230, justify="left").pack(anchor="w", padx=6, pady=8)

        # Züge (gemeinsam für alle Tabs)
        ttk.Label(side, text="Züge", font=("DejaVu Sans", 11, "bold")).pack(anchor="w")
        self.move_list = tk.Listbox(side, height=7, font=("DejaVu Sans Mono", 10),
                                    exportselection=False)
        self.move_list.pack(fill="x", padx=2, pady=2)
        self.move_list.bind("<<ListboxSelect>>", self.on_move_list_select)

        # Neu
        add = ttk.LabelFrame(side, text="Neu", padding=4)
        add.pack(fill="x", padx=2, pady=4)
        ttk.Label(add, text="Titel").pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(add, textvariable=self.name_var).pack(fill="x")
        ttk.Label(add, text="FEN oder PGN").pack(anchor="w", pady=(4, 0))
        self.content_text = tk.Text(add, height=3, font=("DejaVu Sans Mono", 9), wrap="none")
        self.content_text.pack(fill="x")
        self.content_text.bind("<Tab>", lambda e: "break")
        btns = ttk.Frame(add)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Laden", command=self.load_from_entry).pack(side="left", padx=2)
        ttk.Button(btns, text="Hinzufügen", command=self.add_node).pack(side="left", padx=2)
        ttk.Button(btns, text="💾 Board speichern", command=self.save_current_board).pack(side="left", padx=2)
        ttk.Button(btns, text="Neue Lektion", command=self.new_lesson).pack(side="left", padx=2)

    def _make_list_canvas(self, parent, tab_index):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, highlightthickness=0, bg="#fafafa", cursor="hand2")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind("<Button-1>", lambda e, t=tab_index: self.on_list_click(t, e))
        canvas.bind("<Configure>", lambda e, t=tab_index: self.render_tab(t))
        canvas.bind("<Button-4>", lambda e, c=canvas: c.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda e, c=canvas: c.yview_scroll(1, "units"))
        canvas.bind("<MouseWheel>", lambda e, c=canvas: c.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        return canvas

    def _section_header(self, canvas, x, y, text):
        canvas.create_text(x + 6, y + 12, text=text, anchor="w",
                           font=("DejaVu Sans", 11, "bold"), fill="#455a64")
        return y + 26

    def _node_preview_fen(self, node):
        if "fen" in node:
            return node["fen"]
        if node.get("_preview_fen"):
            return node["_preview_fen"]
        try:
            g = chess.pgn.read_game(io.StringIO(node.get("pgn", "")))
            if g:
                return g.board().fen()
        except Exception:
            pass
        return chess.STARTING_FEN

    def _draw_node_row(self, canvas, x, y, size, node, selected=False):
        if selected:
            canvas.create_rectangle(x - 2, y - 2, x + 398, y + size + 2, fill="#fff59d", width=0)
        fen = self._node_preview_fen(node)
        draw_mini_board(canvas, x, y, size, fen)
        tx = x + size + 8
        meta = node.get("meta", "")
        if meta:
            canvas.create_text(tx, y + 20, text=truncate(node.get("title", "?"), 28),
                               anchor="w", font=("DejaVu Sans", 12, "bold"), fill="#222")
            canvas.create_text(tx, y + 44, text=truncate(meta, 40),
                               anchor="w", font=("DejaVu Sans", 9), fill="#666")
        else:
            canvas.create_text(tx, y + size // 2, text=truncate(node.get("title", "?"), 30),
                               anchor="w", font=("DejaVu Sans", 12), fill="#222")

    def render_tab(self, tab_index):
        if tab_index not in self.tab_canvases:
            return
        canvas = self.tab_canvases[tab_index]
        canvas.delete("all")
        hits = []
        del_hits = []
        x, y = 6, 6
        size = 84
        ind = 26
        del_x = 396
        tab = self.tabs[tab_index]
        expanded = self.expanded.get(tab_index, set())

        for li, lesson in enumerate(tab["lessons"]):
            exp = li in expanded
            sel = self.selected_lesson == (tab_index, li)
            bg = "#cfe0f0" if sel else "#e6ecef"
            canvas.create_rectangle(x, y, x + 400, y + 24, fill=bg, width=0)
            canvas.create_text(x + 10, y + 12, text="▾" if exp else "▸",
                               anchor="w", font=("DejaVu Sans", 12), fill="#333")
            canvas.create_text(x + 30, y + 12, text=lesson["title"],
                               anchor="w", font=("DejaVu Sans", 12, "bold"), fill="#222")
            canvas.create_text(del_x, y + 12, text="✕", anchor="center",
                               font=("DejaVu Sans", 12, "bold"), fill="#c62828")
            hits.append((y, y + 24, "lesson", li))
            del_hits.append((y, y + 24, ("lesson", li)))
            y += 28
            if exp:
                for ni, node in enumerate(lesson["exercises"]):
                    sel = (self.current_node is not None
                           and self._node_key(node) == self._node_key(self.current_node))
                    self._draw_node_row(canvas, x + ind, y, size, node, sel)
                    canvas.create_text(del_x, y + size // 2, text="✕", anchor="center",
                                       font=("DejaVu Sans", 12, "bold"), fill="#c62828")
                    hits.append((y, y + size, "exercise", node))
                    del_hits.append((y, y + size, ("lesson_ex", li, ni)))
                    y += size + 8

        if tab["exercises"]:
            y += 6
            y = self._section_header(canvas, x, y, "Übungen")
            for ei, node in enumerate(tab["exercises"]):
                sel = (self.current_node is not None
                       and self._node_key(node) == self._node_key(self.current_node))
                self._draw_node_row(canvas, x, y, size, node, sel)
                canvas.create_text(del_x, y + size // 2, text="✕", anchor="center",
                                   font=("DejaVu Sans", 12, "bold"), fill="#c62828")
                hits.append((y, y + size, "exercise", node))
                del_hits.append((y, y + size, ("ex", ei)))
                y += size + 8

        canvas.configure(scrollregion=(0, 0, max(420, canvas.winfo_width()), max(y + 8, canvas.winfo_height())))
        self.tab_hits[tab_index] = hits
        self.tab_del_hits[tab_index] = del_hits

    def on_list_click(self, tab_index, event):
        canvas = self.tab_canvases[tab_index]
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        if 380 <= cx <= 412:
            for y0, y1, spec in self.tab_del_hits.get(tab_index, []):
                if y0 <= cy <= y1:
                    self._delete_node(tab_index, spec)
                    return
        for y0, y1, kind, data in self.tab_hits.get(tab_index, []):
            if y0 <= cy <= y1:
                if kind == "lesson":
                    li = data
                    self.selected_lesson = (tab_index, li)
                    if li in self.expanded.get(tab_index, set()):
                        self.expanded[tab_index].discard(li)
                    else:
                        self.expanded[tab_index].add(li)
                    self.render_tab(tab_index)
                else:
                    self.selected_lesson = None
                    node = data
                    self.current_node = node
                    self._load_node(node)
                    self.render_tab(tab_index)
                return

    def _remove_node(self, node):
        path = node["_path"]
        if path.lower().endswith(".pgn") and "_index" in node:
            games = []
            try:
                text = read_text(path)
                pgn_io = io.StringIO(text)
                while True:
                    g = chess.pgn.read_game(pgn_io)
                    if g is None:
                        break
                    games.append(g)
            except Exception:
                pass
            if node["_index"] < len(games):
                del games[node["_index"]]
            if games:
                with open(path, "w", encoding="utf-8") as f:
                    for g in games:
                        try:
                            f.write(str(g) + "\n\n")
                        except Exception:
                            pass
            else:
                try:
                    os.remove(path)
                except Exception:
                    pass
        else:
            try:
                os.remove(path)
            except Exception:
                pass

    def _delete_node(self, tab_index, spec):
        kind = spec[0]
        if kind == "lesson":
            li = spec[1]
            lessons = self.tabs[tab_index]["lessons"]
            if 0 <= li < len(lessons):
                title = lessons[li]["title"]
                if messagebox.askyesno("Löschen", f"Lektion „{title}“ mit allen Übungen löschen?", parent=self):
                    target = lessons[li]["id"]
                    if os.path.isdir(target):
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        try:
                            os.remove(target)
                        except Exception:
                            pass
                    self.selected_lesson = None
                    self.load_data()
                    self.render_tab(tab_index)
        elif kind == "lesson_ex":
            _, li, ni = spec
            lessons = self.tabs[tab_index]["lessons"]
            if 0 <= li < len(lessons):
                exs = lessons[li]["exercises"]
                if 0 <= ni < len(exs):
                    if messagebox.askyesno("Löschen", f"Übung „{exs[ni]['title']}“ löschen?", parent=self):
                        self._remove_node(exs[ni])
                        self.load_data()
                        self.render_tab(tab_index)
        elif kind == "ex":
            ei = spec[1]
            exs = self.tabs[tab_index]["exercises"]
            if 0 <= ei < len(exs):
                if messagebox.askyesno("Löschen", f"Übung „{exs[ei]['title']}“ löschen?", parent=self):
                    self._remove_node(exs[ei])
                    self.load_data()
                    self.render_tab(tab_index)

    def on_tab_changed(self, event):
        idx = self.notebook.index("current")
        if idx == self.figures_index:
            self.current_tab_index = "figures"
        else:
            self.current_tab_index = idx
            self.render_tab(idx)
        if self.current_tab_index != "figures" and self.edit_mode:
            self.exit_edit_mode()
            self.board_canvas.redraw()
            self.update_status()

    # -- Laden --------------------------------------------------------------
    def load_fen(self, fen):
        try:
            self.board = chess.Board(fen)
        except Exception as e:
            messagebox.showerror("FEN-Fehler", str(e))
            return
        self.loaded_fen = fen
        self.game_steps = []
        self.step_index = 0
        self.game_index = 0
        self.highlights = []
        self.lines = []
        self.move_step_index = []
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = {}
        self.best_moves = []
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
        self.game_steps = self._build_steps(g)
        self.loaded_fen = self.game_base.fen()
        self.selected = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self.lines = []
        self.best_moves = []
        self._populate_move_list()
        self._rebuild_to_step(0)
        self._sync_move_list_selection()
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def _build_steps(self, game):
        steps = []
        node = game
        for st in parse_annotation_comment(node.comment):
            steps.append(st)
        while node.variations:
            node = node.variations[0]
            # Markierungen VOR dem Zug zeigen (sie erklären den Plan)
            for st in parse_annotation_comment(node.comment):
                steps.append(st)
            steps.append(("move", node.move))
        return steps

    def _rebuild_to_step(self, i):
        i = max(0, min(len(self.game_steps), i))
        b = self.game_base.copy()
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self.lines = []
        self.last_move = None
        move_count = 0
        for st in self.game_steps[:i]:
            kind = st[0]
            if kind == "move":
                b.push(st[1]); self.last_move = st[1]; move_count += 1
                self.arrows = []; self.marks = {}; self.highlights = []; self.lines = []
            elif kind == "arrow":
                self.arrows.append((st[1], st[2]))
            elif kind == "mark":
                self.marks[st[1]] = self.mark_colors[self.mark_color_index]
            elif kind == "highlight":
                self.highlights.append(st[1])
            elif kind == "rank":
                self.lines.append(("rank", st[1]))
            elif kind == "file":
                self.lines.append(("file", st[1]))
            elif kind == "clear":
                self.arrows = []; self.marks = {}; self.highlights = []; self.lines = []
        self.board = b
        self.step_index = i
        self.game_index = move_count

    def game_replay_to(self, i):
        if not self.game_steps:
            return
        self._rebuild_to_step(i)
        self.selected = None
        self.best_moves = []
        self._sync_move_list_selection()
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def game_prev(self):
        self.game_replay_to(self.step_index - 1)

    def game_next(self):
        self.game_replay_to(self.step_index + 1)

    def game_start(self):
        self.game_replay_to(0)

    def game_end(self):
        self.game_replay_to(len(self.game_steps))

    def _populate_move_list(self):
        self.move_list.delete(0, "end")
        self.move_step_index = []
        b = self.game_base.copy()
        moves = 0
        step = 0
        for st in self.game_steps:
            if st[0] == "move":
                m = st[1]
                prefix = f"{moves // 2 + 1}." if moves % 2 == 0 else f"{moves // 2 + 1}..."
                self.move_list.insert("end", f"{prefix} {san_de(b, m)}")
                b.push(m)
                moves += 1
                self.move_step_index.append(step + 1)
            step += 1

    def _sync_move_list(self):
        self.move_list.delete(0, "end")

    def _sync_move_list_selection(self):
        self.move_list.selection_clear(0, "end")
        total = len(self.move_step_index)
        if self.game_index > 0:
            self.move_list.selection_set(self.game_index - 1)
            self.move_list.see(self.game_index - 1)
            self.move_lbl.config(text=f"Zug {self.game_index}/{total}")
        else:
            self.move_lbl.config(text="Start")

    def on_move_list_select(self, event):
        sel = self.move_list.curselection()
        if sel and sel[0] < len(self.move_step_index):
            self.game_replay_to(self.move_step_index[sel[0]])

    # -- Züge / Aktionen ----------------------------------------------------
    def board_click(self, sq):
        if self.edit_mode and self.current_tab_index == "figures":
            self.edit_click(sq)
            return
        board = self.board
        piece = board.piece_at(sq)
        if self.selected is not None:
            for m in board.legal_moves:
                if m.from_square == self.selected and m.to_square == sq:
                    self.board.push(m)
                    self.last_move = m
                    self.selected = None
                    self.best_moves = []
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
            del self.marks[sq]
        else:
            self.marks[sq] = self.mark_colors[self.mark_color_index]
        self.board_canvas.redraw()

    def cycle_mark_color(self):
        if self.mark_colors:
            self.mark_color_index = (self.mark_color_index + 1) % len(self.mark_colors)
            self.board_canvas.redraw()

    # -- Tastatur-Shortcuts ---------------------------------------
    def _typing(self):
        w = self.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, tk.Listbox))

    def _node_key(self, node):
        return (node.get("_path"), node.get("_index"))

    def _load_node(self, node):
        if "fen" in node:
            self.load_fen(node["fen"])
        elif "pgn" in node:
            self.load_pgn(node["pgn"])

    def _update_nav_label(self):
        names = {"tabs": "Tabs", "moves": "Züge", "lessons": "Lektionen", "exercises": "Übungen"}
        self.nav_lbl.config(text="Nav: " + names.get(self.nav_mode, "?"))

    def _set_nav_mode(self, e, mode):
        if self._typing():
            return
        self.nav_mode = mode
        self._update_nav_label()

    def _nav(self, delta):
        if self.nav_mode == "tabs":
            self.goto_tab_relative(delta)
        elif self.nav_mode == "lessons":
            self.goto_lesson_relative(delta)
        elif self.nav_mode == "exercises":
            self.goto_relative(delta)
        else:  # moves
            if delta < 0:
                self.undo()
            else:
                self.game_next()

    def _prev_kb(self, e):
        if not self._typing(): self._nav(-1)

    def _next_kb(self, e):
        if not self._typing(): self._nav(1)

    def _goto_start_kb(self, e):
        if not self._typing(): self.game_start()

    def _goto_end_kb(self, e):
        if not self._typing(): self.game_end()

    def _reset_kb(self, e):
        if not self._typing(): self.reset()

    def _reload_db_kb(self, e):
        if not self._typing(): self.reload_lessons()

    def reload_lessons(self):
        self.load_data()
        self._rebuild_tabs()
        self.update_status()

    def _new_game_kb(self, e):
        if not self._typing(): self.new_game()

    def _toggle_coords_kb(self, e):
        if not self._typing(): self.toggle_coords()

    def _toggle_mark_kb(self, e):
        if not self._typing(): self.toggle_mark_mode()

    def _cycle_mark_color_kb(self, e):
        if not self._typing(): self.cycle_mark_color()

    def _toggle_analyse_kb(self, e):
        if not self._typing():
            self.analyse_var.set(not self.analyse_var.get())
            self.toggle_analyse()

    def _flatten_tab(self):
        if self.current_tab_index == "figures" or not (0 <= self.current_tab_index < len(self.tabs)):
            return []
        tab = self.tabs[self.current_tab_index]
        items = []
        for li, lesson in enumerate(tab["lessons"]):
            for node in lesson["exercises"]:
                items.append((node, li))
        for node in tab["exercises"]:
            items.append((node, None))
        return items

    def goto_relative(self, delta):
        items = self._flatten_tab()
        if not items:
            return
        idx = None
        if self.current_node is not None:
            for i, (n, _) in enumerate(items):
                if self._node_key(n) == self._node_key(self.current_node):
                    idx = i
                    break
        if idx is None:
            idx = 0 if delta > 0 else len(items) - 1
        else:
            idx = max(0, min(len(items) - 1, idx + delta))
        node, li = items[idx]
        self.current_node = node
        if li is not None:
            self.expanded.setdefault(self.current_tab_index, set()).add(li)
            self.selected_lesson = (self.current_tab_index, li)
        self._load_node(node)
        self.render_tab(self.current_tab_index)
        y = self._find_item_y(self.current_tab_index, "exercise", node)
        if y is not None:
            self._scroll_into_view(self.current_tab_index, y)

    def goto_lesson_relative(self, delta):
        if self.current_tab_index == "figures" or not (0 <= self.current_tab_index < len(self.tabs)):
            return
        lessons = self.tabs[self.current_tab_index]["lessons"]
        if not lessons:
            return
        cur = None
        if self.selected_lesson and self.selected_lesson[0] == self.current_tab_index:
            cur = self.selected_lesson[1]
        if cur is None:
            cur = 0 if delta > 0 else len(lessons) - 1
        else:
            cur = max(0, min(len(lessons) - 1, cur + delta))
        self.expanded.setdefault(self.current_tab_index, set()).add(cur)
        self.selected_lesson = (self.current_tab_index, cur)
        exs = lessons[cur]["exercises"]
        if exs:
            self.current_node = exs[0]
            self._load_node(exs[0])
        self.render_tab(self.current_tab_index)
        y = self._find_item_y(self.current_tab_index, "lesson", cur)
        if y is not None:
            self._scroll_to_top(self.current_tab_index, y)

    def goto_tab_relative(self, delta):
        n = len(self.tabs)
        if n == 0:
            return
        cur = self.current_tab_index
        if cur == "figures":
            cur = n if delta < 0 else -1
        cur = max(0, min(n - 1, cur + delta))
        self.current_tab_index = cur
        self.notebook.select(cur)
        self.render_tab(cur)

    def _find_item_y(self, tab_index, kind, data):
        for y0, y1, k, d in self.tab_hits.get(tab_index, []):
            if k != kind:
                continue
            if kind == "lesson" and d == data:
                return y0
            if kind == "exercise" and self._node_key(d) == self._node_key(data):
                return y0
        return None

    def _scroll_to_top(self, tab_index, y):
        canvas = self.tab_canvases.get(tab_index)
        if not canvas:
            return
        try:
            parts = [float(x) for x in canvas.cget("scrollregion").split()]
            total = parts[3]
            if total > 0:
                canvas.yview_moveto(max(0.0, min(1.0, y / total)))
        except Exception:
            pass

    def _scroll_into_view(self, tab_index, y, height=84):
        canvas = self.tab_canvases.get(tab_index)
        if not canvas:
            return
        try:
            parts = [float(x) for x in canvas.cget("scrollregion").split()]
            total = parts[3]
            if total <= 0:
                return
            top, bottom = canvas.yview()
            item_top = y / total
            item_bottom = (y + height) / total
            if item_top < top or item_bottom > bottom:
                canvas.yview_moveto(max(0.0, min(1.0, item_top)))
        except Exception:
            pass

    def set_palette_tool(self, sym):
        self.palette_tool = None if self.palette_tool == sym else sym
        self._refresh_palette_buttons()

    def _refresh_palette_buttons(self):
        for s, btn in self.palette_buttons.items():
            btn.config(relief="sunken" if s == self.palette_tool else "raised")

    def exit_edit_mode(self):
        self.edit_mode = False
        self.edit_var.set(False)
        self.palette_tool = None
        self._refresh_palette_buttons()

    def toggle_edit_mode(self):
        self.edit_mode = self.edit_var.get()
        self.selected = None
        self.best_moves = []
        self.best_scores = []
        if self.edit_mode:
            if self.current_tab_index != "figures":
                self.notebook.select(self.figures_index)
                self.current_tab_index = "figures"
            if self.analyse_on:
                self.analyse_var.set(False)
                self.analyse_on = False
        else:
            self.palette_tool = None
        self._refresh_palette_buttons()
        self.board_canvas.redraw()
        self.update_status()

    def clear_board(self):
        self.board.clear_board()
        self.selected = None
        self.last_move = None
        self.best_moves = []
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def edit_click(self, sq):
        if self.palette_tool == "remove":
            self.board.remove_piece_at(sq)
            self.selected = None
        elif self.palette_tool is not None:
            self.board.set_piece_at(sq, symbol_to_piece(self.palette_tool))
            self.selected = None
        else:
            if self.selected is None:
                self.selected = sq
            else:
                moving = self.board.piece_at(self.selected)
                if moving is not None:
                    self.board.remove_piece_at(self.selected)
                    self.board.set_piece_at(sq, moving)
                self.selected = None
        self.last_move = None
        self.best_moves = []
        self.update_content_field()
        self.board_canvas.redraw()
        self.update_status()

    def undo(self):
        if self.game_steps:
            self.game_prev()
        elif self.board.move_stack:
            self.board.pop()
            self.last_move = self.board.peek() if self.board.move_stack else None
            self.selected = None
            self.best_moves = []
            self.update_content_field()
            self.board_canvas.redraw()
            self.update_status()

    def reset(self):
        if self.game_steps:
            self.game_start()
        else:
            self.load_fen(self.loaded_fen)

    def new_game(self):
        self.load_fen(chess.STARTING_FEN)
        self.exit_edit_mode()
        self.mark_mode = False
        self.mark_btn.state(["!selected"])
        self.board_canvas.redraw()
        self.update_status()

    def toggle_flip(self):
        self.flipped = self.flip_var.get()
        self.board_canvas.redraw()

    def toggle_coords(self):
        self.show_coords = not self.show_coords
        self.coord_btn.state(["selected"] if self.show_coords else ["!selected"])
        self.board_canvas.redraw()

    def toggle_cover(self):
        self.board_hidden = self.cover_var.get()
        self.board_canvas.redraw()
        self.update_status()

    def toggle_cover_key(self):
        self.cover_var.set(not self.cover_var.get())
        self.toggle_cover()

    def toggle_mark_mode(self):
        self.mark_mode = not self.mark_mode
        self.selected = None
        self.board_canvas.redraw()

    def clear_arrows(self):
        self.arrows = []
        self.best_moves = []
        self.best_scores = []
        self.board_canvas.redraw()

    def clear_marks(self):
        self.marks = {}
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
        if not self.tabs or self.current_tab_index == "figures":
            messagebox.showinfo("Hinzufügen", "Bitte zuerst einen Inhalts-Tab wählen.")
            return
        tab = self.tabs[self.current_tab_index]
        title = self.name_var.get().strip() or "Ohne Namen"
        content = self.content_text.get("1.0", "end").strip()
        if not content:
            return
        try:
            chess.Board(content)
            kind = "fen"
        except Exception:
            try:
                g = chess.pgn.read_game(io.StringIO(content))
                if g is None:
                    raise ValueError
                kind = "pgn"
            except Exception:
                messagebox.showerror("Fehler", "Keine gültige FEN oder PGN.")
                return
        if self.selected_lesson and self.selected_lesson[0] == self.current_tab_index:
            target = tab["lessons"][self.selected_lesson[1]]["id"]
        else:
            target = tab["id"]
        num = next_number(target)
        fname = f"{num:04d}_{sanitize(title)}.{kind}"
        path = os.path.join(target, fname)
        if kind == "fen":
            with open(path, "w", encoding="utf-8") as f:
                f.write(title + "\n" + content + "\n")
        else:
            g = chess.pgn.read_game(io.StringIO(content))
            g.headers["Event"] = title
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(g) + "\n")
        self.load_data()
        self.render_tab(self.current_tab_index)

    def new_lesson(self):
        if not self.tabs or self.current_tab_index == "figures":
            messagebox.showinfo("Neue Lektion", "Bitte zuerst einen Inhalts-Tab wählen.")
            return
        tab = self.tabs[self.current_tab_index]
        title = simpledialog.askstring("Neue Lektion", "Titel der Lektion:", parent=self)
        if title:
            num = next_number(tab["id"], dirs_only=True)
            d = os.path.join(tab["id"], f"{num:02d}_{sanitize(title)}")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "_meta.txt"), "w", encoding="utf-8") as f:
                f.write(title + "\n")
            self.load_data()
            self.render_tab(self.current_tab_index)

    def save_current_board(self):
        """Speichert das aktuelle Brett (FEN) als neue Übung im aktuellen Tab/Lektion."""
        if not self.tabs or self.current_tab_index == "figures":
            messagebox.showinfo("Speichern", "Bitte zuerst einen Inhalts-Tab wählen.")
            return
        title = self.name_var.get().strip()
        if not title:
            title = simpledialog.askstring("Board speichern", "Titel der Übung:", parent=self)
        if not title:
            return
        tab = self.tabs[self.current_tab_index]
        if self.selected_lesson and self.selected_lesson[0] == self.current_tab_index:
            target = tab["lessons"][self.selected_lesson[1]]["id"]
        else:
            target = tab["id"]
        num = next_number(target)
        fname = f"{num:04d}_{sanitize(title)}.fen"
        with open(os.path.join(target, fname), "w", encoding="utf-8") as f:
            f.write(title + "\n" + self.board.fen() + "\n")
        self.load_data()
        self.render_tab(self.current_tab_index)

    # -- Status / Content ---------------------------------------------------
    def update_status(self):
        if self.board_hidden:
            self.status_lbl.config(text="Brett verdeckt — Züge/Aufbau weiter möglich")
            return
        if self.edit_mode:
            self.status_lbl.config(text="Bearbeiten-Modus — freies Spiel")
            return
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
    def defense_counts(self, s):
        b = self.board
        turn = b.turn
        attackers = sum(1 for a in b.attackers(turn, s)
                        if b.piece_at(a) is not None and b.piece_at(a).piece_type != chess.KING)
        defenders = sum(1 for d in b.attackers(not turn, s)
                        if b.piece_at(d) is not None and b.piece_at(d).piece_type != chess.KING)
        return attackers, defenders

    def toggle_analyse(self):
        self.analyse_on = self.analyse_var.get()
        if self.analyse_on:
            if self.edit_mode:
                self.analyse_var.set(False)
                self.analyse_on = False
                self.status_lbl.config(text="Analyse im Bearbeiten-Modus nicht möglich.")
                return
            if self._analyse_thread is None or not self._analyse_thread.is_alive():
                self._analyse_thread = threading.Thread(target=self._analyse_loop, daemon=True)
                self._analyse_thread.start()
                self.after(100, self._poll_results)
        else:
            self.best_moves = []
            self.best_scores = []
            self.board_canvas.redraw()
            self.update_status()

    def _analyse_loop(self):
        last_fen = None
        while self.analyse_on:
            fen = self.board.fen()
            if fen != last_fen:
                last_fen = fen
                try:
                    with self._engine_lock:
                        if self.engine is None:
                            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
                        board = chess.Board(fen)
                        if self.engine_multi > 1:
                            infos = self.engine.analyse(board, chess.engine.Limit(time=self.engine_time),
                                                        multipv=self.engine_multi)
                        else:
                            infos = [self.engine.analyse(board, chess.engine.Limit(time=self.engine_time))]
                    results = []
                    for info in infos:
                        pv = info.get("pv", [])
                        if pv:
                            results.append((pv[0], info.get("score")))
                    self._result_queue.put(("ok", (results, fen)))
                except Exception as e:
                    self._result_queue.put(("error", str(e)))
            time.sleep(0.2)

    def _poll_results(self):
        if not self.analyse_on:
            return
        try:
            while True:
                kind, payload = self._result_queue.get_nowait()
                if kind == "ok":
                    results, fen = payload
                    self._apply_analysis(results, fen)
                else:
                    self._analysis_error(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_results)

    def _apply_analysis(self, results, fen):
        if fen != self.board.fen():
            return
        self.best_moves = [m for m, s in results]
        self.best_scores = [s for m, s in results]
        parts = []
        for i, (m, s) in enumerate(results):
            txt = f"{i + 1}. {san_de(self.board, m)}"
            if s is not None:
                pov = s.pov(chess.WHITE)
                if pov.is_mate():
                    ev = f"M{abs(pov.mate())}" if pov.mate() > 0 else f"−M{abs(pov.mate())}"
                else:
                    ev = f"{pov.score() / 100:+.2f}"
                txt += f" ({ev})"
            parts.append(txt)
        if parts:
            self.status_lbl.config(text="  ·  ".join(parts))
        self.board_canvas.redraw()

    def _analysis_error(self, msg):
        self.status_lbl.config(text=f"Analyse nicht möglich: {msg[:60]}")

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Einstellungen")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Engine-Denkzeit (Sekunden):").grid(row=0, column=0, sticky="w", pady=4)
        time_var = tk.StringVar(value=str(self.engine_time))
        ttk.Spinbox(frm, from_=0.2, to=10.0, increment=0.1, textvariable=time_var, width=8).grid(row=0, column=1, padx=8)
        ttk.Label(frm, text="Anzahl Zugvorschläge (1–5):").grid(row=1, column=0, sticky="w", pady=4)
        multi_var = tk.StringVar(value=str(self.engine_multi))
        ttk.Spinbox(frm, from_=1, to=5, increment=1, textvariable=multi_var, width=8).grid(row=1, column=1, padx=8)
        legal_var = tk.BooleanVar(value=self.show_legal_moves)
        ttk.Checkbutton(frm, text="Mögliche Züge anzeigen", variable=legal_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=6)

        def save():
            try:
                t = float(time_var.get().replace(",", "."))
                m = int(float(multi_var.get()))
            except Exception:
                messagebox.showerror("Einstellungen", "Bitte gültige Zahlen eingeben.", parent=win)
                return
            self.engine_time = max(0.1, t)
            self.engine_multi = max(1, min(5, m))
            self.show_legal_moves = legal_var.get()
            self.save_config()
            win.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btns, text="Speichern", command=save).pack(side="left", padx=4)
        ttk.Button(btns, text="Abbrechen", command=win.destroy).pack(side="left", padx=4)
        usb_row = ttk.Frame(frm)
        usb_row.grid(row=4, column=0, columnspan=2, pady=(0, 4))
        ttk.Button(usb_row, text="🔄 Lektionen per USB aktualisieren",
                   command=lambda: (win.destroy(), self.open_usb_sync())).pack()

    def show_help(self, event=None):
        win = tk.Toplevel(self)
        win.title("ChessTeach — Hilfe")
        win.transient(self)
        sh = self.winfo_screenheight()
        sw = self.winfo_screenwidth()
        win.geometry(f"820x{max(600, sh - 60)}+{(sw - 820)//2}+20")
        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        txt = tk.Text(body, wrap="word", font=("DejaVu Sans", 11), padx=10, pady=6)
        scroll = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        ttk.Button(win, text="Schließen", command=win.destroy).pack(pady=6)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<F1>", lambda e: win.destroy())
        win.focus_set()

    def _rebuild_tabs(self):
        for frame in self.content_tab_frames:
            self.notebook.forget(frame)
            frame.destroy()
        self.content_tab_frames = []
        self.tab_canvases = {}
        self.tab_hits = {}
        self.tab_del_hits = {}
        self.expanded = {}
        self.selected_lesson = None
        self.current_node = None
        for i, tab in enumerate(self.tabs):
            frame = ttk.Frame(self.notebook)
            self.notebook.insert(i, frame, text=tab["title"])
            self.content_tab_frames.append(frame)
            self.tab_canvases[i] = self._make_list_canvas(frame, i)
            self.expanded[i] = set()
            self.render_tab(i)
        self.figures_index = len(self.tabs)
        cur = self.current_tab_index
        if not self.tabs:
            cur = "figures"
        elif isinstance(cur, int) and cur >= len(self.tabs):
            cur = 0
        self.current_tab_index = cur
        if cur == "figures":
            self.notebook.select(self.figures_index)
        else:
            self.notebook.select(cur)
            self.render_tab(cur)

    def open_usb_sync(self):
        roots = find_usb_roots()
        win = tk.Toplevel(self)
        win.title("Lektionen per USB aktualisieren")
        win.transient(self)
        win.grab_set()
        win.geometry("680x400")
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="USB-Stick einstecken, dann Lektionen übertragen.",
                  font=("DejaVu Sans", 11)).pack(anchor="w")
        ttk.Label(frm, text="USB-Laufwerk:").pack(anchor="w", pady=(12, 0))
        self.usb_var = tk.StringVar()
        combo = ttk.Combobox(frm, textvariable=self.usb_var, values=roots, state="readonly", width=64)
        combo.pack(anchor="w", fill="x", pady=4)
        if roots:
            combo.current(0)
        self.usb_status = tk.Label(frm, text="", fg="#555555")
        self.usb_status.pack(anchor="w", pady=4)

        def update_status(*_a):
            root = self.usb_var.get()
            if not root:
                self.usb_status.config(text="Kein USB-Laufwerk gefunden.")
                return
            ldir = os.path.join(root, "lektionen")
            if os.path.isdir(ldir):
                n = sum(len(fs) for _, _, fs in os.walk(ldir))
                self.usb_status.config(text=f"OK — „lektionen“-Ordner gefunden ({n} Dateien).")
            else:
                self.usb_status.config(text="Noch kein „lektionen“-Ordner auf dem USB.")
        self.usb_var.trace_add("write", update_status)
        update_status()

        def refresh():
            r = find_usb_roots()
            combo["values"] = r
            if r:
                combo.current(0)
            update_status()

        def do_import():
            root = self.usb_var.get()
            if not root:
                messagebox.showerror("USB", "Kein USB-Laufwerk gefunden.", parent=win)
                return
            src = os.path.join(root, "lektionen")
            if not os.path.isdir(src):
                messagebox.showerror("USB", "Kein „lektionen“-Ordner auf dem USB gefunden.", parent=win)
                return
            if messagebox.askyesno("Importieren", "Lektionen vom USB auf dieses Gerät kopieren?", parent=win):
                try:
                    merge_dir(src, DATA_DIR)
                except Exception as e:
                    messagebox.showerror("Fehler", str(e), parent=win)
                    return
                self.load_data()
                self._rebuild_tabs()
                self.update_status()
                messagebox.showinfo("Fertig", "Lektionen wurden importiert.", parent=win)
                win.destroy()

        def do_export():
            root = self.usb_var.get()
            if not root:
                messagebox.showerror("USB", "Kein USB-Laufwerk gefunden.", parent=win)
                return
            dst = os.path.join(root, "lektionen")
            os.makedirs(dst, exist_ok=True)
            if messagebox.askyesno("Exportieren", "Alle Lektionen dieses Geräts auf den USB kopieren?", parent=win):
                try:
                    merge_dir(DATA_DIR, dst)
                except Exception as e:
                    messagebox.showerror("Fehler", str(e), parent=win)
                    return
                messagebox.showinfo("Fertig", "Lektionen wurden auf den USB kopiert.", parent=win)

        btns = ttk.Frame(frm)
        btns.pack(pady=14)
        ttk.Button(btns, text="Vom USB importieren", command=do_import).pack(side="left", padx=4)
        ttk.Button(btns, text="Auf USB exportieren", command=do_export).pack(side="left", padx=4)
        ttk.Button(btns, text="Aktualisieren", command=refresh).pack(side="left", padx=4)
        ttk.Button(btns, text="Schließen", command=win.destroy).pack(side="left", padx=4)
        win.bind("<Escape>", lambda e: win.destroy())

    # -- Vollbild & Konfig --------------------------------------------------
    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not self.attributes("-fullscreen"))
        self.after(250, self._relayout)

    def _relayout(self):
        try:
            self.update_idletasks()
            w = self.paned.winfo_width()
            if w > 100:
                self.paned.sashpos(0, int(w * 0.6))
        except Exception:
            pass

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
        self.engine_time = float(cfg.get("engine_time", 1.5))
        self.engine_multi = int(cfg.get("engine_multi", 1))
        self.mark_colors = cfg.get("mark_colors", ["#ffd54f", "#f44336", "#2196f3", "#4caf50", "#9c27b0"])
        self.mark_color_index = int(cfg.get("mark_color_index", 0)) % max(1, len(self.mark_colors))
        self.show_legal_moves = bool(cfg.get("show_legal_moves", True))
        if cfg.get("last_fen"):
            try:
                self.board = chess.Board(cfg["last_fen"])
                self.loaded_fen = cfg["last_fen"]
                self.selected = None
                self.last_move = None
                self.arrows = []
                self.marks = {}
                self.best_moves = []
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
            "engine_time": self.engine_time,
            "engine_multi": self.engine_multi,
            "mark_colors": self.mark_colors,
            "mark_color_index": self.mark_color_index,
            "show_legal_moves": self.show_legal_moves,
            "last_fen": self.loaded_fen,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def on_close(self):
        self._closing = True
        self.analyse_on = False
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
