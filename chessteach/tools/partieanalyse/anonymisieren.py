"""Spielernamen in allen PGNs eines Verzeichnisses anonymisieren: eigener Name -> „Ich“, Gegner -> „Gegner“.

Aufruf: CHESS_ME=<Benutzername> python3 anonymisieren.py <verzeichnis>
Betrifft White/Black/Termination und Kommentare; Züge bleiben unverändert.
"""
import os, sys, glob, re, chess.pgn
ME = os.environ["CHESS_ME"]
def fix(text, opp):
    for name, who in ((ME, "Ich"), (opp, "Gegner")):
        if not name: continue
        n = re.escape(name)
        if who == "Ich":
            text = re.sub(n + r" gewinnt", "Ich gewinne", text, flags=re.I)
            text = re.sub(n + r" hat gewonnen", "Ich habe gewonnen", text, flags=re.I)
        text = re.sub(n, who, text, flags=re.I)
    return text.replace("ich gewinnt", "ich gewinne")
opps = set()
for p in glob.glob(sys.argv[1] + "/**/*.pgn", recursive=True):
    out = []
    with open(p, encoding="utf-8") as f:
        while (g := chess.pgn.read_game(f)):
            w, b = g.headers.get("White", ""), g.headers.get("Black", "")
            opp = b if w.lower() == ME.lower() else w
            opps.add(opp)
            for k in list(g.headers.keys()):
                g.headers[k] = fix(g.headers[k], opp)
            g.comment = fix(g.comment, opp)
            for node in g.mainline():
                node.comment = fix(node.comment, opp)
            out.append(g)
    with open(p, "w", encoding="utf-8") as f:
        for g in out: print(g, file=f, end="\n\n")
    print(p.split("/")[-1], len(out))
