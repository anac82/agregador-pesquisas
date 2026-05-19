"""Gera o Excel de saida com 4 abas."""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference


HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill("solid", start_color="1F4E78")
TITULO_FONT = Font(name="Arial", bold=True, size=14, color="1F4E78")
THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


def _formatar_cabecalho(ws, linha, n_cols):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=linha, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _ajustar_larguras(ws, larguras):
    for col_letra, largura in larguras.items():
        ws.column_dimensions[col_letra].width = largura


def gerar_aba_media(wb, agregacao, candidatos):
    ws = wb.create_sheet("Média Ponderada", 0)
    ws["A1"] = "Agregador de Pesquisas — Eleições 2026"
    ws["A1"].font = TITULO_FONT
    ws.merge_cells("A1:D1")

    ws["A3"] = "Data de referência:"
    ws["B3"] = agregacao["data_referencia"].isoformat()
    ws["A4"] = "Pesquisas consideradas:"
    ws["B4"] = agregacao["n_pesquisas"]
    ws["A5"] = "Cenário:"
    ws["B5"] = "Lula vs Bolsonaro"

    for cell in ["A3", "A4", "A5"]:
        ws[cell].font = Font(name="Arial", bold=True)

    ws["A7"] = "Candidato"
    ws["B7"] = "Média Ponderada (%)"
    _formatar_cabecalho(ws, 7, 2)

    for i, candidato in enumerate(candidatos, start=8):
        ws.cell(row=i, column=1, value=candidato).font = Font(name="Arial")
        c = ws.cell(row=i, column=2, value=round(agregacao["medias"].get(candidato, 0), 2))
        c.font = Font(name="Arial")
        c.number_format = "0.00"
        c.alignment = Alignment(horizontal="right")

    _ajustar_larguras(ws, {"A": 28, "B": 22, "C": 18, "D": 18})


def gerar_aba_pesquisas(wb, agregacao, candidatos):
    ws = wb.create_sheet("Pesquisas")
    df = agregacao["detalhamento"]
    if df.empty:
        ws["A1"] = "Nenhuma pesquisa coletada ainda."
        return

    cols = ["instituto", "data_fim_campo", "amostra", "peso_final"] + candidatos
    df = df[cols].copy()
    df = df.sort_values("data_fim_campo", ascending=False)

    for j, col in enumerate(cols, start=1):
        ws.cell(row=1, column=j, value=col)
    _formatar_cabecalho(ws, 1, len(cols))

    for i, row in enumerate(df.itertuples(index=False), start=2):
        for j, valor in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=valor)
            c.font = Font(name="Arial")
            c.border = THIN_BORDER
            if isinstance(valor, float):
                c.number_format = "0.00"

    larguras = {get_column_letter(j): 16 for j in range(1, len(cols) + 1)}
    larguras["A"] = 22
    larguras["B"] = 16
    _ajustar_larguras(ws, larguras)


def gerar_aba_historico(wb, pesquisas_brutas, pesos_institutos, config, candidatos):
    from scrapers.ponderacao import agregar

    ws = wb.create_sheet("Histórico Diário")

    hoje = date.today()
    inicio = hoje - timedelta(days=90)
    janela = config["ponderacao"]["janela_dias"]

    linhas = []
    cursor = inicio
    while cursor <= hoje:
        pesquisas_validas = [
            p for p in pesquisas_brutas
            if date.fromisoformat(str(p["data_fim_campo"])) <= cursor
            and (cursor - date.fromisoformat(str(p["data_fim_campo"]))).days <= janela
        ]
        if pesquisas_validas:
            ag = agregar(pesquisas_validas, pesos_institutos, config, candidatos, cursor)
            linha = {"data": cursor.isoformat(), "n_pesquisas": ag["n_pesquisas"]}
            linha.update({c: round(ag["medias"].get(c, 0), 2) for c in candidatos})
            linhas.append(linha)
        cursor += timedelta(days=1)

    if not linhas:
        ws["A1"] = "Sem dados históricos suficientes."
        return

    cols = ["data", "n_pesquisas"] + candidatos
    for j, col in enumerate(cols, start=1):
        ws.cell(row=1, column=j, value=col)
    _formatar_cabecalho(ws, 1, len(cols))

    for i, l in enumerate(linhas, start=2):
        for j, col in enumerate(cols, start=1):
            c = ws.cell(row=i, column=j, value=l[col])
            c.font = Font(name="Arial")
            if isinstance(l[col], float):
                c.number_format = "0.00"

    chart = LineChart()
    chart.title = "Evolução da média ponderada"
    chart.y_axis.title = "Intenção de voto (%)"
    chart.x_axis.title = "Data"
    chart.height = 10
    chart.width = 20

    n_linhas = len(linhas) + 1
    for j, candidato in enumerate(candidatos, start=3):
        data = Reference(ws, min_col=j, min_row=1, max_row=n_linhas)
        chart.add_data(data, titles_from_data=True)
    cats = Reference(ws, min_col=1, min_row=2, max_row=n_linhas)
    chart.set_categories(cats)
    ws.add_chart(chart, f"{get_column_letter(len(cols) + 2)}2")

    larguras = {get_column_letter(j): 14 for j in range(1, len(cols) + 1)}
    _ajustar_larguras(ws, larguras)


def gerar_aba_config(wb, config, pesos_institutos):
    ws = wb.create_sheet("Configuração")
    ws["A1"] = "Pesos por instituto"
    ws["A1"].font = TITULO_FONT

    ws["A3"] = "Instituto"
    ws["B3"] = "Peso"
    _formatar_cabecalho(ws, 3, 2)

    linha = 4
    for inst, peso in sorted(pesos_institutos.items()):
        ws.cell(row=linha, column=1, value=inst).font = Font(name="Arial")
        c = ws.cell(row=linha, column=2, value=peso)
        c.font = Font(name="Arial")
        c.number_format = "0.00"
        linha += 1

    linha += 2
    ws.cell(row=linha, column=1, value="Parâmetros da ponderação").font = TITULO_FONT
    linha += 2
    ws.cell(row=linha, column=1, value="Recência ativa")
    ws.cell(row=linha, column=2, value=config["ponderacao"]["recencia"]["ativo"])
    linha += 1
    ws.cell(row=linha, column=1, value="Half-life (dias)")
    ws.cell(row=linha, column=2, value=config["ponderacao"]["recencia"]["half_life_dias"])
    linha += 1
    ws.cell(row=linha, column=1, value="Amostra ativa")
    ws.cell(row=linha, column=2, value=config["ponderacao"]["amostra"]["ativo"])
    linha += 1
    ws.cell(row=linha, column=1, value="Amostra de referência")
    ws.cell(row=linha, column=2, value=config["ponderacao"]["amostra"]["amostra_referencia"])
    linha += 1
    ws.cell(row=linha, column=1, value="Janela de pesquisas (dias)")
    ws.cell(row=linha, column=2, value=config["ponderacao"]["janela_dias"])

    _ajustar_larguras(ws, {"A": 30, "B": 16})


def gerar_excel(caminho, agregacao, pesquisas_brutas, pesos_institutos, config, candidatos):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    gerar_aba_media(wb, agregacao, candidatos)
    gerar_aba_pesquisas(wb, agregacao, candidatos)
    gerar_aba_historico(wb, pesquisas_brutas, pesos_institutos, config, candidatos)
    gerar_aba_config(wb, config, pesos_institutos)

    wb.save(caminho)
    return caminho
