# Roteiro de operação do agente — rodada das 6h

Este arquivo é a instrução da rodada diária. Siga na ordem.

## 1. Preparar

```bash
cd radar-noticias && python3 radar.py testar
```
Se a suíte falhar, siga mesmo assim e registre a falha no fim do briefing.

## 1b. Pegar os interesses do leitor

O painel tem entrada com perfil. Leia **antes** de rodar, com a ferramenta de
banco do artifact (ação `get`, url https://claude.ai/artifact/TNy9mqZTd6LLUDgvPpEMff):

1. collection `data/users/me`, doc `perfil` — o perfil privado da conta: `temas`,
   `regioes`, `ritmo` e `leituras` (contagem do que a pessoa abre de fato; os
   três assuntos mais lidos valem como interesse mesmo fora dos favoritos);
2. se não existir, collection `preferencias`, doc `atual` (o espelho que a caixa
   de interesses grava)

Escreva `temas`, `regioes` e `peso` em `config/preferencias.json` (mantenha o
campo `_doc`). Se o documento não existir ou vier vazio, deixe as listas vazias —
radar padrão. Esses interesses **não** passam por cima do piso de pautas do
Brasil: eles mudam o que vem depois do topo.

## 2. Coletar

**Primeiro tente o caminho normal:**
```bash
python3 radar.py rodar
```

Se a saída mostrar os feeds falhando com `rede:` ou `HTTP 403` (a política de
rede do ambiente bloqueia os sites de notícia), vá para o caminho do agente.

**Caminho do agente** — use a busca da web restrita a domínios de veículos.
Faça ao menos 5 buscas, em paralelo, cobrindo:

1. Brasil, geral e política — `g1.globo.com`, `folha.uol.com.br`,
   `agenciabrasil.ebc.com.br`, `poder360.com.br`, `cnnbrasil.com.br`
2. Economia e bolso — `infomoney.com.br`, `valor.globo.com`, `exame.com`,
   `bcb.gov.br`, `g1.globo.com`
3. Mundo — `aljazeera.com`, `cnbc.com`, `nature.com`
4. Tecnologia — `techcrunch.com`, `tecnoblog.net`, `canaltech.com.br`
5. Serviço e utilidade pública (INSS, regras que mudam, calendários, concursos)

Não insista em `estadao.com.br`, `reuters.com`, `apnews.com`, `bbc.com`,
`theguardian.com`, `elpais.com`, `dw.com`: eles bloqueiam o crawler e a busca
devolve erro 400.

Escreva o resultado em `dados/ingest_<data>.json`:

```json
{"itens": [{"titulo": "...", "fonte": "g1", "url": "https://...",
            "resumo": "...", "publicado_em": "2026-10-26T07:00:00-03:00",
            "pais": "BR", "editoria": "economia"}]}
```

Regras duras ao montar esse arquivo:
- **`grupo`** (opcional): mesmo texto em matérias do mesmo fato quando as manchetes usam palavras diferentes ("fugiu", "deixou o país", "passaporte cancelado") — o curador junta na mesma pauta;
- **título e url exatamente como vieram** — nada de reescrever manchete;
- **só entra matéria das últimas 48 horas, e só com data.** O pipeline descarta
  tudo o que for mais antigo *e* tudo o que vier sem data (`selecao.exigir_data`).
  Então a data é o campo mais importante do item:
  - use a data que a fonte informa;
  - se não houver, o pipeline tenta deduzir pela URL (`/2026/10/25/`,
    `-26102026/`) — prefira resultados cujo link traz a data;
  - pode deduzir pelo conteúdo só quando o texto *prova* o limite (ex.: reação ao
    resultado do 2º turno não pode ser anterior à noite da apuração). Nesse caso
    preencha `data_inferida` explicando o porquê;
  - nunca invente data para "salvar" uma matéria boa. Sem data, ela fica de fora;
- **resumo só com o que a fonte diz.** Pode traduzir, não pode completar;
- **tudo em português.** Prefira veículo brasileiro, inclusive para notícia
  internacional (g1 Mundo, CNN Brasil Internacional, Agência Brasil, Poder360,
  Folha Mundo). Se a matéria só existe em outro idioma, traduza título e resumo
  com fidelidade, guarde o original em `titulo_original` e marque `traduzido_de`
  (ex.: "inglês"). Título em outro idioma sem tradução é descartado;
- **mire em 55 a 80 itens cobrindo todos os temas do painel**: política,
  economia, tecnologia, mundo, ciência, saúde, esporte, cultura, meio ambiente e
  cotidiano — mais as regiões (EUA, Reino Unido, Europa, América Latina, Ásia,
  Oriente Médio, África). É isso que faz a caixa de interesses ter o que mostrar
  quando a pessoa escolhe um tema; com meia dúzia de pautas de política, escolher
  "Esporte" devolve tela vazia.
- se um tema ficar sem nada mesmo depois da busca, tudo bem: o painel avisa
  "sem nada hoje de <tema>". Não preencha com matéria velha para tapar buraco.

Depois:
```bash
python3 radar.py rodar --sem-rss --ingest dados/ingest_<data>.json
```

## 3. Conferir antes de publicar

Abra `saida/ultimo.md` e cheque:
- a pauta nº 1 é mesmo a notícia do dia? Se não for, o motivo costuma estar na
  cobertura (um veículo só) ou em data faltando;
- algum roteiro ficou com `[CONFERIR:]` em todos os blocos? Então a pauta veio
  sem resumo — volte e busque o resumo daquela matéria;
- algum aviso de risco ficou sem sentido? Ajuste o léxico em `radar/score.py`.

## 4. Publicar

Publique o painel **no mesmo endereço de sempre**, para o link não mudar:

- arquivo: `saida/painel_artifact.html` (gere com
  `python3 -c "import sys;sys.path.insert(0,'.');from radar.util import ler_json;from radar.painel import gerar_painel;gerar_painel(ler_json('saida/ultimo.json'),modo='artifact')"`)
- `url`: https://claude.ai/artifact/TNy9mqZTd6LLUDgvPpEMff
- leia o artifact antes de publicar (a ferramenta exige).

## 4b. Conferir a reordenação

Se havia interesses, confira no log do `rodar` a linha `interesses do painel:` e
veja se alguma pauta da região pedida entrou. Se a região pedida não apareceu
em nenhuma pauta, é sinal de que a coleta não trouxe nada de lá — vale uma busca
extra só daquela região antes de publicar.

## 5. Guardar

```bash
git add -A && git commit -m "radar: <data>" && git push -u origin main
```

## 6. Avisar

Mensagem curta, em português: as 3 pautas do topo, qual roteiro é o primeiro da
fila de gravação, e o link do painel. Nada de relatório longo.
