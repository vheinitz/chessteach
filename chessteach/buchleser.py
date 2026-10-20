"""Lesemodus für Schachbücher (Reiter „Bücher“ in ChessTeach).

Ein Buch liegt als buecher/<name>/buch.json vor (erzeugt von tools/buecher/pdf_buch.py):
Text wird als Text gezeigt, jeder Zug ist anklickbar. Ein Klick lädt die Partie von ihrer
Ausgangsstellung bis zu diesem Zug in die Zugliste der App; danach weiter mit den
Pfeiltasten. Auch Züge, die mitten in der Partie oder als Variante erwähnt werden, hängen
an ihrer Partie – die Zugliste zeigt immer den ganzen Weg dorthin.
"""
import glob
import io
import json
import os
import tkinter as tk
from tkinter import ttk

import chess
import chess.pgn
from PIL import Image, ImageTk

MAIN_COLOR = "#0d47a1"
VAR_COLOR = "#2e7d32"
CUR_BG = "#ffe082"


def find_books(app_dir):
    books = []
    for path in sorted(glob.glob(os.path.join(app_dir, "buecher", "*", "buch.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            books.append((path, data))
        except (OSError, ValueError):
            continue
    return books


class BookReader(ttk.Frame):
    def __init__(self, parent, app, books, draw_mini_board):
        super().__init__(parent)
        self.app = app
        self.books = books
        self.draw_mini_board = draw_mini_board
        self.data = None
        self.span_node = {}         # Tag „s<k>“ -> (partie, knoten)
        self.node_tags = {}         # (partie, knoten) -> [Tags]
        self.loaded = None          # (game_steps-Objekt, [(partie, knoten) je Halbzug])
        self.canvases = []
        self.images = []            # PhotoImage-Referenzen der Abbildungen
        self.book_dir = None

        top = ttk.Frame(self)
        top.pack(fill="x", padx=2, pady=2)
        self.book_var = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.book_var, state="readonly",
                                  values=[b[1].get("titel", os.path.basename(os.path.dirname(b[0])))
                                          for b in books])
        self.combo.pack(side="left", fill="x", expand=True)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.open_book(self.combo.current()))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, wrap="word", font=("DejaVu Serif", 12), padx=8, pady=6,
                            cursor="arrow", spacing1=2, spacing3=4, relief="flat",
                            bg="#fffdf6")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        t = self.text
        t.tag_configure("h", font=("DejaVu Sans", 13, "bold"), spacing1=12, spacing3=6,
                        foreground="#37474f")
        t.tag_configure("cap", font=("DejaVu Serif", 11, "italic"), justify="center",
                        foreground="#455a64")
        t.tag_configure("fn", font=("DejaVu Serif", 10), foreground="#555")
        t.tag_configure("page", font=("DejaVu Sans", 9), foreground="#9e9e9e", justify="right")
        t.tag_configure("dia", justify="center", spacing1=6, spacing3=6)
        t.tag_configure("mv", font=("DejaVu Sans", 12))
        t.tag_configure("mv_main", foreground=MAIN_COLOR, font=("DejaVu Sans", 12, "bold"))
        t.tag_configure("mv_var", foreground=VAR_COLOR)
        t.tag_configure("fix", underline=True, foreground="#bf360c")
        t.tag_configure("cur", background=CUR_BG)
        t.tag_raise("cur")
        for tag in ("mv_main", "mv_var"):
            t.tag_bind(tag, "<Button-1>", self.on_move_click)
            t.tag_bind(tag, "<Enter>", lambda e: self.text.config(cursor="hand2"))
            t.tag_bind(tag, "<Leave>", lambda e: self.text.config(cursor="arrow"))
        # Fokus zurück an die App, sonst sperrt sie die Pfeiltasten (Eingabefeld hat Fokus)
        t.bind("<ButtonRelease-1>", lambda e: self.after_idle(self.app.focus_set))

    # -- Laden und Darstellen ---------------------------------------------------------
    def open_book(self, index, yview=None):
        if not (0 <= index < len(self.books)):
            return
        self.combo.current(index)
        self.data = self.books[index][1]
        self.book_dir = os.path.dirname(self.books[index][0])
        self.render()
        if yview is not None:
            self.after(50, lambda: self.text.yview_moveto(yview))

    def render(self):
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for c in self.canvases:
            c.destroy()
        self.canvases, self.images = [], []
        self.span_node, self.node_tags = {}, {}
        k = 0
        page = None
        for bl in self.data["bloecke"]:
            if bl.get("page") != page:
                page = bl.get("page")
                t.insert("end", f"— S. {page} —\n", "page")
            kind = bl["t"]
            if kind == "h":
                t.insert("end", bl["text"] + "\n", "h")
            elif kind == "cap":
                t.insert("end", bl["text"] + "\n", "cap")
            elif kind == "dia":
                self._insert_diagram(bl)
            elif kind == "bild":
                self._insert_image(bl)
            elif kind == "p":
                base = ("fn",) if bl.get("fn") else ()
                for s in bl["spans"]:
                    if isinstance(s, str):
                        t.insert("end", s, base)
                        continue
                    tag = f"s{k}"
                    k += 1
                    key = (s["g"], s["n"])
                    self.span_node[tag] = key
                    self.node_tags.setdefault(key, []).append(tag)
                    tags = base + ("mv", "mv_main" if s["b"] else "mv_var", tag)
                    if "k" in s:    # vermuteter Druckfehler: Buchtext dahinter in Klammern
                        t.insert("end", s["m"], tags + ("fix",))
                        t.insert("end", f" [im Buch: {s['k']}]", base + ("fn",))
                    else:
                        t.insert("end", s["m"], tags)
                t.insert("end", "\n\n" if not bl.get("fn") else "\n", base)
        t.configure(state="disabled")

    def _insert_diagram(self, bl):
        size = 168
        c = tk.Canvas(self.text, width=size, height=size + 18, highlightthickness=0,
                      bg="#fffdf6", cursor="hand2")
        try:
            self.draw_mini_board(c, 0, 0, size, bl["fen"] if " " in bl["fen"] else bl["fen"] + " w - - 0 1")
        except ValueError:
            c.create_text(size // 2, size // 2, text="(Diagramm)")
        label = f"Диаграмма {bl['nr']}" if bl.get("nr") else "Диаграмма"
        c.create_text(size // 2, size + 9, text=label, font=("DejaVu Sans", 9), fill="#555")
        c.bind("<Button-1>", lambda e, b=bl: self.on_diagram_click(b))
        self.canvases.append(c)
        self.text.insert("end", "\n", "dia")
        self.text.window_create("end", window=c)
        self.text.insert("end", "\n", "dia")
        self.text.tag_add("dia", "end-3l", "end-1c")

    def _insert_image(self, bl):
        """Abbildung (Schema) aus dem Buchverzeichnis, auf Lesebreite verkleinert."""
        try:
            img = Image.open(os.path.join(self.book_dir, bl["datei"]))
        except OSError:
            return
        if img.width > 520:
            img = img.resize((520, round(img.height * 520 / img.width)), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.images.append(photo)
        self.text.insert("end", "\n", "dia")
        self.text.image_create("end", image=photo)
        self.text.insert("end", "\n", "dia")
        self.text.tag_add("dia", "end-3l", "end-1c")

    # -- Klicks --------------------------------------------------------------------------
    def on_move_click(self, event):
        idx = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(idx):
            if tag in self.span_node:
                self.show_node(*self.span_node[tag], anchor=tag)
                return "break"

    def on_diagram_click(self, bl):
        if bl.get("ref"):
            self.show_node(bl["ref"]["g"], bl["ref"]["n"])
        elif "/" in bl["fen"]:
            fen = bl["fen"] if " " in bl["fen"] else bl["fen"] + " w - - 0 1"
            try:
                chess.Board(fen)
            except ValueError:
                return
            self._unflip()
            self.app.load_fen(fen)
            self.loaded = None

    def line_of(self, g, n):
        """Weg von der Ausgangsstellung zu Knoten n, dann weiter auf der bevorzugten Fortsetzung
        (Hauptlinie, sonst die zuerst im Text genannte)."""
        nodes = self.data["partien"][g]["nodes"]
        path = []
        x = n
        while x >= 0:
            path.append(x)
            x = nodes[x][0]
        path.reverse()
        children = {}
        for i, nd in enumerate(nodes):
            children.setdefault(nd[0], []).append(i)
        x = n
        tail = []
        while x in children:
            kids = children[x]
            nxt = next((c for c in kids if nodes[c][3]), kids[0])
            if nodes[nxt][1] == "0000" and len(tail) > 0:
                break               # Drohung der anderen Seite nicht automatisch anhängen
            tail.append(nxt)
            x = nxt
        return path, tail

    def show_node(self, g, n, anchor=None):
        game = self.data["partien"][g]
        path, tail = self.line_of(g, n)        # n = -1: Ausgangsstellung (Diagramm)
        pg = chess.pgn.Game()
        root = chess.Board(game["root"])
        if root.fen() != chess.STARTING_FEN:
            pg.setup(root)
        node = pg
        for x in path + tail:
            node = node.add_variation(chess.Move.from_uci(game["nodes"][x][1]))
        pg.headers["Event"] = self.data.get("titel", "Buch")
        pg.headers["Site"] = game.get("label", "")
        self._unflip()
        self.app.load_pgn(str(pg))
        self.loaded = (self.app.game_steps, [(g, x) for x in path + tail])
        if path:
            self.app.game_replay_to(self.app.move_step_index[len(path) - 1])
        self.highlight((g, n), anchor)

    def _unflip(self):
        # Buchdiagramme stehen immer mit Weiß unten
        if self.app.flipped:
            self.app.flip_var.set(False)
            self.app.toggle_flip()

    def highlight(self, key, anchor=None):
        t = self.text
        t.tag_remove("cur", "1.0", "end")
        tags = self.node_tags.get(key, [])
        for tag in tags:
            for a, b in zip(t.tag_ranges(tag)[0::2], t.tag_ranges(tag)[1::2]):
                t.tag_add("cur", a, b)
        if not tags:
            return
        # sichtbar machen: Anker oder das nächste Vorkommen nach der aktuellen Anzeige
        target = anchor if anchor in tags else None
        if target is None:
            top = t.index("@0,0")
            target = next((tg for tg in tags if t.compare(t.tag_ranges(tg)[0], ">=", top)), tags[0])
        t.see(t.tag_ranges(target)[0])

    def sync(self, ply):
        """Von der App nach jedem Blättern aufgerufen: aktuellen Zug im Text markieren."""
        if not self.loaded or self.loaded[0] is not self.app.game_steps:
            return
        line = self.loaded[1]
        if 0 < ply <= len(line):
            self.highlight(line[ply - 1])
        else:
            self.text.tag_remove("cur", "1.0", "end")

    def state(self):
        if self.data is None:
            return None
        return {"buch": self.combo.current(), "pos": self.text.yview()[0]}
