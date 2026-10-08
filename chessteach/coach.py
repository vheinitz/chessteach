#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoachMode — eigenständige Schach-Coach-App
==========================================
Der Mensch spielt gegen Stockfish. Die Engine wählt zufällig aus den besten
Zügen (Bewertungs-basiert, mit einstellbaren Regeln). Nach schlechten Zügen
oder verpassten Chancen zeigt der Coach die Folgen animiert und stellt die
Stellung anschließend zurück.

Bedienung:
  - Figur anklicken, dann Zielfeld anklicken
  - Menü „Spiel“: Neue Partie, Brett drehen, Rückgängig, Beenden
  - Rechter Tab „Einstellungen“: alle Coach-Parameter
"""

import os
import math
import random
import re
import json
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

import chess
import chess.engine
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Pfade & Konstanten
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PIECES_DIR = os.path.join(APP_DIR, "pieces")
CONFIG_DIR = os.path.expanduser("~/.config/coachmode")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STOCKFISH = "/usr/games/stockfish"

LIGHT = "#f0d9b5"
DARK = "#b58863"
SELECT_COLOR = "#ffeb3b"
LEGAL_COLOR = "#2e7d32"
CAPTURE_COLOR = "#c62828"
THREAT_COLOR = "#e53935"
CHECK_COLOR = "#d32f2f"
ARROW_COLOR = "#1e88e5"
LAST_COLOR = "#f9a825"
HIGHLIGHT_COLOR = "#4fc3f7"


def square_color(s):
    return DARK if (s % 8 + s // 8) % 2 == 0 else LIGHT


def san_de(board, move):
    return board.san(move).replace("N", "S").replace("B", "L").replace("Q", "D").replace("R", "T")


def parse_opening_moves(text):
    """SAN- oder UCI-Züge (deutsche Figurenbuchstaben erlaubt) -> Zugliste ab Start."""
    if not text:
        return []
    board = chess.Board()
    moves = []
    for token in re.split(r"[\s]+|\d+\.{1,3}", text):
        token = token.strip()
        if not token:
            continue
        m = None
        try:
            m = board.parse_san(token)
        except Exception:
            try:
                en = token
                de_map = {"S": "N", "L": "B", "D": "Q", "T": "R"}
                if en and en[0] in de_map:
                    en = de_map[en[0]] + en[1:]
                if len(en) >= 2 and en[-1] in de_map:
                    en = en[:-1] + de_map[en[-1]]
                m = board.parse_san(en)
            except Exception:
                try:
                    m = board.parse_uci(token)
                except Exception:
                    continue
        if m in board.legal_moves:
            board.push(m)
            moves.append(m)
    return moves


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


# ---------------------------------------------------------------------------
# Brett
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
        if sq is not None:
            self.app.board_click(sq)

    def redraw(self):
        self.delete("all")
        board = self.app.display_board()
        sq = self.sq

        for s in range(64):
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=square_color(s), width=0)

        if self.app.last_move:
            for s in [self.app.last_move.from_square, self.app.last_move.to_square]:
                x0, y0 = self.sq_origin(s)
                self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=LAST_COLOR, width=0, stipple="gray50")

        for s, color in self.app.marks.items():
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=color, width=0, stipple="gray50")
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=color, width=3)

        for s in self.app.highlights:
            x0, y0 = self.sq_origin(s)
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, fill=HIGHLIGHT_COLOR, width=0, stipple="gray50")
            self.create_rectangle(x0, y0, x0 + sq, y0 + sq, outline=HIGHLIGHT_COLOR, width=3)

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
                        m = sq * 0.14
                        self.create_oval(tx - sq / 2 + m, ty - sq / 2 + m,
                                         tx + sq / 2 - m, ty + sq / 2 - m,
                                         outline=CAPTURE_COLOR, width=5)
                    else:
                        rr = max(4, sq // 6)
                        self.create_oval(tx - rr, ty - rr, tx + rr, ty + rr, fill=LEGAL_COLOR)

        if self.app.show_coords:
            self.draw_coords()

        for s, piece in board.piece_map().items():
            x0, y0 = self.sq_origin(s)
            img = PIECES.get(piece.symbol(), sq)
            if img is not None:
                self.create_image(x0, y0, image=img, anchor="nw")

        for a, b in self.app.arrows:
            self.draw_arrow(a, b, ARROW_COLOR)

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

    def draw_arrow(self, a, b, color, width=5):
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
# Coach-App
# ---------------------------------------------------------------------------
class CoachApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CoachMode — Schach-Coach")
        self.configure(bg="#eceff1")

        # Spielzustand
        self.board = chess.Board()
        self.coach_start_board = self.board.copy()
        self.anim_board = None
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self.flipped = False
        self.show_coords = True

        # Coach-Zustand
        self.coach_player_color = chess.WHITE
        self.coach_pending = False
        self.coach_reviewing = False
        self.coach_animating = False
        self.coach_waiting_analysis = False
        self.coach_after_id = None
        self.coach_anim_plies = []
        self.coach_anim_sans = []
        self.coach_anim_captures = []
        self.coach_anim_idx = 0
        self.coach_anim_label = ""
        self.coach_undo_after_anim = False
        self.coach_latest_fen = None
        self.coach_latest_results = []
        self.coach_pre_fen = None
        self.coach_pre_results = []
        self.coach_last_human_move = None
        self.coach_analyzing_fen = None
        self._coach_queue = queue.Queue()
        self._coach_thread = None
        self._coach_polling = False
        self._engine_lock = threading.Lock()
        self._closing = False
        self.engine = None

        # Eval-Balken
        self.eval_fraction = None
        self.eval_text = "?"

        # Konfiguration (Standardwerte)
        self.coach_think_time = 2.0
        self.coach_num_moves = 5
        self.coach_weights = [1.0, 1.0, 1.0, 1.0, 1.0]
        self.coach_pawn_factor = 1.5
        self.coach_escape_factor = 2.0
        self.coach_opening_factor = 2.0
        self.coach_feedback_time = 2.0
        self.coach_anim_sec = 1.0
        self.coach_final_pause = 3.0
        self.coach_opening = ""
        self.coach_bad_threshold = 200.0
        self.coach_tactic_threshold = 250.0

        self.load_config()
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.after(200, self._relayout)
        self.start_game()

    # -- UI -----------------------------------------------------------------
    def build_ui(self):
        self.menubar = tk.Menu(self)
        game_menu = tk.Menu(self.menubar, tearoff=0)
        game_menu.add_command(label="Neue Partie", command=self.new_game)
        game_menu.add_command(label="Rückgängig", command=self.undo)
        game_menu.add_command(label="Brett drehen", command=self.toggle_flip)
        game_menu.add_separator()
        game_menu.add_command(label="Beenden", command=self.on_close)
        self.menubar.add_cascade(label="Spiel", menu=game_menu)

        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="Kurzanleitung", command=self.show_help)
        self.menubar.add_cascade(label="Hilfe", menu=help_menu)
        self.config(menu=self.menubar)

        bar = ttk.Frame(self, padding=4)
        bar.pack(side="top", fill="x")
        ttk.Button(bar, text="Neue Partie", command=self.new_game).pack(side="left", padx=2)
        ttk.Button(bar, text="↩", width=4, command=self.undo).pack(side="left", padx=2)
        ttk.Button(bar, text="Brett drehen", command=self.toggle_flip).pack(side="left", padx=2)
        self.status_lbl = tk.Label(bar, text="", font=("DejaVu Sans", 13, "bold"),
                                   fg="#1a237e", anchor="w")
        self.status_lbl.pack(side="left", padx=10, fill="x", expand=True)

        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True, padx=4, pady=4)
        paned = self.paned

        board_frame = ttk.Frame(paned)
        paned.add(board_frame, weight=3)
        self.board_canvas = BoardCanvas(board_frame, self)
        self.board_canvas.pack(side="left", fill="both", expand=True)
        self.eval_canvas = tk.Canvas(board_frame, width=40, highlightthickness=0, bg="#f2ede2")
        self.eval_canvas.pack(side="right", fill="y", padx=(2, 0))
        self.eval_canvas.bind("<Configure>", lambda e: self.draw_eval_bar())

        side = ttk.Frame(paned)
        paned.add(side, weight=2)
        self.notebook = ttk.Notebook(side)
        self.notebook.pack(fill="both", expand=True)

        # Tab Züge
        moves_tab = ttk.Frame(self.notebook)
        self.notebook.add(moves_tab, text="Züge")
        self.move_list = tk.Listbox(moves_tab, font=("DejaVu Sans Mono", 12), exportselection=False)
        self.move_list.pack(fill="both", expand=True, padx=2, pady=2)
        self.move_list.bind("<<ListboxSelect>>", self.on_move_list_select)

        # Tab Einstellungen
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="Einstellungen")
        self.build_settings_tab()

    def build_settings_tab(self):
        frm = ttk.Frame(self.settings_tab, padding=10)
        frm.pack(fill="both", expand=True)
        canvas = tk.Canvas(frm, highlightthickness=0)
        scroll = ttk.Scrollbar(frm, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def row(r, label, var, widget):
            ttk.Label(inner, text=label).grid(row=r, column=0, sticky="w", pady=3)
            widget.grid(row=r, column=1, padx=8, pady=3, sticky="ew")

        self.set_t_var = tk.StringVar(value=str(self.coach_think_time))
        row(0, "Engine-Denkzeit (Sek.):", self.set_t_var,
            ttk.Spinbox(inner, from_=0.2, to=30.0, increment=0.5, textvariable=self.set_t_var, width=8))
        self.set_n_var = tk.StringVar(value=str(self.coach_num_moves))
        row(1, "Anzahl bester Züge (1–10):", self.set_n_var,
            ttk.Spinbox(inner, from_=1, to=10, increment=1, textvariable=self.set_n_var, width=8))
        self.set_w_var = tk.StringVar(value=",".join(str(int(w)) if float(w).is_integer() else str(w)
                                                     for w in self.coach_weights))
        row(2, "Zug-Gewichte (bester zuerst):", self.set_w_var,
            ttk.Entry(inner, textvariable=self.set_w_var, width=20))
        ttk.Label(inner, text="Basis ist die Bewertung. 1,1,1,1,1 = neutral.",
                  foreground="#666666").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.set_p_var = tk.StringVar(value=str(self.coach_pawn_factor))
        row(4, "Bauernzug-Faktor:", self.set_p_var,
            ttk.Spinbox(inner, from_=0.0, to=20.0, increment=0.5, textvariable=self.set_p_var, width=8))
        self.set_e_var = tk.StringVar(value=str(self.coach_escape_factor))
        row(5, "Flucht-Faktor (Schach):", self.set_e_var,
            ttk.Spinbox(inner, from_=0.0, to=20.0, increment=0.5, textvariable=self.set_e_var, width=8))
        self.set_o_var = tk.StringVar(value=str(self.coach_opening_factor))
        row(6, "Opening-Präferenz-Faktor:", self.set_o_var,
            ttk.Spinbox(inner, from_=0.0, to=20.0, increment=0.5, textvariable=self.set_o_var, width=8))
        self.set_f_var = tk.StringVar(value=str(self.coach_feedback_time))
        row(7, "Analyse-Zeit Feedback (Sek.):", self.set_f_var,
            ttk.Spinbox(inner, from_=0.2, to=30.0, increment=0.5, textvariable=self.set_f_var, width=8))
        self.set_a_var = tk.StringVar(value=str(self.coach_anim_sec))
        row(8, "Animation pro Halbzug (Sek.):", self.set_a_var,
            ttk.Spinbox(inner, from_=0.2, to=5.0, increment=0.1, textvariable=self.set_a_var, width=8))
        self.set_s_var = tk.StringVar(value=str(self.coach_final_pause))
        row(9, "Pause Endkonsequenz (Sek.):", self.set_s_var,
            ttk.Spinbox(inner, from_=0.5, to=10.0, increment=0.5, textvariable=self.set_s_var, width=8))
        self.set_b_var = tk.StringVar(value=str(self.coach_bad_threshold))
        row(10, "Schwelle schlechter Zug (cp):", self.set_b_var,
            ttk.Spinbox(inner, from_=50, to=1000, increment=25, textvariable=self.set_b_var, width=8))
        self.set_c_var = tk.StringVar(value=str(self.coach_tactic_threshold))
        row(11, "Schwelle Taktik/Gewinn (cp):", self.set_c_var,
            ttk.Spinbox(inner, from_=100, to=1000, increment=25, textvariable=self.set_c_var, width=8))
        self.set_op_var = tk.StringVar(value=self.coach_opening)
        ttk.Label(inner, text="Bevorzugtes Opening (SAN-Züge, z. B. e4 e5 Sf3 Sc6 Lb5):").grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Entry(inner, textvariable=self.set_op_var, width=50).grid(
            row=13, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(inner, text="Nur eine weiche Präferenz — der Engine-Zug wird nicht erzwungen.",
                  foreground="#666666").grid(row=14, column=0, columnspan=2, sticky="w")

        btns = ttk.Frame(inner)
        btns.grid(row=15, column=0, columnspan=2, pady=10)
        ttk.Button(btns, text="Speichern", command=self.save_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="Zurücksetzen", command=self.reset_settings).pack(side="left", padx=4)

    def save_settings(self):
        try:
            self.coach_think_time = max(0.1, float(self.set_t_var.get().replace(",", ".")))
            self.coach_num_moves = max(1, min(10, int(float(self.set_n_var.get()))))
            weights = []
            for part in self.set_w_var.get().split(","):
                part = part.strip()
                if part:
                    weights.append(max(0.0, float(part.replace(",", "."))))
            if not weights:
                weights = [1.0]
            self.coach_weights = weights
            self.coach_pawn_factor = max(0.0, float(self.set_p_var.get().replace(",", ".")))
            self.coach_escape_factor = max(0.0, float(self.set_e_var.get().replace(",", ".")))
            self.coach_opening_factor = max(0.0, float(self.set_o_var.get().replace(",", ".")))
            self.coach_feedback_time = max(0.1, float(self.set_f_var.get().replace(",", ".")))
            self.coach_anim_sec = max(0.1, float(self.set_a_var.get().replace(",", ".")))
            self.coach_final_pause = max(0.1, float(self.set_s_var.get().replace(",", ".")))
            self.coach_bad_threshold = max(0.0, float(self.set_b_var.get().replace(",", ".")))
            self.coach_tactic_threshold = max(0.0, float(self.set_c_var.get().replace(",", ".")))
            self.coach_opening = self.set_op_var.get().strip()
        except Exception:
            messagebox.showerror("Einstellungen", "Bitte gültige Zahlen eingeben.", parent=self)
            return
        self.save_config()
        self.status_lbl.config(text="Einstellungen gespeichert.")

    def reset_settings(self):
        self.coach_think_time = 2.0
        self.coach_num_moves = 5
        self.coach_weights = [1.0, 1.0, 1.0, 1.0, 1.0]
        self.coach_pawn_factor = 1.5
        self.coach_escape_factor = 2.0
        self.coach_opening_factor = 2.0
        self.coach_feedback_time = 2.0
        self.coach_anim_sec = 1.0
        self.coach_final_pause = 3.0
        self.coach_opening = ""
        self.coach_bad_threshold = 200.0
        self.coach_tactic_threshold = 250.0
        self.set_t_var.set(str(self.coach_think_time))
        self.set_n_var.set(str(self.coach_num_moves))
        self.set_w_var.set(",".join(str(int(w)) if float(w).is_integer() else str(w) for w in self.coach_weights))
        self.set_p_var.set(str(self.coach_pawn_factor))
        self.set_e_var.set(str(self.coach_escape_factor))
        self.set_o_var.set(str(self.coach_opening_factor))
        self.set_f_var.set(str(self.coach_feedback_time))
        self.set_a_var.set(str(self.coach_anim_sec))
        self.set_s_var.set(str(self.coach_final_pause))
        self.set_b_var.set(str(self.coach_bad_threshold))
        self.set_c_var.set(str(self.coach_tactic_threshold))
        self.set_op_var.set(self.coach_opening)
        self.save_config()

    # -- Spielzustand -------------------------------------------------------
    def display_board(self):
        if self.coach_animating and self.anim_board is not None:
            return self.anim_board
        return self.board

    def start_game(self):
        self._coach_cancel_auto()
        self.board = chess.Board()
        self.coach_start_board = self.board.copy()
        self.anim_board = None
        self.selected = None
        self.last_move = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self.coach_player_color = chess.WHITE if not self.flipped else chess.BLACK
        self.coach_pending = False
        self.coach_reviewing = False
        self.coach_animating = False
        self.coach_waiting_analysis = False
        self.coach_anim_plies = []
        self.coach_latest_fen = None
        self.coach_latest_results = []
        self.coach_pre_fen = None
        self.coach_pre_results = []
        self.coach_analyzing_fen = None
        self._reset_eval()
        self._sync_move_list()
        self.board_canvas.redraw()
        if self._coach_thread is None or not self._coach_thread.is_alive():
            self._coach_thread = threading.Thread(target=self._coach_analyse_loop, daemon=True)
            self._coach_thread.start()
        if not self._coach_polling:
            self._coach_polling = True
            self.after(100, self._coach_poll)
        self._coach_schedule_turn()
        self.update_status()

    def new_game(self):
        self.start_game()

    def toggle_flip(self):
        self.flipped = not self.flipped
        self.start_game()

    def undo(self):
        if self.coach_pending or self.coach_reviewing or self.coach_animating:
            return
        if self.board.turn != self.coach_player_color:
            return
        if len(self.board.move_stack) < 2:
            return
        self._coach_goto(len(self.board.move_stack) - 2)

    def board_click(self, sq):
        if (self.coach_pending or self.coach_reviewing or self.coach_animating):
            return
        board = self.board
        if board.turn != self.coach_player_color:
            return
        if (self.coach_waiting_analysis or self.coach_latest_fen != board.fen()
                or not self.coach_latest_results):
            self.status_lbl.config(text="Coach analysiert…")
            if self.coach_latest_fen != board.fen():
                self.coach_analyzing_fen = None
            return
        piece = board.piece_at(sq)
        if self.selected is not None:
            if sq == self.selected:
                self.selected = None
                self.board_canvas.redraw()
                return
            try:
                move = board.find_move(self.selected, sq)
            except ValueError:
                if piece is not None and piece.color == self.coach_player_color:
                    self.selected = sq
                else:
                    self.selected = None
                self.board_canvas.redraw()
                return
            self.selected = None
            self._coach_apply_human_move(move)
            return
        if piece is not None and piece.color == self.coach_player_color:
            self.selected = sq
        else:
            self.selected = None
        self.board_canvas.redraw()

    def _coach_apply_human_move(self, move):
        self.coach_pre_fen = self.board.fen()
        self.coach_pre_results = list(self.coach_latest_results)
        self.coach_last_human_move = move
        self.board.push(move)
        self.last_move = move
        self._sync_move_list()
        self.board_canvas.redraw()
        self.update_status()
        if self.board.is_game_over():
            self.coach_pending = False
            self.update_status()
            return
        self.coach_pending = True
        self.coach_reviewing = True
        self.status_lbl.config(text="Coach analysiert Deinen Zug…")

    # -- Engine -------------------------------------------------------------
    def _coach_analyse_loop(self):
        while not self._closing:
            if self.coach_animating:
                time.sleep(0.1)
                continue
            fen = self.board.fen()
            if fen != self.coach_analyzing_fen:
                self.coach_analyzing_fen = fen
                try:
                    board = chess.Board(fen)
                    if board.is_game_over():
                        self._coach_queue.put(("analysis", ([], fen)))
                        continue
                    human_turn = board.turn == self.coach_player_color
                    t = self.coach_feedback_time if human_turn else self.coach_think_time
                    n = max(1, min(10, self.coach_num_moves))
                    with self._engine_lock:
                        if self.engine is None:
                            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
                        if n > 1:
                            infos = self.engine.analyse(board, chess.engine.Limit(time=t), multipv=n)
                        else:
                            infos = [self.engine.analyse(board, chess.engine.Limit(time=t))]
                    results = []
                    for info in infos:
                        pv = info.get("pv", [])
                        if pv:
                            results.append({"move": pv[0], "score": info.get("score"), "pv": pv})
                    self._coach_queue.put(("analysis", (results, fen)))
                except Exception as e:
                    self._coach_queue.put(("error", str(e)))
                    try:
                        if self.engine is not None:
                            self.engine.quit()
                    except Exception:
                        pass
                    self.engine = None
                    self.coach_analyzing_fen = None
            time.sleep(0.15)

    def _coach_poll(self):
        if self._closing:
            self._coach_polling = False
            return
        try:
            while True:
                kind, payload = self._coach_queue.get_nowait()
                if kind == "analysis":
                    results, fen = payload
                    self._coach_apply_analysis(results, fen)
                else:
                    self.status_lbl.config(text=f"Engine-Fehler: {payload[:60]}")
        except queue.Empty:
            pass
        self.after(100, self._coach_poll)

    def _coach_apply_analysis(self, results, fen):
        if self.coach_animating:
            return
        if fen != self.board.fen():
            return
        self.coach_latest_fen = fen
        self.coach_latest_results = results
        if results:
            self._update_eval(results[0]["score"])
        else:
            self._reset_eval()
        if self.coach_reviewing:
            self._coach_finish_review(fen, results)
            return
        if self.board.is_game_over():
            self.coach_pending = False
            self.coach_waiting_analysis = False
            self.update_status()
            return
        if self.board.turn != self.coach_player_color and self.coach_pending:
            self._coach_apply_engine_move_from(results)
            return
        if self.board.turn == self.coach_player_color and self.coach_waiting_analysis:
            if results:
                self.coach_waiting_analysis = False
            else:
                self.coach_analyzing_fen = None
            self.update_status()

    def _coach_schedule_turn(self):
        if self.coach_pending or self.coach_reviewing or self.coach_animating:
            return
        self._coach_cancel_auto()
        board = self.board
        if board.is_game_over():
            self.coach_pending = False
            self.update_status()
            return
        if board.turn == self.coach_player_color:
            self.coach_pending = False
            if self.coach_latest_fen == board.fen() and self.coach_latest_results:
                self.coach_waiting_analysis = False
            else:
                self.coach_waiting_analysis = True
            self.update_status()
            return
        self.coach_pending = True
        self.update_status()

    def _coach_finish_review(self, fen, results):
        if not self.coach_reviewing:
            return
        self.coach_reviewing = False
        human = self.coach_player_color
        pre_results = self.coach_pre_results
        pre_score = pre_results[0]["score"] if pre_results else None
        post_score = results[0]["score"] if results else None
        pre_cp = self._coach_score_cp(pre_score, human)
        post_cp = self._coach_score_cp(post_score, human)
        pre_mate = self._coach_mate_in(pre_score, human)
        post_mate = self._coach_mate_in(post_score, human)
        pre_pv = pre_results[0].get("pv", []) if pre_results else []
        post_pv = results[0].get("pv", []) if results else []

        # 1) Mensch hatte forciertes Matt in 1-3 Zügen und hat es nicht gespielt
        if pre_mate is not None and 1 <= pre_mate <= 3:
            expected = pre_pv[0] if pre_pv else None
            played_mate_move = (expected is not None and self.coach_last_human_move == expected)
            if not played_mate_move:
                n = pre_mate
                label = (f"Verpasste Chance: Matt in {n} Zug möglich!" if n == 1
                         else f"Verpasste Chance: Matt in {n} Zügen möglich!")
                pre_board = chess.Board(self.coach_pre_fen)
                self.coach_undo_after_anim = True
                self._coach_start_animation(pre_board, pre_pv, label)
                return

        # 2) Mensch erlaubt dem Gegner ein forciertes Matt in 1-3 Zügen
        if post_mate is not None and -3 <= post_mate < 0:
            n = abs(post_mate)
            label = (f"Schlechter Zug: Matt in {n} Zug droht!" if n == 1
                     else f"Schlechter Zug: Matt in {n} Zügen droht!")
            post_board = chess.Board(fen)
            self.coach_undo_after_anim = True
            self._coach_start_animation(post_board, post_pv, label)
            return

        # 3) Großer Material-/Positionsgewinn verpasst
        if pre_cp >= self.coach_tactic_threshold and post_cp < pre_cp - 100:
            pre_board = chess.Board(self.coach_pre_fen)
            self.coach_undo_after_anim = True
            self._coach_start_animation(pre_board, pre_pv,
                                        "Verpasste Chance! Gewinnstellung (beste Fortsetzung).")
            return

        # 4) Normaler schlechter Zug
        if post_cp < pre_cp - self.coach_bad_threshold:
            post_board = chess.Board(fen)
            self.coach_undo_after_anim = True
            self._coach_start_animation(post_board, post_pv, "Schlechter Zug! So wird er bestraft.")
            return

        self.coach_undo_after_anim = False
        self._coach_apply_engine_move_from(results)

    def _coach_score_cp(self, score, pov):
        if score is None:
            return 0.0
        try:
            p = score.pov(pov)
        except Exception:
            return 0.0
        if p.is_mate():
            return 100000.0 if p.mate() > 0 else -100000.0
        return float(p.score())

    def _coach_mate_in(self, score, pov):
        if score is None:
            return None
        try:
            p = score.pov(pov)
        except Exception:
            return None
        if p.is_mate():
            return p.mate()
        return None

    def _coach_apply_engine_move_from(self, results):
        board = self.board
        if board.is_game_over() or board.turn == self.coach_player_color:
            self.coach_pending = False
            self.update_status()
            return
        legal = list(board.legal_moves)
        if not legal:
            self.coach_pending = False
            self.update_status()
            return
        moves = [(r["move"], r["score"]) for r in results
                 if r.get("move") is not None and r.get("move") in board.legal_moves]
        if not moves:
            move = legal[0] if len(legal) == 1 else random.choice(legal)
        else:
            move = self._coach_pick_move(board, moves)
        self.board.push(move)
        self.last_move = move
        self._sync_move_list()
        self.board_canvas.redraw()
        self.coach_pending = False
        self.update_status()
        self._coach_schedule_turn()

    def _coach_pick_move(self, board, moves):
        side = board.turn
        cps = [self._coach_score_cp(s, side) for m, s in moves]
        best_cp = cps[0] if cps else 0.0
        weights = []
        total = 0.0
        in_check = board.is_check()
        pref = self._coach_opening_preference(board)
        nw = len(self.coach_weights)
        for i, (m, score) in enumerate(moves):
            diff = max(0.0, best_cp - cps[i])
            w = 1.0 / (1.0 + diff / 30.0)
            if nw:
                w *= float(self.coach_weights[min(i, nw - 1)])
            piece = board.piece_at(m.from_square)
            if piece is not None and piece.piece_type == chess.PAWN:
                w *= self.coach_pawn_factor
            if (in_check and piece is not None and piece.piece_type == chess.KING
                    and not board.is_capture(m)):
                w *= self.coach_escape_factor
            if pref is not None and m == pref:
                w *= self.coach_opening_factor
            w = max(0.0, w)
            weights.append(w)
            total += w
        if total <= 0:
            return moves[0][0]
        r = random.random() * total
        acc = 0.0
        for (m, s), w in zip(moves, weights):
            acc += w
            if r <= acc:
                return m
        return moves[-1][0]

    def _coach_opening_preference(self, board):
        if not self.coach_opening:
            return None
        book = parse_opening_moves(self.coach_opening)
        ply = board.ply()
        if ply < len(book):
            return book[ply]
        return None

    # -- Feedback-Animation -------------------------------------------------
    def _coach_build_animation_plies(self, start_board, pv, max_plies=7):
        b = start_board.copy()
        plies, sans, caps = [], [], []

        def material(board):
            v = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                 chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
            return sum(v[p.piece_type] * (1 if p.color == chess.WHITE else -1)
                       for p in board.piece_map().values())

        start_mat = material(b)
        best_loss = 0.0
        best_len = 0
        mate_len = 0
        for m in pv[:max_plies]:
            if m not in b.legal_moves:
                break
            sans.append(san_de(b, m))
            caps.append(b.is_capture(m))
            b.push(m)
            plies.append(m)
            loss = abs(material(b) - start_mat)
            if loss > best_loss:
                best_loss = loss
                best_len = len(plies)
            if b.is_checkmate():
                mate_len = len(plies)
                break
            if b.is_stalemate() or b.is_insufficient_material():
                break
        if mate_len:
            end = mate_len
        elif best_loss > 0:
            end = best_len
        else:
            end = len(plies)
        return plies[:end], sans[:end], caps[:end]

    def _coach_start_animation(self, start_board, plies, label):
        self._coach_cancel_auto()
        self.coach_animating = True
        self.coach_anim_plies, self.coach_anim_sans, self.coach_anim_captures = \
            self._coach_build_animation_plies(start_board, plies)
        self.coach_anim_idx = 0
        self.coach_anim_label = label
        self.anim_board = start_board.copy()
        self.last_move = None
        self.selected = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self._coach_anim_step()

    def _coach_anim_step(self):
        if self._closing:
            return
        if self.coach_anim_idx < len(self.coach_anim_plies):
            move = self.coach_anim_plies[self.coach_anim_idx]
            san = self.coach_anim_sans[self.coach_anim_idx]
            capture = self.coach_anim_captures[self.coach_anim_idx]
            self.coach_anim_idx += 1
            self.anim_board.push(move)
            self.last_move = move
            self._coach_mark_move(move, capture)
            self.board_canvas.redraw()
            b = self.anim_board
            if b.is_checkmate():
                self.status_lbl.config(text=f"{san} — Schachmatt!")
            elif b.is_check():
                self.status_lbl.config(text=f"{san} — Schach!")
            else:
                self.status_lbl.config(text=f"{san}")
            self.coach_after_id = self.after(int(self.coach_anim_sec * 1000), self._coach_anim_step)
        else:
            self._coach_final_marks()
            self.status_lbl.config(text=self.coach_anim_label)
            self.board_canvas.redraw()
            self.coach_after_id = self.after(int(self.coach_final_pause * 1000), self._coach_anim_done)

    def _coach_mark_move(self, move, capture):
        self.highlights = [move.from_square, move.to_square]
        self.arrows = [(move.from_square, move.to_square)]
        self.marks = {}
        if capture:
            self.marks[move.to_square] = THREAT_COLOR
        for s in self._coach_danger_squares(self.anim_board):
            self.marks[s] = THREAT_COLOR

    def _coach_danger_squares(self, board):
        danger = set()
        for sq, piece in board.piece_map().items():
            if piece.piece_type == chess.KING:
                continue
            atk = [a for a in board.attackers(not piece.color, sq)]
            deff = [d for d in board.attackers(piece.color, sq)]
            if atk and len(atk) > len(deff):
                danger.add(sq)
        return danger

    def _coach_final_marks(self):
        self.highlights = []
        self.arrows = []
        self.marks = {}
        if self.coach_anim_plies:
            last = self.coach_anim_plies[-1]
            self.highlights = [last.from_square, last.to_square]
            self.arrows = [(last.from_square, last.to_square)]
            if self.coach_anim_captures and self.coach_anim_captures[-1]:
                self.marks[last.to_square] = THREAT_COLOR
        for s in self._coach_danger_squares(self.anim_board):
            self.marks[s] = THREAT_COLOR

    def _coach_anim_done(self):
        self.coach_after_id = None
        self.anim_board = None
        self.coach_animating = False
        self.coach_anim_plies = []
        self.selected = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        if self.coach_undo_after_anim and self.board.move_stack:
            self.board.pop()
        self.last_move = self.board.peek() if self.board.move_stack else None
        self.coach_undo_after_anim = False
        self.coach_latest_fen = None
        self.coach_analyzing_fen = None
        self._sync_move_list()
        self.board_canvas.redraw()
        self.coach_pending = False
        self.coach_reviewing = False
        self.update_status()
        self._coach_schedule_turn()

    def _coach_cancel_auto(self):
        if self.coach_after_id is not None:
            try:
                self.after_cancel(self.coach_after_id)
            except Exception:
                pass
            self.coach_after_id = None

    # -- Navigation / Anzeige ----------------------------------------------
    def _sync_move_list(self):
        self.move_list.delete(0, "end")
        b = self.coach_start_board.copy()
        moves = self.board.move_stack
        for i, m in enumerate(moves):
            prefix = f"{i // 2 + 1}." if i % 2 == 0 else f"{i // 2 + 1}..."
            try:
                san = san_de(b, m)
            except Exception:
                san = b.uci(m)
            self.move_list.insert("end", f"{prefix} {san}")
            b.push(m)
        self.move_list.selection_clear(0, "end")
        if moves:
            self.move_list.selection_set(len(moves) - 1)
            self.move_list.see(len(moves) - 1)

    def _coach_goto(self, i):
        self._coach_cancel_auto()
        moves = list(self.board.move_stack)
        i = max(0, min(len(moves), i))
        self.board = self.coach_start_board.copy()
        for m in moves[:i]:
            self.board.push(m)
        self.last_move = self.board.peek() if self.board.move_stack else None
        self.selected = None
        self.arrows = []
        self.marks = {}
        self.highlights = []
        self.anim_board = None
        self.coach_animating = False
        self.coach_pending = False
        self.coach_reviewing = False
        self.coach_waiting_analysis = False
        self.coach_latest_fen = None
        self.coach_analyzing_fen = None
        self._sync_move_list()
        self.board_canvas.redraw()
        self._coach_schedule_turn()
        self.update_status()

    def on_move_list_select(self, event):
        sel = self.move_list.curselection()
        if sel:
            self._coach_goto(sel[0] + 1)

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
        if self.coach_reviewing:
            txt += "  ·  Coach analysiert Deinen Zug…"
        elif self.coach_waiting_analysis:
            txt += "  ·  Coach analysiert…"
        elif self.coach_pending:
            txt += "  ·  Engine denkt…"
        elif not b.is_game_over():
            if b.turn == self.coach_player_color:
                txt += "  ·  Dein Zug"
            else:
                txt += "  ·  Engine am Zug"
        self.status_lbl.config(text=txt)

    # -- Eval-Balken --------------------------------------------------------
    def _reset_eval(self):
        self.eval_fraction = None
        self.eval_text = "?"
        self.draw_eval_bar()

    def _update_eval(self, score):
        if score is None:
            self._reset_eval()
            return
        try:
            pov = score.pov(chess.WHITE)
        except Exception:
            self._reset_eval()
            return
        if pov.is_mate():
            m = pov.mate()
            self.eval_fraction = 1.0 if m > 0 else 0.0
            self.eval_text = f"M{m}" if m > 0 else f"-M{abs(m)}"
        else:
            cp = pov.score()
            self.eval_fraction = 1.0 / (1.0 + math.exp(-cp / 400.0))
            self.eval_text = f"{cp / 100:+.1f}"
        self.draw_eval_bar()

    def draw_eval_bar(self):
        c = self.eval_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 5 or h <= 5:
            return
        if self.eval_fraction is None:
            c.create_rectangle(0, 0, w, h, fill="#bdbdbd", width=0)
            c.create_text(w / 2, h / 2, text="?", fill="#fff", font=("DejaVu Sans", 11, "bold"))
            return
        frac = max(0.0, min(1.0, self.eval_fraction))
        wh = int(h * frac)
        if self.flipped:
            c.create_rectangle(0, 0, w, h, fill="#3a3a3a", width=0)
            c.create_rectangle(0, 0, w, wh, fill="#f5f5f5", width=0)
        else:
            c.create_rectangle(0, 0, w, h, fill="#f5f5f5", width=0)
            c.create_rectangle(0, 0, w, h - wh, fill="#3a3a3a", width=0)
        c.create_rectangle(0, 0, w - 1, h - 1, outline="#888888", width=1)
        color = "#222222" if frac >= 0.5 else "#ffffff"
        c.create_text(w / 2, h / 2, text=self.eval_text, fill=color, font=("DejaVu Sans", 11, "bold"))

    # -- Hilfe / Konfig -----------------------------------------------------
    def show_help(self):
        win = tk.Toplevel(self)
        win.title("CoachMode — Hilfe")
        win.transient(self)
        win.geometry("640x480")
        txt = tk.Text(win, wrap="word", font=("DejaVu Sans", 11), padx=10, pady=6)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", """CoachMode — Hilfe

Ziel: Gute Züge machen. Die Engine spielt mit einstellbarer Bedenkzeit und
wählt zufällig aus den besten Zügen (Bewertungs-basiert, nicht immer der
allerbeste Zug).

Bedenke: Nach einem schlechten Zug oder einer verpassten Chance (Matt oder
Materialgewinn) zeigt der Coach die Folgen animiert und markiert die
Gefahren. Danach springt die Stellung vor Deinen Zug zurück — Du darfst es
erneut versuchen.

Bedienung:
  - Figur anklicken, dann Zielfeld anklicken.
  - Menü „Spiel“: Neue Partie, Rückgängig, Brett drehen.
  - Rechter Tab „Einstellungen“: alle Coach-Parameter.

Einstellungen (wichtigste):
  - Engine-Denkzeit: Bedenkzeit der Engine pro Stellung.
  - Anzahl bester Züge: aus wie vielen Top-Zügen gewählt wird.
  - Zug-Gewichte: zusätzliche Rang-Gewichte (1,1,1,1,1 = neutral).
  - Bauernzug-/Flucht-/Opening-Faktoren: Regeln mit Wahrscheinlichkeit.
  - Animation pro Halbzug / Pause: Tempo der Folgeanimation.
""")
        txt.configure(state="disabled")
        ttk.Button(win, text="Schließen", command=win.destroy).pack(pady=6)
        win.focus_set()

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        self.coach_think_time = float(cfg.get("coach_think_time", 2.0))
        self.coach_num_moves = int(cfg.get("coach_num_moves", 5))
        try:
            self.coach_weights = [float(w) for w in cfg.get("coach_weights", [1, 1, 1, 1, 1])]
        except Exception:
            self.coach_weights = [1.0, 1.0, 1.0, 1.0, 1.0]
        self.coach_pawn_factor = float(cfg.get("coach_pawn_factor", 1.5))
        self.coach_escape_factor = float(cfg.get("coach_escape_factor", 2.0))
        self.coach_opening_factor = float(cfg.get("coach_opening_factor", 2.0))
        self.coach_feedback_time = float(cfg.get("coach_feedback_time", 2.0))
        self.coach_anim_sec = float(cfg.get("coach_anim_sec", 1.0))
        self.coach_final_pause = float(cfg.get("coach_final_pause", 3.0))
        self.coach_opening = cfg.get("coach_opening", "")
        self.coach_bad_threshold = float(cfg.get("coach_bad_threshold", 200.0))
        self.coach_tactic_threshold = float(cfg.get("coach_tactic_threshold", 250.0))

    def save_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = {
            "coach_think_time": self.coach_think_time,
            "coach_num_moves": self.coach_num_moves,
            "coach_weights": self.coach_weights,
            "coach_pawn_factor": self.coach_pawn_factor,
            "coach_escape_factor": self.coach_escape_factor,
            "coach_opening_factor": self.coach_opening_factor,
            "coach_feedback_time": self.coach_feedback_time,
            "coach_anim_sec": self.coach_anim_sec,
            "coach_final_pause": self.coach_final_pause,
            "coach_opening": self.coach_opening,
            "coach_bad_threshold": self.coach_bad_threshold,
            "coach_tactic_threshold": self.coach_tactic_threshold,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def _relayout(self):
        try:
            self.update_idletasks()
            w = self.paned.winfo_width() if hasattr(self, "paned") else 800
            if w > 100:
                self.paned.sashpos(0, int(w * 0.62))
        except Exception:
            pass

    def on_close(self):
        self._closing = True
        self._coach_cancel_auto()
        try:
            if self.engine is not None:
                self.engine.quit()
        except Exception:
            pass
        self.save_config()
        self.destroy()


def main():
    app = CoachApp()
    app.mainloop()


if __name__ == "__main__":
    main()
