"""Motor de ponderação: calcula a média ponderada das pesquisas."""
import math
from datetime import date, datetime
from typing import Optional
import pandas as pd


def calcular_peso_recencia(
    data_fim_campo: date,
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
    candidatos: list,
    data_referencia: Optional[date] = None,
) -> dict:
    if data_referencia is None:
        data_referencia = date.today()

    if not pesquisas:
        return {
            "medias": {c: 0.0 for c in candidatos},
            "n_pesquisas": 0,
            "data_referencia": data_referencia,
            "detalhamento": pd.DataFrame(),
        }

    linhas = []
    soma_pesos = 0.0
    soma_ponderada = {c: 0.0 for c in candidatos}

    for p in pesquisas:
        peso = calcular_peso_final(p, pesos_institutos, config, data_referencia)
        soma_pesos += peso

        linha = {
            "instituto": p["instituto"],
            "data_fim_campo": p["data_fim_campo"],
            "amostra": p["amostra"],
            "peso_final": peso,
        }
        for c in candidatos:
            valor = p["resultados"].get(c, 0.0)
            soma_ponderada[c] += valor * peso
            linha[c] = valor
        linhas.append(linha)

    if soma_pesos == 0:
        medias = {c: 0.0 for c in candidatos}
    else:
        medias = {c: soma_ponderada[c] / soma_pesos for c in candidatos}

    return {
        "medias": medias,
        "n_pesquisas": len(pesquisas),
        "data_referencia": data_referencia,
        "detalhamento": pd.DataFrame(linhas),
    }
