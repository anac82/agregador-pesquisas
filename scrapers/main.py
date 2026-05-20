"""Script principal do agregador (v2)."""
import sys
from datetime import date, timedelta
from pathlib import Path
import yaml
import pandas as pd
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scrapers import db, coletores, ponderacao
    from scrapers.excel_writer import gerar_excel
else:
    from . import db, coletores, ponderacao
    from .excel_writer import gerar_excel
ROOT = Path(__file__).parent.parent
def carregar_config():
    with open(ROOT / "data/config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
def carregar_pesos():
    df = pd.read_csv(ROOT / "data/pesos_institutos.csv")
    return dict(zip(df["instituto"], df["peso"]))
def main():
    print("=" * 60)
    print("AGREGADOR DE PESQUISAS — Eleições 2026 (v2)")
    print("=" * 60)
    cfg = carregar_config()
    pesos = carregar_pesos()
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
if __name__ == "__main__":
    main()
