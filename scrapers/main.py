"""Script principal do agregador."""
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
    print("AGREGADOR DE PESQUISAS — Eleições 2026")
    print("=" * 60)

    cfg = carregar_config()
    pesos = carregar_pesos()
    candidatos = cfg["candidatos"]
    cenario = cfg["cenario_ativo"]

    print(f"\n→ Cenário: {cenario}")
    print(f"→ {len(pesos)} institutos configurados")

    print("\n[1/4] Coletando pesquisas...")
    novas = coletores.coletar_todas(str(ROOT / "data/pesquisas_manuais.csv"))
    print(f"   {len(novas)} pesquisas encontradas")

    print("\n[2/4] Salvando no banco...")
    conn = db.get_connection(str(ROOT / cfg["saida"]["banco_sqlite"]))
    inseridas = 0
    for p in novas:
        if db.inserir_pesquisa(conn, p):
            inseridas += 1
    print(f"   {inseridas} pesquisas novas inseridas")

    print("\n[3/4] Carregando pesquisas da janela...")
    janela = cfg["ponderacao"]["janela_dias"]
    desde = date.today() - timedelta(days=janela)
    pesquisas = db.listar_pesquisas(conn, cenario, desde=desde)
    print(f"   {len(pesquisas)} pesquisas dos últimos {janela} dias")

    if not pesquisas:
        print("\n⚠️  Nenhuma pesquisa na janela.")
        return

    print("\n[4/4] Calculando média ponderada e gerando Excel...")
    agregacao = ponderacao.agregar(pesquisas, pesos, cfg, candidatos)
    caminho = gerar_excel(
        str(ROOT / cfg["saida"]["arquivo_excel"]),
        agregacao,
        pesquisas,
        pesos,
        cfg,
        candidatos,
    )

    print("\n" + "=" * 60)
    print("RESULTADO ATUAL:")
    for c in candidatos:
        v = agregacao["medias"].get(c, 0)
        print(f"   {c:20s} {v:6.2f}%")
    print("=" * 60)
    print(f"\n✅ Excel gerado: {caminho}")


if __name__ == "__main__":
    main()
