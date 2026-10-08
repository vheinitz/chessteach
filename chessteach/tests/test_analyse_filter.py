# -*- coding: utf-8 -*-
"""Filter der Alternativvarianten in der Engine-Analyse."""
import chess
import chess.engine as E

import chessteach


def mv(uci):
    return chess.Move.from_uci(uci)


def cp(v, turn=chess.WHITE):
    return E.PovScore(E.Cp(v), turn)


def mate(n, turn=chess.WHITE):
    return E.PovScore(E.Mate(n), turn)


ALT = [(mv("a2a3"), cp(40)), (mv("b2b3"), cp(30))]


def test_matt_in_4_nur_beste_variante():
    res = [(mv("d1h5"), mate(4))] + ALT
    assert chessteach.filter_alternatives(res) == res[:1]


def test_matt_in_5_alternativen_bleiben_wenn_auch_matt():
    res = [(mv("d1h5"), mate(5)), (mv("a2a3"), mate(6))]
    assert len(chessteach.filter_alternatives(res)) == 2


def test_deutlich_schlechtere_alternative_weg():
    res = [(mv("d1h5"), cp(400)), (mv("a2a3"), cp(180)), (mv("b2b3"), cp(250))]
    assert chessteach.filter_alternatives(res) == [res[0], res[2]]


def test_kleine_differenz_bei_ausgeglichener_stellung_bleibt():
    res = [(mv("e2e4"), cp(30)), (mv("d2d4"), cp(-20))]
    assert len(chessteach.filter_alternatives(res)) == 2


def test_schwarz_am_zug_relative_sicht():
    # Schwarz am Zug: Weiß-Sicht −4.00 ist für Schwarz +4.00
    res = [(mv("e7e5"), cp(400, chess.BLACK)), (mv("d7d5"), cp(100, chess.BLACK))]
    assert chessteach.filter_alternatives(res) == res[:1]
