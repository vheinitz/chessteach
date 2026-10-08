"""Baut Übungs-Lektionen aus den eigenen Partien.

Args: evals.json  ziel-verzeichnis (…/lektionen/03_MeinePartien)
Benötigt stats.py (classify, games) im selben Verzeichnis und chessteach.py im Pfad.
"""
import os, sys, json, chess, chess.pgn, chess.engine
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.environ.get("CHESSTEACH_DIR", os.path.join(HERE, "..", "..")))
from chessteach import san_de  # deutsche Notation wie in der App

sys.argv = ["stats", EVALS, os.devnull]
src = open(os.path.join(HERE, "stats.py"), encoding="utf-8").read().split("out = collections.OrderedDict()")[0]
exec(src)  # liefert games, classify, traj, NAME, VAL

DEPTH = 18
OK_MARGIN = 50     # Alternativen innerhalb 0,5 Bauern gelten als „auch gut“
FIGUR = {chess.PAWN: "Bauer", chess.KNIGHT: "Springer", chess.BISHOP: "Läufer",
         chess.ROOK: "Turm", chess.QUEEN: "Dame", chess.KING: "König"}


def num(b, m):
    n = b.fullmove_number
    return f"{n}.{san_de(b, m)}" if b.turn == chess.WHITE else f"{n}…{san_de(b, m)}"


def line_de(b, ucis, n):
    bb = b.copy(stack=False); out = []
    for u in ucis[:n]:
        m = chess.Move.from_uci(u)
        if m not in bb.legal_moves: break
        out.append(num(bb, m) if (not out or bb.turn == chess.WHITE) else san_de(bb, m)); bb.push(m)
    return " ".join(out)


REASONS = [("Bestehende", "eine Figur steht angegriffen"),
           ("Gezogene", "ein naheliegender Zug stellt die Figur ungedeckt hin"),
           ("Deckung", "ein Zug nimmt einer anderen Figur die Deckung"),
           ("Gabel", "der Gegner droht einen Doppelangriff"),
           ("Mehrzügige", "der Gegner hat eine Kombination"),
           ("Schach", "ein Schach des Gegners gewinnt Material"),
           ("Matt", "es droht Matt")]


def bauern(cp):
    return f"{cp / 100:.1f}".replace(".", ",").replace(",0", "")


def pawns(cp):
    return f"{cp / 100:+.1f}".replace(".", ",")


eng = None
def init():
    global eng
    eng = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    eng.configure({"Threads": 1, "Hash": 128})


def verify(fen):
    b = chess.Board(fen)
    infos = eng.analyse(b, chess.engine.Limit(depth=DEPTH), multipv=4)
    res = []
    for i in infos:
        if not i.get("pv"): continue
        res.append((i["pv"][0].uci(), i["score"].relative.score(mate_score=100000), [m.uci() for m in i["pv"][:6]]))
    return fen, res


def side(b):
    return "Weiß" if b.turn == chess.WHITE else "Schwarz"


def meta_headers(g):
    h = g["h"]
    return {"White": h["White"], "Black": h["Black"], "Result": h["Result"], "Date": h["Date"]}


cand = {1: [], 2: [], 3: [], 4: []}
for gi, g in enumerate(games):
    mv = g["moves"]
    # 1) Patzer-Vorbeuge: Stellung vor eigenem Patzer mit Materialverlust
    for m in mv:
        if m["mine"] and m["loss"] >= 300 and m["before"] > -300:
            c, v = classify(g, m)
            if c.startswith(("Bestehende Drohung", "Gezogene Figur", "Deckung", "Gabel", "Mehrzügige", "Schach mit", "Matt zugelassen")):
                cand[1].append((gi, m, c, v))
    # 2) Bestrafe: nach gegnerischem Patzer, eigener Zug nicht bestraft
    for k, m in enumerate(mv):
        if not m["mine"] and m["loss"] >= 300 and abs(m["before"]) < 500 and k + 1 < len(mv):
            nxt = mv[k + 1]
            if nxt["loss"] >= 100:
                cand[2].append((gi, nxt, None, None))
    # 3) Gewinn verwerten: erste Stellung >= +5 (ich am Zug) in nicht gewonnenen Partien
    if g["res"] in "NR":
        for m in mv:
            if m["mine"] and m["before"] >= 500:
                cand[3].append((gi, m, None, None)); break
    # 4) Eröffnungsfehler: erster Fehler >= 1 bis Zug 10 in Niederlagen
    if g["res"] == "N":
        f = next((m for m in mv if m["mine"] and m["loss"] >= 100), None)
        if f and f["no"] <= 10:
            cand[4].append((gi, f, None, None))

fens = sorted({games[gi]["boards"][m["i"]].fen() for L in (1, 2, 4) for gi, m, _, _ in cand[L]})
print({k: len(v) for k, v in cand.items()}, "zu prüfende Stellungen:", len(fens), flush=True)
with Pool(18, initializer=init) as p:
    ver = dict(p.imap_unordered(verify, fens, chunksize=4))


def write(path, games_pgn):
    with open(path, "w", encoding="utf-8") as f:
        for gm in games_pgn:
            print(gm, file=f, end="\n\n")


def puzzle_game(b, title, hdr, task, best, also, after_comment, hint_sq):
    gm = chess.pgn.Game()
    gm.headers.clear()
    gm.headers["Event"] = title
    for k, v in hdr.items(): gm.headers[k] = v
    gm.headers["SetUp"] = "1"; gm.headers["FEN"] = b.fen(); gm.headers["Aufgabe"] = "1"
    gm.comment = task
    node = gm.add_variation(chess.Move.from_uci(best))
    hint = f"[Sq {chess.square_name(hint_sq)}] " if hint_sq is not None else ""
    node.comment = hint + after_comment + (f" Auch gut: {', '.join(also)}." if also else "")
    return gm


def solution(fen, played):
    res = ver.get(fen) or []
    if not res: return None
    best_u, best_cp, pv = res[0]
    if best_u == played: return None          # tiefere Prüfung: gespielter Zug war doch richtig
    b = chess.Board(fen)
    also = [san_de(b, chess.Move.from_uci(u)) for u, cp, _ in res[1:] if best_cp - cp <= OK_MARGIN and u != played]
    played_cp = None
    return best_u, best_cp, pv, also


stats_out = {}
# ---- Lektion 1
out1 = []; seen = set()
for gi, m, c, v in sorted(cand[1], key=lambda t: games[t[0]]["h"]["Date"], reverse=True):
    g = games[gi]; b = g["boards"][m["i"]]; fen = b.fen()
    if fen in seen: continue
    sol = solution(fen, m["move"])
    if not sol: continue
    best_u, best_cp, pv, also = sol
    if best_cp < -200: continue               # Stellung war ohnehin schlecht
    seen.add(fen)
    pm = chess.Move.from_uci(m["move"])
    A = g["boards"][m["i"] + 1]; pA = g["pos"][m["i"] + 1]
    _, caps = traj(A, pA["pv"], g["me"])
    opp = [x for x in caps if x[1] != g["me"]]
    hint_sq = opp[0][3] if opp else None
    vict = f" ({v} verloren)" if v else ""
    punish = line_de(A, pA["pv"], 3)
    reason = next((t for k, t in REASONS if c.startswith(k)), "Gefahr")
    title = f"{side(b)} am Zug · Zug {b.fullmove_number} · {c.split(' (')[0]}"
    task = f"{side(b)} am Zug. Vorsicht: {reason}. Finde einen sicheren Zug!"
    after = (f"Richtig: {num(b, chess.Move.from_uci(best_u))}. In der Partie geschah {num(b, pm)}?? — "
             f"danach {punish}{vict}.")
    out1.append(puzzle_game(b, title, meta_headers(g), task, best_u, also, after, hint_sq))
stats_out["Lektion 1"] = len(out1)
# ---- Lektion 2
out2 = []; seen = set()
for gi, m, _, _ in sorted(cand[2], key=lambda t: games[t[0]]["h"]["Date"], reverse=True):
    g = games[gi]; b = g["boards"][m["i"]]; fen = b.fen()
    if fen in seen: continue
    sol = solution(fen, m["move"])
    if not sol: continue
    best_u, best_cp, pv, also = sol
    if best_cp < 200: continue                # nur klare Bestrafungen
    seen.add(fen)
    bm = chess.Move.from_uci(best_u); pm = chess.Move.from_uci(m["move"])
    tgt = bm.to_square
    title = f"{side(b)} am Zug · Zug {b.fullmove_number} · Gegner hat gepatzt"
    task = f"{side(b)} am Zug. Dein Gegner hat gerade einen groben Fehler gemacht. Bestrafe ihn!"
    after = (f"Richtig: {line_de(b, pv, 3)} (Bewertung {pawns(best_cp)}). "
             f"In der Partie geschah {num(b, pm)}? und die Chance war weg.")
    out2.append(puzzle_game(b, title, meta_headers(g), task, best_u, also, after, None))
stats_out["Lektion 2"] = len(out2)
# ---- Lektion 3: Stellung + tatsächlicher Verlauf mit Markierung der Patzer
out3 = []
for gi, m, _, _ in sorted(cand[3], key=lambda t: games[t[0]]["h"]["Date"], reverse=True):
    g = games[gi]; b = g["boards"][m["i"]]
    gm = chess.pgn.Game(); gm.headers.clear()
    endtxt = g["h"]["Termination"]
    res = "verloren" if g["res"] == "N" else "remis"
    gm.headers["Event"] = f"{side(b)} am Zug · {pawns(m['before'])} · Partie {res}"
    for k, v in meta_headers(g).items(): gm.headers[k] = v
    gm.headers["SetUp"] = "1"; gm.headers["FEN"] = b.fen()
    gm.comment = (f"Hier standest du {pawns(m['before'])}. Spielt die Stellung zu zweit (oder mit Analyse-Hilfe) "
                  f"sicher zu Ende: Figuren tauschen, Drohungen prüfen, auf Patt achten. "
                  f"Mit ▶ siehst du, wie es in der Partie lief ({endtxt}).")
    node = gm; bb = b.copy(stack=False)
    for mm in g["moves"][m["i"]:]:
        mv = chess.Move.from_uci(mm["move"])
        node = node.add_variation(mv)
        if mm["mine"] and mm["loss"] >= 300:
            node.nags.add(chess.pgn.NAG_BLUNDER)
            best = g["pos"][mm["i"]]["pv"][:1]
            bstr = f" Besser war {num(bb, chess.Move.from_uci(best[0]))}." if best else ""
            node.comment = f"{num(bb, mv)}?? verliert {bauern(mm['loss'])} Bauern.{bstr}"
        elif mm["mine"] and mm["loss"] >= 100:
            node.nags.add(chess.pgn.NAG_MISTAKE)
        bb.push(mv)
    gm.headers["Result"] = g["h"]["Result"]
    out3.append(gm)
stats_out["Lektion 3"] = len(out3)
# ---- Lektion 4: Eröffnungsfehler als Partie ab Grundstellung, Korrektur als Hauptzug
out4 = []
def opening_key(t):
    g = games[t[0]]
    return (0 if g["me"] == chess.WHITE else 1, " ".join(g["uci"][:4]))
for gi, m, _, _ in sorted(cand[4], key=opening_key):
    g = games[gi]; b = g["boards"][m["i"]]; fen = b.fen()
    sol = solution(fen, m["move"])
    if not sol: continue
    best_u, best_cp, pv, also = sol
    pm = chess.Move.from_uci(m["move"])
    gm = chess.pgn.Game(); gm.headers.clear()
    start = line_de(chess.Board(), g["uci"], 4)
    gm.headers["Event"] = f"{'Weiß' if g['me'] == chess.WHITE else 'Schwarz'}: {start} · Fehler bei Zug {m['no']}"
    for k, v in meta_headers(g).items(): gm.headers[k] = v
    gm.headers["Aufgabe"] = "1"
    gm.comment = f"Spiele die Eröffnung nach. Bei Zug {m['no']} passierte der erste Fehler — was ist dort besser?"
    node = gm; bb = chess.Board()
    for u in g["uci"][:m["i"]]:
        node = node.add_variation(chess.Move.from_uci(u)); bb.push_uci(u)
    if m["i"] > 0:
        node.comment = f"Jetzt ist {side(bb)} am Zug: Hier kam der Fehler. Finde den besseren Zug!"
    node = node.add_variation(chess.Move.from_uci(best_u))
    node.comment = (f"Besser: {num(bb, chess.Move.from_uci(best_u))}. Gespielt wurde {num(bb, pm)}? "
                    f"(kostet {bauern(m['loss'])} Bauern)."
                    + (f" Auch gut: {', '.join(also)}." if also else ""))
    out4.append(gm)
stats_out["Lektion 4"] = len(out4)

lessons = [("01_Was-haengt", "Was hängt? – Patzer vermeiden", out1),
           ("02_Bestrafe-den-Fehler", "Bestrafe den Fehler des Gegners", out2),
           ("03_Gewinn-verwerten", "Gewinnstellung sicher verwerten", out3),
           ("04_Eroeffnungsfehler", "Meine Eröffnungsfehler", out4)]
for d, title, gs in lessons:
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
    open(os.path.join(OUT, d, "_meta.txt"), "w", encoding="utf-8").write(title + "\n")
    write(os.path.join(OUT, d, "0001_" + d.split("_", 1)[1] + ".pgn"), gs)
if not os.path.exists(os.path.join(OUT, "_meta.txt")):
    open(os.path.join(OUT, "_meta.txt"), "w", encoding="utf-8").write("Meine Partien\n")
print(stats_out)
