"""Stockfish-Bewertung aller Stellungen. Args: pgn out.json depth"""
import os, sys, json, chess, chess.pgn, chess.engine
from multiprocessing import Pool
PGN, OUT, DEPTH = sys.argv[1], sys.argv[2], int(sys.argv[3])

def load():
    games = []
    with open(PGN, encoding="utf-8") as f:
        while (g := chess.pgn.read_game(f)):
            games.append((dict(g.headers), [m.uci() for m in g.mainline_moves()]))
    return games

eng = None
def init():
    global eng
    eng = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    eng.configure({"Threads": 1, "Hash": 64})

def work(item):
    idx, (h, moves) = item
    b = chess.Board(h["FEN"]) if h.get("SetUp") == "1" and "FEN" in h else chess.Board()
    pos = []
    for i in range(len(moves) + 1):
        if b.is_game_over():
            sc = b.outcome()
            pos.append({"cp": None, "mate": 0, "pv": []})
        else:
            info = eng.analyse(b, chess.engine.Limit(depth=DEPTH))
            s = info["score"].white()
            pos.append({"cp": s.score(), "mate": s.mate(), "pv": [m.uci() for m in info.get("pv", [])[:8]]})
        if i < len(moves):
            b.push_uci(moves[i])
    return {"idx": idx, "headers": h, "moves": moves, "pos": pos}

if __name__ == "__main__":
    games = load()
    with Pool(os.cpu_count() or 4, initializer=init) as p:
        res = []
        for k, r in enumerate(p.imap_unordered(work, list(enumerate(games)), chunksize=2)):
            res.append(r)
            if k % 50 == 0: print(k, flush=True)
    res.sort(key=lambda r: r["idx"])
    json.dump(res, open(OUT, "w"))
    print("fertig", len(res))
