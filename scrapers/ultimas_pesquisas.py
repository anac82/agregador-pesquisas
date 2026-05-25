"""Extrai últimas pesquisas do CSV para exibição no HTML."""
import csv
from datetime import datetime


def extrair_ultimas_pesquisas(caminho_csv, n=15):
    """
    Extrai as últimas pesquisas do CSV para exibição.
    
    Args:
        caminho_csv: caminho para o arquivo pesquisas_manuais.csv
        n: número de pesquisas a retornar (padrão: 15)
        
    Returns:
        list de dicts com {instituto, data, amostra, registro_tse}
    """
    pesquisas = []
    
    try:
        with open(caminho_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Filtrar apenas 1º turno (turno=1) e tipo estimulado
                if row.get('turno') == '1' and row.get('tipo') == 'estimulado':
                    try:
                        data = datetime.fromisoformat(row['data_inicio_campo']).date()
                        pesquisas.append({
                            'instituto': row['instituto'],
                            'data': data.isoformat(),
                            'amostra': row.get('amostra', '?'),
                            'registro_tse': row.get('registro_tse', ''),
                            'data_obj': data,
                        })
                    except (ValueError, KeyError):
                        pass
    except FileNotFoundError:
        return []
    
    # Ordenar por data decrescente
    pesquisas.sort(key=lambda x: x['data_obj'], reverse=True)
    
    # Remover duplicatas (mesmo instituto/data)
    vistas = set()
    unicas = []
    for p in pesquisas:
        chave = (p['instituto'], p['data'])
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(p)
    
    # Retornar apenas as últimas N
    return unicas[:n]
