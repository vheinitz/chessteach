"""Wandelt ein Schachbuch (PDF mit Textebene) in das Lese-Format von ChessTeach um.

Text bleibt Text; jede Zugfolge wird gegen eine Stellung aufgelöst und im Lesemodus
anklickbar. Zugfolgen, die mitten in einer Partie beginnen („23... h4“, „Если 23. Ф:h5“),
werden an die zuletzt vollständig notierte Partie angehängt (Partiebaum), sodass jeder
Zug von der Ausgangsstellung aus nachspielbar ist.

  python3 tools/buecher/pdf_buch.py <buch.pdf> <ausgabe-verz> --seiten 16-31 [--titel …]

Ergebnis: <ausgabe-verz>/buch.json (Lesemodus), abbildungen/*.png (Schemata, die keine
Stellung zeigen) und bericht.md (vermutete Druckfehler, nicht auflösbare Züge, Diagramme,
die nicht zur Notation passen). Vermutete Druckfehler werden ersetzt und im Lesemodus mit
dem Buchtext daneben gezeigt. Buchspezifisches (Schriften, Figurine, Diagramm-Glyphen,
Spaltenrinne) steht in PROFIL; vorerst nur für die russische Nimzowitsch-Ausgabe
„Моя система“ (Kalinichenko 2020) ermittelt. Deren vier Werke (PDF-Seiten):
Моя система 16-305, Моя система на практике 309-553, Шахматная блокада 556-597,
Как я стал гроссмейстером 600-640.
"""
import argparse, collections, json, os, re, sys
import chess
import pdfplumber

# --- Buchprofil ------------------------------------------------------------------------
PROFIL = {
    "kopf_bis": 35,                 # laufender Kolumnentitel + Seitenzahl oberhalb
    "rinne": (205.5, 211.3),        # Lücke zwischen den Spalten (zweispaltiger Satz)
    "spalte_links": [49, 211.7],    # linker Rand je Spalte (Einzug = Absatzbeginn)
    # ISChess-Figurine: Buchstabe der Glyphe -> Figur
    "figurine": {"C": chess.KNIGHT, "E": chess.BISHOP, "G": chess.ROOK,
                 "I": chess.QUEEN, "K": chess.KING},
    # Chess-Merida-Glyphen der Diagramme: Glyph -> Figur (Groß = Weiß) bzw. "." leer.
    # Am Buch selbst ermittelt (Diagramme gegen nachgespielte Partien); fehlende werden
    # beim Lauf aus passenden Partiestellungen gelernt und im Bericht genannt.
    "glyphen": {"(cid:6)": ".", "(cid:9)": ".", "(cid:7)": "k", "(cid:8)": "r",
                "(cid:11)": "p", "(cid:12)": "q", "(cid:13)": "P", "(cid:14)": "R",
                "(cid:15)": "n", "(cid:16)": "p", "(cid:17)": "R", "(cid:18)": "B",
                "(cid:19)": "Q", "(cid:20)": "P", "(cid:21)": "K", "(cid:25)": "b",
                "(cid:26)": "q", "(cid:27)": "b", "(cid:28)": "B", "(cid:29)": "N",
                # beim Lauf über S. 16–305 gelernt (Diagramm = Partiestellung bis auf diese Felder)
                " ": "k", "!": "n", "(cid:31)": "N", "(cid:30)": "Q", '"': "K"},
    "rahmen": {"(cid:2)", "(cid:3)", "(cid:4)", "(cid:5)", "(cid:10)",
               "(cid:22)", "(cid:23)", "(cid:24)"},
    "feld": 14.0,                   # Kantenlänge eines Diagrammfelds in pt
    # Eine Figur fehlt im Diagramm-Font und ist als Vektorgrafik gesetzt (S. 5, 19 …):
    # stets der schwarze Turm auf dunklem Feld.
    "vektor_figur": "r",
    "fussnote_unter": 9.5,          # Schriftgröße (pt), darunter Fußnote (nur Fließtextschrift)
}
FIG = {chess.KNIGHT: "♘", chess.BISHOP: "♗", chess.ROOK: "♖", chess.QUEEN: "♕", chess.KING: "♔"}
FIG_TYPE = {v: k for k, v in FIG.items()}
# kyrillische Buchstaben, die im Satz statt lateinischer Linien stehen („3. е5 с5“)
LOOKALIKE = str.maketrans({"а": "a", "с": "c", "е": "e", "в": "b", "О": "O", "о": "o", "х": "x"})
VAR_CUES = re.compile(r"(если|на|или|после|вместо|лучше|сильнее|случае|грозил|угрожал|"
                      r"следовало|могло|можно|\()\W*$", re.I)


# --- 1. PDF -> Zeilen pro Spalte -------------------------------------------------------
def style_of(font):
    f = font.split("+")[-1]
    if "ISChess" in f:
        return "fig"
    if "Merida" in f:
        return "dia"
    if f.startswith("JournalC-Bold"):
        return "b"
    if f.startswith("JournalC-Italic"):
        return "i"
    if f.startswith("JournalC") or f.startswith("TimesNew") or f.startswith("Newton"):
        return "n"
    return "h"                      # AvantGarde, Futura, Pragmatica: Überschriften, Köpfe


def page_items(page):
    """Seite -> (Abschnitte in Lesereihenfolge, Fußnotenzeilen).

    Abschnitt = (linker Rand, Zeilen [(top, x0, [(char, style, x0, x1)])], Diagramme, Abbildungen).
    Die Seite ist meist zweispaltig, Einleitungen und Kapitelköpfe laufen aber über die ganze
    Breite. Daher wird zeilenweise entschieden: Zweispaltiger Satz lässt zwischen den Spalten
    eine Lücke von knapp 6 pt (PROFIL „rinne“), Text über die ganze Breite füllt sie bis auf
    Wortabstände (~2 pt)."""
    figs = figure_regions(page)
    body, foot = [], []
    for c in page.chars:
        if c["top"] < PROFIL["kopf_bis"]:
            continue
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        if any(f["x0"] <= cx <= f["x1"] and f["top"] <= cy <= f["bottom"] for f in figs):
            continue                # Text im Schema steckt im Bild
        st = style_of(c["fontname"])
        # Fußnoten: kleiner Fließtext über die ganze Seitenbreite; kleine AvantGarde-Zeilen
        # sind dagegen Partieköpfe („Рига, 1910“) und gehören in den Text
        if c["size"] < PROFIL["fussnote_unter"] and st in ("n", "i", "b", "fig"):
            foot.append(c)
            continue
        body.append(c)
    a, b = PROFIL["rinne"]
    mid = (a + b) / 2
    rows = text_rows([c for c in body if style_of(c["fontname"]) != "dia"])
    cls = []
    for i, (top, x0, chars) in enumerate(rows):
        left = any((x0_ + x1_) / 2 < mid for _, _, x0_, x1_ in chars)
        right = any((x0_ + x1_) / 2 >= mid for _, _, x0_, x1_ in chars)
        if left and right:
            cls.append("breit" if max_gap(chars, a, b) < 3.5 else "spalten")
        elif left and cls and cls[-1] == "breit" and top - rows[i - 1][0] <= 15:
            cls.append("breit")     # kurze Schlusszeile eines breiten Absatzes
        else:
            cls.append("spalten")
    bands = []                      # [art, top, Zeilen]
    for row, k in zip(rows, cls):
        if bands and bands[-1][0] == k:
            bands[-1][2].append(row)
        else:
            bands.append([k, row[0], [row]])
    if not bands:
        bands = [["spalten", 0, []]]
    dias = []
    for side in (0, 1):             # Diagramme stehen je Spalte oder mittig
        dias += diagrams([c for c in body if style_of(c["fontname"]) == "dia"
                          and (((c["x0"] + c["x1"]) / 2 < mid) == (side == 0))], page.curves)

    def band_of(top):
        k = 0
        for i, bd in enumerate(bands):
            if bd[1] <= top + 2:
                k = i
        return k
    segs = []
    for i, (kind, _, brows) in enumerate(bands):
        bd = [d for d in dias if band_of(d["top"]) == i]
        bf = [f for f in figs if band_of(f["top"]) == i]
        if kind == "breit":
            segs.append((PROFIL["spalte_links"][0], brows, bd, bf))
            continue
        for side in (0, 1):
            def mine(x0, x1, side=side):
                return ((x0 + x1) / 2 < mid) == (side == 0)
            srows = []
            for top, x0, chars in brows:
                cs = [c for c in chars if mine(c[2], c[3])]
                if cs:
                    srows.append((top, cs[0][2], cs))
            sd = [d for d in bd if mine(d["x0"], d["x0"] + 10 * PROFIL["feld"])]
            sf = [f for f in bf if mine(f["x0"], f["x1"]) or f["x0"] < mid < f["x1"] and side == 0]
            segs.append((PROFIL["spalte_links"][side], srows, sd, sf))
    return segs, text_rows(foot)


def max_gap(chars, a, b):
    """Größte von keinem Zeichen bedeckte Strecke im Bereich [a, b]."""
    iv = sorted((max(x0, a), min(x1, b)) for _, _, x0, x1 in chars if x1 > a and x0 < b)
    pos, gap = a, 0.0
    for x0, x1 in iv:
        gap = max(gap, x0 - pos)
        pos = max(pos, x1)
    return max(gap, b - pos)


def figure_regions(page):
    """Schemata (Kästen mit Text, z. B. „Схема к главе …“): Gruppen von Rechtecken -> Bildbereiche."""
    rects = sorted((r for r in page.rects if r["height"] > 5 and r["width"] > 20),
                   key=lambda r: r["top"])
    groups = []
    for r in rects:
        if groups and r["top"] - groups[-1]["bottom"] < 30:
            g = groups[-1]
            g.update(x0=min(g["x0"], r["x0"]), x1=max(g["x1"], r["x1"]),
                     bottom=max(g["bottom"], r["bottom"]))
            g["n"] += 1
        else:
            groups.append({"x0": r["x0"], "x1": r["x1"], "top": r["top"], "bottom": r["bottom"], "n": 1})
    pad = 3
    return [{"x0": g["x0"] - pad, "x1": g["x1"] + pad, "top": g["top"] - pad,
             "bottom": g["bottom"] + pad} for g in groups if g["n"] >= 2]


def text_rows(txt):
    """Zeichen -> Zeilen [(top, x0, [(char, style, x0, x1)])], nach Grundlinie gruppiert."""
    lines = []
    for c in sorted(txt, key=lambda c: (c["bottom"], c["x0"])):
        st = style_of(c["fontname"])
        base = c["bottom"] + (1.8 if st == "fig" else 0)   # Figurine sitzen höher
        for ln in lines:
            if abs(ln["base"] - base) < 3.5:
                ln["chars"].append(c)
                break
        else:
            lines.append({"base": base, "chars": [c]})
    rows = []
    for ln in lines:
        cs = sorted(ln["chars"], key=lambda c: c["x0"])
        rows.append((min(c["top"] for c in cs), cs[0]["x0"],
                     [(c["text"], style_of(c["fontname"]), c["x0"], c["x1"]) for c in cs]))
    rows.sort()
    return rows


def diagrams(chars, curves=()):
    """Merida-Zeichen einer Spalte -> Liste von (top, bottom, placement|None, unbekannte Glyphen)."""
    if not chars:
        return []
    chars = sorted(chars, key=lambda c: c["top"])
    groups, cur = [], [chars[0]]
    for c in chars[1:]:
        if c["top"] - cur[-1]["top"] > PROFIL["feld"] * 1.6:
            groups.append(cur)
            cur = [c]
        else:
            cur.append(c)
    groups.append(cur)
    res = []
    for g in groups:
        x0 = min(c["x0"] for c in g)
        y0 = min(c["top"] for c in g)
        grid = [["?"] * 8 for _ in range(8)]
        unknown = {}
        for c in g:
            f = round((c["x0"] - x0) / PROFIL["feld"]) - 1
            r = round((c["top"] - y0) / PROFIL["feld"]) - 1
            if not (0 <= f < 8 and 0 <= r < 8) or c["text"] in PROFIL["rahmen"]:
                continue
            sym = PROFIL["glyphen"].get(c["text"])
            if sym is None:
                unknown[(r, f)] = c["text"]
                sym = "?"
            grid[r][f] = sym
        # Felder ohne Zeichen: Figur als Vektorgrafik gezeichnet, sonst leer
        vec = set()
        for cv in curves:
            f = int(((cv["x0"] + cv["x1"]) / 2 - x0) // PROFIL["feld"]) - 1
            r = int(((cv["top"] + cv["bottom"]) / 2 - y0) // PROFIL["feld"]) - 1
            if 0 <= f < 8 and 0 <= r < 8:
                vec.add((r, f))
        for r in range(8):
            for f in range(8):
                if grid[r][f] == "?" and (r, f) not in unknown:
                    grid[r][f] = PROFIL["vektor_figur"] if (r, f) in vec else "."
        res.append({"top": y0, "bottom": max(c["bottom"] for c in g), "grid": grid,
                    "unknown": unknown, "x0": x0})
    return res


def grid_placement(grid):
    rows = []
    for r in grid:
        s, n = "", 0
        for x in r:
            if x in ".?":
                n += 1
            else:
                s += (str(n) if n else "") + x
                n = 0
        rows.append(s + (str(n) if n else ""))
    return "/".join(rows)


# --- 2. Zeilen -> Blöcke (Absätze, Überschriften, Diagramme) ---------------------------
def line_text(chars):
    """Zeichen einer Zeile -> Liste (text, style); Figurine werden zu ♘♗♖♕♔."""
    out, prev = [], None
    for ch, st, x0, x1 in chars:
        if st == "fig":
            t = PROFIL["figurine"].get(ch)
            ch, st = (FIG[t], "fig") if t else (ch, "n")
        if prev is not None and x0 - prev > 1.2 and ch != " ":
            out.append((" ", st))
        out.append((ch, st))
        prev = x1
    return out


def blocks_of(pdf, first, last):
    blocks = []
    for pn in range(first, last + 1):
        page = pdf.pages[pn - 1]
        segs, foot = page_items(page)
        for left, rows, dias, figs in segs:
            events = [("line", r[0], r) for r in rows] + [("dia", d["top"], d) for d in dias] \
                + [("bild", f["top"], f) for f in figs]
            events.sort(key=lambda e: e[1])
            last_bottom = None
            for kind, top, obj in events:
                if kind == "dia":
                    blocks.append({"type": "dia", "page": pn, **obj})
                    last_bottom = obj["bottom"]
                    continue
                if kind == "bild":
                    blocks.append({"type": "bild", "page": pn,
                                   "bbox": [obj["x0"], obj["top"], obj["x1"], obj["bottom"]]})
                    last_bottom = obj["bottom"]
                    continue
                _, x0, chars = obj
                runs = line_text(chars)
                text = "".join(c for c, s in runs).strip()
                if not text:
                    continue
                styles = collections.Counter(s for c, s in runs if not c.isspace())
                main_style = styles.most_common(1)[0][0]
                if main_style == "fig":
                    main_style = "n"
                cyr = sum(1 for c in text if "а" <= c.lower() <= "я" or c in "ёЁ")
                if main_style == "b" and cyr > 0.6 * len(text.replace(" ", "")):
                    main_style = "h"            # fette Zwischenüberschrift, keine Züge
                if main_style == "h" or (main_style == "i" and styles["n"] == 0
                                          and styles["b"] == 0):
                    kind2 = "cap" if blocks and blocks[-1]["type"] in ("dia", "cap") \
                        and last_bottom is not None and top - last_bottom < 40 else "h"
                    if text.isdigit() and len(text) <= 3:
                        blocks.append({"type": "dianr", "page": pn, "text": text, "top": top})
                        continue
                    if blocks and blocks[-1]["type"] == kind2 and blocks[-1]["page"] == pn \
                            and last_bottom is not None and top - last_bottom < 20:
                        prev_txt = "".join(c for c, _ in blocks[-1]["runs"]).rstrip()
                        if prev_txt.endswith("-") or text[:1].islower():
                            join_line(blocks[-1]["runs"], runs)   # umbrochener Satz am Rand
                        else:
                            blocks[-1]["runs"] += [("\n", "h")] + runs
                    else:
                        blocks.append({"type": kind2, "page": pn, "runs": runs})
                    last_bottom = obj[0] + 10
                    continue
                gap = (top - last_bottom) if last_bottom is not None else 0
                # Fortsetzung gehört zum letzten Absatz, nicht zur Fußnote der Vorseite
                prev = next((b for b in reversed(blocks) if not b.get("fn")), None)
                new_par = (x0 - left > 6) or gap > 9 or not prev or prev["type"] != "p"
                if new_par:
                    blocks.append({"type": "p", "page": pn, "runs": runs})
                else:
                    join_line(prev["runs"], runs)
                last_bottom = top + 10
        fn = None
        for top, x0, chars in foot:
            runs = line_text(chars)
            text = "".join(c for c, s in runs).strip()
            if not text:
                continue
            if text.startswith("*") or fn is None:
                fn = {"type": "p", "page": pn, "runs": runs, "fn": True}
                blocks.append(fn)
            else:
                join_line(fn["runs"], runs)
    return blocks


def join_line(runs, nxt):
    """Zeile anhängen; Silbentrennung auflösen, aber „g7-“ + „g5“ (lange Notation) erhalten."""
    while runs and runs[-1][0] == " ":
        runs.pop()
    tail = "".join(c for c, s in runs[-4:])
    head = "".join(c for c, s in nxt[:3]).lstrip()
    if tail.endswith("-") and not tail.endswith("--"):
        if re.search(r"[a-h][1-8]-$", tail.translate(LOOKALIKE)) and re.match(r"[a-h♘♗♖♕♔]", head.translate(LOOKALIKE)) \
                or re.search(r"[0OО]-$", tail) and re.match(r"[0OО]", head):
            runs.extend(nxt)        # lange Notation über den Zeilenumbruch
            return
        if re.search(r"\w-$", tail) and head[:1].islower():
            runs.pop()              # Silbentrennung
            runs.extend(nxt)
            return
    runs.append((" ", runs[-1][1] if runs else "n"))
    runs.extend(nxt)


# --- 3. Züge erkennen ------------------------------------------------------------------
NUM = re.compile(r"(?<![\w.])(\d{1,3})\s?(\.\s?\.\s?\.|…|\.)\s*")
SQ = r"[a-h][1-8]"
MOVE = re.compile(
    r"(?P<castle>[0OО]-[0OО](?:-[0OО])?)"
    r"|(?P<long>(?P<lp>[♘♗♖♕♔])?(?P<lfrom>" + SQ + r")[-:x](?P<lto>" + SQ + r")(?:=?(?P<lpromo>[♘♗♖♕]))?)"
    r"|(?P<piece>(?P<pp>[♘♗♖♕♔])(?P<pdis>[a-h]?[1-8]?)(?P<pcap>[:x])?(?P<pto>" + SQ + r"))"
    r"|(?P<capsq>[:x](?P<cto>" + SQ + r"))"
    r"|(?P<pawn>(?P<pf>[a-h])(?P<pwcap>[:x])?(?P<pwto>" + SQ + r"|[a-h](?![a-z]))(?:=?(?P<promo>[♘♗♖♕]))?)"
    r"|(?P<pawnto>(?P<ptsq>" + SQ + r")(?:=?(?P<ppromo>[♘♗♖♕]))?)"
)
LONG_ALONE = re.compile(r"[♘♗♖♕♔]?[a-h][1-8][-:x][a-h][1-8]")
SUFFIX = re.compile(r"[+#]?(?:!!|\?\?|!\?|\?!|!|\?)?\+?")


def find_move(s, i):
    """Ab Index i einen Zug lesen -> (match, ende inkl. Zusatzzeichen) oder None."""
    m = MOVE.match(s, i)
    if not m:
        return None
    end = m.end()
    if end < len(s) and (s[end].isalnum() and not s[end].isdigit()):
        if not (m.group("pawn") and s[end] in "♘♗♖♕"):
            return None             # Teil eines Wortes, z. B. „cdef“
    if end < len(s) and s[end].isdigit():
        return None
    suf = SUFFIX.match(s, end)
    return m, suf.end()


def candidates(board, m, prev_piece, check=False):
    """Legale Züge, die zum Zugtext passen. Figurenzüge: „:“ genau dann, wenn geschlagen
    wird; „+“ nur bei Schachgebot. Sonst zu viele Zufallstreffer in fremden Stellungen."""
    res = _candidates(board, m, prev_piece)
    if check and board.king(not board.turn) is not None:    # Textstellungen ohne König
        res = [mv for mv in res if board.gives_check(mv)]
    return res


def _candidates(board, m, prev_piece):
    legal = list(board.legal_moves)
    g = m.groupdict()
    if g["castle"]:
        long_ = g["castle"].count("-") == 2
        return [mv for mv in legal if board.is_castling(mv)
                and (chess.square_file(mv.to_square) == 2) == long_]
    if g["long"]:
        fr, to = chess.parse_square(g["lfrom"]), chess.parse_square(g["lto"])
        res = [mv for mv in legal if mv.from_square == fr and mv.to_square == to]
        if ":" in g["long"] or "x" in g["long"]:
            res = [mv for mv in res if board.is_capture(mv)]
        if g["lpromo"]:
            res = [mv for mv in res if mv.promotion == FIG_TYPE[g["lpromo"]]]
        elif len(res) > 1:
            res = [mv for mv in res if mv.promotion in (None, chess.QUEEN)]
        return res
    if g["piece"]:
        pt = FIG_TYPE[g["pp"]]
        to = chess.parse_square(g["pto"])
        dis = g["pdis"] or ""
        res = []
        for mv in legal:
            p = board.piece_at(mv.from_square)
            if p.piece_type != pt or mv.to_square != to:
                continue
            if bool(g["pcap"]) != board.is_capture(mv):
                continue
            if any(ch in "abcdefgh" and chess.square_file(mv.from_square) != "abcdefgh".index(ch)
                   or ch in "12345678" and chess.square_rank(mv.from_square) != int(ch) - 1
                   for ch in dis):
                continue
            res.append(mv)
        return res
    if g["capsq"]:                  # „:f4“ – Figur wie im Zug davor
        to = chess.parse_square(g["cto"])
        res = [mv for mv in legal if mv.to_square == to and board.is_capture(mv)]
        if len(res) > 1 and prev_piece:
            res = [mv for mv in res if board.piece_at(mv.from_square).piece_type == prev_piece] or res
        return res
    if g["pawn"]:
        ff = "abcdefgh".index(g["pf"])
        to = g["pwto"]
        res = []
        for mv in legal:
            p = board.piece_at(mv.from_square)
            if p.piece_type != chess.PAWN or chess.square_file(mv.from_square) != ff:
                continue
            if len(to) == 1:        # „cd“: Bauer c schlägt auf Linie d
                if chess.square_file(mv.to_square) != "abcdefgh".index(to) or not board.is_capture(mv):
                    continue
            elif mv.to_square != chess.parse_square(to):
                continue
            if chess.square_file(mv.to_square) == ff:
                continue            # Linie gleich = kein Schlagzug, dann wäre es „pawnto“
            res.append(mv)
        promo = g["promo"]
        res = [mv for mv in res if mv.promotion == (FIG_TYPE[promo] if promo else mv.promotion)]
        if not promo:
            res = [mv for mv in res if mv.promotion in (None, chess.QUEEN)]
        return res
    if g["pawnto"]:
        to = chess.parse_square(g["ptsq"])
        res = [mv for mv in legal if mv.to_square == to
               and board.piece_at(mv.from_square).piece_type == chess.PAWN
               and chess.square_file(mv.from_square) == chess.square_file(to)
               and not board.is_capture(mv)]
        promo = g["ppromo"]
        if promo:
            res = [mv for mv in res if mv.promotion == FIG_TYPE[promo]]
        else:
            res = [mv for mv in res if mv.promotion in (None, chess.QUEEN)]
        return res
    return []


def scan(text):
    """Absatztext -> Liste von Teilen: str (Text) oder dict(Zugfolge-Fragment)."""
    norm = text.translate(LOOKALIKE)
    parts, i, last = [], 0, 0
    while i < len(norm):
        nm = NUM.match(norm, i)
        if not nm or (i > 0 and (norm[i - 1].isalnum())):
            lm = LONG_ALONE.match(norm, i)
            if lm and (i == 0 or not norm[i - 1].isalnum()):
                fm = find_move(norm, i)
                if fm and fm[0].group("long"):
                    m, e = fm
                    if i > last:
                        parts.append(text[last:i])
                    parts.append({"num": None, "black": None, "start": i, "end": e,
                                  "text": text[i:e], "before": text[max(0, i - 40):i],
                                  "moves": [{"m": m, "a": i, "e": e, "txt": text[i:e]}]})
                    last = i = e
                    continue
            i += 1
            continue
        frag = {"num": int(nm.group(1)), "black": nm.group(2) != ".", "moves": [], "start": i}
        j = nm.end()
        black = frag["black"]
        while True:
            k = j
            while k < len(norm) and norm[k] in " .…":
                k += 1                                   # „23. . .g4“, „8...I:d5“
            # neue Zugnummer mitten in der Folge
            nm2 = NUM.match(norm, k)
            if frag["moves"] and nm2 and find_move(norm, nm2.end()):
                n2, b2 = int(nm2.group(1)), nm2.group(2) != "."
                frag["moves"].append({"renum": (n2, b2), "a": k, "e": nm2.end()})
                j = nm2.end()
                continue
            fm = find_move(norm, k)
            if not fm:
                break
            m, e = fm
            frag["moves"].append({"m": m, "a": k, "e": e, "txt": text[k:e]})
            j = e
        real = [x for x in frag["moves"] if "m" in x]
        if not real:
            i = nm.end()
            continue
        # nachlaufende Renummerierung ohne Zug entfernen
        while frag["moves"] and "renum" in frag["moves"][-1]:
            frag["moves"].pop()
        if frag["start"] > last:
            parts.append(text[last:frag["start"]])
        frag["end"] = frag["moves"][-1]["e"]
        frag["text"] = text[frag["start"]:frag["end"]]
        frag["before"] = text[max(0, frag["start"] - 40):frag["start"]]
        parts.append(frag)
        last = i = frag["end"]
    if last < len(text):
        parts.append(text[last:])
    return parts


# --- 4. Partiebaum und Zuordnung --------------------------------------------------------
class Tree:
    def __init__(self, board, label):
        self.root = board.copy(stack=False)
        self.label = label
        self.nodes = []             # [parent, move, board_after, san]
        self.main = [-1]            # Knoten der Hauptlinie, -1 = Wurzel
        self.first_child = {}
        self.pages = set()          # Seiten, auf denen Züge dieser Partie stehen

    def board(self, n):
        return self.root if n < 0 else self.nodes[n][2]

    def add(self, parent, mv):
        for i, (p, m, b, s) in enumerate(self.nodes):
            if p == parent and m == mv:
                return i
        b0 = self.board(parent)
        san = b0.san(mv) if mv else "…"   # Nullzug: Drohung der anderen Seite
        b = b0.copy(stack=False)
        b.push(mv)
        self.nodes.append([parent, mv, b, san])
        self.first_child.setdefault(parent, len(self.nodes) - 1)
        return len(self.nodes) - 1

    def path(self, n):
        out = []
        while n >= 0:
            out.append(n)
            n = self.nodes[n][0]
        return out[::-1]

    def find(self, num, black, prefer):
        """Knoten (vor dem Zug num/black) – zuerst die bevorzugten, dann Hauptlinie, dann alle."""
        want = chess.BLACK if black else chess.WHITE
        seen = []
        for n in prefer + self.main[::-1] + list(range(len(self.nodes) - 1, -2, -1)):
            if n in seen:
                continue
            seen.append(n)
            b = self.board(n)
            if b.turn == want and b.fullmove_number == num:
                yield n


POS_SIDE = re.compile(r"([Бб]елые|[Чч]ерные)\s*[—–:-]\s*")
POS_ITEM = re.compile(r"\s*(?:,|\sи\s)?\s*(?:(?P<fig>[♔♕♖♗♘])(?P<fsq>[a-hа-х][1-8])"
                      r"|(?:пп?\.\s*)(?P<psq>[a-hа-х][1-8])|(?P<sq>[a-hа-х][1-8])(?![\w-]))")


def text_positions(text):
    """Stellungen in Worten: „белые — ♔с5, п. b5; черные — ♔b7, пп. с7, е5“ ->
    [(ende im Text, placement)]."""
    out = []
    for m in re.finditer(r"[Бб]елые\s*[—–:-]", text):
        board = chess.Board(None)
        pos, sides, pawns = m.start(), 0, False
        while sides < 2:
            sm = POS_SIDE.match(text, pos)
            if not sm:
                break
            color = chess.WHITE if sm.group(1).lower().startswith("б") else chess.BLACK
            pos, n = sm.end(), 0
            while True:
                im = POS_ITEM.match(text, pos)
                if not im or (im.group("sq") and not pawns):
                    break
                if im.group("fig"):
                    pt, sq, pawns = FIG_TYPE[im.group("fig")], im.group("fsq"), False
                else:
                    pt, sq, pawns = chess.PAWN, im.group("psq") or im.group("sq"), True
                board.set_piece_at(chess.parse_square(sq.translate(LOOKALIKE)), chess.Piece(pt, color))
                pos, n = im.end(), n + 1
            if not n:
                break
            sides += 1
            pawns = False
            sep = re.match(r"\s*[;,]?\s*", text[pos:])
            pos += sep.end()
        if sides == 2:
            out.append((pos, board.board_fen()))
    return out


def try_line(board, frag, num, black, repair=False):
    """Wendet die Züge des Fragments an -> (anzahl gelöst, [(move|None, Kandidaten)], vollständig,
    {index: (Buchtext, ersetzt durch)}). repair: einen Druckfehler pro Fragment vermuten."""
    b = board.copy(stack=False)
    res, ok, prev_piece, fixes = [], 0, None, {}
    moves = frag["moves"]
    for i, x in enumerate(moves):
        if "renum" in x:
            n2, b2 = x["renum"]
            if b.fullmove_number != n2 or (b.turn == chess.BLACK) != b2:
                return ok, res, False, fixes   # Nummer passt nicht zum Verlauf -> Abbruch
            continue
        c = candidates(b, x["m"], prev_piece, "+" in x["txt"] or "#" in x["txt"])
        if len(c) != 1 and repair and len(fixes) < 3:
            alt = repair_move(b, x["txt"], moves[i + 1:])
            if alt:
                c = [alt]
                fixes[len(res)] = (x["txt"], fig_san(b.san(alt)))
        if len(c) != 1:
            res.append((None, c))
            return ok, res, False, fixes
        mv = c[0]
        prev_piece = b.piece_at(mv.from_square).piece_type
        res.append((mv, c))
        b.push(mv)
        ok += 1
    return ok, res, True, fixes


def _core(t):
    """Zugtext ohne Zusatzzeichen, in Buchschreibweise (Schlagen „:“, lateinische Linien)."""
    t = t.translate(LOOKALIKE).replace("x", ":").replace("O", "0")
    return re.sub(r"[+#!?]", "", t).strip()


def _book_forms(board, mv):
    """Schreibweisen eines Zuges, wie sie im Buch vorkommen können."""
    san = _core(fig_san(board.san(mv)))
    forms = {san, san.replace(":", "")}
    if board.piece_at(mv.from_square).piece_type == chess.PAWN and board.is_capture(mv):
        f, t = chess.square_name(mv.from_square)[0], chess.square_name(mv.to_square)
        forms |= {f + t[0], f + t, f + ":" + t}          # „cd“, „cd5“, „c:d5“
    return forms


def _dist1(a, b):
    """Levenshtein-Abstand höchstens 1?"""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


# Im Satz leicht verwechselte Zeichen („♘е6“ für ♘c6): entscheidet bei Gleichstand
SIMILAR = {frozenset("ec"), frozenset("38"), frozenset("bh"), frozenset("68")}


def _similar(a, b):
    diff = [(x, y) for x, y in zip(a, b) if x != y] if len(a) == len(b) else []
    return len(diff) == 1 and frozenset(diff[0]) in SIMILAR


def repair_move(board, txt, rest):
    """Druckfehler vermuten: legaler Zug, dessen Schreibweise bis auf Schlag-/Schachzeichen
    gleich ist, sonst bis auf ein Zeichen. Gewählt wird der Zug, mit dem die Zugfolge danach
    am weitesten trägt – nur wenn er darin eindeutig ist und noch Züge folgen, die er trägt
    (bei einem Zeichen Unterschied die nächsten drei bzw. alle restlichen)."""
    core = _core(txt)
    nrest = sum(1 for x in rest if "m" in x)
    if nrest == 0:
        return None                 # einzelner Zug: eher falsche Stellung als Druckfehler
    for level in (0, 1):
        scored = []
        for mv in board.legal_moves:
            forms = _book_forms(board, mv)
            hit = core in forms or core.replace(":", "") in forms if level == 0 else \
                any(_dist1(core, f) for f in forms)
            if hit:
                b = board.copy(stack=False)
                b.push(mv)
                scored.append((try_line(b, {"moves": rest}, None, None)[0], mv,
                               any(_similar(core, f) for f in forms)))
        if not scored:
            continue
        scored.sort(key=lambda t: -t[0])
        top = scored[0][0]
        tied = [t for t in scored if t[0] == top]
        if len(tied) > 1:
            tied = [t for t in tied if t[2]]
            if len(tied) != 1:
                return None         # mehrdeutig: lieber offen lassen
            scored = tied
        if top >= min(3 - 2 * (level == 0), nrest):
            return scored[0][1]
    return None


class Book:
    def __init__(self):
        self.trees = []
        self.cur = None             # aktueller Partiebaum
        self.last_end = None        # (tree, node) Ende des letzten Fragments
        self.last_dia = None        # (placement, seq, zugeordnet)
        self.seq = 0                # laufende Nummer der Fragmente/Diagramme
        self.used = {}              # id(tree) -> seq der letzten Benutzung
        self.problems = []
        self.fixes = []             # vermutete Druckfehler: (seite, Buchtext, ersetzt durch, …)
        self.fixed = {}             # (id(tree), knoten, fragmentanfang) -> Buchtext
        self.learned = {}

    def _cands(self, num, black, bold, par_start, same_par, fen):
        """Mögliche Ausgangsstellungen in Vorrangreihenfolge: (tree|None, node|Board, art)."""
        out = []
        if fen:                     # Korrektur: Ausgangsstellung vorgegeben
            out.append((None, chess.Board(fen), "korrektur"))
        if num == 1 and not black:
            out.append((None, chess.Board(), "anfang"))          # neue Partie
        want = chess.BLACK if black else chess.WHITE
        cont = (self.last_end and same_par and not (par_start or bold))
        dia_new = self.last_dia and not self.last_dia[2] and (
            not self.cur or self.last_dia[1] > self.used.get(id(self.cur), -1))
        if dia_new:                 # frisches Diagramm ohne Partiebezug: Stellung daraus
            out.append((None, self._dia_board(want, num), "diagramm"))
        trees = [self.cur] + [t for t in self.trees[::-1] if t is not self.cur][:4] if self.cur else []
        for ti, tree in enumerate(trees):
            prefer = []
            if cont and self.last_end[0] is tree:
                prefer = [self.last_end[1]]
            elif ti == 0:
                prefer = [tree.main[-1]]
            for n in tree.find(num, black, prefer):
                kind = "fortsetzung" if cont and prefer and n == prefer[0] else (
                    "hauptlinie" if n in tree.main else "variante")
                out.append((tree, n, kind if ti == 0 else "frühere Partie"))
            # Drohung: Zug der Seite, die nicht am Zug ist (Nullzug davor)
            if ti == 0:
                tb = (num - 1, True) if not black else (num, False)
                for n in tree.find(tb[0], tb[1], prefer):
                    if not tree.board(n).is_check():    # Nullzug aus dem Schach: ungültig
                        out.append((tree, n, "drohung"))
                    break
        # Schon verwendetes Diagramm nur, wenn noch keine Partie davon ausgeht – sonst würde es
        # bei einer späteren, unpassenden Zugnummer als neue Ausgangsstellung missbraucht
        if self.last_dia and not dia_new and not self.last_dia[2] and not any(
                t.root.board_fen() == self.last_dia[0] for t in self.trees[-5:]):
            out.append((None, self._dia_board(want, num), "diagramm"))
        return out

    def _resolve_loose(self, frag):
        """„g2-g4“, „♗с8-g4“ ohne Zugnummer: in der zuletzt besprochenen Stellung, notfalls
        als Plan/Drohung der anderen Seite. Nicht legal -> bleibt Text (kein Bericht)."""
        if not self.last_end:
            return None
        tree, n = self.last_end
        x = frag["moves"][0]
        for null in (False, True):
            b = tree.board(n)
            if null and b.is_check():
                break
            if null:
                b = b.copy(stack=False)
                b.push(chess.Move.null())
            c = candidates(b, x["m"], None)
            if len(c) == 1:
                base = tree.add(n, chess.Move.null()) if null else n
                return [(tree, tree.add(base, c[0]))]
        return None

    def _dia_board(self, turn, num):
        b = chess.Board(f"{self.last_dia[0]} {'b' if turn == chess.BLACK else 'w'} - - 0 {num}")
        # Diagramme kennen keine Rochaderechte: König und Turm auf Ausgangsfeldern -> erlaubt
        rights = ""
        for color, rank, ks, qs in ((chess.WHITE, 0, "K", "Q"), (chess.BLACK, 7, "k", "q")):
            if b.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, color):
                if b.piece_at(chess.square(7, rank)) == chess.Piece(chess.ROOK, color):
                    rights += ks
                if b.piece_at(chess.square(0, rank)) == chess.Piece(chess.ROOK, color):
                    rights += qs
        b.set_castling_fen(rights or "-")
        return b

    def resolve(self, frag, bold, page, par_start, same_par, fen=None):
        """Fragment einer Stellung zuordnen. Absatzanfang/fett: Hauptlinie zuerst;
        mitten im Text: zuerst Fortsetzung des vorigen Fragments desselben Absatzes."""
        self.seq += 1
        if frag["num"] is None:
            return self._resolve_loose(frag)
        num, black = frag["num"], frag["black"]
        n_moves = sum(1 for x in frag["moves"] if "m" in x)
        best = None
        for prio, (tree, node, kind) in enumerate(
                self._cands(num, black, bold, par_start, same_par, fen)):
            if tree is None:
                board = node
            else:
                board = tree.board(node)
                if kind == "drohung":
                    board = board.copy(stack=False)
                    board.push(chess.Move.null())
            ok, res, full, _ = try_line(board, frag, num, black)
            score = (ok, full, -prio)
            if best is None or score > best[0]:
                best = (score, tree, node, kind, res, {})
        if best and not best[0][1]:
            # Druckfehler? Nur übernehmen, wenn die Zugfolge damit deutlich weiter trägt
            plain = best
            for prio, (tree, node, kind) in enumerate(
                    self._cands(num, black, bold, par_start, same_par, fen)):
                board = node if tree is None else tree.board(node)
                if kind == "drohung":
                    board = board.copy(stack=False)
                    board.push(chess.Move.null())
                ok, res, full, fixes = try_line(board, frag, num, black, repair=True)
                score = (ok, full, -prio)
                better = ok >= plain[0][0] + 2 or (full and ok > plain[0][0])
                if fixes and better and (best is plain or score > best[0]):
                    best = (score, tree, node, kind, res, fixes)
        if best is None or best[0][0] == 0:
            self.problems.append((page, "nicht zuordenbar", frag["text"], frag["before"],
                                  "kein passender Zug in der laufenden oder einer früheren "
                                  "Partie, im letzten Diagramm oder in der Grundstellung"))
            return None
        (ok, full, _), tree, node, kind, res, fixes = best
        if tree is None:            # neue Partie (Grundstellung, Diagramm, Korrektur)
            tree = Tree(node, {"diagramm": "Diagramm", "korrektur": "Korrektur"}.get(kind, "Partie")
                        + f" S. {page}")
            self.trees.append(tree)
            node = -1
        if kind == "drohung":
            node = tree.add(node, chess.Move.null())
        self.cur = tree
        tree.pages.add(page)
        self.used[id(tree)] = self.seq
        # Hauptlinie: fette Züge, oder unmarkierte Fortsetzung am Ende der Hauptlinie
        cue = VAR_CUES.search(frag["before"]) is not None
        extends_main = node == tree.main[-1] and not (not bold and cue) and kind != "drohung"
        reroute_main = bold and node != tree.main[-1] and kind != "drohung"
        out, n = [], node
        for mv, c in res:
            if mv is None:
                break
            n = tree.add(n, mv)
            out.append((tree, n))
        if extends_main or reroute_main:
            base = tree.path(node) if node >= 0 else []
            line = base + [t[1] for t in out]
            if all(tree.nodes[x][1] for x in line):   # Drohung (Nullzug) nie in die Hauptlinie
                tree.main = [-1] + line
        self.last_end = (tree, n)
        for i, (was, wird) in fixes.items():
            self.fixes.append((page, was, wird, frag["text"], frag["before"]))
            if i < len(out):
                self.fixed[(id(out[i][0]), out[i][1], frag["start"])] = was
        if not full:
            c = res[-1][1] if res and res[-1][0] is None else []
            why = ("mehrdeutig: " + ", ".join(tree.board(n).san(m) for m in c)) if len(c) > 1 \
                else "nicht legal in der Stellung" if res and res[-1][0] is None \
                else "Zugnummer passt nicht"
            self.problems.append((page, why, frag["text"], frag["before"],
                                  f"{ok} von {n_moves} Zügen aufgelöst ({kind}), Stellung: "
                                  f"{tree.board(n).fen()}"))
        return out

    def diagram(self, d, page):
        pl = grid_placement(d["grid"])
        match = None
        if self.cur:
            for n in ([self.last_end[1]] if self.last_end and self.last_end[0] is self.cur else []) \
                    + self.cur.main[::-1][:4]:
                b = self.cur.board(n)
                if same_placement(b, d):
                    match = (self.cur, n)
                    break
        if d["unknown"]:
            self.learn(d, page)
            pl = grid_placement(d["grid"])
        # Diagramm passt zu keiner Stellung der laufenden Partie: knapp daneben = Widerspruch.
        # Bei höchstens zwei Feldern gilt die Partiestellung (Satzfehler im Diagramm, S. 428:
        # schwarzer statt weißer Läufer), sonst ginge der Faden der Partie verloren.
        if not match and self.cur and self.last_end and self.last_end[0] is self.cur:
            b = self.cur.board(self.last_end[1])
            diff = placement_diff(b, d["grid"])
            if 0 < len(diff) <= 3:
                self.problems.append((page, "Diagramm weicht ab", "", "",
                                      f"Diagramm vs. Stellung nach {self.cur.nodes[self.last_end[1]][3] if self.last_end[1] >= 0 else 'Beginn'}: "
                                      + ", ".join(diff)
                                      + ("; gezeigt wird die Partiestellung" if len(diff) <= 2 else "")))
                if len(diff) <= 2:
                    match = (self.cur, self.last_end[1])
        self.seq += 1
        self.last_dia = (pl, self.seq, bool(match))
        return match

    def learn(self, d, page):
        """Unbekannte Glyphen aus der Stellung der laufenden Partie ableiten."""
        if not (self.cur and self.last_end and self.last_end[0] is self.cur):
            self.problems.append((page, "Diagramm-Glyphe unbekannt", "", "",
                                  ", ".join(sorted(set(d["unknown"].values())))))
            return
        b = self.cur.board(self.last_end[1])
        if len(placement_diff(b, d["grid"])) - len(d["unknown"]) > 0:
            self.problems.append((page, "Diagramm-Glyphe unbekannt", "", "",
                                  ", ".join(sorted(set(d["unknown"].values())))))
            return
        for (r, f), g in d["unknown"].items():
            p = b.piece_at(chess.square(f, 7 - r))
            sym = p.symbol() if p else "."
            PROFIL["glyphen"][g] = sym
            self.learned[g] = sym
            d["grid"][r][f] = sym
        d["unknown"] = {}


def same_placement(b, d):
    return not d["unknown"] and b.board_fen() == grid_placement(d["grid"])


def placement_diff(b, grid):
    out = []
    for r in range(8):
        for f in range(8):
            sq = chess.square(f, 7 - r)
            p = b.piece_at(sq)
            a = p.symbol() if p else "."
            g = grid[r][f]
            if g != a and g != "?":
                out.append(f"{chess.square_name(sq)}: Buch {g if g != '.' else 'leer'}, "
                           f"Notation {a if a != '.' else 'leer'}")
    return out


# --- 5. Ausgabe -------------------------------------------------------------------------
def fig_san(san):
    for t, f in FIG.items():
        san = san.replace(chess.piece_symbol(t).upper(), f)
    return san


def convert(pdf_path, first, last, title, korr=()):
    """korr: Korrekturen aus korrekturen.json – {"seite", "beginnt", "fen"} gibt einer
    Zugfolge die Ausgangsstellung vor, {"seite", "ersetze", "durch"} ändert Buchtext."""
    pdf = pdfplumber.open(pdf_path)
    blocks = blocks_of(pdf, first, last)
    book = Book()
    out_blocks = []
    pend_nr = None
    n_bild = 0
    for bl in blocks:
        if bl["type"] == "dianr":
            pend_nr = bl["text"]
            continue
        if bl["type"] == "bild":
            n_bild += 1
            out_blocks.append({"t": "bild", "page": bl["page"], "bbox": bl["bbox"],
                               "datei": f"abbildungen/s{bl['page']:03d}_{n_bild}.png"})
            continue
        if bl["type"] == "dia":
            m = book.diagram(bl, bl["page"])
            if m:
                tree, n = m
                ref = {"g": book.trees.index(tree), "n": n}
            else:
                ref = None
            fen = grid_placement(bl["grid"])
            if m:
                fen = m[0].board(m[1]).fen()
            out_blocks.append({"t": "dia", "fen": fen, "nr": pend_nr, "page": bl["page"],
                               "ref": ref})
            pend_nr = None
            continue
        text = "".join(c for c, s in bl["runs"])
        # Sperrsatz (Hervorhebung „ц е н т р е“): Buchstaben mit genau einem Leerzeichen;
        # echte Wortgrenzen davor/danach haben im PDF mehrere Leerzeichen
        text = re.sub(r"(?:(?<=  )|^|(?<=[«(]))((?:[а-яёА-ЯЁ] ){3,}[а-яёА-ЯЁ])(?=  |$|[,.;:!?»)])",
                      lambda m: m.group(1).replace(" ", ""), text)
        if bl["type"] in ("h", "cap"):
            text = "\n".join(re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n"))
            out_blocks.append({"t": bl["type"], "text": text.strip(), "page": bl["page"]})
            continue
        text = fix_spaces(re.sub(r"\s+", " ", text).strip())
        for k in korr:
            if k.get("ersetze") and k["seite"] == bl["page"] and k["ersetze"] in text:
                text = text.replace(k["ersetze"], k["durch"])
                k["benutzt"] = True
        bold_at = bold_mask(bl["runs"], text)
        spans = []
        first_frag = True
        # Fußnoten stehen am Seitenende, beziehen sich aber auf weiter oben: danach
        # gilt wieder die Partie, die der Haupttext gerade bespricht
        saved = (book.cur, book.last_end, book.last_dia) if bl.get("fn") else None
        tpos = text_positions(text)
        for part in scan(text):
            if isinstance(part, str):
                spans.append(part)
                continue
            while tpos and tpos[0][0] <= part["start"] + 1:
                book.seq += 1       # Stellung in Worten gilt wie ein frisches Diagramm
                book.last_dia = (tpos.pop(0)[1], book.seq, False)
            fl = [f for f in bold_at[part["start"]:part["end"]] if f is not None]
            bold = sum(fl) > len(fl) / 2
            par_start = not text[:part["start"]].strip(" (")
            fen = None
            for k in korr:
                if k.get("fen") and k["seite"] == bl["page"] and part["text"].startswith(k["beginnt"]):
                    fen = k["fen"]
                    k["benutzt"] = True
            res = book.resolve(part, bold, bl["page"], par_start, not first_frag, fen)
            first_frag = False
            spans.extend(render_frag(part, res, book, bold))
        out = {"t": "p", "spans": merge(spans), "page": bl["page"]}
        if saved:
            book.cur, book.last_end, book.last_dia = saved
            out["fn"] = True
        out_blocks.append(out)
    for bl in out_blocks:
        if bl["t"] == "dia" and not bl["ref"] and "/" in bl["fen"]:
            pl = bl["fen"].split()[0]
            for gi, tr in enumerate(book.trees):
                hit = -1 if tr.root.board_fen() == pl else \
                    next((i for i, nd in enumerate(tr.nodes) if nd[2].board_fen() == pl), None)
                if hit is not None and tr.pages and min(tr.pages) - 1 <= bl["page"] <= max(tr.pages) + 1:
                    bl["ref"] = {"g": gi, "n": hit}
                    bl["fen"] = tr.board(hit).fen()
                    break
    games = []
    for tr in book.trees:
        main = set(tr.main)
        nodes = []
        for i, (p, mv, b, san) in enumerate(tr.nodes):
            nodes.append([p, mv.uci(), fig_san(san), 1 if i in main else 0])
        games.append({"root": tr.root.fen(), "label": tr.label, "nodes": nodes})
    return {"titel": title, "quelle": os.path.basename(pdf_path), "seiten": [first, last],
            "bloecke": out_blocks, "partien": games}, book


def fix_spaces(text):
    """Satzfehler mit echtem Leerzeichen im PDF: „17... ♗:е5 1 8. ♘d4“, „♖ае 8“, „♗: f3“."""
    def num(m):
        prev = [int(x) for x in re.findall(r"(\d+)\s?\.", text[:m.start()])][-1:]
        n = int(m.group(1) + m.group(2))
        return f"{n}." if prev and 0 <= n - prev[0] <= 2 else m.group(0)

    def num_comma(m):
        prev = [int(x) for x in re.findall(r"(\d+)\s?\.", text[:m.start()])][-1:]
        n = int(m.group(1))
        return f"{n}." if prev and 0 <= n - prev[0] <= 1 else m.group(0)
    text = re.sub(r"(?<!- )(?<![\d.\-])([1-9]) (\d)\.", num, text)
    text = re.sub(r"([♘♗♖♕♔a-hа-х]:) ([a-hа-х][1-8])", r"\1\2", text)    # „♗: f3“
    # „20, gf g4!“: Komma statt Punkt nach der Zugnummer
    text = re.sub(r"(?<![\d.,])(\d{1,3}),(?= (?:[♘♗♖♕♔]|[a-hасе][a-hасе]?:?[1-8]|[a-hасе][a-hасе]\b|0-0))",
                  num_comma, text)
    return re.sub(r"([♘♗♖♕♔][a-hа-х]{1,2}) ([1-8])(?![\d.])", r"\1\2", text)


def bold_mask(runs, text):
    """Fett-Markierung je Zeichen des normalisierten Textes (ungefähr, über Zeichenfolge)."""
    raw = "".join(c for c, s in runs)
    flags = [None if s == "fig" or ch.isspace() else s == "b" for c, s in runs for ch in c]
    out, j = [], 0
    for ch in text:
        while j < len(raw) and raw[j] != ch:
            j += 1
        out.append(flags[j] if j < len(raw) else None)
        j += 1
    return out


def render_frag(frag, res, book, bold):
    if not res:
        return [frag["text"]]
    out, k = [], 0
    pos = frag["start"]
    text = frag["text"]
    for x in frag["moves"]:
        if "renum" in x:
            continue
        if k >= len(res):
            break
        tree, n = res[k]
        a, e = x["a"], x["e"]
        if a > pos:
            out.append(text[pos - frag["start"]:a - frag["start"]])
        orig = text[a - frag["start"]:e - frag["start"]]
        marks = re.search(r"(!!|\?\?|!\?|\?!|!|\?)$", orig)
        san = fig_san(tree.nodes[n][3]) + (marks.group(1) if marks else "")
        sp = {"m": san, "g": book.trees.index(tree), "n": n, "b": 1 if bold else 0, "o": orig}
        if (id(tree), n, frag["start"]) in book.fixed:
            sp["k"] = orig          # Druckfehler vermutet: im Buch steht orig
        out.append(sp)
        pos = e
        k += 1
    if pos < frag["end"]:
        out.append(text[pos - frag["start"]:])
    return out


def merge(spans):
    out = []
    for s in spans:
        if isinstance(s, str) and out and isinstance(out[-1], str):
            out[-1] += s
        elif s != "":
            out.append(s)
    return out


def write_report(path, book, data, args):
    lines = [f"# Bericht: {data['titel']}", "",
             f"Quelle: {data['quelle']}, Seiten {data['seiten'][0]}–{data['seiten'][1]}", ""]
    nm = sum(1 for b in data["bloecke"] if b["t"] == "p" for s in b["spans"] if isinstance(s, dict))
    nd = sum(1 for b in data["bloecke"] if b["t"] == "dia")
    nr = sum(1 for b in data["bloecke"] if b["t"] == "dia" and b["ref"])
    lines += [f"- {nm} anklickbare Züge in {len(data['partien'])} Partien/Beispielen",
              f"- {nd} Diagramme, davon {nr} einer Partiestellung zugeordnet", ""]
    if book.learned:
        lines += ["Gelernte Diagramm-Glyphen: " + ", ".join(f"{k} = {v}" for k, v in book.learned.items()), ""]
    if args.korrekturen:
        lines += ["## Angewendete Korrekturen (korrekturen.json)", ""]
        for k in args.korrekturen:
            lines.append(f"- S. {k['seite']}: {k.get('grund', '')}")
        lines.append("")
    if book.fixes:
        lines += ["## Vermutete Druckfehler (automatisch ersetzt, bitte prüfen)", ""]
        for page, was, wird, txt, before in book.fixes:
            lines.append(f"- S. {page}: „{was}“ → **{wird}** in …{before[-30:]}{txt}")
        lines.append("")
    lines += ["## Widersprüche und nicht auflösbare Stellen", ""]
    if not book.problems:
        lines.append("keine")
    for page, why, txt, before, detail in book.problems:
        ctx = f"…{before[-30:]}**{txt}**" if txt else ""
        lines.append(f"- S. {page} – {why}: {ctx}  \n  {detail}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("ausgabe")
    ap.add_argument("--seiten", required=True, help="z. B. 16-31 (PDF-Seiten)")
    ap.add_argument("--titel", default=None)
    a = ap.parse_args()
    first, last = map(int, a.seiten.split("-"))
    title = a.titel or os.path.splitext(os.path.basename(a.pdf))[0]
    kpath = os.path.join(a.ausgabe, "korrekturen.json")
    korr = json.load(open(kpath, encoding="utf-8")) if os.path.exists(kpath) else []
    data, book = convert(a.pdf, first, last, title, korr)
    if book.learned:                # gelernte Glyphen gelten auch für frühere Diagramme
        learned = dict(book.learned)
        data, book = convert(a.pdf, first, last, title, korr)
        book.learned = learned
    for k in korr:
        if not k.pop("benutzt", False):
            book.problems.append((k["seite"], "Korrektur nicht angewendet", "", "", json.dumps(k, ensure_ascii=False)))
    os.makedirs(a.ausgabe, exist_ok=True)
    pdf = pdfplumber.open(a.pdf)
    for bl in data["bloecke"]:
        if bl["t"] == "bild":       # Schemata als Bild ins Buchverzeichnis
            os.makedirs(os.path.join(a.ausgabe, "abbildungen"), exist_ok=True)
            pdf.pages[bl["page"] - 1].crop(bl.pop("bbox")).to_image(resolution=150) \
                .save(os.path.join(a.ausgabe, bl["datei"]))
    with open(os.path.join(a.ausgabe, "buch.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    a.korrekturen = korr
    write_report(os.path.join(a.ausgabe, "bericht.md"), book, data, a)
    print(open(os.path.join(a.ausgabe, "bericht.md"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
