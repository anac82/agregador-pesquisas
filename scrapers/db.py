"""Camada de banco de dados (v2)."""

import sqlite3
import hashlib
from pathlib import Path
from datetime import date
from typing import Optional


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
    return conn


def gerar_hash_pesquisa(
    instituto: str,
    data_fim_campo: str,
    turno: int,
    amostra: int,
    candidatos_str: str = "",
    registro_tse: Optional[str] = None,
    tipo: str = "",
) -> str:
    # Chave baseada em registro_tse + turno + tipo — garante unicidade real
    # independente de pequenas variações nos campos (url, zeros, etc.)
    if registro_tse:
        chave = f"TSE:{registro_tse}|T{turno}|{tipo}"
    else:
        chave = f"{instituto}|{data_fim_campo}|T{turno}|{tipo}|{amostra}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:16]


def classificar_cenario(pesquisa: dict, cenarios_config: list) -> Optional[str]:
    """
    Decide a qual cenário uma pesquisa pertence.

    Turno 1:
        - Só aceita tipo exatamente igual a "estimulado"

    Turno 2:
        - Primeiro tenta bater o campo `tipo` diretamente com o nome do cenário
        - Se não bater, usa o filtro por candidatos como fallback
    """
    turno = int(pesquisa.get("turno", 1))
    tipo  = str(pesquisa.get("tipo", "")).strip().lower()
    resultados = pesquisa.get("resultados", {})
    candidatos_reais = [
        c for c, v in resultados.items()
        if v and v > 0 and c not in ("Branco/Nulo", "Não sabe", "Outros")
    ]

    if turno == 1:
        if tipo != "estimulado":
            return None
        for cen in cenarios_config:
            if cen["turno"] == 1:
                return cen["nome"]
        return None

    # Turno 2: primeiro tenta bater pelo nome do tipo com o nome do cenário
    for cen in cenarios_config:
        if cen["turno"] != 2:
            continue
        nome_cen = cen["nome"].strip().lower()
        if tipo == nome_cen:
            return cen["nome"]

    # Fallback: inferir pelos candidatos com valor > 0
    for cen in cenarios_config:
        if cen["turno"] != 2:
            continue
        filtro = set(cen.get("filtro_candidatos") or [])
        if not filtro:
            continue
        if filtro.issubset(set(candidatos_reais)) and len(candidatos_reais) <= 2:
            return cen["nome"]

    return None


def inserir_pesquisa(
    conn: sqlite3.Connection,
    pesquisa: dict,
    cenarios_config: list,
) -> Optional[int]:
    cenario = classificar_cenario(pesquisa, cenarios_config)
    if cenario is None:
        return None

    candidatos_str = ",".join(sorted(pesquisa["resultados"].keys()))
    tipo = pesquisa.get("tipo", "estimulada")

    hash_unico = gerar_hash_pesquisa(
        pesquisa["instituto"],
        pesquisa["data_fim_campo"],
        int(pesquisa.get("turno", 1)),
        pesquisa["amostra"],
        candidatos_str,
        pesquisa.get("registro_tse"),
        tipo=tipo,
    )

    existing = conn.execute(
        "SELECT id FROM pesquisas WHERE hash_unico = ?", (hash_unico,)
    ).fetchone()
    if existing:
        return None

    cursor = conn.execute(
        """
        INSERT INTO pesquisas (
            instituto, contratante, data_inicio_campo, data_fim_campo,
            amostra, margem_erro, intervalo_confianca, cenario, tipo, turno,
            metodologia, votos_validos, registro_tse, url_fonte, hash_unico
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pesquisa["instituto"],
            pesquisa.get("contratante"),
            pesquisa["data_inicio_campo"],
            pesquisa["data_fim_campo"],
            pesquisa["amostra"],
            pesquisa.get("margem_erro"),
            pesquisa.get("intervalo_confianca", 95.0),
            cenario,
            tipo,
            int(pesquisa.get("turno", 1)),
            pesquisa.get("metodologia"),
            int(pesquisa.get("votos_validos", 0)),
            pesquisa.get("registro_tse"),
            pesquisa.get("url_fonte"),
            hash_unico,
        ),
    )
    pesquisa_id = cursor.lastrowid

    for candidato, percentual in pesquisa["resultados"].items():
        if percentual is None:
            continue
        conn.execute(
            "INSERT INTO resultados (pesquisa_id, candidato, percentual) VALUES (?, ?, ?)",
            (pesquisa_id, candidato, percentual),
        )

    conn.commit()
    return pesquisa_id


def listar_pesquisas(
    conn: sqlite3.Connection,
    cenario: str,
    desde: Optional[date] = None,
) -> list:
    query = "SELECT * FROM pesquisas WHERE cenario = ?"
    params: list = [cenario]
    if desde:
        query += " AND data_fim_campo >= ?"
        params.append(desde.isoformat())
    query += " ORDER BY data_fim_campo DESC"

    pesquisas = []
    for row in conn.execute(query, params).fetchall():
        p = dict(row)
        resultados = conn.execute(
            "SELECT candidato, percentual FROM resultados WHERE pesquisa_id = ?",
            (p["id"],),
        ).fetchall()
        p["resultados"] = {r["candidato"]: r["percentual"] for r in resultados}
        pesquisas.append(p)
    return pesquisas
