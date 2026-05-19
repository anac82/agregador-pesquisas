# Agregador de Pesquisas Eleitorais — 2026

Coleta pesquisas eleitorais, aplica sua ponderação personalizada, e gera um Excel atualizado com a média.

---

## O que esse projeto faz

1. **Coleta pesquisas** de duas fontes:
   - **Manual** (já funciona): você cola pesquisas que viu na imprensa em um CSV.
   - **TSE PesqEle** (fase 2, a fazer): scraper automático do sistema oficial.
2. **Guarda tudo** num banco SQLite (não perde nada, não duplica).
3. **Aplica sua ponderação**: peso por instituto × recência × tamanho da amostra.
4. **Gera um Excel** com 4 abas: média atual, lista de pesquisas, histórico diário, configuração.
5. **Roda sozinho na nuvem** (GitHub Actions) todo dia às 9h de Brasília.

---

## Como usar — passo a passo (zero conhecimento de programação)

### Primeira vez (instalação no Windows)

1. **Instale o Python 3** se você ainda não tem: <https://www.python.org/downloads/>
   - **IMPORTANTE**: na primeira tela do instalador, marque a caixinha **"Add Python to PATH"** antes de clicar em Install. Sem isso, os botões `.bat` não vão funcionar.
2. Baixe este projeto inteiro do GitHub (botão verde "Code" → "Download ZIP").
3. Descompacte o ZIP em uma pasta que você lembre (ex: `C:\Users\SeuNome\Documentos\agregador-pesquisas`).
4. **Dê duplo-clique em `instalar.bat`**.
   - Se o Windows mostrar um aviso azul "O Windows protegeu o computador", clique em **"Mais informações"** → **"Executar mesmo assim"**. Isso acontece com qualquer `.bat` baixado da internet.
5. Espere a instalação terminar (1-3 minutos). Pronto. Esse passo só é feito uma vez.

### Rodar o agregador

**Dê duplo-clique em `rodar.bat`**. Ele vai:
- Ler suas pesquisas no CSV manual.
- Atualizar o banco.
- Calcular a média ponderada.
- Gerar o Excel em `output\agregador_pesquisas.xlsx`.
- Abrir o Excel automaticamente.

### Adicionar uma nova pesquisa manualmente

Abra `data\pesquisas_manuais.csv` no Excel (clique com botão direito → Abrir com → Excel). Cada linha é uma pesquisa. Adicione uma linha nova preenchendo as colunas: `instituto, contratante, data_inicio_campo (YYYY-MM-DD), data_fim_campo (YYYY-MM-DD), amostra, margem_erro, cenario, tipo, registro_tse, url_fonte`, e depois os percentuais de cada candidato.

**Atenção ao salvar pelo Excel**: ele pode oferecer salvar como `.xlsx`. **Você precisa manter o formato CSV (separado por vírgulas)**. Quando for salvar (Ctrl+S), o Excel vai perguntar — clique em "Sim, manter este formato".

Depois de salvar, dê duplo-clique em `rodar.bat` de novo.

### Ajustar pesos por instituto

Abra `data\pesos_institutos.csv` no Excel. Cada linha tem um instituto e um peso (número). Mude os números, salve (mantendo formato CSV), e rode `rodar.bat` de novo.

Exemplo:
```
instituto,peso,observacao
Datafolha,1.2,Confio mais nas séries longas
Quaest,1.1,
AtlasIntel,0.9,Painel online, ajusto pra baixo
```

### Ajustar parâmetros gerais

Abra `data\config.yaml` no Bloco de Notas (clique com botão direito → Abrir com → Bloco de Notas). Lá você pode mudar:
- `half_life_dias`: depois de quantos dias uma pesquisa perde metade do peso (padrão: 30).
- `amostra_referencia`: tamanho de amostra que recebe peso 1.0 (padrão: 2000).
- `janela_dias`: ignora pesquisas mais antigas que isso (padrão: 180).
- Ligar/desligar a ponderação por recência ou amostra.

---

## Como funciona a fórmula de ponderação

Para cada pesquisa `i`:

```
peso_final_i = peso_instituto × peso_recencia × peso_amostra
```

- **peso_instituto**: vem do seu CSV.
- **peso_recencia**: decaimento exponencial. Pesquisa de hoje = 1.0; pesquisa de 30 dias atrás (half-life) = 0.5; de 60 dias = 0.25; etc.
- **peso_amostra**: `sqrt(amostra / 2000)`. Pesquisa com 500 entrevistados = 0.5; 2000 = 1.0; 8000 = 2.0.

Para cada candidato, a média é:

```
média = Σ(percentual_i × peso_final_i) / Σ(peso_final_i)
```

Quer mudar a fórmula? Edite `scrapers\ponderacao.py`.

---

## Automação na nuvem (GitHub Actions)

Para rodar automaticamente todo dia sem você fazer nada:

1. Crie um repositório no GitHub e suba esta pasta inteira.
2. Pronto. O arquivo `.github\workflows\agregar.yml` já está configurado.
3. Todo dia às 9h (horário de Brasília) o GitHub vai:
   - Rodar o agregador.
   - Commitar o Excel atualizado no próprio repositório.
4. Você baixa o Excel atualizado direto do GitHub (ou clona o repo para sincronizar).

Para forçar uma execução: GitHub → aba "Actions" → "Agregador diário de pesquisas" → "Run workflow".

**Vantagem**: o GitHub Actions roda em Linux na nuvem, então a automação funciona independente de qual sistema operacional você usa no seu computador. Você pode até nem ligar o computador — ele atualiza sozinho.

---

## Solução de problemas (Windows)

**"Python não foi encontrado"** ao rodar `instalar.bat`:
- Você não marcou "Add Python to PATH" durante a instalação. Reinstale o Python (não precisa desinstalar o antigo) e marque a caixa.

**"O Windows protegeu o computador"** ao tentar rodar `.bat`:
- Normal. Clique em "Mais informações" → "Executar mesmo assim".

**Janela fecha sozinha sem mostrar erro**:
- Abra o Prompt de Comando (digite `cmd` no menu Iniciar), navegue até a pasta do projeto com `cd C:\caminho\para\agregador-pesquisas`, e rode `instalar.bat` ou `rodar.bat` por ali. Assim você vê a mensagem de erro completa.

**Excel não abre automaticamente**:
- Abra manualmente o arquivo em `output\agregador_pesquisas.xlsx`. O agregador rodou normalmente, só o auto-open falhou.

**Caracteres estranhos no Bloco de Notas** ao abrir CSV:
- O CSV está em UTF-8 mas o Bloco de Notas antigo pode mostrar acentos errados. Use o Excel, VS Code, ou o Notepad++. Ou simplesmente o Bloco de Notas das versões recentes do Windows 10/11 — esse já entende UTF-8.

---

## Roadmap

### ✅ Fase 1 (pronto)
- Estrutura do projeto, banco SQLite, motor de ponderação, Excel, automação GitHub.
- Coleta manual via CSV.

### 🚧 Fase 2 — Scraper do TSE
- Sistema PesqEle (<https://pesqele-divulgacao.tse.jus.br/>) é o registro oficial.
- É um SPA (JavaScript): scraper precisa de Playwright OU engenharia reversa da API.
- Próximo passo: abrir o site, inspecionar DevTools → Network, mapear endpoints.

### 🔮 Fase 3 — Scrapers individuais dos institutos
- Datafolha, Quaest, AtlasIntel, Paraná Pesquisas, Ipespe.
- Um por um, mais frágeis (sites mudam).

### 🔮 Fase 4 — Mais cenários
- Lula vs Tarcísio, Lula vs Michelle, espontânea, estimulada com lista cheia.

### 🔮 Fase 5 — Notificações
- Avisar via Telegram/email quando uma nova pesquisa entrar.

---

## Estrutura do projeto

```
agregador-pesquisas\
├── data\
│   ├── config.yaml              ← parâmetros (edite aqui)
│   ├── pesos_institutos.csv     ← seus pesos (edite aqui)
│   ├── pesquisas_manuais.csv    ← pesquisas que você adiciona (edite aqui)
│   └── pesquisas.db             ← banco SQLite (gerado automaticamente)
├── output\
│   └── agregador_pesquisas.xlsx ← Excel atualizado (gerado)
├── scrapers\
│   ├── main.py                  ← script principal
│   ├── db.py                    ← camada de banco
│   ├── ponderacao.py            ← motor de média ponderada
│   ├── coletores.py             ← coletores (manual + TSE)
│   ├── excel_writer.py          ← gerador do Excel
│   └── schema.sql               ← schema do banco
├── .github\workflows\
│   └── agregar.yml              ← cron diário no GitHub Actions
├── instalar.bat                 ← duplo-clique para instalar
├── rodar.bat                    ← duplo-clique para rodar
├── requirements.txt             ← dependências Python
└── README.md                    ← este arquivo
```

---

## Limitações conhecidas

- O termo "Bolsonaro" em pesquisas pode se referir a Jair, Flávio, Michelle ou Eduardo. Você precisa cuidar disso na coleta — recomendado: cenários separados quando o sistema crescer.
- Pesquisa via Telegram/online vs presencial têm vieses diferentes; o sistema não corrige isso, mas você pode embutir nos pesos por instituto.
- O TSE só mantém pesquisas registradas por 30 dias na consulta pública — então o scraper precisa rodar com frequência para não perder dados.
