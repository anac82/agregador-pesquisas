"""Coletores de pesquisas eleitorais (v2)."""
import csv
from pathlib import Path


META_COLS = {
    "instituto", "contratante", "data_inicio_campo", "data_fim_campo",
    "amostra", "margem_erro", "intervalo_confianca", "turno", "tipo",
    "metodologia", "votos_validos", "registro_tse", "url_fonte",
}


def coletar_do_csv_manual(arquivo_csv: str) -> list:
    if not Path(arquivo_csv).exists():
        return []

    pesquisas = []
    with open(arquivo_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("instituto"):
                continue

            resultados = {}
            for k, v in row.items():
                if k not in META_COLS and v not in (None, ""):
                    try:
                        resultados[k] = float(str(v).replace(",", "."))
                    except (ValueError, AttributeError):
                        pass

            if not resultados:
                continue

            pesquisas.append({
                "instituto": row["instituto"].strip(),
                "contratante": row.get("contratante", "").strip() or None,
                "data_inicio_campo": row["data_inicio_campo"],
                "data_fim_campo": row["data_fim_campo"],
                "amostra": int(row["amostra"]),
                "margem_erro": float(row["margem_erro"]) if row.get("margem_erro") else None,
                "intervalo_confianca": float(row["intervalo_confianca"]) if row.get("intervalo_confianca") else 95.0,
                "turno": int(row.get("turno", 1)) if row.get("turno") else 1,
                "tipo": row.get("tipo", "estimulada"),
                "metodologia": row.get("metodologia", "").strip() or None,
                "votos_validos": int(row["votos_validos"]) if row.get("votos_validos") else 0,
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
