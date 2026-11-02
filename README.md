# Trabalho de final de semestre (A3) para a unidade curricular "Sistemas de Controle Inteligente Artificial"

Este repositório contém o projeto desenvolvido para a unidade curricular "Sistemas de Controle Inteligente Artificial", incluindo notebooks, dados e documentação relacionados ao trabalho final de semestre.

## Estrutura do repositório

- `notebooks/`: Contém os notebooks utilizados para análise e desenvolvimento do projeto.
- `dados/`: Contém os conjuntos de dados utilizados no projeto.
- `README.md`: Este arquivo, contendo informações sobre o projeto.
- `docs/`: Contém a documentação adicional do projeto, se houver.

## Sobre o período analisado

O projeto abrange dados referentes ao período de 2005 a 2025, considerando anos de eleição a cada dois anos.
Os dados incluem informações sobre municípios, redes de ensino e indicadores educacionais, organizados de forma a facilitar a análise temporal e geográfica.
A relação entre ano de avaliação e ano de eleição é considerada para organizar os dados de forma consistente, permitindo análises que levem em conta o contexto temporal das avaliações educacionais.
O ano da avaliação está relacionado aos dois anos anteriores, o que pode corresponder a uma alternância de partido mandatário e não ao partido eleito (que assume no ano seguinte à eleição).

## Exportação de municípios

O script `extrair_prefeituras.py` gera arquivos em `parquet/` com uma linha por
município e ano de eleição, contendo as colunas `ano_eleicao`, `uf`,
`codigo_municipio` e `nome_municipio`. Os códigos de município são normalizados
como inteiros na extração, na busca do partido e na exportação: `04600` vira `4600`.
Na leitura do CSV eleitoral, todas as colunas são carregadas como texto para
evitar tipos mistos antes da normalização dos códigos. Os votos são convertidos em
números ao calcular o partido mais votado.

A exportação também inclui `numero_partido`, `sigla_partido` e `nome_partido`,
sem os valores de votos. Empates no maior total (votos nominais + legenda) são
registrados como `0`, `EE` e `EMPATE`, respectivamente. Ao final da execução,
é impresso um resumo com o ano, UF, código e nome dos municípios com empate.
Municípios sem registros para o cargo configurado são mantidos com código de
partido `0`, sigla `NA` e nome `NA`, sem interromper o processamento. Esses casos
aparecem em um resumo separado ao final, incluindo também a descrição do cargo.
