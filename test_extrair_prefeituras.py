"""Testes da leitura de arquivos CSV eleitorais."""

import pandas as pd
import pytest

import extrair_prefeituras
from extrair_prefeituras import extrair_dados


def test_extrair_dados_preserva_acentos_latin1(tmp_path):
    """Preserva acentos, delimitadores e a linha de cabeçalho."""
    caminho = tmp_path / "eleicoes.csv"
    caminho.write_bytes(
        (
            '"NM_ELEICAO";"NM_MUNICIPIO"\n'
            '"Eleição Ordinária";"São Paulo"\n'
        ).encode("latin-1")
    )

    df = extrair_dados(caminho)

    assert df.values.tolist() == [
        ["NM_ELEICAO", "NM_MUNICIPIO"],
        ["Eleição Ordinária", "São Paulo"],
    ]


def test_extrair_dados_arquivo_inexistente(tmp_path):
    with pytest.raises(RuntimeError, match="não foi encontrado"):
        extrair_dados(tmp_path / "inexistente.csv")


def test_normaliza_codigo_para_busca_do_partido(tmp_path, config_partidos):
    caminho = tmp_path / "eleicoes.csv"
    caminho.write_text(
        "UF;MUNICIPIO;CARGO;NUMERO;SIGLA;PARTIDO;NOMINAIS;LEGENDA\n"
        "PA;4600;Vereador;10;AA;Partido A;10;0\n"
        "PA;04600;Prefeito;20;BB;Partido B;30;5\n",
        encoding="latin-1",
    )
    config = {
        **config_partidos,
        "coluna_nome_municipio": "F",
    }

    df = extrair_dados(caminho)
    municipios = extrair_prefeituras.extrair_municipios(df, "PA", config)

    assert list(municipios) == [4600]
    assert df.iloc[1:, 6].tolist() == ["10", "30"]
    resultado = extrair_prefeituras.extrair_partido_mais_votado(
        df, "PA", next(iter(municipios)), config
    )
    assert resultado["numero_partido"] == 20


def test_exportar_parquet_uma_linha_por_municipio(tmp_path, monkeypatch):
    """Preserva anos, UFs e nomes, exportando códigos como inteiros."""
    monkeypatch.setattr(extrair_prefeituras, "BASE_DIR", tmp_path)
    data = {
        2000: {
            "AC": {
                "01120": {"nome": "ACRELANDIA"},
                "01007": {"nome": "BUJARI"},
            },
            "SP": {"71072": {"nome": "SÃO PAULO"}},
        },
        2004: {"AC": {"01120": {"nome": "ACRELANDIA"}}},
    }
    for ufs in data.values():
        for municipios in ufs.values():
            for municipio in municipios.values():
                municipio.update(
                    numero_partido=0, sigla_partido="EE", nome_partido="EMPATE"
                )

    extrair_prefeituras.exportar_parquet(data, "planilhas/eleicoes.csv")

    df = pd.read_parquet(tmp_path / "parquet" / "eleicoes.parquet")

    assert df.columns.tolist() == [
        "ano_eleicao", "uf", "codigo_municipio", "nome_municipio",
        "numero_partido", "sigla_partido", "nome_partido",
    ]
    assert df.values.tolist() == [
        [2000, "AC", 1120, "ACRELANDIA", 0, "EE", "EMPATE"],
        [2000, "AC", 1007, "BUJARI", 0, "EE", "EMPATE"],
        [2000, "SP", 71072, "SÃO PAULO", 0, "EE", "EMPATE"],
        [2004, "AC", 1120, "ACRELANDIA", 0, "EE", "EMPATE"],
    ]
    assert pd.api.types.is_integer_dtype(df["codigo_municipio"])
    assert not df.duplicated(["ano_eleicao", "uf", "codigo_municipio"]).any()


@pytest.mark.parametrize("codigo", ["invalido", None, "4600.5"])
def test_normalizar_codigo_rejeita_valores_invalidos(codigo):
    with pytest.raises(ValueError):
        extrair_prefeituras.normalizar_codigos_municipios(pd.Series([codigo]))


@pytest.fixture
def config_partidos():
    return {
        "linha_inicial": 2,
        "coluna_uf": "A",
        "coluna_codigo_municipio": "B",
        "coluna_descricao_cargo": "C",
        "descricao_cargo": "Prefeito",
        "coluna_numero_partido": "D",
        "coluna_sigla_partido": "E",
        "coluna_nome_partido": "F",
        "coluna_qt_votos_nominais": "G",
        "coluna_qt_votos_legenda": "H",
    }


def test_partido_mais_votado_soma_linhas_e_filtra_cargo_uf_municipio(config_partidos):
    df = pd.DataFrame([
        ["AC", "01120", "Prefeito", 99, "ZZ", "Cabeçalho", "9999", "0"],
        ["AC", "01120", "Prefeito", 10, "AA", "Partido A", "30", "5"],
        ["AC", "01120", "Prefeito", "10", "AA", "Partido A", 30, 10],
        ["AC", "01120", "Prefeito", 20, "BB", "Partido B", "70", "0"],
        ["AC", "01120", "Vereador", 20, "BB", "Partido B", 9999, 0],
        ["SP", "01120", "Prefeito", 20, "BB", "Partido B", 9999, 0],
        ["AC", "99999", "Prefeito", 20, "BB", "Partido B", 9999, 0],
    ])

    resultado = extrair_prefeituras.extrair_partido_mais_votado(
        df, "AC", "01120", config_partidos
    )

    assert resultado == {
        "numero_partido": 10,
        "sigla_partido": "AA",
        "nome_partido": "Partido A",
    }


def test_partido_mais_votado_cargo_configuravel_codigo_numerico(config_partidos):
    config_partidos.update(linha_inicial=1, descricao_cargo="Vereador")
    df = pd.DataFrame([
        ["AC", 1120, "Prefeito", 10, "AA", "Partido A", 500, 0],
        ["AC", 1120, "Vereador", 20, "BB", "Partido B", 10, 5],
    ])
    resultado = extrair_prefeituras.extrair_partido_mais_votado(
        df, "AC", "1120", config_partidos
    )
    assert resultado["numero_partido"] == 20


def test_partido_mais_votado_empate(config_partidos):
    config_partidos["linha_inicial"] = 1
    df = pd.DataFrame([
        ["AC", "01120", "Prefeito", 10, "AA", "Partido A", 10, 5],
        ["AC", "01120", "Prefeito", 20, "BB", "Partido B", 15, 0],
    ])
    assert extrair_prefeituras.extrair_partido_mais_votado(
        df, "AC", "01120", config_partidos
    ) == {"numero_partido": 0, "sigla_partido": "EE", "nome_partido": "EMPATE"}


def test_processamento_exporta_partidos_e_resumo_final(
    tmp_path, monkeypatch, capsys, config_partidos
):
    config = {
        **config_partidos,
        "linha_inicial": 1,
        "coluna_nome_municipio": "I",
        "ano_eleicao": 2000,
        "arquivo": "eleicoes.csv",
    }
    df = pd.DataFrame([
        ["PA", "04600", "Prefeito", 10, "AA", "Partido A", 10, 5, "NOVA IPIXUNA"],
        ["PA", "04600", "Prefeito", 20, "BB", "Partido B", 15, 0, "NOVA IPIXUNA"],
        ["AC", "01120", "Prefeito", 10, "AA", "Partido A", 20, 0, "ACRELANDIA"],
        ["MT", "89834", "Vereador", 10, "AA", "Partido A", 20, 0, "MUNICIPIO TESTE"],
    ])
    monkeypatch.setattr(extrair_prefeituras, "BASE_DIR", tmp_path)
    monkeypatch.setattr(extrair_prefeituras, "FONTE_ODS", [config])
    monkeypatch.setattr(extrair_prefeituras, "extrair_dados", lambda caminho: df)

    extrair_prefeituras.__main__()

    resultado = pd.read_parquet(tmp_path / "parquet" / "eleicoes.parquet")
    empate = resultado.loc[resultado.uf.eq("PA")].iloc[0]
    assert empate["numero_partido"] == 0
    assert empate["sigla_partido"] == "EE"
    assert empate["nome_partido"] == "EMPATE"
    assert resultado.loc[resultado.uf.eq("AC"), "numero_partido"].iloc[0] == 10
    ausente = resultado.loc[resultado.uf.eq("MT")].iloc[0]
    assert ausente["numero_partido"] == 0
    assert ausente["sigla_partido"] == "NA"
    assert ausente["nome_partido"] == "NA"
    assert len(resultado) == 3
    saida = capsys.readouterr().out
    assert "Resumo de empates: 1 ocorrência(s)." in saida
    assert "2000 | PA | 4600 | NOVA IPIXUNA" in saida
    assert "Resumo de municípios sem registros para o cargo: 1 ocorrência(s)." in saida
    assert "2000 | MT | 89834 | MUNICIPIO TESTE | Prefeito" in saida
    assert "qt_votos_nominais" not in resultado.columns


def test_resumo_sem_empates(monkeypatch, capsys):
    monkeypatch.setattr(extrair_prefeituras, "FONTE_ODS", [])
    extrair_prefeituras.__main__()
    saida = capsys.readouterr().out
    assert "Resumo de empates: 0 ocorrência(s)." in saida
    assert "Resumo de municípios sem registros para o cargo: 0 ocorrência(s)." in saida


def test_partido_mais_votado_sem_registros(config_partidos):
    df = pd.DataFrame([
        ["AC", "01120", "Vereador", 10, "AA", "Partido A", 10, 5],
    ])
    config_partidos["linha_inicial"] = 1
    assert extrair_prefeituras.extrair_partido_mais_votado(
        df, "AC", "01120", config_partidos
    ) == {"numero_partido": 0, "sigla_partido": "NA", "nome_partido": "NA"}


@pytest.mark.parametrize("votos", ["inválido", None])
def test_partido_mais_votado_rejeita_votos_invalidos(config_partidos, votos):
    config_partidos["linha_inicial"] = 1
    df = pd.DataFrame([
        ["AC", "01120", "Prefeito", 10, "AA", "Partido A", votos, 5],
    ])
    with pytest.raises((ValueError, RuntimeError)):
        extrair_prefeituras.extrair_partido_mais_votado(
            df, "AC", "01120", config_partidos
        )
