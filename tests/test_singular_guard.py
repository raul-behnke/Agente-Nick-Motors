"""Hard guard: bolhas no plural são reescritas pra singular quando count=1."""
from __future__ import annotations

from zoi_agent.orchestrator import _enforce_singular_question


def test_algum_desses_veiculos_chamou_atencao() -> None:
    out = _enforce_singular_question("Algum desses veículos chamou a sua atenção?")
    assert "desses" not in out.lower()
    assert "veículos" not in out.lower()
    assert "esse" in out.lower()


def test_qual_desses() -> None:
    out = _enforce_singular_question("Qual desses chamou mais sua atenção?")
    assert "desses" not in out.lower()


def test_algum_deles() -> None:
    out = _enforce_singular_question("Algum deles te interessou?")
    assert "deles" not in out.lower()


def test_desses_carros() -> None:
    out = _enforce_singular_question("Topou em algum desses carros?")
    assert "desses carros" not in out.lower()


def test_frase_singular_passa_intacta() -> None:
    msg = "Topou nesse?"
    assert _enforce_singular_question(msg) == msg


def test_string_vazia() -> None:
    assert _enforce_singular_question("") == ""
