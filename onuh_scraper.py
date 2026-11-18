
"""
ImportX - Robô Onuh V3 - NOME PELO LINK (definitivo)
Mudança: em vez de tentar adivinhar o nome no card da lista,
ele entra na página de cada produto e pega H1 + preço de lá.
Mais lento, mas 100% certo.
"""
import json, csv, re, os, time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://catalogo.onuh.com.br"
OUT_JSON = Path("data/produtos.json")
OUT_CSV = Path("data/variacao_precos.csv")
COOKIES_FILE = Path("onuh_cookies.json")
JUNK = {"ver detalhes","esgotado","lançamento","lancamento","mais vendidos","adicionar","comprar","ver mais","novo","promoção","promocao","indisponível","indisponivel"}

def clean_name(txt):
    if not txt: return ""
    txt = txt.strip()
    if txt.lower() in JUNK: return ""
    if len(txt) < 3: return ""
    return txt

def parse_prices(page_text):
    # Pega todos os R$ e retorna o maior valor plausível (preço, não parcela de 2,50)
    vals = []
    for m in re.finditer(r"R\$\s*([\d\.]+,\d{2})", page_text):
        v = float(m.group(1).replace(".","").replace(",","."))
        if 3 <= v <= 5000:
            vals.append(v)
    return vals

def run():
    OUT_JSON.parent.mkdir(exist_ok=True, parents=True)
    antigos = {}
    if OUT_JSON.exists():
        try:
            for p in json.loads(OUT_JSON.read_text(encoding="utf-8")):
                antigos[p.get("link_onuh")] = p
        except: pass

    links = {}  # link -> categoria
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width":1366,"height":900}, locale="pt-BR")
        if COOKIES_FILE.exists():
            ctx.add_cookies(json.loads(COOKIES_FILE.read_text(encoding="utf-8")))
        else:
            raw = os.environ.get("ONUH_COOKIES_JSON")
            if raw: ctx.add_cookies(json.loads(raw))
        page = ctx.new_page()

        # PASSO 1: Coletar links de produtos (rápido)
        # Página principal já tem Mais Vendidos + Lançamentos, depois categorias
        urls = [BASE + "/", BASE + "/categoria/perfumes-arabes", BASE + "/categoria/nicho", BASE + "/categoria/k-beauty", BASE + "/categoria/skincare", BASE + "/categoria/body-splash", BASE + "/categoria/coffret", BASE + "/categoria/miniaturas", BASE + "/categoria/openbox", BASE + "/categoria/cuidados-corporais", BASE + "/categoria/cabelos", BASE + "/categoria/kids", BASE + "/categoria/designer"]
        for url in urls:
            try:
                print(f"Coletando links: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                for _ in range(10):
                    page.mouse.wheel(0, 4000); time.sleep(1)
                    try:
                        btn = page.locator("text=Carregar mais").first
                        if btn.is_visible(): btn.click(); time.sleep(2)
                    except: pass
                hrefs = page.evaluate("() => Array.from(document.querySelectorAll('a[href*=\"/produto/\"]')).map(a=>a.href)")
                for h in hrefs:
                    if h not in links: links[h] = url
                print(f"  Total links até agora: {len(links)}")
            except Exception as e:
                print(f"  Erro {url}: {e}")

        print(f"\nTotal links únicos: {len(links)} - Agora visitando cada produto...")

        # PASSO 2: Visitar cada produto e pegar nome/preço certos
        produtos = []
        for i, (link, cat_url) in enumerate(links.items()):
            try:
                page.goto(link, wait_until="domcontentloaded", timeout=30000)
                time.sleep(0.6)
                # Nome: PEGA DO LINK - é o mais confiável!
                # Ex: /produto/afnan-discovery-set-5-unidades -> "Afnan Discovery Set 5 Unidades"
                # H1 do site vem errado ("Ver detalhes"), então NÃO usa H1.
                slug_parts = link.split("/produto/")[-1].split("?")[0].split("-")
                if slug_parts and slug_parts[-1].isdigit(): slug_parts = slug_parts[:-1]
                nome = " ".join(slug_parts).title().strip()
                # Tenta H1 só se slug falhar
                if len(nome) < 5:
                    try: nome = page.locator("h1").first.inner_text(timeout=2000).strip()
                    except: pass
                # Preço: procura no texto da página
                txt = page.inner_text("body") if True else ""
                vals = parse_prices(txt)
                preco = vals[0] if vals else None
                # Foto
                foto = ""
                try: foto = page.locator("img").first.get_attribute("src") or ""
                except: pass
                # Estoque
                em_estoque = "esgotado" not in txt.lower() or "adicionar" in txt.lower()
                # Categoria pelo slug / url
                categoria = "geral"
                for c in ["arabes","nicho","k-beauty","skincare","body-splash","coffret","miniaturas","openbox"]:
                    if c in cat_url: categoria = c
                sku = re.sub(r"\W+", "-", nome.lower())[:90]
                produtos.append({"sku": sku, "nome": nome, "marca": nome.split()[0] if nome else "", "categoria": categoria, "preco_atacado": preco, "em_estoque": em_estoque, "foto": foto, "link_onuh": link, "atualizado_em": datetime.now().isoformat()})
                if (i+1) % 100 == 0: print(f"  {i+1}/{len(links)} - último: {nome} - R$ {preco}")
            except Exception as e:
                print(f"  Erro produto {link}: {e}")
                continue
        browser.close()

    print(f"\nTotal final: {len(produtos)}")
    OUT_JSON.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["link","nome","preco_ontem","preco_hoje","variacao_R$","status"])
        for p in produtos:
            old = antigos.get(p["link_onuh"], {})
            po = old.get("preco_atacado"); pn = p["preco_atacado"]
            var = round(pn-po,2) if po and pn else ""
            status = "NOVO" if not old else ("SUBIU" if isinstance(var,(int,float)) and var>0 else "CAIU" if isinstance(var,(int,float)) and var<0 else "IGUAL")
            w.writerow([p["link_onuh"], p["nome"], po, pn, var, status])
    print("Salvo produtos.json + variacao_precos.csv")

if __name__ == "__main__":
    run()
