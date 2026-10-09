"""Übernimmt Taktik-Aufgaben aus der Lichess-Aufgabendatenbank (CC0) als Lektionen.

Args: lichess_db_puzzle.csv.zst  lektionen-verzeichnis  [aufgaben-pro-thema=20]
Download: https://database.lichess.org/lichess_db_puzzle.csv.zst
Je Thema eine Lektion in 01_Grundlagen (23…), dazu Ergänzung von 03_MeinePartien/06_Scheinbar-gedeckt.
Auswahl: Rating 900–1500 (passt zu ~600–800 Elo chess.com), beliebt und oft gespielt,
nach Rating sortiert gleichmäßig verteilt, damit die Lektion leicht beginnt und schwerer wird.
"""
import csv, io, os, subprocess, sys, chess, chess.pgn

SRC, LEK = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 20
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from chessteach import san_de

THEMEN = [  # (Lichess-Thema, Ordner, Titel, Hinweis für die Aufgabe)
    # Lichess kennt kein Thema „Überlastung“ (steckt in deflection); ausgewählt wird per scheinbar_gedeckt()
    ("overloading", "23_Ueberlastung", "Überlastung",
     "Eine gegnerische Figur hat zwei Aufgaben auf einmal. Gib ihr zu viel zu tun!"),
    ("deflection", "24_Ablenkung", "Ablenkung",
     "Lenke einen Verteidiger weg von dem, was er schützen muss!"),
    ("attraction", "25_Hinlenkung", "Hinlenkung",
     "Locke eine gegnerische Figur (oft den König) auf ein schlechtes Feld!"),
    ("pin", "26_Fesselung", "Fesselung",
     "Eine Figur kann nicht ziehen, weil dahinter etwas Wertvolleres steht. Nutze das aus!"),
    ("capturingDefender", "27_Verteidiger-beseitigen", "Beseitigung des Verteidigers",
     "Schlage die Figur, die alles zusammenhält – danach fällt der Rest!"),
    ("backRankMate", "28_Grundreihenmatt", "Grundreihenmatt",
     "Der König ist auf der Grundreihe eingesperrt. Finde das Matt!"),
    ("trappedPiece", "29_Figurenfang", "Figurenfang",
     "Eine gegnerische Figur hat keine sicheren Felder mehr. Fang sie!"),
    ("quietMove", "30_Stiller-Zug", "Stiller Zug",
     "Kein Schach, kein Schlagen – und trotzdem gewinnt ein ruhiger Zug. Finde ihn!"),
]
SEEN_IDS = set()


def num(b, m):
    n = b.fullmove_number
    return f"{n}.{san_de(b, m)}" if b.turn == chess.WHITE else f"{n}…{san_de(b, m)}"


def line_de(b, moves):
    bb = b.copy(stack=False); out = []
    for m in moves:
        out.append(num(bb, m) if (not out or bb.turn == chess.WHITE) else san_de(bb, m)); bb.push(m)
    return " ".join(out)


def side(b):
    return "Weiß" if b.turn == chess.WHITE else "Schwarz"


def read_rows():
    p = subprocess.Popen(["zstdcat", SRC], stdout=subprocess.PIPE)
    for r in csv.DictReader(io.TextIOWrapper(p.stdout, encoding="utf-8")):
        rating, pop, plays = int(r["Rating"]), int(r["Popularity"]), int(r["NbPlays"])
        if 900 <= rating <= 1500 and pop >= 90 and plays >= 2000:
            yield r


def start(r):
    """Lichess-FEN steht vor dem Zug des Gegners; der erste Zug gehört zur Aufgabe."""
    b = chess.Board(r["FEN"])
    moves = [chess.Move.from_uci(u) for u in r["Moves"].split()]
    last = moves[0]
    last_txt = num(b, last)
    b.push(last)
    return b, last, last_txt, moves[1:]


def game(r, title, task):
    b, last, last_txt, sol = start(r)
    gm = chess.pgn.Game(); gm.headers.clear()
    gm.headers["Event"] = f"{side(b)} am Zug · {title} · Lichess {r['Rating']}"
    gm.headers["Site"] = r["GameUrl"]
    gm.headers["White"] = "?"; gm.headers["Black"] = "?"; gm.headers["Result"] = "*"
    gm.headers["SetUp"] = "1"; gm.headers["FEN"] = b.fen(); gm.headers["Aufgabe"] = "1"
    sq = chess.square_name
    gm.comment = (f"[Ar {sq(last.from_square)}{sq(last.to_square)}] Zuletzt zog der Gegner {last_txt}. "
                  f"{side(b)} am Zug. {task}")
    node = gm
    for m in sol:
        node = node.add_variation(m)
    node.comment = f"Gelöst: {line_de(b, sol)}. (Aufgabe {r['PuzzleId']} von lichess.org, CC0)"
    return gm


def scheinbar_gedeckt(r):
    """Erster Lösungszug schlägt eine nominell gedeckte Figur; Zurückschlagen ist wegen Fesselung
    verboten, oder es ist erlaubt und der nächste Zug geht auf ein Feld, das der Verteidiger deckte."""
    b, _, _, sol = start(r)
    if len(sol) < 3: return None
    first, reply, follow = sol[0], sol[1], sol[2]
    if not b.is_capture(first) or b.is_en_passant(first): return None
    after = b.copy(); after.push(first)
    tgt = first.to_square
    nominal = list(after.attackers(not b.turn, tgt))
    if not nominal: return None
    rec = [m for m in after.legal_moves if m.to_square == tgt]
    if not rec and any(after.is_pinned(not b.turn, d) for d in nominal):
        return "pin"
    if reply in rec and follow.to_square != tgt and follow.to_square in after.attacks(reply.from_square):
        return "overload"
    return None


def lesson_file(folder, title):
    os.makedirs(folder, exist_ok=True)
    meta = os.path.join(folder, "_meta.txt")
    if not os.path.exists(meta):
        open(meta, "w", encoding="utf-8").write(title + "\n")
    path = os.path.join(folder, f"0001_{os.path.basename(folder)[3:]}.pgn")
    return path


def spread(rows, n):
    rows = sorted(rows, key=lambda r: int(r["Rating"]))
    if len(rows) <= n: return rows
    return [rows[round(i * (len(rows) - 1) / (n - 1))] for i in range(n)]


pool = {t: [] for t, *_ in THEMEN}
schein = []
for r in read_rows():
    th = set(r["Themes"].split())
    if len(r["Moves"].split()) > 9: continue          # höchstens 4 eigene Züge
    for t in pool:
        if t in th: pool[t].append(r)
    if th & {"pin", "capturingDefender", "deflection"}:
        kind = scheinbar_gedeckt(r)
        if kind:
            schein.append(r)
        if kind == "overload":
            pool["overloading"].append(r)

for t, ordner, titel, hinweis in THEMEN:
    pick = [r for r in spread([r for r in pool[t] if r["PuzzleId"] not in SEEN_IDS], N)]
    SEEN_IDS.update(r["PuzzleId"] for r in pick)
    folder = os.path.join(LEK, "01_Grundlagen", ordner)
    path = lesson_file(folder, titel)
    with open(path, "w", encoding="utf-8") as f:
        for r in pick:
            print(game(r, titel, hinweis), file=f, end="\n\n")
    print(ordner, len(pick), "aus", len(pool[t]))

# 06_Scheinbar-gedeckt: eigene Stellungen stehen in 0001_…, Lichess ergänzt als 0002_…
folder = os.path.join(LEK, "03_MeinePartien", "06_Scheinbar-gedeckt")
pick = spread([r for r in schein if r["PuzzleId"] not in SEEN_IDS], N)
os.makedirs(folder, exist_ok=True)
with open(os.path.join(folder, "0002_Scheinbar-gedeckt-Lichess.pgn"), "w", encoding="utf-8") as f:
    for r in pick:
        kind = scheinbar_gedeckt(r)
        task = ("Eine Figur des Gegners sieht gedeckt aus – ist sie es wirklich? "
                "Prüfe jeden Verteidiger: Ist er gefesselt? Muss er noch etwas anderes decken?")
        gm = game(r, "Scheinbar gedeckt", task)
        b, _, _, sol = start(r)
        tgt = sol[0].to_square
        why = ("Der Verteidiger ist gefesselt." if kind == "pin" else
               f"Der Verteidiger ist überlastet: Nach dem Zurückschlagen fehlt er auf {chess.square_name(sol[2].to_square)}.")
        end = gm.end(); end.comment = f"{why} " + end.comment
        print(gm, file=f, end="\n\n")
print("06_Scheinbar-gedeckt (Lichess)", len(pick), "aus", len(schein))
