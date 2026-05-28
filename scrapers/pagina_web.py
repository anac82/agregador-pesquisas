"""Gera uma página HTML (estilo BBC/FT) com o gráfico de evolução das pesquisas.

A página é estática (HTML + Chart.js via CDN) e pode ser publicada no GitHub Pages.
Recebe as séries temporais já calculadas por ponderacao.agregar_serie_temporal().
"""
import json
from datetime import date, datetime
from pathlib import Path


# Cores fixas por candidato (políticas/partidárias quando faz sentido)
CORES_CANDIDATOS = {
    "Lula": "#C0392B",      # vermelho (PT)
    "Flávio": "#2471A3",    # azul (PL)
    "Caiado": "#7D8A2E",    # verde-oliva (PSD)
    "Zema": "#CA8A04",      # amarelo/âmbar (Novo)
    "Renan": "#7E57C2",     # roxo (Missão)
    "Cury": "#16A085",      # teal (Avante)
    "Tarcísio": "#2C3E50",  # azul-escuro
    "Haddad": "#E74C3C",    # vermelho-claro (PT)
    "Ratinho Junior": "#27AE60",
    "Eduardo Leite": "#8E44AD",
    "Aldo": "#95A5A6",
    "Daciolo": "#D35400",
    "Samara": "#C0392B",
}
COR_PADRAO = "#888780"


def _to_date(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v).date()
    return v


def _preparar_dados_grafico(serie, top_n=5):
    """Converte a série temporal no formato que o JavaScript do gráfico espera."""
    pontos = serie.get("pontos", [])
    if not pontos:
        return None

    # Rótulos do eixo X: datas formatadas dd/mês
    meses = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]
    labels = []
    for pt in pontos:
        d = _to_date(pt["data"])
        labels.append(f"{d.day:02d}/{meses[d.month - 1]}")

    # Escolher top_n candidatos pela média mais recente com dados
    medias_recentes = {}
    for pt in reversed(pontos):
        if pt["n_pesquisas"] > 0:
            medias_recentes = pt["medias"]
            break
    especiais = {"Outros", "Branco/Nulo", "Não sabe"}
    candidatos = sorted(
        [c for c in serie["candidatos"] if c not in especiais],
        key=lambda c: medias_recentes.get(c, 0),
        reverse=True,
    )[:top_n]

    # Montar séries de dados
    series_js = []
    for cand in candidatos:
        dados = []
        for pt in pontos:
            v = pt["medias"].get(cand)
            dados.append(round(v, 1) if v else None)
        series_js.append({
            "label": cand,
            "cor": CORES_CANDIDATOS.get(cand, COR_PADRAO),
            "dados": dados,
            # linha mais grossa para os 2 primeiros (favoritos)
            "largura": 3.5 if cand in candidatos[:2] else 2,
        })

    return {
        "labels": labels,
        "series": series_js,
        "passo_dias": serie.get("passo_dias", 7),
        "janela_dias": serie.get("janela_dias", 30),
    }


def gerar_pagina_html(caminho, series_por_cenario, data_geracao=None, cenario_principal="1º Turno", ultimas_pesquisas=None, slopes=None):
    """
    Gera a página HTML com o gráfico de evolução.

    series_por_cenario: dict {nome_cenario: serie_temporal}
    cenario_principal: qual cenário mostrar no gráfico (default: 1º Turno)
    ultimas_pesquisas: list de dicts com {instituto, data, amostra, registro_tse}
    slopes: dict {candidato: slope_pp_por_semana} — pré-calculado no Python
    """
    if data_geracao is None:
        data_geracao = date.today()

    # Pegar a série do cenário principal (ou a primeira disponível)
    serie = series_por_cenario.get(cenario_principal)
    if serie is None or not serie.get("pontos"):
        for nome, s in series_por_cenario.items():
            if s and s.get("pontos"):
                serie = s
                cenario_principal = nome
                break

    dados = _preparar_dados_grafico(serie) if serie else None

    if dados is None:
        dados_json = "null"
    else:
        # Injetar slopes pré-calculados
        if slopes:
            dados["slopes"] = slopes
        dados_json = json.dumps(dados, ensure_ascii=False)

    meses_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    data_fmt = f"{data_geracao.day} de {meses_pt[data_geracao.month - 1]} de {data_geracao.year}"

    # Formatar últimas pesquisas
    html_pesquisas = _formatar_ultimas_pesquisas(ultimas_pesquisas or [])

    html = _TEMPLATE_HTML.replace("{{DADOS_JSON}}", dados_json)
    html = html.replace("{{CENARIO}}", cenario_principal)
    html = html.replace("{{DATA_GERACAO}}", data_fmt)
    html = html.replace("{{ULTIMAS_PESQUISAS}}", html_pesquisas)

    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    return caminho


def _formatar_ultimas_pesquisas(pesquisas):
    """Formata as últimas pesquisas para exibição no rodapé."""
    if not pesquisas:
        return ""
    
    meses_pt = ["jan", "fev", "mar", "abr", "mai", "jun",
                "jul", "ago", "set", "out", "nov", "dez"]
    
    linhas = []
    for p in pesquisas[:10]:  # Mostrar últimas 10
        instituto = p.get("instituto", "?")
        data_str = p.get("data", "")
        amostra = p.get("amostra", "?")
        registro = p.get("registro_tse", "")
        
        # Formatar data
        if data_str:
            try:
                d = _to_date(data_str)
                data_fmt = f"{d.day} de {meses_pt[d.month - 1]}"
            except:
                data_fmt = data_str
        else:
            data_fmt = "?"
        
        # Montar linha
        linha = f"<li><strong>{instituto}</strong> ({data_fmt}, n={amostra})"
        if registro:
            linha += f" <code>{registro}</code>"
        linha += "</li>"
        linhas.append(linha)
    
    if linhas:
        return "<ul style='font-size:11px; color:#999; margin-top:4px; margin-bottom:0;'>" + \
               "".join(linhas) + "</ul>"
    return ""


_TEMPLATE_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agregador de Pesquisas — Presidente 2026</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #ffffff;
    color: #1a1a1a;
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 860px; margin: 0 auto; }
  h1 { font-size: 24px; font-weight: 600; margin-bottom: 4px; }
  .subtitulo { font-size: 14px; color: #666; margin-bottom: 4px; }
  .atualizado { font-size: 12px; color: #999; margin-bottom: 28px; }
  .grafico-wrap { position: relative; width: 100%; height: 440px; margin-bottom: 16px; }
  .legenda-tend {
    font-size: 11px; color: #999; line-height: 1.7; margin-top: 8px;
    border-top: 1px solid #eee; padding-top: 12px;
  }
  .rodape {
    margin-top: 32px; padding-top: 16px; border-top: 1px solid #eee;
    font-size: 12px; color: #999;
  }
  .sem-dados { color: #999; font-style: italic; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <h1>Intenção de voto — {{CENARIO}}</h1>
  <div class="subtitulo">Média móvel ponderada · Eleições presidenciais 2026</div>
  <div class="atualizado">Atualizado em {{DATA_GERACAO}}</div>

  <div class="grafico-wrap">
    <canvas id="grafico" role="img" aria-label="Gráfico de evolução da intenção de voto ao longo do tempo."></canvas>
  </div>

  <div class="legenda-tend" id="legenda-tend"></div>

  <div class="rodape">
    <p>Fonte: agregação própria de pesquisas registradas no TSE (Quaest, Datafolha, AtlasIntel, Futura, Meio/Ideia).
    A seta indica a tendência nas últimas 4 semanas. Este é um agregador independente, sem fins comerciais.</p>
    
    <details style="margin-top: 12px;">
      <summary style="cursor: pointer; color: #666; font-weight: 500;">
        Últimas pesquisas consideradas →
      </summary>
      {{ULTIMAS_PESQUISAS}}
    </details>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){
  const DADOS = {{DADOS_JSON}};
  const wrap = document.querySelector('.grafico-wrap');
  const legendaEl = document.getElementById('legenda-tend');

  if (!DADOS) {
    wrap.innerHTML = '<div class="sem-dados">Ainda não há dados suficientes para gerar o gráfico.</div>';
    return;
  }

  function seta(slopePerWeek){
    // slope em pp/semana
    if (slopePerWeek >  1.0) return {s:'\u21C8', cl:'#1D9E75'};
    if (slopePerWeek >  0.3) return {s:'\u2191', cl:'#1D9E75'};
    if (slopePerWeek >= -0.3)return {s:'\u2192', cl:'#888780'};
    if (slopePerWeek >= -1.0)return {s:'\u2193', cl:'#D85A30'};
    return {s:'\u21CA', cl:'#C0392B'};
  }
  function lastIdx(a){ for(let i=a.length-1;i>=0;i--) if(a[i]!=null) return i; return -1; }

  // Regressão linear ponderada — calcula inclinação em pp/semana
  // Usa os últimos maxPontos pontos não-nulos, com peso decrescente por recência
  function slopeRegPonderada(dados, labels, idxAtual, maxPontos){
    const pts = [];
    for(let i=idxAtual; i>=0 && pts.length<maxPontos; i--){
      if(dados[i]==null) continue;
      pts.push({x: i, y: dados[i]});
    }
    if(pts.length < 3) return 0;  // pontos demais faltando

    // Peso = decaimento exponencial por posição (mais recente = mais peso)
    const n = pts.length;
    let sw=0, swx=0, swy=0, swxx=0, swxy=0;
    pts.forEach((p, idx) => {
      const w = Math.exp(-0.05 * idx);  // mais recente = idx 0 = peso 1
      sw   += w;
      swx  += w * p.x;
      swy  += w * p.y;
      swxx += w * p.x * p.x;
      swxy += w * p.x * p.y;
    });
    const denom = sw*swxx - swx*swx;
    if(Math.abs(denom) < 1e-10) return 0;
    const slope = (sw*swxy - swx*swy) / denom;
    // Converter de pp/ponto para pp/semana
    return slope * (7 / DADOS.passo_dias);
  }

  const labels = DADOS.labels;
  const datasets = DADOS.series.map(s => ({
    label: s.label, data: s.dados,
    borderColor: s.cor, backgroundColor: s.cor,
    borderWidth: s.largura, tension: 0.4,
    pointRadius: 0, pointHoverRadius: 4, spanGaps: true, fill: false
  }));

  // passo entre pontos = passo_dias; 4 semanas = 28 dias => back em nº de pontos
  const passoPontos4sem = Math.max(1, Math.round(28 / DADOS.passo_dias));
  const idxIni4 = labels.length - 1 - passoPontos4sem;

  const faixa = {
    id:'faixa',
    beforeDatasetsDraw(chart){
      const {ctx, chartArea:{top,bottom}, scales:{x}} = chart;
      const x0=x.getPixelForValue(Math.max(0,idxIni4)), x1=x.getPixelForValue(labels.length-1);
      ctx.save();
      ctx.fillStyle='rgba(136,135,128,0.10)'; ctx.fillRect(x0,top,x1-x0,bottom-top);
      ctx.strokeStyle='rgba(136,135,128,0.25)'; ctx.setLineDash([3,3]);
      ctx.beginPath(); ctx.moveTo(x0,top); ctx.lineTo(x0,bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.font='500 10px sans-serif'; ctx.fillStyle='#888780'; ctx.textAlign='center';
      ctx.fillText('últimas 4 semanas',(x0+x1)/2, top+12); ctx.restore();
    }
  };
  const setasFlutuantes = {
    id:'setasFlutuantes',
    afterDatasetsDraw(chart){
      const {ctx, chartArea:{top}, scales:{x,y}} = chart;
      const xUlt=x.getPixelForValue(labels.length-1);
      ctx.save(); ctx.textBaseline='middle';
      const usadosSeta=[]; const usadosNome=[];
      DADOS.series.forEach(s=>{
        const i=lastIdx(s.dados); if(i<0) return;
        const atual=s.dados[i];
        let slope;
        if (DADOS.slopes && DADOS.slopes[s.label] !== undefined) {
          slope = DADOS.slopes[s.label];  // pré-calculado no Python
        } else {
          const maxPontos = Math.max(6, Math.round(60 / DADOS.passo_dias));
          slope = slopeRegPonderada(s.dados, labels, i, maxPontos);
        }
        const t=seta(slope);
        const yLinha=y.getPixelForValue(atual);
        let ySeta=yLinha-22; if(ySeta<top+8) ySeta=top+8;
        usadosSeta.forEach(u=>{ if(Math.abs(u-ySeta)<18) ySeta=u-18; }); usadosSeta.push(ySeta);
        ctx.beginPath(); ctx.arc(xUlt,yLinha,3,0,Math.PI*2); ctx.fillStyle=s.cor; ctx.fill();
        ctx.font='500 18px sans-serif'; ctx.fillStyle=t.cl; ctx.textAlign='center';
        ctx.fillText(t.s, xUlt, ySeta);
        let yNome=yLinha;
        usadosNome.forEach(u=>{ if(Math.abs(u-yNome)<17) yNome=u+17; }); usadosNome.push(yNome);
        ctx.textAlign='left'; ctx.font='500 13px sans-serif'; ctx.fillStyle=s.cor;
        ctx.fillText(s.label+'  '+atual.toFixed(1)+'%', xUlt+12, yNome);
      });
      ctx.restore();
    }
  };

  new Chart(document.getElementById('grafico'),{
    type:'line', data:{labels,datasets}, plugins:[faixa,setasFlutuantes],
    options:{ responsive:true, maintainAspectRatio:false,
      layout:{padding:{right:120,top:8}},
      interaction:{mode:'index',intersect:false},
      scales:{
        y:{min:0,max:52,ticks:{stepSize:10,callback:v=>v+'%',font:{size:12},color:'#888780'},
           grid:{color:'rgba(136,135,128,0.15)',drawTicks:false},border:{display:false}},
        x:{ticks:{font:{size:11},color:'#888780',maxRotation:0,autoSkip:true,maxTicksLimit:8},
           grid:{display:false},border:{color:'rgba(136,135,128,0.3)'}}
      },
      plugins:{legend:{display:false},
        tooltip:{backgroundColor:'#2C2C2A',padding:10,cornerRadius:8,
          callbacks:{label:c=>c.dataset.label+': '+(c.parsed.y==null?'\u2014':c.parsed.y.toFixed(1)+'%')}}}
    }
  });

  legendaEl.innerHTML = 'A seta indica a <b style="font-weight:500;color:#666">tendência por regressão linear ponderada</b> nos últimos 60 dias: ' +
    '<span style="color:#1D9E75">&#8648; forte alta</span> · ' +
    '<span style="color:#1D9E75">&#8593; alta</span> · ' +
    '<span style="color:#888780">&#8594; estável</span> · ' +
    '<span style="color:#D85A30">&#8595; queda</span> · ' +
    '<span style="color:#C0392B">&#8650; forte queda</span>';
})();
</script>
</body>
</html>
"""
