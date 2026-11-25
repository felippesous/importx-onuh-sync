"""Roda 1x no PC. Faz login na Onuh e salva onuh_cookies.json LOCAL. NUNCA suba esse arquivo no GitHub."""
import json, time
from playwright.sync_api import sync_playwright
print("Vai abrir o navegador. Faça login na Onuh e volte aqui e aperte ENTER.")
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=False)
    ctx = b.new_context()
    page = ctx.new_page()
    page.goto("https://catalogo.onuh.com.br")
    input("Fez login? Aperte ENTER...")
    cookies = ctx.cookies()
    pathlib = __import__("pathlib").Path("onuh_cookies.json")
    pathlib.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Salvo onuh_cookies.json com {len(cookies)} cookies. Agora cole o conteúdo dele no Secret ONUH_COOKIES_JSON no GitHub.")
    b.close()
