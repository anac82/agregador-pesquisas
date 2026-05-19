"""Camada de banco de dados."""
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
    cenario: str,
    amostra: int,
    registro_tse: Optional[str] = None,
) -> str:
    if registro_tse:
        chave = f"TSE:{registro_tse}"
    else:
        chave = f"{instituto}|{data_fim_campo}|{cenario}|{amostra}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:16]


def inserir_pesquisa(conn: sqlite3.Connection, pesquisa: dict) -> Optional[int]:
    hash_unico = gerar_hash_pesquisa(
        pesquisa["instituto"],
        pesquisa["data_fim_campo"],
        pesquisa["cenario"],
        pesquisa["amostra"],
        pesquisa.get("registro_tse"),
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
            amostra, margem_erro, intervalo_confianca, cenario, tipo,
            turno, registro_tse, url_fonte, hash_unico
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pesquisa["instituto"],
            pesquisa.get("contratante"),
            pesquisa["data_inicio_campo"],
            pesquisa["data_fim_campo"],
            pesquisa["amostra"],
            pesquisa.get("margem_erro"),
            pesquisa.get("intervalo_confianca", 95.0),
            pesquisa["cenario"],
            pesquisa.get("tipo", "estimulada"),
            pesquisa.get("turno", 1),
            pesquisa.get("registro_tse"),
            pesquisa.get("url_fonte"),
            hash_unico,
        ),
    )
    pesquisa_id = cursor.lastrowid

    for candidato, percentual in pesquisa["resultados"].items():
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
) -> list[dict]:
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
