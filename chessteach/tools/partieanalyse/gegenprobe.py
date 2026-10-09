"""Stichprobe: Lösungen der Lektionen 1/2 bei Tiefe 22 gegen den Partiezug prüfen.

Aufruf: python3 gegenprobe.py <…/03_MeinePartien>
"""
import os, sys, re, random, chess, chess.pgn, chess.engine
sys.path.insert(0, os.environ.get("CHESSTEACH_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from multiprocessing import Pool
def items(path):
    out=[]; f=open(path,encoding="utf-8")
    while (g:=chess.pgn.read_game(f)):
        b=g.board(); sol=g.next().move; c=g.next().comment
        m=re.search(r"In der Partie geschah \d+\.(?:\.\.)?…?([^\s?]+)|In der Partie geschah \d+…([^\s?]+)", c)
        out.append((b.fen(), sol.uci(), (m.group(1) or m.group(2)) if m else None))
    return out
def chk(t):
    fen, sol, played_san = t
    e=chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    b=chess.Board(fen)
    import chessteach
    # deutsche SAN -> Zug
    pm=next((m for m in b.legal_moves if chessteach.san_de(b,m)==played_san),None)
    r={}
    for name,mv in (("sol",chess.Move.from_uci(sol)),("played",pm)):
        if mv is None: r[name]=None; continue
        i=e.analyse(b,chess.engine.Limit(depth=22),root_moves=[mv])
        r[name]=i["score"].relative.score(mate_score=100000)
    e.quit(); return fen, r
random.seed(1)
S=sys.argv[1]
sample=random.sample(items(S+"/01_Was-haengt/0001_Was-haengt.pgn"),20)+random.sample(items(S+"/02_Bestrafe-den-Fehler/0001_Bestrafe-den-Fehler.pgn"),20)
with Pool(os.cpu_count() or 4) as p: res=p.map(chk,sample)
bad=[(f,r) for f,r in res if r["played"] is None or r["sol"]-r["played"]<150]
print("geprüft",len(res),"Lösung >= 1,5 Bauern besser als Partiezug:",len(res)-len(bad))
for f,r in bad: print("  auffällig:",f,r)
