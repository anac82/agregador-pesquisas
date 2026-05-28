"""
scrapers/buscar_resultados.py
------------------------------
Para cada pesquisa aprovada no TSE mas sem dados no pesquisas_manuais.csv,
usa Claude (com web_search) para tentar encontrar os resultados publicados.

Se encontrar → adiciona automaticamente no pesquisas_manuais.csv
Se não encontrar → registra no alerta.txt para coleta manual

Executado pelo workflow após o monitor_tse.py.
"""

import csv
import io
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ROOT         = Path(__file__).parent.parent
MANUAIS      = ROOT / "data" / "pesquisas_manuais.csv"
HISTORICO    = ROOT / "data" / "historico_tse.csv"
ALERTA       = ROOT / "alerta.txt"
HOJE         = date.today()

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Candidatos que rastreamos — na mesma ordem das colunas do CSV
CANDIDATOS = ["Lula", "Flávio", "Zema", "Caiado", "Renan", "Cury",
              "Daciolo", "Samara", "Aldo", "Hertz", "Rui"]


# ─── Helpers CSV ──────────────────────────────────────────────────────────────

def ler_manuais() -> tuple[list[dict], list[str]]:
    with open(MANUAIS, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows   = list(reader)
        fields = reader.fieldnames
    return rows, fields


def protos_manuais(rows: list[dict]) -> set:
    return {r["registro_tse"].strip() for r in rows if r.get("registro_tse", "").strip()}


def ler_pendentes() -> list[dict]:
    """Lê historico_tse.csv e retorna pesquisas aprovadas sem dados no manuais."""
    if not HISTORICO.exists():
        return []
    with open(HISTORICO, encoding="utf-8") as f:
        hist = list(csv.DictReader(f))

    rows, _ = ler_manuais()
    protos  = protos_manuais(rows)

    pendentes = []
    vistas    = set()
    for r in hist:
        proto = r.get("NR_PROTOCOLO_REGISTRO", "").strip()
        if not proto or proto in vistas:
            continue
        vistas.add(proto)
        if r.get("usa_no_agregador", "").strip().lower() in ("true", "1") \
                and proto not in protos:
            pendentes.append(r)

    # Ordenar do mais recente para o mais antigo
    pendentes.sort(key=lambda r: r.get("campo_fim", ""), reverse=True)
    return pendentes


def salvar_linha(row: dict, fields: list[str]) -> None:
    rows, _ = ler_manuais()
    rows.append(row)
    with open(MANUAIS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ─── Claude com web_search ────────────────────────────────────────────────────

def chamar_claude(prompt: str, api_key: str) -> str | None:
    """
    Chama Claude com web_search habilitado.
    Usa system prompt para reforçar foco em fontes abertas e formato JSON.
    """
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta":    "web-search-2025-03-05",
        "content-type":      "application/json",
    }
    payload = {
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "system": (
            "Você é um extrator especializado de dados de pesquisas eleitorais brasileiras. "
            "Sua única função é buscar resultados de pesquisas na web e retornar JSON estruturado. "
            "Sempre priorize Poder360, G1, UOL e CNN Brasil como fontes. "
            "NUNCA retorne texto fora do JSON solicitado. "
            "Se os dados estiverem atrás de paywall ou não disponíveis, retorne "
            '{"encontrou": false, "motivo": "paywall"} imediatamente.'
        ),
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = requests.post(ANTHROPIC_URL, headers=headers,
                          json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        texto = " ".join(
            b["text"] for b in data.get("content", [])
            if b.get("type") == "text"
        )
        return texto.strip() or None
    except Exception as e:
        log.error(f"    Erro Claude API: {e}")
        return None


def montar_prompt(p: dict) -> str:
    mes_ano = p.get("divulgacao", "")[:7].replace("-", "/") if p.get("divulgacao") else ""
    return f"""Você é um assistente especializado em pesquisas eleitorais brasileiras.

Preciso dos resultados desta pesquisa de intenção de voto para presidente do Brasil em 2026:

- Instituto: {p.get('instituto')}
- Protocolo TSE: {p.get('NR_PROTOCOLO_REGISTRO')}
- Período de campo: {p.get('campo_inicio')} até {p.get('campo_fim')}
- Data de divulgação: {p.get('divulgacao')}
- Amostra: {p.get('QT_ENTREVISTADO')} entrevistados

INSTRUÇÕES DE BUSCA:
1. Busque primeiro no Poder360 (poder360.com.br) — eles publicam tabelas completas de todas as pesquisas
2. Se não encontrar, busque em: G1 (g1.globo.com), UOL (uol.com.br), CNN Brasil (cnnbrasil.com.br), Folha de S.Paulo (folha.uol.com.br), O Globo (oglobo.globo.com)
3. Use queries como: "{p.get('instituto')} pesquisa presidente {mes_ano} resultado" ou "pesquisa eleitoral presidente {p.get('campo_fim', '')[:7]} {p.get('instituto')}"
4. Foque no cenário de 1º turno estimulado (lista de candidatos apresentada ao entrevistado)
5. Se encontrar cenários de 2º turno (Lula vs Flávio, Lula vs Zema, etc.), inclua também

CANDIDATOS A RASTREAR (inclua apenas os que aparecerem na pesquisa):
Lula, Flávio Bolsonaro, Romeu Zema, Ronaldo Caiado, Renan Filho, Cury, Daciolo, Samara, Aldo Rebelo, Hertz, Rui Costa

FORMATO DE RESPOSTA — retorne SOMENTE este JSON válido, sem texto antes ou depois, sem markdown:

Se encontrou:
{{
  "encontrou": true,
  "fonte": "https://url-da-fonte.com.br/artigo",
  "veiculo": "Poder360",
  "cenarios": [
    {{
      "turno": 1,
      "tipo": "estimulado",
      "candidatos": {{
        "Lula": 40.0,
        "Flávio": 35.0,
        "Zema": 4.0,
        "Caiado": 5.0,
        "Renan": 3.0,
        "Branco/Nulo": 8.0,
        "Não sabe": 5.0
      }}
    }},
    {{
      "turno": 2,
      "tipo": "Lula vs Flávio",
      "candidatos": {{
        "Lula": 47.0,
        "Flávio": 43.0,
        "Branco/Nulo": 8.0,
        "Não sabe": 2.0
      }}
    }}
  ]
}}

Se não encontrou:
{{"encontrou": false, "motivo": "paywall / não divulgado / não encontrado"}}
"""


def parsear_resposta(texto: str) -> dict | None:
    """Tenta extrair JSON válido da resposta do Claude."""
    if not texto:
        return None
    # Remover markdown se houver
    texto = texto.strip()
    if "```" in texto:
        partes = texto.split("```")
        for parte in partes:
            parte = parte.strip().lstrip("json").strip()
            try:
                return json.loads(parte)
            except Exception:
                continue
    try:
        return json.loads(texto)
    except Exception:
        # Tentar encontrar JSON dentro do texto
        import re
        m = re.search(r'\{.*\}', texto, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


def montar_linha_csv(pesquisa: dict, cenario: dict, fields: list[str]) -> dict:
    """Converte um cenário encontrado pelo Claude em linha do CSV."""
    base = {f: "" for f in fields}
    cands = cenario.get("candidatos", {})

    base.update({
        "instituto":          pesquisa.get("instituto", ""),
        "contratante":        "",
        "data_inicio_campo":  pesquisa.get("campo_inicio", ""),
        "data_fim_campo":     pesquisa.get("campo_fim", ""),
        "amostra":            str(int(float(pesquisa.get("QT_ENTREVISTADO", 0) or 0))),
        "margem_erro":        "",
        "intervalo_confianca":"95",
        "turno":              str(cenario.get("turno", 1)),
        "tipo":               cenario.get("tipo", "estimulado"),
        "metodologia":        pesquisa.get("metodologia", ""),
        "votos_validos":      "",
        "registro_tse":       pesquisa.get("NR_PROTOCOLO_REGISTRO", ""),
        "url_fonte":          cenario.get("fonte", ""),
    })

    # Candidatos
    for cand in CANDIDATOS:
        base[cand] = str(cands.get(cand, "")) if cands.get(cand) else ""

    # Branco/Nulo e Não sabe
    base["Branco/Nulo"] = str(cands.get("Branco/Nulo", "")) if cands.get("Branco/Nulo") else ""
    base["Não sabe"]    = str(cands.get("Não sabe", ""))    if cands.get("Não sabe")    else ""

    return base


# ─── Pipeline principal ───────────────────────────────────────────────────────

def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY não definida — pulando busca automática")
        return

    pendentes = ler_pendentes()
    if not pendentes:
        log.info("Nenhuma pesquisa pendente para buscar.")
        return

    log.info(f"Pesquisas pendentes para busca automática: {len(pendentes)}")

    rows, fields = ler_manuais()
    protos_ja    = protos_manuais(rows)

    encontradas  = []
    nao_encontradas = []

    for i, p in enumerate(pendentes):
        proto = p.get("NR_PROTOCOLO_REGISTRO", "")
        inst  = p.get("instituto", "")
        log.info(f"  [{i+1}/{len(pendentes)}] Buscando: {inst} — {proto}")

        # Respeitar rate limit
        if i > 0:
            time.sleep(3)

        prompt  = montar_prompt(p)
        resposta = chamar_claude(prompt, api_key)
        dados   = parsear_resposta(resposta)

        if not dados:
            log.warning(f"    Sem resposta parseável para {proto}")
            nao_encontradas.append(p)
            continue

        if not dados.get("encontrou"):
            motivo = dados.get("motivo", "não encontrado")
            log.info(f"    Não encontrado: {motivo}")
            nao_encontradas.append({**p, "_motivo": motivo})
            continue

        cenarios = dados.get("cenarios", [])
        fonte    = dados.get("fonte", "")
        linhas_adicionadas = 0

        for cenario in cenarios:
            cenario["fonte"] = fonte
            linha = montar_linha_csv(p, cenario, fields)
            # Verificar se já existe essa combinação
            chave = (linha["registro_tse"], linha["turno"], linha["tipo"])
            ja_existe = any(
                (r["registro_tse"], r["turno"], r["tipo"]) == chave
                for r in rows
            )
            if not ja_existe:
                salvar_linha(linha, fields)
                rows, _ = ler_manuais()  # recarregar após salvar
                linhas_adicionadas += 1

        if linhas_adicionadas > 0:
            log.info(f"    ✅ {linhas_adicionadas} linha(s) adicionada(s) — fonte: {fonte}")
            encontradas.append({**p, "_fonte": fonte, "_cenarios": len(cenarios)})
        else:
            log.info(f"    ⚠️  Dados encontrados mas todos já existiam no CSV")

    # ── Atualizar alerta.txt com resultado da busca ───────────────────────────
    alerta_atual = ALERTA.read_text(encoding="utf-8") if ALERTA.exists() else ""

    resumo = [
        "",
        "=" * 60,
        f"BUSCA AUTOMÁTICA DE RESULTADOS — {HOJE}",
        "=" * 60,
        "",
    ]

    if encontradas:
        resumo.append(f"✅ ENCONTRADAS E ADICIONADAS ({len(encontradas)}):")
        resumo.append("-" * 60)
        for p in encontradas:
            resumo.append(
                f"  {p.get('instituto'):30} {p.get('NR_PROTOCOLO_REGISTRO'):20} "
                f"→ {p.get('_cenarios',0)} cenário(s)  fonte: {p.get('_fonte','')[:50]}"
            )
        resumo.append("")

    if nao_encontradas:
        resumo.append(f"❌ NÃO ENCONTRADAS — COLETA MANUAL NECESSÁRIA ({len(nao_encontradas)}):")
        resumo.append("-" * 60)
        for p in nao_encontradas:
            motivo = p.get("_motivo", "sem resposta")
            resumo.append(
                f"  {p.get('instituto'):30} {p.get('NR_PROTOCOLO_REGISTRO'):20} "
                f"divulg: {p.get('divulgacao')}  [{motivo}]"
            )
        resumo.append("")

    ALERTA.write_text(alerta_atual + "\n".join(resumo), encoding="utf-8")
    log.info(f"  alerta.txt atualizado")
    log.info(f"  Encontradas: {len(encontradas)} | Não encontradas: {len(nao_encontradas)}")


if __name__ == "__main__":
    run()
