from __future__ import annotations

from zoi_agent.tools.inventory import _normalize_vehicle, norm, summarize

# Busca/filtros determinísticos foram removidos na migração Agno (EstoqueExpert
# raciocina sobre o inventário no prompt). Sobram: norm, _normalize_vehicle
# (ponte entre os 2 schemas Nick) e summarize.


def test_norm() -> None:
    assert norm("Mecânico") == "mecanico"
    assert norm(None) == ""
    assert norm("SÃO PAULO") == "sao paulo"


def test_normalize_schema_enxuto():
    """Schema Nick enxuto: id/km/url sem imagens -> ponte p/ shape interno."""
    v = {"id": "960913", "km": 51665, "url": "https://nickmotors.com.br/x",
         "marca": "Caoa", "modelo": "Tiggo", "ano": 2020, "preco": 67900,
         "diferenciais": ["A", "B"]}
    out = _normalize_vehicle(v)
    assert out["external_id"] == "960913"
    assert out["quilometragem"] == 51665      # km -> quilometragem
    assert out["url_anuncio"] == "https://nickmotors.com.br/x"
    assert out["opcionais"] == ["A", "B"]      # diferenciais -> opcionais
    assert out["imagens"] == []                 # sem imagens (graceful)


def test_normalize_schema_completo():
    """Schema Nick completo: external_id/quilometragem/imagens já no shape."""
    v = {"external_id": "111", "quilometragem": 30000, "url_anuncio": "u",
         "marca": "VW", "modelo": "Gol", "ano": 2019, "preco": 50000,
         "imagens": ["a.jpg", "b.jpg"], "opcionais": ["ar"]}
    out = _normalize_vehicle(v)
    assert out["external_id"] == "111"
    assert out["quilometragem"] == 30000
    assert out["imagens"] == ["a.jpg", "b.jpg"]


def test_summarize():
    v = _normalize_vehicle({
        "external_id": "1", "marca": "VW", "modelo": "Gol", "ano": 2019,
        "preco": 50000, "quilometragem": 30000, "cambio": "manual", "cor": "prata",
        "imagens": ["http://img/1a.jpg", "http://img/1b.jpg"],
        "opcionais": ["ar", "abs", "airbag", "vidro", "trava", "som"],
    })
    s = summarize(v)
    assert s.external_id == "1"
    assert s.imagem == "http://img/1a.jpg"
    assert s.quilometragem == 30000
    assert len(s.opcionais) <= 5
