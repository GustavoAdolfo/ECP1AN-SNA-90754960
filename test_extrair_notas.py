"""Testes da hierarquia de anos, UFs, municípios, redes e da exportação."""

import pandas as pd
import pytest

import extrair_notas


@pytest.mark.parametrize("identificador", ["iniciais", "finais"])
def test_processar_conteudo_preserva_hierarquia(tmp_path, monkeypatch, identificador):
    """Preserva municípios, redes e índices em cada ano e na leitura do Parquet."""
    monkeypatch.setattr(extrair_notas, "BASE_DIR", tmp_path)
    df = pd.DataFrame(
        [
            ["UF", "Código", "Nome", "Rede", "Geral", "Rendimento", "Período"],
            ["CE", 2300101, "Abaiara", "Municipal", 90, 0.9, 91],
            ["CE", 2300101, "Abaiara", "Estadual", 80, 0.8, 81],
            ["CE", 2300101, "Abaiara", "Pública", "-", None, 85],
            ["CE", 2300150, "Acarape", "Municipal", 70, 0.7, 71],
            ["BA", 2900108, "Abaíra", "Municipal", 60, 0.6, 61],
            ["RJ", 3300100, "Angra dos Reis", "Estadual", 50, 0.5, 51],
        ]
    )
    config = {
        "identificador": identificador,
        "arquivo": f"{identificador}.ods",
        "linhaInicial": 2,
        "uf": "A",
        "codigoMunicipio": "B",
        "nomeMunicipio": "C",
        "rede": "D",
    }
    anos = list(range(2005, 2026, 2))
    for ano in anos:
        config[str(ano)] = {
            "geral": "E",
            "indicadorRendimento": "F",
            "periodos": [{"ano_1": "G"}],
            "notaSAEB": {
                "matematica": "E",
                "linguaPortuguesa": "G",
                "notaMediaPadronizada": "F",
            },
            "idebNxP": "F",
            "metaPrimeiroCiclo": "-",
        }
    config["2007"]["geral"] = "G"

    data = extrair_notas.processar_conteudo(df, config)

    assert set(data) == {identificador}
    assert list(data[identificador]) == anos
    for ano in anos:
        assert set(data[identificador][ano]) == {"BA", "CE", "RJ"}
        assert set(data[identificador][ano]["CE"]) == {"2300101", "2300150"}
        municipio = data[identificador][ano]["CE"]["2300101"]
        assert municipio["nome"] == "Abaiara"
        assert set(municipio) == {"nome", "Municipal", "Estadual", "Pública"}
        assert municipio["Municipal"] == {
            "geral": 91 if ano == 2007 else 90,
            "indicadorRendimento": 0.9,
            "ano_1": 91,
            "idebNxP": 0.9,
            "metaPrimeiroCiclo": None,
            "notaSAEB": {
                "matematica": 90,
                "linguaPortuguesa": 91,
                "notaMediaPadronizada": 0.9,
            },
        }
        assert municipio["Estadual"]["geral"] == (81 if ano == 2007 else 80)
        assert municipio["Pública"]["indicadorRendimento"] is None
    assert data[identificador][2005]["CE"]["2300101"]["Pública"]["geral"] is None
    assert data[identificador][2005]["CE"] is not data[identificador][2007]["CE"]
    assert data[identificador][2005]["CE"] is not data[identificador][2005]["BA"]

    resultado = pd.read_parquet(tmp_path / "parquet" / f"{identificador}.parquet")
    assert list(resultado.columns) == [
        "identificador",
        "ano",
        "uf",
        "codigoMunicipio",
        "nomeMunicipio",
        "rede",
        "geral",
        "indicadorRendimento",
        "ano_1",
        "idebNxP",
        "metaPrimeiroCiclo",
        "notaSAEB",
    ]
    assert len(resultado) == len(anos) * 6
    dimensoes = ["identificador", "ano", "uf", "codigoMunicipio", "rede"]
    assert set(resultado[dimensoes].itertuples(index=False, name=None)) == {
        (identificador, ano, uf, str(codigo), rede)
        for ano in anos
        for uf, codigo, _, rede, *_ in df.iloc[1:].itertuples(index=False, name=None)
    }
    filtrado = resultado.loc[
        (resultado["ano"] == 2007)
        & (resultado["uf"] == "CE")
        & (resultado["codigoMunicipio"] == "2300101")
        & (resultado["rede"] == "Municipal")
    ]
    assert len(filtrado) == 1
    assert filtrado.iloc[0]["nomeMunicipio"] == "Abaiara"
    assert filtrado.iloc[0]["geral"] == 91
    assert filtrado.iloc[0]["notaSAEB"] == {
        "matematica": 90,
        "linguaPortuguesa": 91,
        "notaMediaPadronizada": 0.9,
    }


def test_exportar_parquet_preserva_rede_sem_indices(tmp_path, monkeypatch):
    """Redes ainda sem índices também produzem linhas consultáveis."""
    monkeypatch.setattr(extrair_notas, "BASE_DIR", tmp_path)
    data = {
        "iniciais": {
            2005: {
                "CE": {
                    "2300101": {
                        "nome": "Abaiara",
                        "Municipal": {},
                        "Estadual": {},
                        "Pública": {},
                    }
                }
            }
        }
    }

    extrair_notas.exportar_parquet(data, "iniciais.ods")

    resultado = pd.read_parquet(tmp_path / "parquet" / "iniciais.parquet")
    assert len(resultado) == 3
    assert set(resultado["rede"]) == {"Municipal", "Estadual", "Pública"}
    assert resultado["ano"].tolist() == [2005] * 3
    assert resultado["codigoMunicipio"].tolist() == ["2300101"] * 3


@pytest.mark.parametrize(
    "config", extrair_notas.FONTE_ODS, ids=lambda c: c["identificador"]
)
@pytest.mark.parametrize("ano", range(2005, 2026, 2))
def test_extrair_notas_e_metas_conforme_mapas(config, ano):
    """Verifica as colunas de cada ano nos dois mapas reais."""
    mapa = config[str(ano)]
    colunas = {
        **mapa["notaSAEB"],
        "idebNxP": mapa["idebNxP"],
        "metaPrimeiroCiclo": mapa["metaPrimeiroCiclo"],
    }
    largura = (
        max(
            extrair_notas.indice_coluna(coluna)
            for coluna in colunas.values()
            if coluna != "-"
        )
        + 1
    )
    df = pd.DataFrame(
        [[None] * largura for _ in range(config["linhaInicial"])], dtype=object
    )
    linha = config["linhaInicial"] - 1
    df.iat[linha, extrair_notas.indice_coluna(config["codigoMunicipio"])] = "2300101"
    df.iat[linha, extrair_notas.indice_coluna(config["rede"])] = "Municipal"
    esperados = {}
    for indice, (chave, coluna) in enumerate(colunas.items(), start=1):
        if coluna == "-":
            esperados[chave] = None
        else:
            esperados[chave] = indice + 0.25
            df.iat[linha, extrair_notas.indice_coluna(coluna)] = str(esperados[chave])

    valores = extrair_notas.extrair_valores_indices(
        df, ano, "2300101", config, "Municipal"
    )

    assert valores["notaSAEB"] == {
        chave: esperados[chave] for chave in mapa["notaSAEB"]
    }
    assert valores["idebNxP"] == esperados["idebNxP"]
    assert valores["metaPrimeiroCiclo"] == esperados["metaPrimeiroCiclo"]


@pytest.mark.parametrize(
    "valor", [None, float("nan"), "-", "ND", "ND*", "ND***", " ND "]
)
def test_extrair_valor_numerico_ausente(valor):
    """Células sem valor numérico resultam em None."""
    assert extrair_notas.extrair_valor_numerico(pd.Series([valor]), "A") is None


def test_extrair_valor_numerico_invalido():
    """Textos inesperados não são silenciosamente convertidos em ausência."""
    with pytest.raises(ValueError):
        extrair_notas.extrair_valor_numerico(pd.Series(["inválido"]), "A")


@pytest.mark.parametrize(
    "valor", [231.42, "231.42", "231,42", " 231,42 ", "231,42*", "231,42**"]
)
def test_extrair_valor_numerico_decimal(valor):
    """Aceita valores numéricos e notas textuais com ponto ou vírgula decimal."""
    assert extrair_notas.extrair_valor_numerico(pd.Series([valor]), "A") == 231.42
