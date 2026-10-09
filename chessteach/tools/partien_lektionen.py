"""Holt die Partien eines Spielers von Lichess oder chess.com und baut daraus einen Lektionen-Reiter.

Reines Python + Stockfish (/usr/games/stockfish), kein Konto nötig:
  python3 tools/partien_lektionen.py --lichess <name> --anzeige Lena
  python3 tools/partien_lektionen.py --chesscom <name> --anzeige Max --max 150
  python3 tools/partien_lektionen.py --pgn partien.pgn --name <name> --anzeige Max

Ergebnis: lektionen/NN_Partien-<Anzeige>/ mit
  01 Was hängt?  02 Bestrafe den Fehler  03 Gewinn verwerten  04 Eröffnungsfehler
  05 Mehrzügig bestrafen  06 Scheinbar gedeckt
Die Aufgaben beginnen 3 Züge früher und zeigen den Partiezug als roten Pfeil (kontext_einfuegen.py).
Spielernamen werden zu „Ich“/„Gegner“. Die Reiter enthalten trotzdem Partien von Kindern und
gehören nicht ins öffentliche Repo (siehe .gitignore).
Zwischenstände (partien.pgn, evals.json) liegen in ~/.cache/chessteach/<name>/.
"""
import argparse, glob, io, json, os, re, shutil, subprocess, sys, urllib.request
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PA = os.path.join(HERE, "partieanalyse")
UA = {"User-Agent": "ChessTeach-Lektionen (github.com/vheinitz/chessteach)"}


def http(url, accept=None):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
        return r.read().decode("utf-8")


def fetch_lichess(user, n):
    return http(f"https://lichess.org/api/games/user/{user}?max={n}&clocks=false&evals=false&opening=false",
                "application/x-chess-pgn")


def fetch_chesscom(user, n):
    archives = json.loads(http(f"https://api.chess.com/pub/player/{user.lower()}/games/archives"))["archives"]
    texts, count = [], 0
    for url in reversed(archives):              # neueste Monate zuerst
        t = http(url + "/pgn")
        texts.append(t)
        count += t.count("[Event ")
        if count >= n:
            break
    return "\n\n".join(texts)


def filter_games(text, user, n, tc):
    """Nur Standard-Schach aus der Grundstellung mit dem Spieler; neueste n Partien."""
    games, f = [], io.StringIO(text)
    while (g := chess.pgn.read_game(f)):
        h = g.headers
        if h.get("Variant", "Standard") not in ("Standard", "") or h.get("SetUp") == "1":
            continue
        if user.lower() not in (h.get("White", "").lower(), h.get("Black", "").lower()):
            continue
        if tc and h.get("TimeControl", "").split("+")[0] != tc:
            continue
        if len(list(g.mainline_moves())) < 10:
            continue
        games.append(g)
    games.sort(key=lambda g: (g.headers.get("UTCDate") or g.headers.get("Date", ""),
                              g.headers.get("UTCTime") or g.headers.get("EndTime", "")))
    return games[-n:]


def run(script, *args, env):
    print(f"→ {script}", flush=True)
    subprocess.run([sys.executable, os.path.join(PA, script), *args], check=True, env=env)


def next_tab_dir(lek, anzeige):
    slug = re.sub(r"[^A-Za-z0-9-]+", "-", anzeige.replace("ä", "ae").replace("ö", "oe")
                  .replace("ü", "ue").replace("ß", "ss")).strip("-")
    for d in glob.glob(os.path.join(lek, "*_Partien-" + slug)):
        return d                                   # vorhandenen Reiter neu befüllen
    nums = [int(os.path.basename(d)[:2]) for d in glob.glob(os.path.join(lek, "[0-9][0-9]_*"))]
    return os.path.join(lek, f"{max(nums, default=0) + 1:02d}_Partien-{slug}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--lichess", metavar="NAME")
    src.add_argument("--chesscom", metavar="NAME")
    src.add_argument("--pgn", metavar="DATEI")
    ap.add_argument("--name", help="Benutzername in der PGN (nur mit --pgn)")
    ap.add_argument("--anzeige", required=True, help="Name für den Reiter, z. B. Vorname")
    ap.add_argument("--max", type=int, default=200, help="höchstens so viele neueste Partien (200)")
    ap.add_argument("--zeit", help="nur diese Bedenkzeit in Sekunden, z. B. 600")
    ap.add_argument("--tiefe", type=int, default=14, help="Stockfish-Tiefe der Erstanalyse (14)")
    ap.add_argument("--lektionen", default=os.path.join(APP, "lektionen"))
    a = ap.parse_args()

    user = a.lichess or a.chesscom or a.name
    if not user:
        ap.error("--pgn braucht --name")
    work = os.path.join(os.path.expanduser("~/.cache/chessteach"), re.sub(r"\W+", "_", user.lower()))
    os.makedirs(work, exist_ok=True)

    if a.lichess:
        text = fetch_lichess(user, a.max * 2)
    elif a.chesscom:
        text = fetch_chesscom(user, a.max * 2)
    else:
        text = open(a.pgn, encoding="utf-8").read()
    games = filter_games(text, user, a.max, a.zeit)
    if not games:
        sys.exit(f"Keine passenden Partien für {user} gefunden.")
    pgn = os.path.join(work, "partien.pgn")
    with open(pgn, "w", encoding="utf-8") as f:
        for g in games:
            print(g, file=f, end="\n\n")
    print(f"{len(games)} Partien von {user} → {pgn}", flush=True)

    out = next_tab_dir(a.lektionen, a.anzeige)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "_meta.txt"), "w", encoding="utf-8") as f:
        f.write(f"Partien {a.anzeige}\n")
    env = dict(os.environ, CHESS_ME=user, CHESSTEACH_DIR=APP)
    evals = os.path.join(work, "evals.json")
    run("run_engine.py", pgn, evals, str(a.tiefe), env=env)
    run("lektionen_bauen.py", evals, out, env=env)
    run("lektionen_mehrzuegig.py", evals, out, env=env)
    aufgaben = [p for d in ("01_*", "02_*", "05_*", "06_*") for p in glob.glob(os.path.join(out, d, "0001_*.pgn"))]
    run("kontext_einfuegen.py", pgn, *aufgaben, env=env)
    run("anonymisieren.py", out, env=env)

    print(f"\nFertig: Reiter „Partien {a.anzeige}“ in {out}")
    for d in sorted(glob.glob(os.path.join(out, "[0-9][0-9]_*"))):
        n = sum(open(p, encoding="utf-8").read().count("[Event ") for p in glob.glob(os.path.join(d, "*.pgn")))
        if n == 0:
            shutil.rmtree(d)                       # leere Lektion nicht anzeigen
            print(f"  {os.path.basename(d):28s}    – (keine passenden Stellungen)")
        else:
            print(f"  {os.path.basename(d):28s} {n:4d} Übungen")
    print("In der App mit F5 neu laden.")


if __name__ == "__main__":
    main()
