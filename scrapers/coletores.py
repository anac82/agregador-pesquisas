"""Coletores de pesquisas eleitorais."""
import csv
from pathlib import Path


def coletar_do_csv_manual(arquivo_csv: str) -> list:
    if not Path(arquivo_csv).exists():
        return []

    pesquisas = []
    with open(arquivo_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        meta_cols = {
            "instituto", "contratante", "data_inicio_campo", "data_fim_campo",
            "amostra", "margem_erro", "cenario", "tipo", "registro_tse",
            "url_fonte",
        }
        for row in reader:
            if not row.get("instituto"):
                continue
            resultados = {}
            for k, v in row.items():
                if k not in meta_cols and v:
                    try:
                        resultados[k] = float(str(v).replace(",", "."))
                    except (ValueError, AttributeError):
                        pass

            pesquisas.append({
                "instituto": row["instituto"].strip(),
                "contratante": row.get("contratante", "").strip() or None,
                "data_inicio_campo": row["data_inicio_campo"],
                "data_fim_campo": row["data_fim_campo"],
                "amostra": int(row["amostra"]),
                "margem_erro": float(row["margem_erro"]) if row.get("margem_erro") else None,
                "cenario": row.get("cenario", "Lula vs Bolsonaro"),
                "tipo": row.get("tipo", "estimulada"),
                "registro_tse": row.get("registro_tse", "").strip() or None,
                "url_fonte": row.get("url_fonte", "").strip() or None,
                "resultados": resultados,
            })
    return pesquisas


def coletar_do_tse() -> list:
    """Scraper do TSE PesqEle. A implementar na fase 2."""
    print("[TSE] Scraper ainda nao implementado (fase 2). Pulando.")
    return []


def coletar_todas(csv_manual: str = "data/pesquisas_manuais.csv") -> list:
    todas = []
    todas.extend(coletar_do_csv_manual(csv_manual))
    todas.extend(coletar_do_tse())
    return todas
