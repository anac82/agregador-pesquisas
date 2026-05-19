-- Schema do banco de pesquisas eleitorais

CREATE TABLE IF NOT EXISTS pesquisas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instituto TEXT NOT NULL,
    contratante TEXT,
    data_inicio_campo DATE NOT NULL,
    data_fim_campo DATE NOT NULL,
    amostra INTEGER NOT NULL,
    margem_erro REAL,
    intervalo_confianca REAL DEFAULT 95.0,
    cenario TEXT NOT NULL,
    tipo TEXT,
    turno INTEGER DEFAULT 1,
    registro_tse TEXT,
    url_fonte TEXT,
    coletado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    hash_unico TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pesquisa_id INTEGER NOT NULL,
    candidato TEXT NOT NULL,
    percentual REAL NOT NULL,
    FOREIGN KEY (pesquisa_id) REFERENCES pesquisas(id),
    UNIQUE(pesquisa_id, candidato)
);

CREATE INDEX IF NOT EXISTS idx_pesquisas_data ON pesquisas(data_fim_campo);
CREATE INDEX IF NOT EXISTS idx_pesquisas_cenario ON pesquisas(cenario);
CREATE INDEX IF NOT EXISTS idx_pesquisas_instituto ON pesquisas(instituto);
CREATE INDEX IF NOT EXISTS idx_resultados_candidato ON resultados(candidato);
