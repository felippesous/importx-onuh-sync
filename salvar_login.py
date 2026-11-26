"""Salva o login da Onuh (cookies + localStorage) para o GitHub Actions.

Rode no seu computador, faca login na janela que abrir e aperte ENTER.
O script so salva se o preco de lojista estiver visivel no produto-teste.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from onuh_auth import BASE, carregar_estado, criar_contexto, verificar_login

print("Vai abrir UMA JANELA NOVA do Chromium.")
print("FACA LOGIN DENTRO DESSA JANELA NOVA - nao no seu Chrome normal.")
print("Quando aparecer seu nome / Minha conta, volte aqui e aperte ENTER.")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    ctx = criar_contexto(browser, carregar_estado())
    page = ctx.new_page()
    page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
    input("\nFez login DENTRO DA JANELA NOVA? Aperte ENTER... ")

    resultado = verificar_login(page, ctx)
    print("\n--- TESTE DO LOGIN ---")
    print(f"Logado: {'SIM' if resultado['ok'] else 'NAO'}", flush=True)
    print(f"Usuario: {resultado['usuario'] or 'nao identificado'}", flush=True)
    print(f"Produto-teste: R$ {resultado['preco_teste']}", flush=True)
    if not resultado["ok"]:
        print(f"Motivo: {resultado['motivo']}", flush=True)
        print("Nada foi salvo. Rode de novo e faca login na janela nova.", flush=True)
        browser.close()
        raise SystemExit(1)

    estado = ctx.storage_state()
    Path("onuh_storage.json").write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cookies = estado.get("cookies", [])
    Path("onuh_cookies.json").write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nSalvo onuh_storage.json e onuh_cookies.json.", flush=True)
    print(f"Cookies: {len(cookies)} | origins: {len(estado.get('origins', []))}", flush=True)
    print("\nCOPIE TODO o conteudo de onuh_storage.json para o Secret ONUH_STORAGE_STATE_JSON.", flush=True)
    print("(Ou cole o conteudo de onuh_cookies.json em ONUH_COOKIES_JSON.)", flush=True)
    browser.close()
