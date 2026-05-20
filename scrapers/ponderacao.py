"""Motor de ponderação: calcula a média ponderada das pesquisas."""
import math
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd


def calcular_peso_recencia(
    data_fim_campo,
    data_referencia: date,
    half_life_dias: float = 30.0,
) -> float:
    if isinstance(data_fim_campo, str):
        data_fim_campo = datetime.fromisoformat(data_fim_campo).date()
    delta_dias = (data_referencia - data_fim_campo).days
    if delta_dias < 0:
        delta_dias = 0
    return math.exp(-math.log(2) * delta_dias / half_life_dias)


def calcular_peso_amostra(amostra: int, amostra_referencia: int = 2000) -> float:
    if amostra <= 0:
        return 0.0
    return math.sqrt(amostra / amostra_referencia)


def calcular_peso_final(
    pesquisa: dict,
    pesos_institutos: dict,
    config: dict,
    data_referencia: date,
) -> float:
    peso_inst = pesos_institutos.get(pesquisa["instituto"], 1.0)
    peso_rec = 1.0
    if config["ponderacao"]["recencia"]["ativo"]:
        peso_rec = calcular_peso_recencia(
            pesquisa["data_fim_campo"],
            data_referencia,
            config["ponderacao"]["recencia"]["half_life_dias"],
        )
    peso_amo = 1.0
    if config["ponderacao"]["amostra"]["ativo"]:
        peso_amo = calcular_peso_amostra(
            pesquisa["amostra"],
            config["ponderacao"]["amostra"]["amostra_referencia"],
        )
    return peso_inst * peso_rec * peso_amo


def agregar(
    pesquisas: list,
    pesos_institutos: dict,
    config: dict,
    data_referencia: Optional[date] = None,
) -> dict:
    """
    Agrega uma lista de pesquisas. Diferente da v1: descobre os candidatos
    automaticamente unindo o que apareceu nas pesquisas.
    """
    if data_referencia is None:
        data_referencia = date.today()
    if not pesquisas:
        return {
            "medias": {},
            "candidatos": [],
            "n_pesquisas": 0,
            "data_referencia": data_referencia,
            "detalhamento": pd.DataFrame(),
        }
    candidatos_set = set()
    for p in pesquisas:
        candidatos_set.update(p["resultados"].keys())
    especiais = ["Outros", "Branco/Nulo", "Não sabe"]
    principais = sorted([c for c in candidatos_set if c not in especiais])
    candidatos = principais + [c for c in especiais if c in candidatos_set]
    linhas = []
    soma_pesos_por_cand = {c: 0.0 for c in candidatos}
    soma_ponderada = {c: 0.0 for c in candidatos}
    for p in pesquisas:
        peso = calcular_peso_final(p, pesos_institutos, config, data_referencia)
        linha = {
            "instituto": p["instituto"],
            "data_fim_campo": p["data_fim_campo"],
            "amostra": p["amostra"],
            "peso_final": peso,
        }
        for c in candidatos:
            valor = p["resultados"].get(c)
            if valor is not None:
                soma_ponderada[c] += valor * peso
                soma_pesos_por_cand[c] += peso
                linha[c] = valor
            else:
                linha[c] = None
        linhas.append(linha)
    medias = {}
    for c in candidatos:
        if soma_pesos_por_cand[c] > 0:
            medias[c] = soma_ponderada[c] / soma_pesos_por_cand[c]
        else:
            medias[c] = 0.0
    return {
        "medias": medias,
        "candidatos": candidatos,
        "n_pesquisas": len(pesquisas),
        "data_referencia": data_referencia,
        "detalhamento": pd.DataFrame(linhas),
    }


def agregar_serie_temporal(
    pesquisas: list,
    pesos_institutos: dict,
    config: dict,
    passo_dias: int = 7,
    janela_dias: int = 30,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
) -> dict:
    """
    Calcula a média móvel ponderada ao longo do tempo (série temporal).

    Para cada data de referência (a cada `passo_dias`), pega as pesquisas
    dentro de uma janela de `janela_dias` ANTERIORES a essa data e calcula
    a média ponderada usando a função agregar() existente.

    Retorna um dicionário com:
      - "pontos": lista de dicts {data, medias, n_pesquisas} ordenada no tempo
      - "candidatos": lista de candidatos que aparecem em qualquer ponto
      - "passo_dias", "janela_dias"
    """
    if not pesquisas:
        return {"pontos": [], "candidatos": [], "passo_dias": passo_dias,
                "janela_dias": janela_dias}

    # Converter datas de fim de campo para objetos date
    def _to_date(v):
        if isinstance(v, str):
            return datetime.fromisoformat(v).date()
        return v

    datas_campo = [_to_date(p["data_fim_campo"]) for p in pesquisas]

    # Intervalo da série: da pesquisa mais antiga até hoje (ou data_fim)
    if data_inicio is None:
        data_inicio = min(datas_campo)
    if data_fim is None:
        data_fim = date.today()

    # Descobrir todos os candidatos do conjunto inteiro (para colunas estáveis)
    candidatos_set = set()
    for p in pesquisas:
        candidatos_set.update(p["resultados"].keys())
    especiais = ["Outros", "Branco/Nulo", "Não sabe"]
    principais = sorted([c for c in candidatos_set if c not in especiais])
    candidatos = principais + [c for c in especiais if c in candidatos_set]

    pontos = []
    data_ref = data_inicio
    while data_ref <= data_fim:
        # Janela: pesquisas com data_fim_campo entre (data_ref - janela) e data_ref
        ini_janela = data_ref - timedelta(days=janela_dias)
        na_janela = [
            p for p, dc in zip(pesquisas, datas_campo)
            if ini_janela <= dc <= data_ref
        ]
        if na_janela:
            ag = agregar(na_janela, pesos_institutos, config, data_referencia=data_ref)
            pontos.append({
                "data": data_ref,
                "medias": ag["medias"],
                "n_pesquisas": ag["n_pesquisas"],
            })
        else:
            # Sem pesquisas na janela: ponto vazio (mantém continuidade do eixo)
            pontos.append({
                "data": data_ref,
                "medias": {},
                "n_pesquisas": 0,
            })
        data_ref += timedelta(days=passo_dias)

    return {
        "pontos": pontos,
        "candidatos": candidatos,
        "passo_dias": passo_dias,
        "janela_dias": janela_dias,
    }
