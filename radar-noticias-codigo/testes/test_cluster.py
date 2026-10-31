"""Calibracao do agrupamento: pares que DEVEM juntar e pares que NAO devem."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radar.pauta import _assinatura, similaridade, agrupar, classificar_editoria
from radar.util import iso, agora_br

LIMIAR = 0.40

def sim(t1, t2):
    return similaridade(_assinatura({"titulo": t1, "resumo": ""}),
                        _assinatura({"titulo": t2, "resumo": ""}))

DEVEM_JUNTAR = [
    ("Dólar fecha abaixo de R$ 5 pela primeira vez desde outubro",
     "Câmbio: dólar encerra sexta abaixo de R$ 5,00"),
    ("Congresso aprova projeto de isenção do Imposto de Renda",
     "Câmara conclui votação da isenção do IR para quem ganha até R$ 5 mil"),
    ("Banco Central mantém Selic em 15% ao ano",
     "Copom decide manter juros em 15%, o maior nível em duas décadas"),
    ("Ukraine and Russia resume peace talks in Istanbul",
     "Rússia e Ucrânia retomam negociações de paz em Istambul"),
    ("Lula sanciona lei que amplia licença-paternidade",
     "Presidente assina sanção da nova licença-paternidade"),
    ("Chuva forte causa alagamentos em São Paulo",
     "Temporal provoca alagamento na capital paulista"),
    ("OpenAI lança novo modelo de inteligência artificial",
     "OpenAI anuncia novo modelo de IA para empresas"),
]

NAO_DEVEM_JUNTAR = [
    ("Dólar fecha abaixo de R$ 5", "Congresso aprova isenção do Imposto de Renda"),
    ("Flamengo vence o Palmeiras no Maracanã", "Palmeiras anuncia novo técnico para 2027"),
    ("Lula sanciona lei de licença-paternidade", "Lula viaja à China para encontro comercial"),
    ("Estudo revela nova vacina contra dengue", "Vacinação contra gripe começa em São Paulo"),
    ("Nasa descobre exoplaneta a 40 anos-luz", "Nasa adia lançamento de foguete por falha"),
    ("Ibovespa sobe 1,2% puxado por Vale", "Vale anuncia demissão de 500 funcionários"),
]

def main():
    falhas = 0
    print(f"limiar = {LIMIAR}\n--- devem juntar ---")
    for a, b in DEVEM_JUNTAR:
        s = sim(a, b); ok = s >= LIMIAR
        falhas += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FALHA'} {s:.3f}  {a[:44]!r} ~ {b[:44]!r}")
    print("--- nao devem juntar ---")
    for a, b in NAO_DEVEM_JUNTAR:
        s = sim(a, b); ok = s < LIMIAR
        falhas += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FALHA'} {s:.3f}  {a[:44]!r} ~ {b[:44]!r}")

    print("--- editorias ---")
    casos = [("Banco Central mantém Selic em 15%", "economia"),
             ("STF julga ação sobre marco temporal", "politica"),
             ("Estudo da Nasa mostra buraco negro inédito", "ciencia"),
             ("OpenAI lança modelo de IA", "tecnologia"),
             ("Chuva causa enchente no Rio Grande do Sul", "meio-ambiente"),
             ("Seleção brasileira vence por 3 a 0", "esporte")]
    for texto, esperado in casos:
        got = classificar_editoria(texto)
        ok = got == esperado
        falhas += 0 if ok else 1
        print(f"  {'OK ' if ok else 'FALHA'} {texto[:40]!r} -> {got} (esperado {esperado})")

    print(f"\n{'TODOS OS TESTES PASSARAM' if not falhas else str(falhas) + ' FALHA(S)'}")
    return 1 if falhas else 0

if __name__ == "__main__":
    sys.exit(main())
