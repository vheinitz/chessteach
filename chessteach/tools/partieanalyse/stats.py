"""Kennzahlen aus der Engine-Bewertung (evals.json von run_engine.py).

Aufruf: python3 stats.py evals.json stats.json  — schreibt Kennzahlen und
stats_firsterr.json (Stellungen der ersten Fehler). Liefert außerdem classify()
für zusatzstatistik.py und lektionen_bauen.py.
"""
import os, json, sys, collections, statistics as st, chess
ME = os.environ.get("CHESS_ME", "Ich")  # eigener Name in der PGN (frischer Export: chess.com-Benutzername)
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAME = {chess.PAWN: "Bauer", chess.KNIGHT: "Springer", chess.BISHOP: "Läufer", chess.ROOK: "Turm", chess.QUEEN: "Dame"}
data = json.load(open(sys.argv[1]))

def material(b, color):
    return sum(VAL[p.piece_type] * (1 if p.color == color else -1) for p in b.piece_map().values())

def ev_white(p, b):
    if p["cp"] is None and p["mate"] in (0, None):
        if b.is_checkmate(): return -1000 if b.turn == chess.WHITE else 1000
        return 0
    if p["mate"] is not None:
        return 1000 if p["mate"] > 0 else -1000
    return max(-1000, min(1000, p["cp"]))

def pv_material(b, pv, color, plies=4):
    bb = b.copy(stack=False)
    for u in pv[:plies]:
        m = chess.Move.from_uci(u)
        if m not in bb.legal_moves: break
        bb.push(m)
    return material(bb, color)

def attacked_valuables(b, sq, victim_color):
    """Figuren von victim_color, die die Figur auf sq angreift (Wert >=3 oder König)."""
    res = []
    for t in b.attacks(sq):
        p = b.piece_at(t)
        if p and p.color == victim_color and (p.piece_type == chess.KING or VAL[p.piece_type] >= 3):
            res.append(p.piece_type)
    return res

games = []
for g in data:
    h = g["headers"]
    me = chess.WHITE if h["White"].lower() == ME.lower() else chess.BLACK
    r = h["Result"]
    res = "R" if r == "1/2-1/2" else ("S" if (r == "1-0") == (me == chess.WHITE) else "N")
    b = chess.Board()
    boards = [b.copy()]
    for u in g["moves"]:
        b.push_uci(u); boards.append(b.copy())
    sign = 1 if me == chess.WHITE else -1
    evs = [sign * ev_white(p, bd) for p, bd in zip(g["pos"], boards)]  # aus meiner Sicht
    moves = []
    for i, u in enumerate(g["moves"]):
        mover = boards[i].turn
        before = evs[i]; after = evs[i + 1]
        loss = (before - after) if mover == me else (after - before)  # Verlust des Ziehenden
        loss = max(0, loss)
        moves.append({"i": i, "mine": mover == me, "move": u, "loss": loss, "before": before,
                      "after": after, "no": boards[i].fullmove_number})
    myelo = int(h["WhiteElo" if me == chess.WHITE else "BlackElo"] or 0)
    opelo = int(h["BlackElo" if me == chess.WHITE else "WhiteElo"] or 0)
    games.append(dict(h=h, me=me, res=res, boards=boards, evs=evs, moves=moves, pos=g["pos"],
                      myelo=myelo, opelo=opelo, uci=g["moves"]))

def traj(b, pv, color, plies=8):
    """Material (Sicht color) nach jedem Halbzug der PV, plus Schlagzüge."""
    bb = b.copy(stack=False); vals = [material(bb, color)]; caps = []
    for u in pv[:plies]:
        m = chess.Move.from_uci(u)
        if m not in bb.legal_moves: break
        if bb.is_capture(m):
            v = bb.piece_at(m.to_square)
            caps.append((len(vals) - 1, bb.turn, v.piece_type if v else chess.PAWN, m.to_square))
        bb.push(m); vals.append(material(bb, color))
    return vals, caps

def classify(gm, mv):
    """Ursache eines eigenen Fehlers (Heuristik über die Engine-Hauptvariante)."""
    i = mv["i"]; B = gm["boards"][i]; A = gm["boards"][i + 1]; me = gm["me"]
    pB, pA = gm["pos"][i], gm["pos"][i + 1]
    m = chess.Move.from_uci(mv["move"])
    mateA = pA["mate"]
    if mateA is not None and mateA != 0 and ((mateA < 0) == (me == chess.WHITE)) and abs(mateA) <= 6:
        if not (pB["mate"] is not None and ((pB["mate"] < 0) == (me == chess.WHITE))):
            return "Matt zugelassen", None
    vals, caps = traj(A, pA["pv"], me)
    end_i = len(vals) - 1 if (len(vals) - 1) % 2 == 0 else len(vals) - 2  # nach meinem Antwortzug
    lost = vals[0] - vals[max(0, end_i)]
    reply = chess.Move.from_uci(pA["pv"][0]) if pA["pv"] else None
    if reply is not None and lost >= 2:
        opp_caps = [c for c in caps if c[1] != me]
        victim = max(opp_caps, key=lambda c: VAL[c[2]])[2] if opp_caps else None
        vname = NAME.get(victim) if victim else None
        if A.is_capture(reply):
            if reply.to_square == m.to_square:
                return "Gezogene Figur ungedeckt/ungünstig hingestellt", vname
            Bn = B.copy(stack=False); Bn.turn = not me
            if reply in Bn.pseudo_legal_moves and Bn.is_legal(reply) and B.piece_at(reply.to_square) == A.piece_at(reply.to_square):
                return "Bestehende Drohung übersehen (Figur stand schon angegriffen)", vname
            return "Deckung/Linie geöffnet – andere Figur hängt danach", vname
        A2 = A.copy(stack=False); A2.push(reply)
        if len(attacked_valuables(A2, reply.to_square, me)) >= 2:
            return "Gabel/Doppelangriff zugelassen", vname
        if A2.is_check():
            return "Schach mit Folgen übersehen (Königssicherheit)", vname
        return "Mehrzügige Taktik des Gegners übersehen", vname
    if pB["pv"]:
        bv, _ = traj(B, pB["pv"], me)
        e = len(bv) - 1 if (len(bv) - 1) % 2 == 1 else len(bv) - 2   # endet nach meinem Zug
        if e >= 1 and bv[e] - bv[0] >= 2 and mv["move"] != pB["pv"][0]:
            return "Materialgewinn nicht genommen (Gegner-Fehler nicht bestraft)", None
    if reply is not None:
        A2 = A.copy(stack=False); A2.push(reply)
        if A2.is_check() and mv["loss"] >= 300:
            return "Schach mit Folgen übersehen (Königssicherheit)", None
    return "Ohne direkten Materialverlust (Stellung/Entwicklung/Tempo)", None


def cls(loss):
    return "Patzer" if loss >= 300 else "Fehler" if loss >= 100 else "Ungenau" if loss >= 50 else None

out = collections.OrderedDict()
cnt = collections.Counter((g["res"]) for g in games)
out["Ergebnisse"] = dict(cnt)
out["Ergebnisse nach Farbe"] = {f'{"Weiß" if c else "Schwarz"}': dict(collections.Counter(g["res"] for g in games if g["me"] == c)) for c in (True, False)}
# Elo-Verlauf
el = [(g["h"]["Date"] + g["h"].get("EndTime", ""), g["myelo"]) for g in games if g["myelo"] and g["h"].get("TimeControl") == "300"]
el.sort()
out["Elo erste/letzte/min/max"] = (el[0], el[-1], min(e for _, e in el), max(e for _, e in el))
monthly = collections.defaultdict(list)
for d, e in el: monthly[d[:7]].append(e)
out["Elo-Verlauf (5 min) je 25 Partien"] = [round(st.mean(e for _, e in el[k:k+25])) for k in range(0, len(el), 25)]
out["Elo Monatsmittel"] = {k: round(st.mean(v)) for k, v in sorted(monthly.items())}
mres = collections.defaultdict(collections.Counter)
for g in games: mres[g["h"]["Date"][:7]][g["res"]] += 1
out["Ergebnis je Monat"] = {k: dict(v) for k, v in sorted(mres.items())}
# Elo-Differenz
bins = collections.defaultdict(collections.Counter)
for g in games:
    d = g["opelo"] - g["myelo"]
    k = "Gegner >100 stärker" if d > 100 else "Gegner 30-100 stärker" if d > 30 else "etwa gleich (±30)" if d >= -30 else "Gegner 30-100 schwächer" if d >= -100 else "Gegner >100 schwächer"
    bins[k][g["res"]] += 1
out["Ergebnis nach Elo-Differenz"] = {k: dict(v) for k, v in bins.items()}
# Partieende
term = collections.defaultdict(collections.Counter)
for g in games:
    t = g["h"]["Termination"]
    k = "Matt" if "Schachmatt" in t else "Aufgabe" if "Aufgabe" in t else "Zeit" if "auf Zeit" in t else "verlassen" if "verlassen" in t else "Remis"
    term[g["res"]][k] += 1
out["Partieende"] = {k: dict(v) for k, v in term.items()}
out["Partielänge Median (Züge) S/N"] = {r: st.median([len(g["uci"]) // 2 for g in games if g["res"] == r]) for r in "SNR"}

# Erster Fehler >= 1 Bauer in Niederlagen
sev_first = collections.Counter(); first = []; causes_first = collections.Counter(); victims_first = collections.Counter(); before_first = []
allcause = collections.Counter(); allvict = collections.Counter()
phase_err = collections.Counter(); phase_moves = collections.Counter()
for g in games:
    mine = [m for m in g["moves"] if m["mine"]]
    for m in mine:
        ph = "Eröffnung (Zug 1-10)" if m["no"] <= 10 else "Mittelspiel (11-30)" if m["no"] <= 30 else "Endspiel (>30)"
        phase_moves[ph] += 1
        if m["loss"] >= 100 and m["before"] > -500:
            phase_err[ph] += 1
            c, v = classify(g, m); allcause[c] += 1
            if v: allvict[v] += 1
    if g["res"] == "N":
        f = next((m for m in mine if m["loss"] >= 100), None)
        if f:
            first.append(f["no"]); before_first.append(f["before"])
            c, v = classify(g, f); causes_first[c] += 1; sev_first[cls(f["loss"])] += 1
            if v: victims_first[v] += 1
            g["first_err"] = f
nl = sum(1 for g in games if g["res"] == "N")
out["Niederlagen mit Fehler>=1"] = f"{len(first)} von {nl}"
hist = collections.Counter()
for n in first:
    k = "1-5" if n <= 5 else "6-10" if n <= 10 else "11-15" if n <= 15 else "16-20" if n <= 20 else "21-30" if n <= 30 else ">30"
    hist[k] += 1
out["Erster Fehler – Zugnummer"] = {k: hist[k] for k in ["1-5", "6-10", "11-15", "16-20", "21-30", ">30"]}
out["Erster Fehler – Median Zug"] = st.median(first)
out["Erster Fehler – Stellung davor (meine Sicht)"] = {
    "ich besser (>+1)": sum(b > 100 for b in before_first), "ausgeglichen": sum(-100 <= b <= 100 for b in before_first),
    "ich schon schlechter (<-1)": sum(b < -100 for b in before_first)}
out["Erster Fehler – Schwere"] = dict(sev_first)
out["Erster Fehler – Ursache"] = dict(causes_first.most_common())
out["Erster Fehler – verlorene Figur"] = dict(victims_first.most_common())
out["Alle Fehler>=1 (Stellung nicht schon verloren) – Ursache"] = dict(allcause.most_common())
out["Alle Fehler – verlorene Figur"] = dict(allvict.most_common())
out["Fehlerquote je Phase (Fehler je 100 eigene Züge)"] = {k: round(100 * phase_err[k] / phase_moves[k], 1) for k in phase_moves}

# Fehler pro Partie, Patzer pro Partie
def per_game(g, who_mine, thr):
    return sum(1 for m in g["moves"] if m["mine"] == who_mine and m["loss"] >= thr)
for r in "SN":
    gs = [g for g in games if g["res"] == r]
    out[f"Ø Patzer(>=3) je Partie [{r}] ich/Gegner"] = (round(st.mean(per_game(g, True, 300) for g in gs), 2),
                                                     round(st.mean(per_game(g, False, 300) for g in gs), 2))
# Durchschnittlicher Verlust (ACPL) – auf ±10 gekappt
acpl = {r: round(st.mean(st.mean([m["loss"] for m in g["moves"] if m["mine"]] or [0]) for g in games if g["res"] == r)) for r in "SNR"}
out["ACPL (Ø Bauernverlust×100 je Zug, gekappt) S/N/R"] = acpl

# Siege: wer patzt zuerst?
wins = [g for g in games if g["res"] == "S"]
def first_blunder(g, mine, thr=300):
    return next((m["i"] for m in g["moves"] if m["mine"] == mine and m["loss"] >= thr and abs(m["before"]) < 500), None)
w_cat = collections.Counter()
for g in wins:
    o = first_blunder(g, False); s = first_blunder(g, True)
    if "verlassen" in g["h"]["Termination"] and (o is None):
        w_cat["Gegner hat verlassen, ohne vorherigen Patzer"] += 1
    elif o is None:
        w_cat["Ohne gegnerischen Patzer gewonnen (Druck/Technik/Zeit)"] += 1
    elif s is None or o < s:
        w_cat["Gegner patzt zuerst, ich verwerte"] += 1
    else:
        w_cat["Ich patze zuerst, Gegner patzt zurück (Comeback)"] += 1
out["Siege – Entstehung"] = dict(w_cat.most_common())
loss_cat = collections.Counter()
for g in [g for g in games if g["res"] == "N"]:
    o = first_blunder(g, False); s = first_blunder(g, True)
    if s is None: loss_cat["Ohne eigenen Patzer verloren (schleichend/Zeit)"] += 1
    elif o is None or s < o: loss_cat["Ich patze zuerst"] += 1
    else: loss_cat["Gegner patzt zuerst, ich gebe es zurück"] += 1
out["Niederlagen – Entstehung"] = dict(loss_cat.most_common())
# Verwertung
conv = collections.Counter(); comeback = collections.Counter()
for g in games:
    mx = max(g["evs"][:-1] or [0]); mn = min(g["evs"][:-1] or [0])
    if mx >= 500: conv[g["res"]] += 1
    if mn <= -500: comeback[g["res"]] += 1
out["Partien mit eigenem Vorteil >=+5 → Ergebnis"] = dict(conv)
out["Partien mit eigenem Nachteil <=-5 → Ergebnis"] = dict(comeback)
# verpasste Matts / verpasster Materialgewinn nach Gegner-Patzer
missed_mate = 0; had_mate = 0; punish = collections.Counter()
for g in games:
    for m in g["moves"]:
        if not m["mine"]: continue
        p = g["pos"][m["i"]]
        if p["mate"] and ((p["mate"] > 0) == (g["me"] == chess.WHITE)) and abs(p["mate"]) <= 2:
            had_mate += 1
            if m["move"] != (p["pv"][0] if p["pv"] else None) and m["loss"] >= 100: missed_mate += 1
    for k, m in enumerate(g["moves"]):
        if not m["mine"] and m["loss"] >= 300 and abs(m["before"]) < 500 and k + 1 < len(g["moves"]):
            nxt = g["moves"][k + 1]
            punish["bestraft" if nxt["loss"] < 100 else "nicht bestraft"] += 1
out["Matt in 1-2 möglich: Stellungen / nicht gespielt"] = (had_mate, missed_mate)
out["Gegner-Patzer (>=3): sofort bestraft?"] = dict(punish)

# Eröffnungen
def seq(g, n):
    b = chess.Board(); s = []
    for u in g["uci"][:n]:
        mv = chess.Move.from_uci(u); s.append(b.san(mv)); b.push(mv)
    return " ".join(s)
for color, lab in ((chess.WHITE, "Weiß"), (chess.BLACK, "Schwarz")):
    gs = [g for g in games if g["me"] == color]
    for n in (1, 2, 4):
        c = collections.defaultdict(collections.Counter)
        for g in gs: c[seq(g, n)][g["res"]] += 1
        top = sorted(c.items(), key=lambda kv: -sum(kv[1].values()))[:10]
        out[f"Eröffnung als {lab}, erste {n} Halbzüge"] = {k: f'{sum(v.values())} Partien: {v["S"]}S {v["N"]}N {v["R"]}R ({round(100*(v["S"]+0.5*v["R"])/sum(v.values()))}%)' for k, v in top}
    # Bewertung nach Zug 10
    ev10 = collections.defaultdict(list)
    for g in gs:
        if len(g["evs"]) > 20: ev10[seq(g, 2)].append(g["evs"][20])
    out[f"Ø Bewertung nach Zug 10 als {lab} (meine Sicht), je Anfang"] = {k: (len(v), round(st.mean(v) / 100, 1)) for k, v in sorted(ev10.items(), key=lambda kv: -len(kv[1]))[:8]}
# Damenverlust früh
qloss = 0
for g in games:
    for m in g["moves"]:
        if m["mine"] and m["loss"] >= 300 and m["no"] <= 15:
            c, v = classify(g, m)
            if v == "Dame": qloss += 1
out["Dame eingestellt bis Zug 15 (Anzahl)"] = qloss
# frühe Damenausflüge: eigene Dame zieht vor Zug 5
qe = collections.Counter()
for g in games:
    b = chess.Board(); early = False
    for i, u in enumerate(g["uci"][:10]):
        mv = chess.Move.from_uci(u)
        if b.turn == g["me"] and b.piece_at(mv.from_square).piece_type == chess.QUEEN: early = True
        b.push(mv)
    qe[("Dame früh (bis Zug 5)" if early else "Dame nicht früh", g["res"])] += 1
out["Früher Damenzug vs. Ergebnis"] = {f"{k[0]} {k[1]}": v for k, v in sorted(qe.items())}
# Rochade
ro = collections.Counter()
for g in games:
    b = chess.Board(); castled = None
    for u in g["uci"]:
        mv = chess.Move.from_uci(u)
        if b.turn == g["me"] and b.is_castling(mv) and castled is None: castled = b.fullmove_number
        b.push(mv)
    k = "keine Rochade" if castled is None else "Rochade bis Zug 10" if castled <= 10 else "Rochade nach Zug 10"
    ro[(k, g["res"])] += 1
out["Rochade vs. Ergebnis"] = {f"{k[0]} {k[1]}": v for k, v in sorted(ro.items())}
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
# Beispiel-Stellungen der ersten Fehler sichern
ex = [{"fen": g["boards"][g["first_err"]["i"]].fen(), "move": g["first_err"]["move"], "no": g["first_err"]["no"],
       "best": g["pos"][g["first_err"]["i"]]["pv"][:1], "loss": g["first_err"]["loss"], "cause": classify(g, g["first_err"]),
       "opp": g["h"]["White"] if g["me"] == chess.BLACK else g["h"]["Black"], "date": g["h"]["Date"]} for g in games if g.get("first_err")]
json.dump(ex, open(sys.argv[2].replace(".json", "_firsterr.json"), "w"), ensure_ascii=False, indent=1)
