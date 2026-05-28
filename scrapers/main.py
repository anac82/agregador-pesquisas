"""Script principal do agregador (v2)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import yaml
import pandas as pd
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scrapers import db, coletores, ponderacao, pagina_web
    from scrapers.excel_writer import gerar_excel
else:
    from . import db, coletores, ponderacao, pagina_web
    from .excel_writer import gerar_excel
ROOT = Path(__file__).parent.parent
def carregar_config():
    with open(ROOT / "data/config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
def carregar_pesos():
    df = pd.read_csv(ROOT / "data/pesos_institutos.csv")
    return dict(zip(df["instituto"], df["peso"]))
def carregar_scores():
    """Lê historico_tse.csv e retorna dict {protocolo: dict_de_campos}."""
    path = ROOT / "data" / "historico_tse.csv"
    if not path.exists():
        return {}
    cols_needed = ["NR_PROTOCOLO_REGISTRO", "score", "custo_reais",
                   "custo_por_entrevistado", "flag_instituto_conhecido",
                   "flag_nacional_explicito", "metodologia"]
    df = pd.read_csv(path, usecols=lambda c: c in cols_needed)
    resultado = {}
    for _, row in df.iterrows():
        proto = str(row["NR_PROTOCOLO_REGISTRO"])
        resultado[proto] = {
            "score":                    row.get("score"),
            "custo_reais":              row.get("custo_reais"),
            "custo_por_entrevistado":   row.get("custo_por_entrevistado"),
            "flag_instituto_conhecido": row.get("flag_instituto_conhecido"),
            "flag_nacional_explicito":  row.get("flag_nacional_explicito"),
            "metodologia_tse":          row.get("metodologia"),
        }
    return resultado

def main():
    print("=" * 60)
    print("AGREGADOR DE PESQUISAS — Eleições 2026 (v2)")
    print("=" * 60)
    cfg = carregar_config()
    pesos = carregar_pesos()
    scores = carregar_scores()
    print(f"→ {len(scores)} scores carregados do historico_tse.csv")
    cenarios = cfg["cenarios"]
    print(f"\n→ {len(cenarios)} cenários configurados:")
    for cen in cenarios:
        print(f"   - {cen['nome']} (turno {cen['turno']})")
    print(f"→ {len(pesos)} institutos com pesos")
    print("\n[1/4] Coletando pesquisas...")
    novas = coletores.coletar_todas(str(ROOT / "data/pesquisas_manuais.csv"))
    print(f"   {len(novas)} pesquisas encontradas")
    print("\n[2/4] Salvando no banco (classificando cenários)...")
    conn = db.get_connection(str(ROOT / cfg["saida"]["banco_sqlite"]))

    # Limpar banco e reinserir tudo do CSV — garante que o banco
    # sempre reflita exatamente o CSV, sem acúmulo de versões antigas
    conn.execute("DELETE FROM resultados")
    conn.execute("DELETE FROM pesquisas")
    conn.commit()
    print("   Banco limpo — reinserindo do CSV...")

    inseridas = 0
    nao_classificadas = 0
    for p in novas:
        result = db.inserir_pesquisa(conn, p, cenarios)
        if result is not None:
            inseridas += 1
        elif db.classificar_cenario(p, cenarios) is None:
            nao_classificadas += 1
    print(f"   {inseridas} pesquisas novas inseridas")
    if nao_classificadas > 0:
        print(f"   {nao_classificadas} pesquisas nao se encaixaram em nenhum cenario")
    print("\n[3/4] Agregando por cenário...")
    janela = cfg["ponderacao"]["janela_dias"]
    desde = date.today() - timedelta(days=janela)

    # Parâmetros da série temporal (Fase A) — com defaults se não estiverem no config
    serie_cfg = cfg["ponderacao"].get("serie_temporal", {})
    serie_ativa = serie_cfg.get("ativo", True)
    passo_dias = serie_cfg.get("passo_dias", 7)
    janela_movel = serie_cfg.get("janela_dias", 30)

    agregacoes_por_cenario = {}
    pesquisas_por_cenario = {}
    series_por_cenario = {}
    for cen in cenarios:
        pesquisas = db.listar_pesquisas(conn, cen["nome"], desde=desde)
        pesquisas_por_cenario[cen["nome"]] = pesquisas
        ag = ponderacao.agregar(pesquisas, pesos, cfg)
        agregacoes_por_cenario[cen["nome"]] = ag
        print(f"   {cen['nome']:30s} {ag['n_pesquisas']:3d} pesquisas")

        # Série temporal: usa TODAS as pesquisas do cenário (sem corte de janela),
        # pois a janela móvel é aplicada ponto a ponto dentro da função.
        if serie_ativa:
            todas_cen = db.listar_pesquisas(conn, cen["nome"])
            serie = ponderacao.agregar_serie_temporal(
                todas_cen, pesos, cfg,
                passo_dias=passo_dias, janela_dias=janela_movel,
            )
            series_por_cenario[cen["nome"]] = serie
    todas_pesquisas = []
    for cen in cenarios:
        todas_pesquisas.extend(db.listar_pesquisas(conn, cen["nome"]))

    # Injetar campos do histórico em cada pesquisa via protocolo TSE
    CAMPOS_HISTORICO = ["score", "custo_reais", "custo_por_entrevistado",
                        "flag_instituto_conhecido", "flag_nacional_explicito",
                        "metodologia_tse"]

    def _injetar(lista):
        for p in lista:
            proto = p.get("registro_tse", "")
            dados = scores.get(proto, {})
            for campo in CAMPOS_HISTORICO:
                p[campo] = dados.get(campo)

    _injetar(todas_pesquisas)
    for cen_pesquisas in pesquisas_por_cenario.values():
        _injetar(cen_pesquisas)

    print("\n[4/4] Gerando Excel...")
    caminho = gerar_excel(
        str(ROOT / cfg["saida"]["arquivo_excel"]),
        agregacoes_por_cenario,
        todas_pesquisas,
        pesos,
        cfg,
        pesquisas_por_cenario,
        series_por_cenario=series_por_cenario,
    )
    print("\n" + "=" * 60)
    print("RESULTADO POR CENÁRIO:")
    print("=" * 60)
    for nome, ag in agregacoes_por_cenario.items():
        print(f"\n{nome} ({ag['n_pesquisas']} pesquisas):")
        if ag["n_pesquisas"] == 0:
            print("   (sem dados)")
        else:
            for c in ag["candidatos"]:
                v = ag["medias"].get(c, 0)
                print(f"   {c:20s} {v:6.2f}%")
    print("\n" + "=" * 60)
    print(f"\nExcel gerado: {caminho}")

    # Calcular slopes sobre a série agregada (já ponderada)
    def calcular_slopes(series_por_cenario: dict) -> dict:
        """
        Calcula slope (pp/semana) por candidato usando os pontos
        da série temporal agregada já ponderada — últimos 60 dias.
        """
        import math
        serie = series_por_cenario.get("1º Turno", {})
        pontos = serie.get("pontos", [])
        if not pontos:
            return {}

        HOJE = date.today()
        result = {}

        # Coletar candidatos disponíveis
        candidatos = set()
        for p in pontos:
            candidatos.update(p.get("medias", {}).keys())

        for cand in candidatos:
            pts = []
            for p in pontos:
                data = p.get("data")
                val  = p.get("medias", {}).get(cand)
                if data and val is not None:
                    try:
                        d = date.fromisoformat(str(data)[:10])
                        dias = (HOJE - d).days
                        if dias <= 60:
                            pts.append((dias, val))
                    except Exception:
                        pass

            if len(pts) < 3:
                continue

            # Regressão ponderada: mais recente = mais peso
            w  = [math.exp(-0.05 * p[0]) for p in pts]
            x  = [-p[0] for p in pts]
            y  = [p[1] for p in pts]
            sw   = sum(w)
            swx  = sum(wi*xi for wi,xi in zip(w,x))
            swy  = sum(wi*yi for wi,yi in zip(w,y))
            swxx = sum(wi*xi*xi for wi,xi in zip(w,x))
            swxy = sum(wi*xi*yi for wi,xi,yi in zip(w,x,y))
            denom = sw*swxx - swx*swx
            if abs(denom) < 1e-10:
                continue
            slope = (sw*swxy - swx*swy) / denom * 7  # pp/semana
            result[cand] = round(slope, 3)

        return result

    slopes = calcular_slopes(series_por_cenario)
    print(f"   Slopes (pp/sem): {slopes}")

    # Gerar página web (GitHub Pages) se houver séries temporais
    if series_por_cenario:
        print("\n[+] Gerando página web (docs/index.html)...")
        from scrapers.ultimas_pesquisas import extrair_ultimas_pesquisas
        ultimas = extrair_ultimas_pesquisas(str(ROOT / "data/pesquisas_manuais.csv"))
        caminho_html = pagina_web.gerar_pagina_html(
            str(ROOT / "docs/index.html"),
            series_por_cenario,
            data_geracao=date.today(),
            cenario_principal="1º Turno",
            ultimas_pesquisas=ultimas,
            slopes=slopes,
        )
        print(f"    Página gerada: {caminho_html}")
if __name__ == "__main__":
    main()
