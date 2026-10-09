"""Ergänzt Aufgaben aus eigenen Partien um den Vorlauf und den tatsächlich gespielten Zug.

Args: partien.pgn  aufgaben.pgn [aufgaben.pgn …]   (Dateien werden überschrieben)
Läuft nach lektionen_bauen.py / lektionen_mehrzuegig.py; bereits ergänzte Aufgaben
(Kopf [Kontext …]) bleiben unverändert.

- Die Aufgabe beginnt KONTEXT Halbzüge früher (gerade Zahl, damit dieselbe Seite am Zug ist
  und die App das Brett gleich dreht); der Aufgabentext hängt an der Aufgabenstellung.
- Der Partiezug steht als Nebenvariante mit ?/?? an der Lösung; die App zeigt ihn als roten Pfeil.
"""
import os, re, sys, chess, chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("CHESSTEACH_DIR", os.path.join(HERE, "..", "..")))
from chessteach import san_de

KONTEXT = 6
SRC, FILES = sys.argv[1], sys.argv[2:]


def num(b, m):
    n = b.fullmove_number
    return f"{n}.{san_de(b, m)}" if b.turn == chess.WHITE else f"{n}…{san_de(b, m)}"


# Stellung (FEN, Datum) -> (Partie-Zugliste, Halbzug-Index)
index = {}
with open(SRC, encoding="utf-8") as f:
    while (g := chess.pgn.read_game(f)):
        b = g.board(); moves = list(g.mainline_moves())
        for i, m in enumerate(moves):
            index.setdefault((b.fen(), g.headers.get("Date")), (moves, i))
            b.push(m)

PLAYED_RE = re.compile(r"\s*In der Partie geschah (.*?)(?=\s+Auch gut|\s*$)", re.S)

for path in FILES:
    with open(path, encoding="utf-8") as f:
        games = []
        while (g := chess.pgn.read_game(f)):
            games.append(g)
    out, done, missing = [], 0, 0
    for g in games:
        key = (g.headers.get("FEN"), g.headers.get("Date"))
        if "Kontext" in g.headers or key not in index or not g.variations:
            missing += key not in index and "Kontext" not in g.headers
            out.append(g); continue
        moves, i = index[key]
        k = min(KONTEXT, i) // 2 * 2
        start = chess.Board()
        for m in moves[:i - k]:
            start.push(m)
        played = moves[i]
        ng = chess.pgn.Game(); ng.headers.clear()
        for h, v in g.headers.items():
            ng.headers[h] = v
        ng.headers["FEN"] = start.fen(); ng.headers["SetUp"] = "1"; ng.headers["Kontext"] = str(k)
        node = ng
        if k:
            ng.comment = "So kam es zur Stellung – spiele die Züge mit ▶ durch."
            for m in moves[i - k:i]:
                node = node.add_variation(m)
        node.comment = g.comment  # Aufgabentext an der Aufgabenstellung
        task_board = node.board()
        # Lösung übernehmen; Satz „In der Partie geschah …“ wandert an die Nebenvariante
        src, dst, played_txt = g, node, None
        while src.variations:
            src = src.variations[0]
            c = src.comment
            mt = PLAYED_RE.search(c)
            if mt:
                played_txt = mt.group(1).strip()
                c = PLAYED_RE.sub("", c).strip()
            dst = dst.add_variation(src.move, comment=c, nags=src.nags)
        if played != node.variations[0].move:
            blunder = "??" in (played_txt or "")
            alt = node.add_variation(played, nags={chess.pgn.NAG_BLUNDER if blunder else chess.pgn.NAG_MISTAKE})
            alt.comment = ("Rot: In der Partie geschah " + played_txt) if played_txt else \
                f"Rot: In der Partie geschah {num(task_board, played)}{'??' if blunder else '?'}"
        out.append(ng); done += 1
    with open(path, "w", encoding="utf-8") as f:
        for g in out:
            print(g, file=f, end="\n\n")
    print(f"{path}: {done} ergänzt, {missing} ohne Quelle, {len(out)} gesamt")
