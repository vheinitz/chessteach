# -*- coding: utf-8 -*-
"""Kommentartext für die Anzeige: [Befehle] und [%…]-Daten entfernen."""
import chessteach


def test_befehle_werden_entfernt():
    assert chessteach.comment_text("[Sq e1] Richtig: 18.Te1. [Ar e2e4]") == "Richtig: 18.Te1."


def test_clk_daten_werden_entfernt():
    assert chessteach.comment_text("[%clk 0:04:58] gut") == "gut"


def test_leer():
    assert chessteach.comment_text(None) == ""
