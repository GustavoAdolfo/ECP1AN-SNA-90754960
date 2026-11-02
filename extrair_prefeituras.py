"""Extrai dados de arquivos ODS usando pandas e exporta para Parquet."""

import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent


def carregar_mapa(caminho):
    """Carrega um mapa de configuração a partir de um arquivo JSON."""
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


FONTE_ODS = [
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2000.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2004.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2008.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2012.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2016.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2020.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_partidos_prefeituras_2024.json"),
]


def indice_coluna(letras):
    """Converte letras de coluna (ex: 'A', 'B', 'AA') em índice numérico (0-based)."""
    letras = letras.strip().upper()
    if not letras or not letras.isascii() or not letras.isalpha():
        raise ValueError(f"Coluna inválida: {letras!r}")

    indice = 0
    for letra in letras:
        indice = indice * 26 + ord(letra) - ord("A") + 1
    return indice - 1


def extrair_dados(caminho_arquivo):
    """Lê o CSV eleitoral em Latin-1 como texto, preservando zeros iniciais."""
    try:
        df = pd.read_csv(
            caminho_arquivo, sep=";", header=None, encoding="latin-1", dtype=str
        )
        if df.empty:
            raise RuntimeError(f"O arquivo {caminho_arquivo} está vazio.")
        return df
    except FileNotFoundError as exc:
        raise RuntimeError(f"O arquivo {caminho_arquivo} não foi encontrado.") from exc


def extrair_ufs(df, config):
    """Extrai os dados de uma determinada UF a partir de um DataFrame."""
    linha_inicial = config["linha_inicial"]
    coluna_uf = config["coluna_uf"]
    try:
        ufs = {
            valor
            for valor in df.iloc[linha_inicial - 1 :, indice_coluna(coluna_uf)]
            if isinstance(valor, str) and len(valor) == 2
        }
        if not ufs:
            raise RuntimeError(
                f"Não foram encontrados dados de UFs a partir da linha {linha_inicial}."
            )
        return ufs
    except KeyError as exc:
        raise RuntimeError(
            f'A coluna "{coluna_uf}" não foi encontrada no DataFrame.'
        ) from exc


def normalizar_codigos_municipios(codigos):
    """Converte códigos para inteiros, rejeitando ausências e frações."""
    numeros = pd.to_numeric(codigos, errors="raise")
    if numeros.isna().any() or (numeros % 1 != 0).any():
        raise ValueError(
            "Códigos de município devem ser números inteiros não ausentes."
        )
    return numeros.astype("int64")


def extrair_municipios(df, uf, config):
    """Extrai os dados de municípios de uma determinada UF a partir de um DataFrame."""
    try:
        coluna_uf, linha_inicial, coluna_codigo, coluna_nome = (
            config["coluna_uf"],
            config["linha_inicial"],
            config["coluna_codigo_municipio"],
            config["coluna_nome_municipio"],
        )
        dados = df.iloc[linha_inicial - 1 :]
        linhas_uf = dados[dados.iloc[:, indice_coluna(coluna_uf)] == uf]
        municipios = {}
        for codigo, nome in zip(
            normalizar_codigos_municipios(
                linhas_uf.iloc[:, indice_coluna(coluna_codigo)]
            ),
            linhas_uf.iloc[:, indice_coluna(coluna_nome)],
        ):
            if isinstance(codigo, (int, str)) and isinstance(nome, str):
                chave = int(codigo)
                if chave not in municipios:
                    municipios[chave] = {"nome": nome}
        if not municipios:
            raise RuntimeError(
                f"Não foram encontrados municípios a partir da linha {linha_inicial}."
            )
        return municipios
    except KeyError as exc:
        raise RuntimeError(
            f'Colunas "{coluna_codigo}" ou "{coluna_nome}" não foram encontradas no DataFrame.'
        ) from exc


def extrair_valor_numerico(linha, coluna):
    """Converte números com notas de rodapé; '-' e resultados ND viram None."""
    if coluna == "-":
        return None
    valor = linha.iloc[indice_coluna(coluna)]
    if isinstance(valor, str):
        valor = valor.strip()
        if valor in {"ND", "ND*", "ND***"}:
            return None
        valor = valor.rstrip("*").replace(",", ".")
    if pd.isna(valor) or valor == "-":
        return None
    return pd.to_numeric(valor, errors="raise")


def extrair_partido_mais_votado(df, uf, codigo_municipio, config):
    """Soma votos nominais e de legenda por partido para a UF, município e cargo.

    Retorna apenas a identificação do partido; empates usam 0 / EE / EMPATE.
    Ausência de registros para o cargo usa 0 / NA / NA.
    """
    try:
        (
            linha_inicial,
            coluna_descricao_cargo,
            descricao_cargo,
            coluna_codigo_municipio,
            coluna_uf,
            coluna_numero_partido,
            coluna_sigla_partido,
            coluna_nome_partido,
            coluna_qt_votos_nominais,
            coluna_qt_votos_legenda,
        ) = (
            config["linha_inicial"],
            config["coluna_descricao_cargo"],
            config["descricao_cargo"],
            config["coluna_codigo_municipio"],
            config["coluna_uf"],
            config["coluna_numero_partido"],
            config["coluna_sigla_partido"],
            config["coluna_nome_partido"],
            config["coluna_qt_votos_nominais"],
            config["coluna_qt_votos_legenda"],
        )
        dados = df.iloc[linha_inicial - 1 :]
        linhas = dados[
            (dados.iloc[:, indice_coluna(coluna_uf)] == uf)
            & (
                normalizar_codigos_municipios(
                    dados.iloc[:, indice_coluna(coluna_codigo_municipio)]
                )
                == int(codigo_municipio)
            )
            & (dados.iloc[:, indice_coluna(coluna_descricao_cargo)] == descricao_cargo)
        ]
        if linhas.empty:
            return {
                "numero_partido": 0,
                "sigla_partido": "NA",
                "nome_partido": "NA",
            }

        partidos = pd.DataFrame(
            {
                "numero_partido": linhas.iloc[
                    :, indice_coluna(coluna_numero_partido)
                ].astype("string"),
                "sigla_partido": linhas.iloc[:, indice_coluna(coluna_sigla_partido)],
                "nome_partido": linhas.iloc[:, indice_coluna(coluna_nome_partido)],
                "qt_votos_nominais": pd.to_numeric(
                    linhas.iloc[:, indice_coluna(coluna_qt_votos_nominais)],
                    errors="raise",
                ),
                "qt_votos_legenda": pd.to_numeric(
                    linhas.iloc[:, indice_coluna(coluna_qt_votos_legenda)],
                    errors="raise",
                ),
            }
        )
        if partidos.isna().any().any():
            raise RuntimeError(
                f"Identificação de partido ou votos ausentes para o cargo "
                f"{descricao_cargo!r}, município {codigo_municipio} e UF {uf}."
            )

        totais = partidos.groupby("numero_partido", sort=False, as_index=False).agg(
            sigla_partido=("sigla_partido", "first"),
            nome_partido=("nome_partido", "first"),
            qt_votos_nominais=("qt_votos_nominais", "sum"),
            qt_votos_legenda=("qt_votos_legenda", "sum"),
        )
        totais["total_votos"] = totais["qt_votos_nominais"] + totais["qt_votos_legenda"]
        vencedores = totais[totais["total_votos"] == totais["total_votos"].max()]
        if len(vencedores) > 1:
            return {
                "numero_partido": 0,
                "sigla_partido": "EE",
                "nome_partido": "EMPATE",
            }
        vencedor = vencedores.iloc[0]
        return {
            "numero_partido": int(vencedor["numero_partido"]),
            "sigla_partido": vencedor["sigla_partido"],
            "nome_partido": vencedor["nome_partido"],
        }
    except KeyError as exc:
        raise RuntimeError(
            f"Chave {exc.args[0]!r} não encontrada na configuração ou nos dados "
            f"ao extrair o partido mais votado, "
            f"município {codigo_municipio} e UF {uf}."
        ) from exc


def exportar_parquet(data, fonte):
    """Exporta uma linha por município e ano de eleição para Parquet."""
    caminho_saida = BASE_DIR / "parquet" / f"{Path(fonte).stem}.parquet"
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "ano_eleicao": ano_eleicao,
                "uf": uf,
                "codigo_municipio": codigo,
                "nome_municipio": municipio["nome"],
                "numero_partido": municipio["numero_partido"],
                "sigla_partido": municipio["sigla_partido"],
                "nome_partido": municipio["nome_partido"],
            }
            for ano_eleicao, ufs in data.items()
            for uf, municipios in ufs.items()
            for codigo, municipio in municipios.items()
        ]
    )
    df["codigo_municipio"] = normalizar_codigos_municipios(df["codigo_municipio"])
    df.to_parquet(caminho_saida, index=False)


def processar_conteudo(df, config):
    """Organiza ano eleição > ano > UF > município > cargo > partido."""
    ano_eleicao = config["ano_eleicao"]
    ufs = extrair_ufs(df, config)
    data = {ano_eleicao: {uf: {} for uf in sorted(ufs)}}
    for uf in ufs:
        municipios = extrair_municipios(df, uf, config)
        for codigo, conteudo in municipios.items():
            partido = extrair_partido_mais_votado(df, uf, codigo, config)
            data[ano_eleicao][uf][codigo] = {"nome": conteudo["nome"], **partido}

    exportar_parquet(data, config["arquivo"])
    return data


def __main__():
    empates = []
    sem_registros = []
    for config in FONTE_ODS:
        fonte = config["arquivo"]
        df = extrair_dados(config["arquivo"])
        data = processar_conteudo(df, config)
        for ano, ufs in data.items():
            for uf, municipios in ufs.items():
                for codigo, municipio in municipios.items():
                    if municipio["sigla_partido"] == "EE":
                        empates.append((ano, uf, codigo, municipio["nome"]))
                    elif municipio["sigla_partido"] == "NA":
                        sem_registros.append(
                            (ano, uf, codigo, municipio["nome"], config["descricao_cargo"])
                        )
        print(f"Dados extraídos de {fonte}")
    print(f"Resumo de empates: {len(empates)} ocorrência(s).")
    for ano, uf, codigo, nome in sorted(empates):
        print(f"{ano} | {uf} | {codigo} | {nome}")
    print(f"Resumo de municípios sem registros para o cargo: {len(sem_registros)} ocorrência(s).")
    for ano, uf, codigo, nome, cargo in sorted(sem_registros):
        print(f"{ano} | {uf} | {codigo} | {nome} | {cargo}")


if __name__ == "__main__":
    __main__()
