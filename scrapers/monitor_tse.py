"""
scrapers/monitor_tse.py
-----------------------
Baixa o CSV do TSE, atualiza data/historico_tse.csv e gera alerta.txt.

Executado automaticamente pelo workflow todo dia antes do agregador rodar.
Não tem dependência de repositório externo — tudo fica no próprio agregador.
"""

import csv
import io
import json
import logging
import math
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

ROOT         = Path(__file__).parent.parent
HISTORICO    = ROOT / "data" / "historico_tse.csv"
MANUAIS      = ROOT / "data" / "pesquisas_manuais.csv"
ALERTA       = ROOT / "alerta.txt"
HOJE         = date.today()

URL_TSE        = ("https://cdn.tse.jus.br/estatistica/sead/odsele/"
                  "pesquisa_eleitoral/pesquisa_eleitoral_2026.zip")
ARQUIVO_BRASIL = "pesquisa_eleitoral_2026_BRASIL.csv"

# ─── Mapeamento de nomes ───────────────────────────────────────────────────────

FANTASIA_PARA_CURTO = {
    "GRUPO GERP GERP MERCADO GERP OPINIAO GERPAUDIT":  "Gerp",
    "BOAS IDEIAS, ESTRATEGIA E INTELIGENCIA DIGITAL.": "Boas Ideias",
    "INSTITUTO FRANCA DE PESQUISA PESQUISA E ASSESSORIA": "Instituto França",
    "DATA POVO CONSULTORIA":            "Data Povo",
    "INDEXA PESQUISAS":                 "Indexa",
    "JOTA JORNALISMO":                  "Jota",
    "PODERDATA":                        "PoderData",
    "REAL TIME BIG DATA":               "Real Time Big Data",
    "RANKING BRASIL INTELIGENCIA":      "Ranking Brasil",
    "IPSENSUS PESQUISAS":               "Ipsensus",
    "MEDIA - INTELIGENCIA EM PESQUISA": "Média Inteligência",
    "ATLASINTEL":                       "AtlasIntel",
    "100 CIDADES":                      "100 Cidades",
    "NEXUS":                            "Nexus",
    "VERITA":                           "Veritá",
    "QUALITTA EMPREENDIMENTOS":         "Qualitta",
    "DELTA AGENCIA DE PESQUISA":        "Delta Agência",
    "INSTITUTO PHOENIX & ASSOCIADOS":   "Instituto Phoenix",
    "INSTITUTO DE PESQUISA MULTIPLA":   "Inst. Pesquisa Múltipla",
    "AFFARE INSTITUTE":                 "Affare Institute",
    "ANOVA INSTITUTO DE PESQUISA":      "Anova",
    "DATATRENDS":                       "DataTrends",
    "EXATUS CONSULTORIA E PESQUISA":    "Exatus",
    "ITEM PESQUISAS TECNICAS":          "Item Pesquisas",
    "INSTITUTO GP1 DE PESQUISA":        "GP1 Pesquisa",
    "INSTITUTO AMAZONIA DE PESQUISA - IAP": "Inst. Amazônia",
    "IPEN - INSTITUTO DE PESQUISA DO NORTE": "IPEN",
    "PERCENT PESQUISA DE MERCADO E OPINIAO": "Percent",
    "DATA CONTROL INSTITUTO DE PESQUISA": "Data Control",
    "IGAPE- INSTITUTO GAZETA DE PEQUISAS": "IGAPE",
    "SECULUS CONSULTORIA E ASSESSORIA LTDA": "Seculus",
}

RAZAO_PARA_CURTO = {
    "QUAEST PESQUISAS, CONSULTORIA E PROJETOS LTDA.":                  "Quaest",
    "DATAFOLHA INSTITUTO DE PESQUISAS LTDA.":                          "Datafolha",
    "INSTITUTO PARANA DE PESQUISAS E ANALISE DE CONSUMIDOR LTDA":      "Paraná Pesquisas",
    "MDA-PESQUISA DE OPINIAO PUBLICA E CONSULT. ESTATIST. LTDA - EPP": "MDA",
    "IPESPE INST DE PESQUISAS SOCIAIS POLITICAS E ECONOMICAS":         "Ipespe",
    "VETOR ARROW INSTITUTO DE PESQUISA E OPINIAO LTDA":                "Vetor",
    "INSTITUTO VOX BRASIL OPINIAO E PESQUISAS LTDA":                   "Vox Brasil",
    "COLECTTA INSTITUTO DE PESQUISA E ESTATISTICA LTDA":               "Colectta",
    "INSTITUTO DE PESQUISAS PERFIL LTDA":                              "Perfil Pesquisas",
    "DATA TEMPO LIMITADA":                                             "Data Tempo",
    "DATAPRESS INSTITUTO DE PESQUISA, COMUNICACAO E PUBLICIDADE LTDA": "Datapress",
    "INSTITUTO DE PESQUISAS RESULTADO IPR":                            "IPR",
    "MORAIS & DIAS INSTITUTO DE OPINI O P BLICA LTDA  - ME":          "Morais & Dias",
    "DATA CENSUS LTDA":                                                "Data Census",
    "MAPA MARKETING E PARTICIPACOES LTDA":                             "Mapa Pesquisas",
    "VIAVOX CONSULTORIA ADMINISTRATIVA E PESQUISAS DE OPINIAO LTDA":   "Viavox",
}

PADROES_NACIONAL = [
    r"eleitorado brasileiro", r"todo o (país|brasil)", r"26 estados",
    r"(cinco|5).*regiões do brasil", r"regiões do brasil",
    r"abrangência.*(é )?nacional", r"coleta.*(é|de abrangência) nacional",
    r"universo.*brasil", r"eleitorado.*brasil",
    r"amostra.*representativa.*brasil",
    r"estratificad.*(por|pelas?) (grandes? )?regiões",
    r"área de abrangência.*nacional", r"nível nacional",
    r"eleitores?.*(de )?todo.*brasil",
]
PADROES_ESTADUAL = [
    r"eleitorado do estado", r"eleitorado desta unidade da federação",
    r"eleitores? do estado", r"pesquisa realizada no estado",
    r"realizada? no estado", r"abrangência.*estado",
    r"coleta.*estado (do|da) [a-z]", r"universo.*estado (do|da) [a-z]",
    r"representativa.*estado (do|da) [a-z]",
    r"eleitorado de [a-záàâãéèêíïóôõöúüç]+(,| |$)",
]
INSTITUTOS_CONHECIDOS = {
    "QUAEST", "DATAFOLHA", "ATLASINTEL", "PARANA PESQUISAS",
    "REAL TIME BIG DATA", "FUTURA", "NEXUS", "FSB", "MDA", "GERP",
    "BOAS IDEIAS", "PODERDATA", "100 CIDADES", "JOTA", "INDEXA",
    "DATA POVO", "IPESPE", "VETOR", "VOX BRASIL", "COLECTTA",
    "QUAEST PESQUISAS", "DATAFOLHA INSTITUTO",
    "INSTITUTO PARANA DE PESQUISAS", "MDA-PESQUISA",
}

def _normalizar_protocolo(p: str) -> str:
    """Converte BR008352026 → BR-00835/2026."""
    import re
    p = str(p).strip().upper()
    # Já está no formato correto
    if re.match(r'^BR-\d{5}/\d{4}$', p):
        return p
    # Formato sem hífen e sem barra: BR008352026
    m = re.match(r'^BR0*(\d+)(\d{4})$', p)
    if m:
        numero = m.group(1).zfill(5)
        ano    = m.group(2)
        return f"BR-{numero}/{ano}"
    return p


COLUNAS_HISTORICO = [
    "NR_PROTOCOLO_REGISTRO", "instituto", "tse_registro",
    "campo_inicio", "campo_fim", "campo_dias", "divulgacao",
    "QT_ENTREVISTADO", "custo_reais", "custo_por_entrevistado",
    "score",
    "metodologia", "pesquisa_propria",
    "status", "usa_no_agregador",
    "flag_amostra_ok", "flag_nacional_explicito",
    "flag_estadual_explicito", "flag_instituto_conhecido",
]


# ─── Funções ───────────────────────────────────────────────────────────────────

def baixar() -> pd.DataFrame:
    log.info("Baixando CSV do TSE...")
    r = requests.get(URL_TSE, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        with zf.open(ARQUIVO_BRASIL) as f:
            df = pd.read_csv(f, sep=";", encoding="latin1", low_memory=False)
    log.info(f"  {len(df)} registros totais")
    return df


def processar(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["DS_CARGO"] == "Presidente"].copy()

    texto = (
        df["DS_METODOLOGIA_PESQUISA"].fillna("") + " " +
        df["DS_PLANO_AMOSTRAL"].fillna("") + " " +
        df["DS_DADO_MUNICIPIO"].fillna("")
    ).str.lower()

    qt = pd.to_numeric(df["QT_ENTREVISTADO"], errors="coerce").fillna(0)

    f2 = pd.Series(False, index=df.index)
    for p in PADROES_NACIONAL:
        f2 |= texto.str.contains(p, regex=True, na=False)

    f3 = pd.Series(False, index=df.index)
    for p in PADROES_ESTADUAL:
        f3 |= texto.str.contains(p, regex=True, na=False)

    inst_combined = (df["NM_EMPRESA_FANTASIA"].fillna("").str.upper() + " " +
                     df["NM_EMPRESA"].fillna("").str.upper())
    f_conh = inst_combined.apply(lambda x: any(k in x for k in INSTITUTOS_CONHECIDOS))

    df["flag_amostra_ok"]          = qt > 1000
    df["flag_nacional_explicito"]  = f2
    df["flag_estadual_explicito"]  = f3
    df["flag_instituto_conhecido"] = f_conh
    df["usa_no_agregador"]         = (qt > 1000) & f2

    def _status(row):
        n = int(row["QT_ENTREVISTADO"]) if pd.notna(row["QT_ENTREVISTADO"]) else 0
        if not row["flag_amostra_ok"]:          return f"4_EXCLUIDA_AMOSTRA (n={n})"
        if row["flag_nacional_explicito"]:       return "1_APROVADA"
        if row["flag_estadual_explicito"]:       return "2_EXCLUIDA_ESTADUAL"
        return "3_INCONCLUSIVA"

    df["status"] = df.apply(_status, axis=1)

    def _nome(row):
        fantasia = str(row["NM_EMPRESA_FANTASIA"]).strip()
        razao    = str(row["NM_EMPRESA"]).strip()
        if fantasia and fantasia not in ("#NULO#", "nan", ""):
            return FANTASIA_PARA_CURTO.get(fantasia, fantasia)
        return RAZAO_PARA_CURTO.get(razao, razao)

    df["instituto"] = df.apply(_nome, axis=1)

    df["custo_reais"] = pd.to_numeric(
        df["VR_PESQUISA"].astype(str).str.replace(",", "."), errors="coerce"
    )
    for orig, novo in [
        ("DT_INICIO_PESQUISA", "campo_inicio"),
        ("DT_FIM_PESQUISA",    "campo_fim"),
        ("DT_DIVULGACAO",      "divulgacao"),
        ("DT_REGISTRO",        "tse_registro"),
    ]:
        df[novo] = pd.to_datetime(df[orig], errors="coerce").dt.date

    df["campo_dias"] = (
        pd.to_datetime(df["DT_FIM_PESQUISA"]) -
        pd.to_datetime(df["DT_INICIO_PESQUISA"])
    ).dt.days

    m = df["DS_METODOLOGIA_PESQUISA"].fillna("").str.lower()

    # Ordem de precedência: URA > online > telefone > presencial
    df["metodologia"] = "presencial"
    df.loc[
        m.str.contains(r"telefon|cati", regex=True) &
        ~m.str.contains(r"\bura\b|robocall|automatiz|online|web|formulário", regex=True),
        "metodologia"
    ] = "telefone"
    df.loc[
        m.str.contains(r"online|coleta.*web|questionário.*web|formulário eletrônico", regex=True),
        "metodologia"
    ] = "online"
    df.loc[
        m.str.contains(r"\bura\b|robocall|automatiz", regex=True),
        "metodologia"
    ] = "URA"

    df["pesquisa_propria"] = df["ST_PESQUISA_PROPRIA"] == "S"

    df["custo_por_entrevistado"] = df.apply(
        lambda r: round(r["custo_reais"] / r["QT_ENTREVISTADO"], 2)
        if pd.notna(r["custo_reais"]) and r["QT_ENTREVISTADO"] > 0 else None,
        axis=1
    )

    # ── Score da pesquisa ─────────────────────────────────────────────────────
    # score = f_amostra × f_metodologia × f_custo
    # Calculado sobre o conjunto completo; a mediana de custo/entrevistado
    # é usada como referência para normalizar o fator custo.
    PESO_METOD = {"presencial": 1.00, "telefone": 0.90, "online": 0.80, "URA": 0.65}
    cpp_vals   = df["custo_por_entrevistado"].dropna()
    cpp_ref    = cpp_vals.median() if len(cpp_vals) > 0 else 1.0

    def _score(row):
        n   = row["QT_ENTREVISTADO"] if pd.notna(row["QT_ENTREVISTADO"]) else 0
        n   = min(n, 10000)          # cap em 10.000 para evitar distorção de amostras suspeitas
        f_a = math.sqrt(max(n, 0) / 2000)
        f_m = PESO_METOD.get(row["metodologia"], 0.75)
        cpp = row["custo_por_entrevistado"]
        if pd.notna(cpp) and cpp > 0 and cpp_ref > 0:
            f_c = math.sqrt(cpp / cpp_ref)
            f_c = max(0.5, min(1.5, f_c))
        else:
            f_c = 1.0
        return round(f_a * f_m * f_c, 3)

    df["score"] = df.apply(_score, axis=1)

    # Normalizar protocolo para formato BR-XXXXX/2026 (igual ao pesquisas_manuais.csv)
    df["NR_PROTOCOLO_REGISTRO"] = df["NR_PROTOCOLO_REGISTRO"].apply(_normalizar_protocolo)

    return df


def protocolos_csv(caminho: Path, coluna: str) -> set:
    if not caminho.exists():
        return set()
    with open(caminho, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {r[coluna].strip() for r in reader if r.get(coluna, "").strip()}


def gerar_alerta(df: pd.DataFrame,
                 protos_historico: set,
                 protos_manuais: set) -> tuple[str, bool]:
    """Retorna (texto_alerta, tem_novas)."""

    aprovadas  = df[df["usa_no_agregador"]].drop_duplicates("NR_PROTOCOLO_REGISTRO")
    novas_tse  = aprovadas[~aprovadas["NR_PROTOCOLO_REGISTRO"].astype(str).isin(protos_historico)]
    sem_dados  = aprovadas[~aprovadas["NR_PROTOCOLO_REGISTRO"].astype(str).isin(protos_manuais)]

    L = [
        "=" * 60,
        f"MONITOR TSE — {HOJE}",
        f"Presidenciais no TSE: {len(df)}   |   Aprovadas: {len(aprovadas)}",
        "=" * 60,
        "",
    ]

    # Novas no TSE
    if len(novas_tse) > 0:
        L.append(f"🆕 NOVAS NO TSE ({len(novas_tse)}):")
        L.append("-" * 60)
        for _, r in novas_tse.sort_values("divulgacao").iterrows():
            proto = str(r["NR_PROTOCOLO_REGISTRO"])
            n     = int(r["QT_ENTREVISTADO"]) if pd.notna(r["QT_ENTREVISTADO"]) else 0
            custo = f"R$ {r['custo_reais']:,.0f}".replace(",", ".") if pd.notna(r["custo_reais"]) else "n/d"
            cpp   = f" (R$ {r['custo_por_entrevistado']:.2f}/entrev.)".replace(",", ".") if pd.notna(r["custo_por_entrevistado"]) else ""
            flag  = "✅ já no manuais" if proto in protos_manuais else "❌ falta no manuais"
            L += [
                f"INSTITUTO:   {r['instituto']}",
                f"PROTOCOLO:   {proto}",
                f"CAMPO:       {r['campo_inicio']} até {r['campo_fim']}",
                f"DIVULGAÇÃO:  {r['divulgacao']}",
                f"AMOSTRA:     {n:,} entrevistados".replace(",", "."),
                f"CUSTO:       {custo}{cpp}",
                f"METODOLOGIA: {r['metodologia']}",
                f"MANUAIS:     {flag}",
                "-" * 60,
                "",
            ]
    else:
        L += ["✅ Nenhuma pesquisa nova no TSE hoje.", ""]

    # Aprovadas sem dados no manuais
    if len(sem_dados) > 0:
        L.append(f"⏳ APROVADAS SEM DADOS NO AGREGADOR ({len(sem_dados)}):")
        L.append("-" * 60)
        for _, r in sem_dados.sort_values("campo_fim", ascending=False).iterrows():
            n = int(r["QT_ENTREVISTADO"]) if pd.notna(r["QT_ENTREVISTADO"]) else 0
            L.append(
                f"  {r['instituto']:30} {str(r['NR_PROTOCOLO_REGISTRO']):20} "
                f"campo_fim: {r['campo_fim']}  n={n:,}  divulg: {r['divulgacao']}".replace(",", ".")
            )
        L.append("")
    else:
        L += ["✅ Todas as aprovadas já têm dados no manuais.", ""]

    L.append(f"Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    return "\n".join(L), len(novas_tse) > 0


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    log.info(f"=== Monitor TSE — {HOJE} ===")

    df_raw = baixar()
    df     = processar(df_raw)

    # Ler histórico e manuais locais
    protos_hist    = protocolos_csv(HISTORICO,  "NR_PROTOCOLO_REGISTRO")
    protos_manuais = protocolos_csv(MANUAIS,    "registro_tse")

    log.info(f"  historico_tse.csv:     {len(protos_hist)} protocolos")
    log.info(f"  pesquisas_manuais.csv: {len(protos_manuais)} protocolos")

    # Atualizar historico_tse.csv
    hist_novo = (
        df[COLUNAS_HISTORICO]
        .sort_values(["campo_fim", "instituto"], ascending=[False, True])
        .reset_index(drop=True)
    )
    hist_novo.to_csv(HISTORICO, index=False, encoding="utf-8")
    log.info(f"  historico_tse.csv atualizado: {len(hist_novo)} pesquisas")

    # Gerar alerta
    alerta, tem_novas = gerar_alerta(df, protos_hist, protos_manuais)
    ALERTA.write_text(alerta, encoding="utf-8")
    log.info(f"  alerta.txt salvo")
    print("\n" + alerta)

    return 1 if tem_novas else 0


if __name__ == "__main__":
    sys.exit(run())
