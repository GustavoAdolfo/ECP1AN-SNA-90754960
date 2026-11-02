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
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_iniciais.json"),
    carregar_mapa(BASE_DIR / "planilhas" / "mapa_finais.json"),
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


def extrair_ods(caminho_arquivo, aba=0):
    """Extrai dados de um arquivo ODS e retorna um DataFrame do pandas"""
    try:
        df = pd.read_excel(
            caminho_arquivo, engine="odf", sheet_name=aba, na_values=["NA"], header=None
        )
        if df.empty:
            raise RuntimeError(f"O arquivo {caminho_arquivo} está vazio.")
        return df
    except FileNotFoundError as exc:
        raise RuntimeError(f"O arquivo {caminho_arquivo} não foi encontrado.") from exc


def extrair_ufs(df, config):
    """Extrai os dados de uma determinada UF a partir de um DataFrame."""
    linha_inicial = config["linhaInicial"]
    coluna_uf = config["uf"]
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


def extrair_municipios(df, uf, config):
    """Extrai os dados de municípios de uma determinada UF a partir de um DataFrame."""
    try:
        coluna_uf, linha_inicial, coluna_codigo, coluna_nome, coluna_rede = (
            config["uf"],
            config["linhaInicial"],
            config["codigoMunicipio"],
            config["nomeMunicipio"],
            config["rede"],
        )
        dados = df.iloc[linha_inicial - 1 :]
        linhas_uf = dados[dados.iloc[:, indice_coluna(coluna_uf)] == uf]
        municipios = {}
        for codigo, nome, rede in zip(
            linhas_uf.iloc[:, indice_coluna(coluna_codigo)],
            linhas_uf.iloc[:, indice_coluna(coluna_nome)],
            linhas_uf.iloc[:, indice_coluna(coluna_rede)],
        ):
            if (
                isinstance(codigo, (int, str))
                and isinstance(nome, str)
                and isinstance(rede, str)
            ):
                chave = str(codigo)
                if chave not in municipios:
                    municipios[chave] = {"nome": nome, "rede": []}
                if rede not in municipios[chave]["rede"]:
                    municipios[chave]["rede"].append(rede)
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


def extrair_valores_indices(df, ano_indice, codigo_municipio, config, rede):
    """Extrai rendimento, períodos, notas SAEB, IDEB e meta de cada rede."""
    try:
        coluna_codigo = indice_coluna(config["codigoMunicipio"])
        coluna_rede = indice_coluna(config["rede"])
        mapa_ano = config[str(ano_indice)]
        colunas = {
            "geral": mapa_ano["geral"],
            "indicadorRendimento": mapa_ano["indicadorRendimento"],
            **{
                chave: coluna
                for periodo in mapa_ano["periodos"]
                for chave, coluna in periodo.items()
            },
            "idebNxP": mapa_ano["idebNxP"],
            "metaPrimeiroCiclo": mapa_ano["metaPrimeiroCiclo"],
        }

        dados = df.iloc[config["linhaInicial"] - 1 :]
        linhas = dados[
            (dados.iloc[:, coluna_codigo].astype("string") == str(codigo_municipio))
            & (dados.iloc[:, coluna_rede] == rede)
        ]
        valores = {}
        for _, linha in linhas.iterrows():
            valores = {
                chave: extrair_valor_numerico(linha, coluna)
                for chave, coluna in colunas.items()
            }
            valores["notaSAEB"] = {
                chave: extrair_valor_numerico(linha, coluna)
                for chave, coluna in mapa_ano["notaSAEB"].items()
            }
        return valores
    except KeyError as exc:
        raise RuntimeError(
            f"Chave {exc.args[0]!r} não encontrada na configuração ou nos dados "
            f"ao extrair os índices do ano {ano_indice}, "
            f"município {codigo_municipio} e rede {rede!r}."
        ) from exc


def exportar_parquet(data, fonte):
    """Exporta uma linha por rede, preservando notaSAEB como campo estruturado."""
    caminho_saida = BASE_DIR / "parquet" / f"{Path(fonte).stem}.parquet"
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "identificador": identificador,
                "ano": ano,
                "uf": uf,
                "codigoMunicipio": codigo,
                "nomeMunicipio": municipio["nome"],
                "rede": rede,
                **valores,
            }
            for identificador, anos in data.items()
            for ano, ufs in anos.items()
            for uf, municipios in ufs.items()
            for codigo, municipio in municipios.items()
            for rede, valores in municipio.items()
            if rede != "nome"
        ]
    )
    df.to_parquet(caminho_saida, index=False)


def processar_conteudo(df, config):
    """Organiza identificador > ano > UF > código do município > rede e exporta."""
    identificador = config["identificador"]
    ufs = extrair_ufs(df, config)
    data = {
        identificador: {
            ano_indice: {uf: {} for uf in sorted(ufs)}
            for ano_indice in range(2005, 2026, 2)
        }
    }
    for uf in ufs:
        municipios = extrair_municipios(df, uf, config)
        for codigo, conteudo in municipios.items():
            for ano_indice in range(2005, 2026, 2):
                data[identificador][ano_indice][uf][codigo] = {"nome": conteudo["nome"]}
                for rede in conteudo["rede"]:
                    valores_indices = extrair_valores_indices(
                        df, ano_indice, codigo, config, rede
                    )
                    data[identificador][ano_indice][uf][codigo][rede] = valores_indices

    exportar_parquet(data, config["arquivo"])
    return data


def __main__():
    for config in FONTE_ODS:
        fonte = config["arquivo"]
        df = extrair_ods(config["arquivo"])
        processar_conteudo(df, config)
        print(f"Dados extraídos de {fonte}")


if __name__ == "__main__":
    __main__()
