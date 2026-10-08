# Partieanalyse eigener chess.com-Partien (01.08.–08.10.2026)

Erstellt am 2026-10-08 mit Claude Code (Stockfish 16).

> Auftrag: „gehe bis zum ersten großen fehler >= 1 und mache die statistik ab
> welchem zug der erste grobe fehler passierte und an was das lag, dann
> analysiere auch andere Fehler und finde gibt es systematik in meinen
> niederlagen? […] Gebe die Vorschläge, wie ich mich verbessern soll, welche
> eröffnung besser lernen etc. Analysiere auch meine Gewinne […] Zufall oder
> systematik?“
>
> Ablage: „falls noch kein doc dir im projekt, bitte anlegen und report dort für
> weitere abarbeitung ablegen.“

## Datenbasis

- `lektionen/03_MeinePartien/chess_com_games_2026-10-08.pgn`: **419 Partien**,
  fast alle Blitz 5 min. Ohne Zugzeiten (`%clk`) und ohne ECO-Codes.
- Die 15 Partien vom **12.09.2026** sind entfernt (14 Niederlagen in Folge).
  Begründung des Auftraggebers: „das muss mein Sohn gewesen sein“.
- Bewertet wurde jede Stellung mit Stockfish 16 bei Suchtiefe 14. Die Werte sind
  auf ±10 Bauern gekappt; ein Matt zählt als ±10.

**Begriffe:**

| Begriff | Bewertungsverlust des Zuges |
|---|---|
| Ungenauigkeit | ≥ 0,5 Bauern |
| Fehler | ≥ 1 Bauer |
| Patzer | ≥ 3 Bauern |

Die Ursache eines Fehlers bestimmt ein Skript automatisch. Es wertet die
Hauptvariante der Engine nach dem Zug aus, 8 Halbzüge weit. Das ist eine
Näherung und keine Handanalyse.

## Bilanz

- 216 Siege, 179 Niederlagen, 24 Remis (54 %). Mit Weiß und Schwarz fast gleich.
- Elo (5 min): Start etwa 450 · Höchststand 795 (08.–11.09.) · Stand 08.10. etwa 665–690.

## Niederlagen

**Erster Fehler (≥ 1 Bauer):** in 178 von 179 Niederlagen.

| Zug | 1–5 | 6–10 | 11–15 | 16–20 | > 20 |
|---|---|---|---|---|---|
| Niederlagen | 53 | 73 | 44 | 8 | 0 |

- Median ist Zug 8. 134 dieser ersten Fehler sind kleine Fehler, nur 44 sind Patzer.
- Meist geht kein Material sofort verloren (100 Fälle): Es sind schwache Eröffnungszüge.
- Typische Züge: frühe Springer- und Läuferzüge, zu frühe Dame (18), Randbauern a/b/g/h (21), f-Bauer (10), König (10).
- In 68 Fällen stand ich vor dem ersten Fehler sogar besser.

**Erster Patzer (≥ 3 Bauern):** in 159 Niederlagen. Median ist Zug 14, die Quartile liegen bei 10 und 21.

| Ursache | Anzahl |
|---|---|
| Figur stand schon angegriffen, Drohung übersehen | 44 |
| Gerade gezogene Figur ungedeckt hingestellt | 35 |
| Stellung oder Tempo, ohne direkten Materialverlust | 24 |
| Fehler des Gegners nicht bestraft | 22 |
| mehrzügige Taktik 10 · Matt zugelassen 8 · Schach übersehen 7 · Deckung entfernt 5 · Gabel 4 | 34 |

Die verlorene Figur war 34-mal die Dame. Bis Zug 15 wurde die Dame in allen Partien zusammen 46-mal eingestellt.

**Systematik 1: hängende Figuren.** Die Hälfte der entscheidenden Patzer (79 von 159) ist eine einfach hängende Figur.

## Weitere Muster

| Befund | Wert |
|---|---|
| Gegner-Patzer (≥ 3) nicht sofort bestraft | 197 von 508 (39 %) |
| Gewinnstellung ≥ +5 nicht gewonnen | 58 (40 verloren, 18 remis) |
| Remis aus Gewinnstellung | 18 von 24 (Zeit bei zu wenig Material 8, Stellungswiederholung 6, Patt 1) |
| Von +5 bis zum Matt (Median, oberes Quartil) | 10,5 Züge, 27 Züge |
| Matt in 1–2 möglich und nicht gespielt | 13 von 177 |
| Fehler je 100 eigene Züge: Eröffnung / Mittelspiel / Endspiel | 11 / 22 / 12 |
| Dame bis Zug 5 gezogen → Punkte | 43 % (sonst 56 %) |

**Systematik 2: Müdigkeit und Tilt** (nach Niederlagen frustriert schlechter weiterspielen).

| Situation | Punkte |
|---|---|
| Partie 1–5 des Tages | 61 % |
| Partie 6–10 des Tages | 47 % |
| ab Partie 11 | 47 % |
| nach 2 Niederlagen in Folge | 40 % |

## Siege: Zufall oder Systematik?

| Entstehung | Anzahl |
|---|---|
| Gegner patzt zuerst, ich verwerte | 114 |
| Ich patze zuerst, Gegner patzt zurück | 61 |
| ohne Patzer des Gegners (Druck, Technik, Zeit) | 30 |
| Gegner hat verlassen | 11 |

- 81 % der Siege beruhen auf Patzern des Gegners. Auf diesem Niveau ist das normal.
- Systematisch ist: Gewonnen wird, wenn man selbst weniger patzt. Eigene Patzer pro Partie: 1,3 in Siegen, 2,1 in Niederlagen.
- Durchschnittlicher Verlust pro Zug (Bauern ×100): 53 in Siegen, 92 in Niederlagen.

## Eröffnungen

Punkte in Prozent, Remis zählt halb. Die Bewertung nach Zug 10 ist aus eigener Sicht.

| Als Weiß | Partien | Punkte | Bewertung nach Zug 10 | Patzer bis Zug 12 |
|---|---|---|---|---|
| 1.e4 | 150 | 56 % | e5: +1,0 · d5: +1,7 | 31 % |
| 1.d4 | 27 | 39 % | d5: +0,6 | 44 % |
| 1.f4 | 28 | 61 % | +1,1 | 11 % |

| Als Schwarz | Partien | Punkte | Bewertung nach Zug 10 |
|---|---|---|---|
| 1.e4 e5 | 68 | 50 % | +0,5 |
| 1.e4 d6 | 45 | 47 % | +0,1 |
| 1.e4 d5 | 22 | 50 % | −1,0 |
| 1.d4 d5 | 20 | 80 % | +0,2 |
| 1.d4 Sf6 | 15 | 53 % | −0,4 |

## Empfehlungen

1. **Patzerkontrolle vor jedem Zug:**
   - Was hat der letzte Zug des Gegners angegriffen?
   - Ist das Zielfeld meiner Figur gedeckt?
   - Hängt beim Gegner etwas, oder gibt es ein Schach?
2. **Täglich etwa 15 Minuten Taktik:** „Figur hängt“ und „Fehler bestrafen“. Dazu dienen die Lektionen 1 und 2 unten.
3. **Höchstens 5–6 Partien pro Tag**, und nach 2 Niederlagen in Folge aufhören.
4. **Eröffnungen:**
   - Als Weiß bei 1.e4 bleiben und Italienisch als Prinzipienschule lernen. 1.d4 vorerst meiden. 1.f4 läuft gut (kleine Stichprobe).
   - Als Schwarz gegen 1.e4 auf 1…e5 setzen und die Antworten auf Italienisch, Schottisch und Vierspringer lernen. Skandinavisch (1…d5) aufgeben oder gründlich lernen.
   - Gegen 1.d4 bei 1…d5 bleiben.
   - Allgemein: keine Dame vor Zug 6, keine Randbauernzüge, f-Bauer stehen lassen.
5. **Verwertung üben:** Mattführung mit Dame und mit Turm, bei Vorsprung tauschen, auf Patt achten, mit Vorsprung zügig spielen.
6. **Zum Trainieren gelegentlich 10 Minuten statt 5 spielen.**

## Abarbeitung (Stand 2026-10-08)

Umgesetzt unter `lektionen/03_MeinePartien/`. Alle Lösungen sind mit Stockfish
bei Tiefe 18 und 4 Kandidatenzügen geprüft.

| Lektion | Inhalt | Anzahl |
|---|---|---|
| 01 Was hängt? – Patzer vermeiden | Stellung vor eigenem Patzer mit Materialverlust oder Matt; Aufgabe: sicherer Zug | 344 |
| 02 Bestrafe den Fehler des Gegners | Stellung nach nicht bestraftem Gegner-Patzer; Lösung mindestens +2 | 161 |
| 03 Gewinnstellung sicher verwerten | erste Stellung ≥ +5 in nicht gewonnenen Partien; danach der Partieverlauf mit ?? und besserem Zug | 58 |
| 04 Meine Eröffnungsfehler | erster Fehler bis Zug 10 in Niederlagen, nach Eröffnung sortiert; Korrektur als Hauptzug | 126 |

Die Anzahlen schwanken bei einem erneuten Lauf um wenige Stellungen, weil die
Engine mehrfädig und damit nicht deterministisch rechnet.

**Gegenprobe:** 40 Zufallsstellungen aus den Lektionen 1 und 2 bei Tiefe 22.
In allen 40 ist die Lösung mindestens 1,5 Bauern besser als der Partiezug.

**Dafür nötige Änderungen in `chessteach.py`:**
- Unter der Zugliste zeigt ein Feld den Kommentartext zum aktuellen Zug. Die `[Befehle]` im Kommentar werden dabei ausgeblendet.
- Der PGN-Kopf `[Aufgabe "1"]` verdeckt künftige Züge in der Zugliste mit „…“, im Repertoire-Training genauso.

**Offen:**
- Im Repertoire-Training zählt nur der Lösungszug als richtig. Gleichwertige Züge („Auch gut: …“ im Kommentar) gelten dort als falsch.
- Das Brett dreht sich bei Aufgaben mit Schwarz am Zug nicht automatisch. Der Titel sagt, wer am Zug ist.
- Anonymisierung (2026-10-08, Auftrag: „vor dem pushen die namen von mir und gegner als ich und gegner anonymisieren“): Die Kopfzeilen White, Black und Termination sowie die Kommentare in allen PGNs von `03_MeinePartien` nennen nur noch „Ich“ und „Gegner“.
- Die Elo-Differenz zum Gegner ist nicht ausgewertet: Der Export enthält vermutlich die Wertung *nach* der Partie.

## Werkzeuge

Die Skripte liegen in `tools/partieanalyse/`.

```
python3 run_engine.py <pgn> evals.json 14           # ~3 min, 18 Prozesse
python3 stats.py evals.json stats.json              # Kennzahlen
python3 zusatzstatistik.py evals.json               # Patzer, Tilt, Verwertung
python3 lektionen_bauen.py evals.json <ziel>/03_MeinePartien   # ~2 min
python3 gegenprobe.py <ziel>/03_MeinePartien        # Stichprobe bei Tiefe 22
```

Spielernamen in den PGNs sind anonymisiert („Ich“ und „Gegner“). Die Skripte erkennen die eigene Seite über `CHESS_ME` (Vorgabe `Ich`). Für einen frischen chess.com-Export setzt man `CHESS_ME=<Benutzername>`; vor dem Einchecken anonymisiert man die neue PGN mit `CHESS_ME=<Benutzername> python3 anonymisieren.py <verzeichnis>`.
Der Partien-Filter für den 12.09. steckt nicht in den Skripten: Die Partien
wurden aus der PGN-Datei gelöscht.
