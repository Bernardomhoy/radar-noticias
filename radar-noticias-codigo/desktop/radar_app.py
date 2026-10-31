"""Radar de Notícias para Windows: abre o site do radar numa janela própria.

O robô do GitHub atualiza o site a cada 30 min; o app só mostra a versão mais
nova. Se o site do Netlify não responder, cai para a cópia que o robô salva no
próprio repositório.
"""
import urllib.request

import webview

# Trocado pelo endereço do Netlify na hora de montar o .exe (variável SITE_URL do repositório).
SITE = "__SITE_URL__"
RESERVA = "https://raw.githubusercontent.com/Bernardomhoy/radar-noticias/main/site/index.html"


def responde(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> None:
    titulo = "Radar de Notícias"
    if SITE.startswith("http") and responde(SITE):
        webview.create_window(titulo, SITE, width=1200, height=850, min_size=(380, 600))
    else:
        try:
            with urllib.request.urlopen(RESERVA, timeout=10) as r:
                html = r.read().decode("utf-8")
        except Exception:
            html = ("<body style='background:#0e1218;color:#f5ecdc;font-family:sans-serif;"
                    "display:grid;place-items:center;height:100vh'>"
                    "<p>Sem conexão. Abra o Radar de novo quando a internet voltar.</p></body>")
        webview.create_window(titulo, html=html, width=1200, height=850, min_size=(380, 600))
    webview.start(private_mode=False)


if __name__ == "__main__":
    main()
