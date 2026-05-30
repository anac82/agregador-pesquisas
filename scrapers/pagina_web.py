"""pagina_web.py — Gera o index.html para GitHub Pages."""

import json
from datetime import date
from pathlib import Path

CORES_CANDIDATOS = {
    "Lula":   "#C0392B",
    "Flávio": "#2471A3",
    "Zema":   "#CA8A04",
    "Caiado": "#7D8A2E",
    "Renan":  "#7E57C2",
    "Cury":   "#16A085",
}
COR_PADRAO = "#888780"


def _to_date(valor):
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _formatar_ultimas_pesquisas(pesquisas):
    if not pesquisas:
        return ""
    itens = []
    for p in pesquisas[:10]:
        inst  = p.get("instituto", "")
        data  = p.get("data", "")
        n     = p.get("amostra", "")
        reg   = p.get("registro_tse", "")
        try:
            d = _to_date(data)
            meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
            data_fmt = f"{d.day} de {meses[d.month-1]}"
        except Exception:
            data_fmt = str(data)[:10]
        try:
            n_fmt = f"{int(float(n)):,}".replace(",",".")
        except Exception:
            n_fmt = str(n)
        itens.append(f"<li><b>{inst}</b> ({data_fmt}, n={n_fmt}) <code>{reg}</code></li>")
    return "\n".join(itens)


def _preparar_dados_grafico(serie, top_n=5):
    pontos = serie.get("pontos", [])
    if not pontos:
        return None

    meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
    labels = []
    for pt in pontos:
        d = _to_date(pt["data"])
        labels.append(f"{d.day:02d}/{meses[d.month-1]}")

    medias_recentes = {}
    for pt in reversed(pontos):
        if pt["n_pesquisas"] > 0:
            medias_recentes = pt["medias"]
            break

    especiais = {"Outros","Branco/Nulo","Não sabe"}
    candidatos = sorted(
        [c for c in serie["candidatos"] if c not in especiais],
        key=lambda c: medias_recentes.get(c, 0),
        reverse=True,
    )[:top_n]

    series_js = []
    for cand in candidatos:
        dados = []
        for pt in pontos:
            v = pt["medias"].get(cand)
            dados.append(round(v, 1) if v else None)
        series_js.append({
            "label":   cand,
            "cor":     CORES_CANDIDATOS.get(cand, COR_PADRAO),
            "dados":   dados,
            "largura": 3.5 if cand in candidatos[:2] else 2,
        })

    return {
        "labels":     labels,
        "series":     series_js,
        "passo_dias": serie.get("passo_dias", 7),
        "janela_dias":serie.get("janela_dias", 30),
    }


def gerar_pagina_html(caminho, series_por_cenario, data_geracao=None,
                      cenario_principal="1º Turno", ultimas_pesquisas=None,
                      slopes=None):
    if data_geracao is None:
        data_geracao = date.today()

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
        if slopes:
            dados["slopes"] = slopes
        dados_json = json.dumps(dados, ensure_ascii=False)

    meses_pt = ["janeiro","fevereiro","março","abril","maio","junho",
                "julho","agosto","setembro","outubro","novembro","dezembro"]
    data_fmt = f"{data_geracao.day} de {meses_pt[data_geracao.month-1]} de {data_geracao.year}"

    html_pesquisas = _formatar_ultimas_pesquisas(ultimas_pesquisas or [])

    html = _TEMPLATE_HTML.replace("PLACEHOLDER_DADOS_JSON", dados_json)
    html = html.replace("PLACEHOLDER_CENARIO", cenario_principal)
    html = html.replace("PLACEHOLDER_DATA", data_fmt)
    html = html.replace("PLACEHOLDER_PESQUISAS", html_pesquisas)

    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    return caminho


_TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agregador de Pesquisas — Presidente 2026</title>
<style>
  body { font-family: Arial, sans-serif; margin: 0; padding: 16px; background: #f9f9f9; color: #333; max-width: 900px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.3rem; margin-bottom: 4px; }
  .sub { color: #666; font-size: 0.85rem; margin-bottom: 16px; }
  .grafico-wrap { position: relative; width: 100%; height: 380px; margin-bottom: 16px; background: #fff; border-radius: 8px; padding: 8px; box-sizing: border-box; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
  .sem-dados { display: flex; align-items: center; justify-content: center; height: 100%; color: #999; font-size: 1rem; }
  .legenda-tend { font-size: 0.78rem; color: #555; margin-bottom: 12px; }
  .rodape { font-size: 0.75rem; color: #888; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 16px; }
  .ultimas { font-size: 0.78rem; margin-bottom: 12px; }
  .ultimas ul { margin: 4px 0; padding-left: 20px; }
  .ultimas li { margin-bottom: 2px; }
  details summary { cursor: pointer; font-weight: bold; font-size: 0.82rem; color: #555; }
  code { background: #eee; padding: 1px 4px; border-radius: 3px; font-size: 0.75rem; }
</style>
</head>
<body>
<h1>Intenção de voto — PLACEHOLDER_CENARIO</h1>
<div class="sub">Média ponderada por recência, amostra e metodologia · Eleições presidenciais 2026 · Atualizado em PLACEHOLDER_DATA</div>
<div class="grafico-wrap">
  <canvas id="grafico" role="img" aria-label="Gráfico de evolução da intenção de voto."></canvas>
</div>
<div class="legenda-tend" id="legenda-tend"></div>
<div class="ultimas">
  <details>
    <summary>Últimas pesquisas consideradas →</summary>
    <ul>PLACEHOLDER_PESQUISAS</ul>
  </details>
</div>
<div class="rodape">
  Fonte: agregação própria de pesquisas registradas no TSE. A seta indica a tendência por regressão linear ponderada nos últimos 60 dias. Agregador independente, sem fins comerciais.
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){
  var DADOS = PLACEHOLDER_DADOS_JSON;
  var wrap = document.querySelector('.grafico-wrap');
  var legendaEl = document.getElementById('legenda-tend');

  if (!DADOS) {
    wrap.innerHTML = '<div class="sem-dados">Ainda não há dados suficientes.</div>';
    return;
  }

  function seta(delta){
    if (delta > 2.0)  return {t:'\u21C8', cor:'#1D9E75'};
    if (delta > 0.5)  return {t:'\u2191', cor:'#1D9E75'};
    if (delta >= -0.5)return {t:'\u2192', cor:'#888780'};
    if (delta >= -2.0)return {t:'\u2193', cor:'#D85A30'};
    return {t:'\u21CA', cor:'#C0392B'};
  }

  function lastIdx(a){
    for(var i=a.length-1;i>=0;i--) if(a[i]!=null) return i;
    return -1;
  }

  // Valor de N pontos não-nulos atrás
  function valAgo(dados, idx, n){
    var count=0;
    for(var i=idx-1;i>=0;i--){
      if(dados[i]!=null){ count++; if(count>=n) return dados[i]; }
    }
    return dados[idx];
  }

  var labels = DADOS.labels;
  var datasets = DADOS.series.map(function(s){
    return {
      label: s.label,
      data: s.dados,
      borderColor: s.cor,
      backgroundColor: s.cor+'22',
      borderWidth: s.largura,
      pointRadius: 0,
      tension: 0.35,
      spanGaps: true
    };
  });

  var faixa = {
    id:'faixa',
    beforeDraw: function(chart){
      var ctx=chart.ctx, x=chart.scales.x, y=chart.scales.y;
      var n=DADOS.labels.length, pts4=Math.max(1,Math.round(28/DADOS.passo_dias));
      var x0=x.getPixelForValue(Math.max(0,n-pts4)), x1=x.getPixelForValue(n-1);
      var top=chart.chartArea.top, bot=chart.chartArea.bottom;
      ctx.save();
      ctx.fillStyle='rgba(200,200,200,0.15)';
      ctx.fillRect(x0,top,x1-x0,bot-top);
      ctx.fillStyle='#bbb'; ctx.font='11px Arial'; ctx.textAlign='center';
      ctx.fillText('últimas 4 semanas',(x0+x1)/2,top+12);
      ctx.restore();
    }
  };

  var setasFlutuantes = {
    id:'setasFlutuantes',
    afterDatasetsDraw: function(chart){
      var ctx=chart.ctx, x=chart.scales.x, y=chart.scales.y;
      var xUlt=x.getPixelForValue(DADOS.labels.length-1);
      var usados=[];
      ctx.save(); ctx.textBaseline='middle';
      DADOS.series.forEach(function(s){
        var i=lastIdx(s.dados); if(i<0) return;
        var pts4=Math.max(1,Math.round(28/DADOS.passo_dias));
        var delta=s.dados[i] - valAgo(s.dados,i,pts4);
        var t=seta(delta);
        var yLinha=y.getPixelForValue(s.dados[i]);
        var yS=yLinha-22;
        if(yS<chart.chartArea.top+8) yS=chart.chartArea.top+8;
        usados.forEach(function(u){ if(Math.abs(u-yS)<18) yS=u-18; });
        usados.push(yS);
        ctx.beginPath(); ctx.arc(xUlt,yLinha,3,0,Math.PI*2);
        ctx.fillStyle=s.cor; ctx.fill();
        ctx.font='500 18px sans-serif'; ctx.fillStyle=t.cor; ctx.textAlign='center';
        ctx.fillText(t.t, xUlt+18, yS);
        ctx.font='bold 12px Arial'; ctx.fillStyle=s.cor;
        ctx.fillText(s.dados[i].toFixed(1)+'%', xUlt+42, yS);
      });
      ctx.restore();
    }
  };

  new Chart(document.getElementById('grafico'),{
    type:'line',
    data:{labels:labels, datasets:datasets},
    plugins:[faixa, setasFlutuantes],
    options:{
      responsive:true,
      maintainAspectRatio:false,
      layout:{padding:{right:80,top:8}},
      interaction:{mode:'index',intersect:false},
      scales:{
        x:{grid:{display:false}, ticks:{maxRotation:45,font:{size:10}}},
        y:{min:20, max:60, ticks:{callback:function(v){return v+'%';}}}
      },
      plugins:{
        legend:{display:false},
        tooltip:{
          callbacks:{
            label:function(c){
              return c.dataset.label+': '+(c.parsed.y==null?'—':c.parsed.y.toFixed(1)+'%');
            }
          }
        }
      }
    }
  });

  if(legendaEl){
    var parts = DADOS.series.map(function(s){
      var i=lastIdx(s.dados); if(i<0) return '';
      var pts4=Math.max(1,Math.round(28/DADOS.passo_dias));
      var delta=s.dados[i] - valAgo(s.dados,i,pts4);
      var t=seta(delta);
      return '<span style="color:'+s.cor+';font-weight:600">'+s.label+'</span> '+
             '<span style="color:'+t.cor+'">'+t.t+'</span>';
    }).filter(Boolean);
    legendaEl.innerHTML = parts.join(' &nbsp;·&nbsp; ') +
      ' &nbsp;<span style="color:#aaa;font-size:0.95em">(vs 4 semanas atrás)</span>';
  }
})();
</script>
</body>
</html>"""
