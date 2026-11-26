"""Teste de cookies/login da Onuh (usado pelo GitHub Actions).

Sai com codigo 1 se o cookie nao der acesso aos precos de lojista.
Nao imprime tokens, cookies nem senhas.
"""
import sys

from playwright.sync_api import sync_playwright

from onuh_auth import PRODUTO_TESTE, carregar_estado, criar_contexto, verificar_login


def main():
    estado = carregar_estado()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = criar_contexto(browser, estado)
        page = ctx.new_page()
        resultado = verificar_login(page, ctx)
        browser.close()

    if not resultado["ok"]:
        print("TESTE DE COOKIES: FALHOU", flush=True)
        print(f"Motivo: {resultado['motivo']}", flush=True)
        print("Acao: rode salvar_login.py e atualize ONUH_STORAGE_STATE_JSON, "
              "ou configure ONUH_EMAIL + ONUH_PASSWORD.", flush=True)
        sys.exit(1)

    preco = resultado["preco_teste"]
    print("TESTE DE COOKIES: OK", flush=True)
    print(f"LOGADO como: {resultado['usuario'] or 'lojista'}", flush=True)
    print(f"Produto de teste: {PRODUTO_TESTE.rsplit('/', 1)[-1]} = R$ {preco:.2f}", flush=True)
    print(f"Preco final no site apos margem: R$ {preco + 30:.2f}", flush=True)


if __name__ == "__main__":
    main()
