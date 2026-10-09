"""Baut Lektion 05 (Mehrzügig bestrafen) und 06 (Scheinbar gedeckt) aus den eigenen Partien.

Args: evals.json  ziel-verzeichnis (…/lektionen/03_MeinePartien)
Ausgangsmenge wie Lektion 02: Gegner patzt (>= 3 Bauern), eigener Antwortzug >= 1 Bauer schlechter.
Anders als 02 enthält die Lösung die ganze Zugfolge bis zum Materialgewinn bzw. Matt, weil der
Gewinn hier erst nach mehreren Zügen sichtbar wird (Auswertung 2026-10-09: 39 % der Fälle).
"""
import os, sys, chess, chess.pgn, chess.engine
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.environ.get("CHESSTEACH_DIR", os.path.join(HERE, "..", "..")))
from chessteach import san_de

sys.argv = ["stats", EVALS, os.devnull]
src = open(os.path.join(HERE, "stats.py"), encoding="utf-8").read().split("out = collections.OrderedDict()")[0]
exec(src)  # liefert games, ME

DEPTH = 20
MAX_PLIES = 8      # höchstens 4 eigene Züge; längere Engine-Folgen sind nicht mehr erzwungen genug zum Üben
VAL = {1: 1, 2: 3, 3: 3, 4: 5, 5: 9, 6: 0}
FIGUR = {1: "Bauer", 2: "Springer", 3: "Läufer", 4: "Turm", 5: "Dame", 6: "König"}


def bal(b, me):
    return sum((VAL[p.piece_type] if p.color == me else -VAL[p.piece_type]) for p in b.piece_map().values())


def num(b, m):
    n = b.fullmove_number
    return f"{n}.{san_de(b, m)}" if b.turn == chess.WHITE else f"{n}…{san_de(b, m)}"


def line_de(b, moves):
    bb = b.copy(stack=False); out = []
    for m in moves:
        out.append(num(bb, m) if (not out or bb.turn == chess.WHITE) else san_de(bb, m)); bb.push(m)
    return " ".join(out)


def pawns(cp):
    return f"{cp / 100:+.1f}".replace(".", ",")


def side(b):
    return "Weiß" if b.turn == chess.WHITE else "Schwarz"


eng = None
def init():
    global eng
    eng = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    eng.configure({"Threads": 1, "Hash": 128})


def ana(fen):
    infos = eng.analyse(chess.Board(fen), chess.engine.Limit(depth=DEPTH), multipv=3)
    return fen, [(i["score"].relative.score(mate_score=100000), [m.uci() for m in i["pv"][:16]]) for i in infos if i.get("pv")]


def real_defenders(b, sq, color):
    return [d for d in b.attackers(color, sq) if not b.is_pinned(color, d)]


def classify(b, score, pv):
    """-> (art, zugfolge) ; art in mate/multi/overload/None"""
    me = b.turn
    first = pv[0]
    if score >= 90000:
        n = 100000 - score  # Halbzüge bis Matt
        return ("mate", pv[:n]) if 3 <= n <= MAX_PLIES else (None, None)
    base = bal(b, me); bb = b.copy(); when = None
    for j, m in enumerate(pv):
        bb.push(m)
        if j % 2 == 1 and bal(bb, me) - base >= 2:
            when = j; break
    if b.is_capture(first) and not b.is_en_passant(first):
        cap = b.piece_at(first.to_square); tgt = first.to_square
        after = b.copy(); after.push(first)
        nominal = list(after.attackers(not me, tgt))
        recapture = [mm for mm in after.legal_moves if mm.to_square == tgt]
        if nominal and not recapture and when is not None:
            if any(after.is_pinned(not me, d) for d in nominal):
                return "pinned", pv[:when + 1]
            return None, None                      # nur der König „deckt“: einfach ungedeckt
        if recapture and when is not None:
            return "defended", pv[:when + 1]       # Überlastung wird in overload() nachgewiesen
        if when is not None and when <= 1:
            return None, None  # einfacher Schlagzug, gehört zu Lektion 02
    if when is not None and 3 <= when < MAX_PLIES:
        return "multi", pv[:when + 1]
    return None, None


def overload(b, first):
    """Zurückschlagen ist legal, verliert aber, weil der Verteidiger eine zweite Aufgabe hatte:
    Mein Folgezug nach dem Zurückschlagen geht auf ein Feld, das der Verteidiger vorher deckte."""
    after = b.copy(); after.push(first)
    rec = [mm for mm in after.legal_moves if mm.to_square == first.to_square]
    info = refute.analyse(after, chess.engine.Limit(depth=DEPTH), root_moves=rec)
    r = info["pv"][:5]
    sc = info["score"].pov(b.turn).score(mate_score=100000)
    if len(r) < 2 or sc < 200: return None
    duty = r[1].to_square
    if duty == first.to_square or duty not in after.attacks(r[0].from_square): return None
    return r, sc, duty


def headers(g):
    h = g["h"]
    nm = lambda p: "Ich" if p.lower() == ME.lower() else "Gegner"
    return {"White": nm(h["White"]), "Black": nm(h["Black"]), "Result": h["Result"], "Date": h["Date"]}


def puzzle(b, title, hdr, task, line, final):
    gm = chess.pgn.Game(); gm.headers.clear()
    gm.headers["Event"] = title
    for k, v in hdr.items(): gm.headers[k] = v
    gm.headers["SetUp"] = "1"; gm.headers["FEN"] = b.fen(); gm.headers["Aufgabe"] = "1"
    gm.comment = task
    node = gm
    for m in line:
        node = node.add_variation(m)
    node.comment = final
    return gm


cands = []
for gi, g in enumerate(games):
    mv = g["moves"]
    for k, m in enumerate(mv):
        if not m["mine"] and m["loss"] >= 300 and abs(m["before"]) < 500 and k + 1 < len(mv) and mv[k + 1]["loss"] >= 100:
            cands.append((gi, mv[k + 1]))

fens = sorted({games[gi]["boards"][m["i"]].fen() for gi, m in cands})
with Pool(18, initializer=init) as p:
    res = dict(p.imap_unordered(ana, fens, chunksize=2))

refute = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
out5, out6, seen = [], [], set()
for gi, m in sorted(cands, key=lambda t: games[t[0]]["h"]["Date"], reverse=True):
    g = games[gi]; b = g["boards"][m["i"]]; fen = b.fen()
    if fen in seen or not res.get(fen): continue
    score, pv_u = res[fen][0]
    if score < 200 or pv_u[0] == m["move"]: continue
    pv = [chess.Move.from_uci(u) for u in pv_u]
    art, line = classify(b, score, pv)
    ov = None
    if art == "defended":
        ov = overload(b, line[0])
        art = "overload" if ov else ("multi" if 4 <= len(line) <= MAX_PLIES else None)
    if not art: continue
    seen.add(fen)
    pm = chess.Move.from_uci(m["move"])
    also = [san_de(b, chess.Move.from_uci(u[0])) for s, u in res[fen][1:]
            if score - s <= 50 and u[0] not in (pv_u[0], m["move"])]
    also_txt = f" Auch gut war {', '.join(also)}." if also else ""
    played = f" In der Partie geschah {num(b, pm)}? und die Chance war weg."
    hdr = headers(g)
    if art == "mate":
        n = (len(line) + 1) // 2
        title = f"{side(b)} am Zug · Zug {b.fullmove_number} · Matt in {n}"
        task = f"{side(b)} am Zug. Dein Gegner hat gepatzt: Du kannst in {n} Zügen mattsetzen. Rechne die ganze Folge!"
        final = f"Matt! Lösung: {line_de(b, line)}.{also_txt}{played}"
        out5.append(puzzle(b, title, hdr, task, line, final))
    elif art == "multi":
        n = (len(line) + 1) // 2
        title = f"{side(b)} am Zug · Zug {b.fullmove_number} · Gewinn in {n} Zügen"
        task = (f"{side(b)} am Zug. Bewertung {pawns(score)}, aber direkt zu holen gibt es nichts. "
                f"Finde den Plan über mehrere Züge – Schach, Schlagen, Drohen!")
        final = f"Material gewonnen. Lösung: {line_de(b, line)} (Bewertung {pawns(score)}).{also_txt}{played}"
        out5.append(puzzle(b, title, hdr, task, line, final))
    else:
        first = line[0]; tgt = first.to_square
        cap = b.piece_at(tgt)
        defs = sorted(b.attackers(not b.turn, tgt))
        dtxt = ", ".join(f"{FIGUR[b.piece_at(d).piece_type]} {chess.square_name(d)}" for d in defs)
        after = b.copy(); after.push(first); refut = ""
        if art == "pinned":
            pinned = [d for d in defs if after.is_pinned(not b.turn, d)]
            why = f"{FIGUR[b.piece_at(pinned[0]).piece_type]} {chess.square_name(pinned[0])} ist gefesselt und darf nicht zurückschlagen."
        else:
            r, sc, duty = ov
            d = r[0].from_square
            why = (f"{FIGUR[b.piece_at(d).piece_type]} {chess.square_name(d)} ist überlastet: "
                   f"Er deckt auch {chess.square_name(duty)}.")
            refut = (f" Schlägt er zurück, folgt {line_de(after, r)}"
                     f" ({'Matt' if sc >= 90000 else 'Bewertung ' + pawns(sc)}).")
        title = f"{side(b)} am Zug · Zug {b.fullmove_number} · Scheinbar gedeckt"
        task = (f"{side(b)} am Zug. Eine Figur des Gegners sieht gedeckt aus – ist sie es wirklich? "
                f"Prüfe jeden Verteidiger: Ist er gefesselt? Muss er noch etwas anderes decken?")
        sq = " ".join(f"[Sq {chess.square_name(d)}]" for d in defs)
        final = (f"{sq} {FIGUR[cap.piece_type]} {chess.square_name(tgt)} war nur scheinbar gedeckt "
                 f"({dtxt}), aber {why}{refut} Lösung: {line_de(b, line)} "
                 f"(Bewertung {pawns(score)}).{also_txt}{played}")
        out6.append(puzzle(b, title, hdr, task, line, final))

for d, title, games_pgn in (("05_Mehrzuegig-bestrafen", "Mehrzügig bestrafen", out5),
                            ("06_Scheinbar-gedeckt", "Scheinbar gedeckt", out6)):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
    open(os.path.join(OUT, d, "_meta.txt"), "w", encoding="utf-8").write(title + "\n")
    with open(os.path.join(OUT, d, f"0001_{d[3:]}.pgn"), "w", encoding="utf-8") as f:
        for gm in games_pgn:
            print(gm, file=f, end="\n\n")
    print(d, len(games_pgn))
refute.quit()
