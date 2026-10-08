# -*- coding: utf-8 -*-
"""Regressionstests für die Schachbrett-Farbzuordnung.

Merksatz: "Weißes Feld unten rechts" -> h1 ist hell, a1 ist dunkel.
"""
import chess

import chessteach


def test_a1_ist_dunkel():
    assert chessteach.square_color(chess.A1) == chessteach.DARK


def test_h1_ist_hell():
    assert chessteach.square_color(chess.H1) == chessteach.LIGHT


def test_a8_ist_hell():
    assert chessteach.square_color(chess.A8) == chessteach.LIGHT


def test_h8_ist_dunkel():
    assert chessteach.square_color(chess.H8) == chessteach.DARK


def test_benachbarte_felder_wechseln_die_farbe():
    # horizontal (f < 7) und vertikal (r < 7) darf nie dieselbe Farbe folgen
    for s in range(64):
        f, r = s % 8, s // 8
        if f < 7:
            assert chessteach.square_color(s) != chessteach.square_color(s + 1)
        if r < 7:
            assert chessteach.square_color(s) != chessteach.square_color(s + 8)


def test_32_helle_und_32_dunkle_felder():
    colors = [chessteach.square_color(s) for s in range(64)]
    assert colors.count(chessteach.LIGHT) == 32
    assert colors.count(chessteach.DARK) == 32


def test_beide_zeichenstellen_nutzen_dieselbe_logik():
    # draw_mini_board und BoardCanvas.redraw rufen beide square_color() auf,
    # daher muss es hier nur eine einzige Quelle der Wahrheit geben.
    import inspect
    src = inspect.getsource(chessteach)
    assert src.count("square_color(s)") >= 2
    assert "LIGHT if (f + r)" not in src
