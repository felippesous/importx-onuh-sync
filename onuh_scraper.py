
"""
ImportX Atacado - Robô Onuh
Roda todo dia no GitHub Actions (grátis) ou no seu PC.
NÃO usa senha. Usa cookies salvos em onuh_cookies.json (gerado 1x no seu PC).
Saídas: data/produtos.json + data/variacao_precos.csv
"""
import json, csv, re, os, time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://catalogo.onuh.com.br"
OUT_JSON = Path("data/produtos.json")
OUT_CSV = Path("data/variacao_precos.csv")
COOKIES_FILE = Path("onuh_cookies.json")

CATEGORIAS = [
    "perfumes-arabes", "nicho", "k-beauty", "skincare",
    "body-splash", "coffret", "miniaturas", "openbox",
    "mais-vendidos", "lancamentos", "cuidados-corporais",
    "cabelos", "kids", "designer", "promocao",
]

def parse_price(txt):
    if not txt: return None
    txt = txt.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try: return float(re.findall(r"[\d.]+", txt)[0])
    except: return None

def run():
    OUT_JSON.parent.mkdir(exist_ok=True, parents=True)
    antigos = {}
    if OUT_JSON.exists():
        try:
            for p in json.loads(OUT_JSON.read_text(encoding="utf-8")):
                antigos[p.get("sku") or p.get("nome")] = p
        except: pass

    produtos = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            viewport={"width": 1366, "height": 900},
            locale="pt-BR",
        )
        # 1) Login por cookies (seguro - sem senha no código)
        if COOKIES_FILE.exists():
            cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            ctx.add_cookies(cookies)
        else:
            # No GitHub Actions, cookies vêm de Secret
            raw = os.environ.get("ONUH_COOKIES_JSON")
            if raw:
                ctx.add_cookies(json.loads(raw))

        page = ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # Verifica se está logado: procura texto de preço / sair / minha conta
        html = page.content().lower()
        logado = any(x in html for x in ["sair", "minha conta", "meus pedidos", "r$"])
        print(f"Logado? {logado} - URL atual: {page.url}")
        if not logado:
            print("AVISO: Não detectou login. Gere onuh_cookies.json no seu PC com: python salvar_login.py")
            # Continua mesmo assim - alguns produtos podem aparecer sem preço

        # 2) Varre categorias - tenta 3 seletores genéricos comuns em catálogos
        # AJUSTE RÁPIDO: se o site mudar o HTML, só trocar os seletores aqui
        for cat in CATEGORIAS:
            url = f"{BASE}/categoria/{cat}" if cat not in ["mais-vendidos"] else f"{BASE}/"
            print(f"\nCategoria: {cat} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                # Scroll infinito / paginação
                for _ in range(8):
                    page.mouse.wheel(0, 3000)
                    time.sleep(1.2)
                    # clica em "carregar mais" se existir
                    try:
                        btn = page.locator("text=Carregar mais, text=Ver mais, text=Mostrar mais").first
                        if btn.is_visible():
                            btn.click(); time.sleep(2)
                    except: pass

                # Extração genérica: procura cards de produto
                cards = page.locator("article, [data-product], .product-card, .produto").all()
                print(f"  Cards encontrados: {len(cards)}")
                for c in cards:
                    try:
                        txt = c.inner_text(timeout=2000)
                        linhas = [l.strip() for l in txt.split("\n") if l.strip()]
                        if not linhas: continue
                        nome = linhas[0]
                        preco_txt = next((l for l in linhas if "R$" in l), "")
                        preco = parse_price(preco_txt)
                        img = ""
                        try: img = c.locator("img").first.get_attribute("src") or ""
                        except: pass
                        link = ""
                        try: link = c.locator("a").first.get_attribute("href") or ""
                        except: pass
                        if link and link.startswith("/"): link = BASE + link
                        sku = re.sub(r"\W+", "-", nome.lower())[:80]
                        produtos.append({
                            "sku": sku,
                            "nome": nome,
                            "marca": nome.split()[0] if nome else "",
                            "categoria": cat,
                            "preco_atacado": preco,
                            "em_estoque": "esgotado" not in txt.lower() and "indisponível" not in txt.lower(),
                            "foto": img,
                            "link_onuh": link,
                            "atualizado_em": datetime.now().isoformat(),
                        })
                    except: continue
            except Exception as e:
                print(f"  Erro em {cat}: {e}")

        browser.close()

    # 3) Deduplica por SKU, mantém menor preço se duplicar
    unico = {}
    for p in produtos:
        if p["sku"] not in unico or (p["preco_atacado"] and (not unico[p["sku"]]["preco_atacado"] or p["preco_atacado"] < unico[p["sku"]]["preco_atacado"])):
            unico[p["sku"]] = p
    lista = list(unico.values())
    print(f"\nTotal únicos: {len(lista)}")

    # 4) Salva JSON que o site ImportX lê
    OUT_JSON.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5) CSV de variação de preço (para você ver o que subiu/desceu)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sku","nome","preco_ontem","preco_hoje","variacao_R$","variacao_%","status"])
        for p in lista:
            old = antigos.get(p["sku"], {})
            po = old.get("preco_atacado"); pn = p["preco_atacado"]
            if po and pn:
                var = round(pn-po,2); varp = round((pn-po)/po*100,1) if po else 0
                status = "SUBIU" if var>0 else "CAIU" if var<0 else "IGUAL"
            else:
                var=""; varp=""; status="NOVO" if not old else "SEM PRECO"
            w.writerow([p["sku"], p["nome"], po, pn, var, varp, status])
    print(f"Salvo: {OUT_JSON} e {OUT_CSV}")
    return lista

if __name__ == "__main__":
    run()
