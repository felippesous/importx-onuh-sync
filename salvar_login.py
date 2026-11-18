
"""
Rode 1x NO SEU PC: python salvar_login.py
Abre o navegador, você faz login na Onuh manualmente,
aperta ENTER, e ele salva onuh_cookies.json (só cookies, sem senha).
Depois você cola o conteúdo desse arquivo no GitHub Secret ONUH_COOKIES_JSON.
"""
import json
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=False)
    ctx = b.new_context(locale="pt-BR")
    page = ctx.new_page()
    page.goto("https://catalogo.onuh.com.br/login")
    print(">>> Faça login na Onuh no navegador que abriu, depois volte aqui e aperte ENTER")
    input()
    cookies = ctx.cookies()
    open("onuh_cookies.json","w",encoding="utf-8").write(json.dumps(cookies, ensure_ascii=False, indent=2))
    print(f"Salvo onuh_cookies.json com {len(cookies)} cookies. Não compartilhe esse arquivo.")
    b.close()
