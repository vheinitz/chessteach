"""Lektionen umordnen: 2 Reiter (Grundlagen, Fortgeschritten). Args: lektionen-dir done.json"""
import os, sys, json, shutil, subprocess
L, DONE = sys.argv[1], sys.argv[2]
moves = [  # alt (relativ) -> neu (relativ)
    ("04_Eroeffnungen/01_Kurze-Matts", "01_Grundlagen/04_Kurze-Matts"),
    ("04_Eroeffnungen/02_Offene-Spiele", "01_Grundlagen/05_Offene-Spiele"),
    ("04_Eroeffnungen/03_Halboffene-Spiele", "01_Grundlagen/06_Halboffene-Spiele"),
    ("04_Eroeffnungen/04_Geschlossene-Spiele", "01_Grundlagen/07_Geschlossene-Spiele"),
    ("04_Eroeffnungen/04_Verteidigungen", "01_Grundlagen/08_Verteidigungen"),
    ("03_Endspiel/01_Endspiel", "01_Grundlagen/09_Endspiel"),
    ("03_Endspiel/02_Mattvarianten", "01_Grundlagen/10_Mattvarianten"),
    ("02_Taktik/01_Taktiken-Tricks", "01_Grundlagen/11_Taktiken-Tricks"),
    ("02_Taktik/02_Mattbilder", "01_Grundlagen/12_Mattbilder"),
    ("05_Matt-Aufgaben/01_Matt-in-1", "01_Grundlagen/13_Matt-in-1"),
    ("05_Matt-Aufgaben/02_Matt-in-2", "01_Grundlagen/14_Matt-in-2"),
    ("05_Matt-Aufgaben/03_Matt-in-3", "01_Grundlagen/15_Matt-in-3"),
    ("06_Lernlektionen/01_Koenig-Turm", "01_Grundlagen/16_Koenig-Turm"),
    ("06_Lernlektionen/02_Zwei-Tuerme", "01_Grundlagen/17_Zwei-Tuerme"),
    ("06_Lernlektionen/03_Koenig-Dame", "01_Grundlagen/18_Koenig-Dame"),
    ("06_Lernlektionen/04_Opposition", "01_Grundlagen/19_Opposition"),
    ("06_Lernlektionen/05_Quadratregel", "01_Grundlagen/20_Quadratregel"),
    ("06_Lernlektionen/06_Zentrum", "01_Grundlagen/21_Zentrum"),
    ("06_Lernlektionen/07_Automatik-und-Zwischenzug", "01_Grundlagen/22_Automatik-und-Zwischenzug"),
    ("06_Lernlektionen/0001_test1.fen", "01_Grundlagen/0001_test1.fen"),
    ("99_adv/05_art_of_chess_analysis.pgn", "02_Fortgeschritten/01_art_of_chess_analysis.pgn"),
    ("99_adv/06_Larsen+-+Larsen's+Good+Move+Guide.pgn", "02_Fortgeschritten/02_Larsen+-+Larsen's+Good+Move+Guide.pgn"),
    ("99_adv/07_mysystem_pgn.pgn", "02_Fortgeschritten/03_mysystem_pgn.pgn"),
    ("99_adv/08_understandingpawnplayinchess.pgn", "02_Fortgeschritten/04_understandingpawnplayinchess.pgn"),
    ("05-brilliant-checkmates.pgn", "02_Fortgeschritten/05_brilliant-checkmates.pgn"),
    ("07_Eröffnungsfallen.pgn", "02_Fortgeschritten/06_Eröffnungsfallen.pgn"),
]
os.makedirs(os.path.join(L, "02_Fortgeschritten"), exist_ok=True)
with open(os.path.join(L, "02_Fortgeschritten", "_meta.txt"), "w", encoding="utf-8") as f:
    f.write("Fortgeschritten\n")
for old, new in moves:
    src, dst = os.path.join(L, old), os.path.join(L, new)
    if not os.path.exists(src):
        print("fehlt (übersprungen):", old); continue
    if os.path.exists(dst):
        sys.exit(f"Ziel existiert schon: {new}")
    shutil.move(src, dst)
# leere alte Reiter (nur _meta.txt übrig) entfernen
for tab in ("02_Taktik", "03_Endspiel", "04_Eroeffnungen", "05_Matt-Aufgaben", "06_Lernlektionen", "99_adv"):
    p = os.path.join(L, tab)
    if os.path.isdir(p):
        rest = [x for x in os.listdir(p) if x != "_meta.txt"]
        if rest: print("NICHT leer, bleibt:", tab, rest)
        else: shutil.rmtree(p)
# Erledigt-Markierungen nachziehen
if os.path.exists(DONE):
    shutil.copy(DONE, DONE + ".bak")
    d = json.load(open(DONE, encoding="utf-8"))
    Lab = os.path.abspath(L) + os.sep
    def fix(path):
        if not path.startswith(Lab): return path
        rel = path[len(Lab):]
        for old, new in moves:
            if rel == old or rel.startswith(old + os.sep):
                return Lab + new + rel[len(old):]
        return path
    d["lessons"] = sorted(fix(p) for p in d.get("lessons", []))
    d["exercises"] = [[fix(p), i] for p, i in d.get("exercises", [])]
    json.dump(d, open(DONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fertig")
