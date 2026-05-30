"""Motor de ponderação: calcula a média ponderada das pesquisas."""
import math
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd

# Pesos por metodologia — refletem qualidade relativa de cobertura
# presencial > telefone > online > URA
PESOS_METODOLOGIA = {
    "presencial": 1.00,
    "telefone":   0.90,
    "telefonica": 0.90,
    "telefônica": 0.90,
    "cati":       0.90,
    "online":     0.80,
    "web":        0.80,
    "ura":        0.65,
    "robocall":   0.65,
    "automatizado": 0.65,
}


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
    # Cap em 3x a referência para evitar que amostras muito grandes dominem
    amostra_cap = min(amostra, amostra_referencia * 3)
    return math.sqrt(amostra_cap / amostra_referencia)


def calcular_peso_metodologia(metodologia: str) -> float:
    if not metodologia:
        return 1.0
    # Normalizar: minúsculas, sem acentos simples, pegar primeira palavra
    # Ex: "URA (telefone)" → "ura", "telefônica" → "telefônica"
    chave = metodologia.lower().strip().split()[0] if metodologia.strip() else ""
    return PESOS_METODOLOGIA.get(chave, 1.0)


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

    # Usar score do historico_tse se disponível
    # score já embute: amostra + metodologia + custo/entrevistado
    # Se não disponível, fallback para peso_amostra × peso_metodologia
    score = pesquisa.get("score")
    if score and float(score) > 0:
        peso_qualidade = float(score)
    else:
        peso_amo = 1.0
        if config["ponderacao"]["amostra"]["ativo"]:
            peso_amo = calcular_peso_amostra(
                pesquisa["amostra"],
                config["ponderacao"]["amostra"]["amostra_referencia"],
            )
        peso_qualidade = peso_amo * calcular_peso_metodologia(
            pesquisa.get("metodologia", "")
        )

    return peso_inst * peso_rec * peso_qualidade


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
    ultimas_medias = {}  # propaga o último valor até hoje
    while data_ref <= data_fim:
        # Janela: pesquisas com data_fim_campo entre (data_ref - janela) e data_ref
        ini_janela = data_ref - timedelta(days=janela_dias)
        na_janela = [
            p for p, dc in zip(pesquisas, datas_campo)
            if ini_janela <= dc <= data_ref
        ]
        if na_janela:
            ag = agregar(na_janela, pesos_institutos, config, data_referencia=data_ref)
            ultimas_medias = ag["medias"]
            pontos.append({
                "data":        data_ref,
                "medias":      ag["medias"],
                "n_pesquisas": ag["n_pesquisas"],
                "pesquisas":   na_janela,
            })
        else:
            # Sem pesquisas na janela: propagar último valor (linha não cai)
            pontos.append({
                "data":        data_ref,
                "medias":      ultimas_medias,
                "n_pesquisas": 0,
                "pesquisas":   [],
            })
        data_ref += timedelta(days=passo_dias)

    return {
        "pontos": pontos,
        "candidatos": candidatos,
        "passo_dias": passo_dias,
        "janela_dias": janela_dias,
    }
