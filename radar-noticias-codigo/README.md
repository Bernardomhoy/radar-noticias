# Radar de Notícias

Radar diário de notícias do Brasil, com um olho no mundo: lê dezenas de veículos,
junta as matérias que falam da mesma coisa, pontua e fecha a pauta do dia.

Roda às 6h da manhã, fecha o briefing e publica o painel.

- **Painel do dia:** https://claude.ai/artifact/TNy9mqZTd6LLUDgvPpEMff
- Saída em `saida/<data>/`: `briefing.md`, `radar.json` e o painel HTML.

## Os cinco agentes

| Agente | Arquivo | O que faz |
|---|---|---|
| **Caçador** | `radar/coleta.py` | lê 38 feeds RSS/Atom de 29 veículos em paralelo (só stdlib) |
| **Curador** | `radar/pauta.py`, `radar/score.py` | junta matérias da mesma pauta e pontua cada uma |
| **Editor-chefe** | `radar/editor.py` | escolhe a pauta do dia com cotas e anti-repetição |
| **Roteirista** | `radar/roteiro.py` | monta roteiro de reels — **desligado** em `config.json` |
| **Publicador** | `radar/briefing.py`, `radar/painel.py` | escreve o briefing e o painel |

## Só as últimas 48 horas

`selecao.janela_horas = 48` e `selecao.exigir_data = true`: entra no radar só o que
foi publicado nas últimas 48 horas, e só o que tem data — informada pela fonte ou
deduzida da URL. Sem data não há como garantir que a matéria é atual, então ela
sai. O painel mostra o corte às claras: "23 matérias na janela · de 73 lidas".

Consequência honesta: num dia em que nenhum veículo publicou sobre Saúde nas
últimas 48h, Saúde aparece como "nada hoje". Com os feeds RSS (em casa, rede
liberada) isso quase não acontece, porque todo item de RSS traz `pubDate`.

## Dois scores, de propósito

Misturar "notícia importante" com "notícia que rende vídeo" dá ranking ruim —
tragédia fica em primeiro e calendário de pagamento fica em último, ou o
contrário. Então são duas contas:

- **`score_noticia`** — corroboração (quantos veículos distintos), peso da fonte,
  recência e calor (volume e ritmo). **Ordena o briefing.**
- **`score_reels`** — potencial de vídeo curto (bolso, utilidade, espanto,
  conflito, tecnologia, humano, cultura pop) + recência + corroboração.
  **Ordena a fila de gravação.**

Toda pauta vem com `explicacao` e `explicacao_reels` em texto: a escolha nunca é
caixa-preta.

## Roteiro de reels: desligado

`config.json` tem `roteiros.ativo: false`. Com isso o agente roteirista não roda,
a fila de gravação some do briefing e o score de reels sai do painel. O código
continua inteiro no repositório: mude para `true` e volta tudo — os ganchos, os
blocos cronometrados, a trilha, as hashtags e os avisos de checagem.

## O painel

- **Entrada com perfil.** Antes do globo, a página reconhece a conta do claude.ai
  (nome e foto) — sem senha, porque a página não teria como conferir uma. Na
  primeira visita, três passos: como quer ser chamado, assuntos favoritos, regiões
  e jeito de ler ("com contexto" ou "manchetes rápidas"). Nas seguintes, saudação,
  seus assuntos, quantas pautas deles há hoje e o que você mais lê. O perfil fica em
  `data/users/<id>/perfil`, que só o dono da conta lê.
- **Gostos aprendidos.** Abrir a página de um assunto, a prévia ou o link de uma
  matéria conta ponto para aquele assunto. Quando um assunto muito lido não está
  nos favoritos, a entrada sugere incluí-lo.
- **Só português.** Título em outro idioma sai; matéria que o agente traduziu fica,
  com o selo "traduzido" e o título original na prévia. Os feeds RSS em inglês
  estão desligados (`ativo: false`) e entraram internacionais em português.

- **Abertura: mãos segurando o globo** — duas mãos cartunescas erguem o planeta,
  que flutua enquanto os continentes giram com borrão horizontal, o halo pulsa e
  faíscas piscam fora de fase. As frases são os números reais da rodada, não
  enfeite. Sai dissolvendo em desfoque, tem botão *pular*, teto de 6,5 s e some
  por completo em `prefers-reduced-motion`.
- **Dois carregamentos, dois personagens** — as mãos abrem o sistema; os olhos
  bravos (com chamas) aparecem quando você troca de assunto ou confirma
  interesses.
- **Cada assunto tem a sua página.** Clicar num atalho, no chip de editoria de
  um cartão ou confirmar um único interesse abre a página daquele assunto: só as
  pautas dele, com um ambiente próprio — emojis do tema flutuando atrás do
  título, com desfoque e velocidades diferentes. Cada página tem endereço
  (`#tecnologia`, `#oriente-medio`), então dá para voltar pelo botão do navegador.
- **Vários interesses juntos** montam um radar misto: *Principais do Brasil*
  (3, que não cedem lugar) + *Do seu interesse* (até 14), tirados do pool inteiro
  da coleta — por isso o pipeline guarda até 60 pautas no JSON, não só as do corte.
- **Tema vazio é dito na cara.** Se a coleta do dia não trouxe nada de Saúde, a
  nota diz *"sem nada hoje de Saúde"* em vez de mostrar uma lista que parece
  quebrada. O radar não inventa matéria.
- **Prévia no hover** — passe o mouse por uma pauta e sobe um cartão (com motion
  blur) trazendo o resumo inteiro, quando saiu, quem cobriu, por que entrou e o
  que ela rende em vídeo. No telefone, o botão `prévia` abre a mesma coisa como
  folha ancorada embaixo.
- **"Sobre o que você quer ler"** — caixa no canto com temas e regiões. Ao
  confirmar, entra a tela de carregamento (olhos animados), a pauta do dia é
  reordenada na hora e a escolha vai para o banco do artifact. A rodada das 6h
  do dia seguinte lê de lá e já começa por ali.
- **O piso do Brasil vale sempre.** Interesse reordena o que vem depois do topo;
  `selecao.min_br` não cede. Se você pede uma região, ela ganha vaga garantida —
  desde que a coleta tenha trazido alguma pauta de lá.
- **Motion blur** em cinco lugares: o giro do globo na abertura, borrão direcional proporcional à velocidade
  real de rolagem (filtro SVG com `stdDeviation` em y), a varredura do radar no
  o borrão direcional proporcional à velocidade real de rolagem (filtro SVG com
  `stdDeviation` em y), a varredura do radar no cabeçalho, o rastro no número da
  pauta e a entrada da prévia e da caixa. Tudo desliga em
  `prefers-reduced-motion`.

## Freios editoriais

- Pauta com vítimas, saúde mental ou menores tem o potencial de reels reduzido
  (0,62 / 0,45 / 0,70) e **não entra na fila de gravação** — continua no briefing
  como notícia.
- Cada risco detectado vira um aviso no roteiro (eleitoral, judicial, saúde,
  financeiro...).
- Matéria com um veículo só é marcada como tal, e o roteiro manda falar
  "segundo *fulano*".
- Trecho que o sistema não pôde confirmar vira `[CONFERIR: ...]` no roteiro.
  Trecho em outro idioma vira `[TRADUZIR PARA A FALA: "..."]`.
- Nenhum número é inventado: tudo vem do material coletado.

## Uso

```bash
python3 radar.py rodar                          # ciclo completo via RSS
python3 radar.py rodar --ingest itens.json      # RSS + itens trazidos pelo agente
python3 radar.py rodar --sem-rss --ingest x.json  # só o que o agente trouxe
python3 radar.py rodar --pautas 8 --roteiros 4  # muda o tamanho do dia
python3 radar.py painel                         # regenera o painel do último radar
python3 radar.py stats                          # histórico do que já passou
python3 radar.py testar                         # suíte de calibração do agrupamento
```

Sem dependências: Python 3.9+ e biblioteca padrão.

## Configuração

`config/config.json`
- `perfil` — tom, duração alvo, palavras por segundo, CTA do canal.
- `selecao` — quantas pautas e roteiros por dia, piso de pautas do Brasil
  (`min_br`), piso e teto de internacionais (`min_mundo`, `max_mundo`), teto por
  editoria, janela de coleta e dias de anti-repetição.
- `pesos_noticia` / `pesos_reels` — os dois conjuntos de pesos.
- `limiar_cluster` — 0.40. Acima disso duas matérias viram a mesma pauta.

`config/fontes.json` — 29 veículos com peso editorial, país e feeds.
`config/regioes.json` — termos (em português e inglês) que marcam a região de
uma pauta. É o que faz "Israeli" e "Iran" casarem com Oriente Médio.
`config/preferencias.json` — interesses vindos do painel. Vazio = radar padrão.
`config/sinonimos.json` — canonicalização do noticiário brasileiro: faz "IR"
casar com "Imposto de Renda", "Câmara" com "Congresso", "capital paulista" com
"São Paulo". É o que segura o agrupamento sem depender de embeddings.

## Como o agrupamento funciona

Sem biblioteca de NLP. Para cada manchete:

1. **canonicalização** — frases e siglas viram um token padrão (`sinonimos.json`);
2. **radical** — corta em 6 letras e tira vogal final (`fechou` e `fecha` → `fech`);
3. **similaridade** — 50% sobreposição de radicais + 20% jaccard + 22% entidades
   em comum + 8% do resumo, com bônus para número e para dois nomes próprios iguais;
4. **ligação simples** — entra no grupo se passar do limiar com qualquer membro.

A calibração está em `testes/test_cluster.py`: 7 pares que **devem** juntar,
6 que **não devem** e 6 classificações de editoria. `python3 radar.py testar`.

## Limitações conhecidas

- **A página não busca notícia sozinha.** Um artifact publicado não tem como
  sair para a internet: ele mostra o que a rodada coletou. A busca atualizada
  acontece na rodada das 6h (ou quando você roda `python3 radar.py rodar` em
  casa, com os feeds liberados) — a tela do globo cobre a montagem da lista e a
  volta do banco, não uma coleta ao vivo.
- O casamento é lexical. Duas manchetes sobre o mesmo fato sem palavra em comum
  não se juntam; duas pautas próximas do mesmo veículo podem se juntar demais
  (ex.: dois calendários do INSS). O limiar de 0.40 é o ponto onde a suíte passa.
- A camada de busca do agente só alcança veículos que permitem o crawler. Alguns
  grandes (Estadão, Reuters, AP, BBC, Guardian) bloqueiam — para eles, o caminho
  é o RSS.
- Item sem data informada recebe recência neutra (0,5), não "agora".

## No ar pelo Netlify

- **Robô 24 h — GitHub Actions** (`.github/workflows/radar.yml`) roda sozinho a cada
  30 min, dia e noite: lê os feeds RSS de `config/fontes.json`, faz a curadoria,
  gera `site/index.html` e faz commit. Não usa o Claude, então não gasta token.
  Em repositório público o Actions é grátis; em privado, rodar a cada 30 min passa
  da cota grátis (2.000 min/mês). Nesse caso, troque o cron para `7 * * * *` (de hora em hora).
- **Netlify** (`netlify.toml`) publica a pasta `site/` a cada commit. Sem build.
- Para rodar na hora: aba **Actions → radar → Run workflow** no GitHub.
- Fora do claude.ai não há login da conta Claude: o perfil do leitor fica no
  navegador (localStorage), um por aparelho.
