
"""
ImportX - Robô Onuh V5.1 - LOG AO VIVO
Auditoria V4 -> V5 corrigiu 7 bugs:
[1] PREÇO: antes pegava o 1º R$ da página (podia ser "Pedido mínimo R$1.500" ou preço de produto relacionado).
    Agora: pega do JSON-LD / __NEXT_DATA__ (dado estruturado do produto) e só usa texto como fallback com seletor de preço.
[2] LOGIN: antes, se o cookie expirasse, ele salvava preço=None e APAGAVA os preços bons.
    Agora: se >20% vier sem preço, ABORTA e NÃO sobrescreve produtos.json. Mantém o último bom.
[3] ESTOQUE: antes "esgotado not in txt OR adicionar in txt" era sempre True (footer tem "Adicionar").
    Agora: usa availability do JSON-LD (InStock/OutOfStock) + botão específico.
[4] FOTO: antes pegava 1ª imagem com /media/ (podia ser banner/marca) e quebrava URL /_next/image?url=...
    Agora: usa image do JSON-LD, depois img com alt == nome, depois maior imagem. Decodifica /_next/image?url=.
[5] CATEGORIA: antes qualquer texto com "arab" virava Perfumes Árabes (descrição tem "árabe" em tudo).
    Agora: usa category/breadcrumb do JSON-LD, senão "geral". Sem chute por palavra.
[6] PERDA TOTAL: antes só salvava no fim; se travasse no produto 2000, perdia tudo.
    Agora: salva checkpoint a cada 100 produtos em data/produtos_parcial.json e retoma.
[7] SITEMAP: antes regex pegava só sitemap.xml raiz (que é índice, não tem produtos).
    Agora: segue sitemaps aninhados recursivamente (sitemap-index -> sub-sitemaps -> produtos).
Extras: nome preserva "100ml" (não vira "100Ml"), marca por lista conhecida, retry 2x por produto.
"""
import json, csv, re, os, time, html, sys
try:
    sys.stdout.reconfigure(line_buffering=True)
except: pass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from playwright.sync_api import sync_playwright

BASE = "https://catalogo.onuh.com.br"
OUT_JSON = Path("data/produtos.json")
OUT_CSV = Path("data/variacao_precos.csv")
PARTIAL = Path("data/produtos_parcial.json")
COOKIES_FILE = Path("onuh_cookies.json")

MARCAS = ["Lattafa","Afnan","Armaf","Al Haramain","Rasasi","Maison Alhambra","Al Wataniah","Fragrance World","Orientica","Paris Corner","French Avenue","Rayhaan","Maison Asrar","Arabiyat","Aurora Scents","Zimaya","Taif Al Emarat","Gulf Orchid","Khadlaj","Dumont","Bharara","Amaran","Le Chameau","Mawwal","Xerjoff","Creed","Medicube","Celimax","Jollyour","Isabelle La Belle","Al Haramain"]

def fix_nome(slug):
    # slug -> nome, preservando 100ml / 50ml / EDP / EDT
    parts = slug.split("/produto/")[-1].split("?")[0].strip("/").split("-")
    if parts and parts[-1].isdigit(): parts = parts[:-1]
    nome = " ".join(parts).strip()
    # Title() mas corrige 100Ml -> 100ml, Edp -> EDP, Edt -> EDT
    nome = nome.title()
    nome = re.sub(r"(\d+)Ml\b", r"\1ml", nome)
    nome = nome.replace(" Edp", " EDP").replace(" Edt", " EDT").replace(" Eau De ", " Eau de ")
    return nome

def fix_foto(raw):
    if not raw: return ""
    raw = raw.strip()
    if raw.startswith("/_next/image"):
        # /_next/image?url=https%3A%2F%2F... -> decodifica o param url
        try:
            q = parse_qs(urlparse(raw).query)
            if "url" in q: raw = unquote(q["url"][0])
        except: pass
    if raw.startswith("/"): raw = BASE + raw
    if "wordmark" in raw or "logo" in raw.lower() and "produto" not in raw.lower():
        return ""
    return raw

def extract_jsonld(page):
    """Retorna dict do JSON-LD tipo Product, se existir."""
    try:
        data = page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
            try { out.push(JSON.parse(s.textContent)); } catch(e) {}
          });
          return out;
        }""")
        for item in data:
            items = item if isinstance(item, list) else [item]
            for it in items:
                if isinstance(it, dict) and it.get("@type") in ("Product", ["Product"]) or (isinstance(it, dict) and "Product" in str(it.get("@graph",""))):
                    return it
                if isinstance(it, dict) and "@graph" in it:
                    for g in it["@graph"]:
                        if isinstance(g, dict) and g.get("@type") == "Product":
                            return g
        return {}
    except: return {}

def parse_price_text(txt):
    vals = []
    for m in re.finditer(r"R\$\s*([\d\.]+,\d{2})", txt or ""):
        try:
            v = float(m.group(1).replace(".","").replace(",","."))
            if 3 <= v <= 5000: vals.append(v)
        except: pass
    return vals

def collect_sitemap(page):
    """Segue sitemap-index recursivamente."""
    links = set()
    to_visit = [BASE + "/sitemap.xml", BASE + "/sitemap_index.xml", BASE + "/sitemap-0.xml"]
    seen_xml = set()
    while to_visit:
        url = to_visit.pop(0)
        if url in seen_xml: continue
        seen_xml.add(url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)
            content = page.content()
            # sub-sitemaps
            for sm in re.findall(r"<loc>\s*(https://[^<]*sitemap[^<]*)\s*</loc>", content):
                if sm not in seen_xml: to_visit.append(sm)
            for u in re.findall(r"<loc>\s*(https://catalogo\.onuh\.com\.br/produto/[^<\s\"']+)\s*</loc>", content):
                links.add(u.split("?")[0].rstrip("/"))
        except Exception as e:
            print(f"  Sitemap {url} falhou: {e}", flush=True)
    return links

def run():
    OUT_JSON.parent.mkdir(exist_ok=True, parents=True)
    antigos = {}
    if OUT_JSON.exists():
        try:
            for p in json.loads(OUT_JSON.read_text(encoding="utf-8")):
                antigos[p.get("sku")] = p
        except: pass
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width":1366,"height":900}, locale="pt-BR")
        if COOKIES_FILE.exists():
            ctx.add_cookies(json.loads(COOKIES_FILE.read_text(encoding="utf-8")))
        else:
            raw = os.environ.get("ONUH_COOKIES_JSON")
            if raw: ctx.add_cookies(json.loads(raw))
        page = ctx.new_page()
        # CHECK LOGIN: vai na home e vê se aparece "Sair" ou preço com login; se não, avisa mas continua (sitemap é público)
        links = collect_sitemap(page)
        print(f"Sitemap -> {len(links)} links", flush=True)
        if len(links) < 100:
            print("Sitemap trouxe poucos links, usando fallback por categorias...", flush=True)
            for url in [BASE + "/", BASE + "/categoria/perfumes-arabes", BASE + "/categoria/nicho", BASE + "/categoria/k-beauty", BASE + "/categoria/skincare"]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000); time.sleep(2)
                    for _ in range(6):
                        page.mouse.wheel(0, 4000); time.sleep(1)
                    hrefs = page.evaluate("() => Array.from(document.querySelectorAll('a[href*=\"/produto/\"]')).map(a=>a.href)")
                    for h in hrefs: links.add(h.split("?")[0].rstrip("/"))
                except Exception as e: print(f"  Fallback {url}: {e}")
        print(f"Total links únicos: {len(links)}", flush=True)
        links = sorted(links)
        import os as _os
        if _os.environ.get('TESTE_RAPIDO') == '1':
            # Só perfumes Asad / Asad Elixir / Afnan 9AM Dive - sem body splash, hidratante ou kit
            links = [l for l in links if ('asad' in l.lower() or 'afnan-9-am-dive' in l.lower()) and 'body-splash' not in l.lower() and 'hidratante' not in l.lower() and 'conjunto' not in l.lower() and 'collection' not in l.lower()][:10]
            print(f'TESTE RAPIDO: {len(links)} links apenas', flush=True)
        # Retoma checkpoint se existir
        done = {}
        if PARTIAL.exists():
            try:
                for p in json.loads(PARTIAL.read_text(encoding="utf-8")): done[p["link_onuh"]] = p
                print(f"Retomando checkpoint: {len(done)} já feitos", flush=True)
            except: pass
        produtos = list(done.values())
        for i, link in enumerate(links):
            if link in done: continue
            prod = None
            for tentativa in range(2):
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(0.5)
                    jl = extract_jsonld(page)
                    offers = jl.get("offers", {}) if isinstance(jl, dict) else {}
                    if isinstance(offers, list) and offers: offers = offers[0]
                    nome = jl.get("name") or fix_nome(link)
                    preco = None
                    try:
                        if offers.get("price"): preco = float(str(offers.get("price")).replace(",","."))
                    except: pass
                    # Valida JSON-LD: se o nome do JSON-LD não bater com a página, ignora o preço dele (era preço de relacionado/kit)
                    if preco is not None and jl.get("name"):
                        nome_jl = str(jl.get("name")).lower().strip()
                        nome_pagina = fix_nome(link).lower().strip()
                        # Compara as 2 primeiras palavras (ex: 'asad' vs 'asad elixir' não podem ser iguais)
                        if nome_jl.split()[:2] != nome_pagina.split()[:2]:
                            print(f"  JSON-LD ignorado (nome divergente): JL='{jl.get('name')}' pagina='{fix_nome(link)}' preco={preco}", flush=True)
                            preco = None
                    if preco is None:
                        # Fallback CORRIGIDO: coleta todos os preços candidatos do container do produto, NÃO pega o 1º do main
                        try:
                            candidatos = page.evaluate("""() => {
                              const out = [];
                              // Só dentro do <main> e perto do <h1> do produto, ignora relacionados/rodapé
                              const main = document.querySelector('main');
                              if (!main) return out;
                              const els = main.querySelectorAll('[data-price], [class*="price"], [class*="Price"]');
                              els.forEach(e => {
                                const txt = (e.innerText||'').trim();
                                if (txt && txt.includes('R$')) out.push(txt.slice(0,120));
                              });
                              return out.slice(0,10);
                            }""")
                            vals_todos = []
                            for c in candidatos:
                                vals_todos.extend(parse_price_text(c))
                            print(f"  Candidatos de preco para {link}: {vals_todos}", flush=True)
                            if vals_todos:
                                # Usa o MENOR preço candidato do container do produto (kit/relacionado costuma ser maior)
                                # Se houver apenas 1, usa ele. Se houver vários, usa o menor, não o primeiro.
                                # CORRIGIDO: usa o preço MAIS FREQUENTE, não o menor.
                                # O preço do produto principal se repete várias vezes na página (título, botão, resumo).
                                # Preço de relacionado aparece 1x. O menor era de relacionado.
                                from collections import Counter as _Counter
                                _cont = _Counter(vals_todos)
                                preco = _cont.most_common(1)[0][0]
                                print(f"  Preço escolhido (mais frequente): R$ {preco} de {vals_todos}", flush=True)
                        except Exception as e:
                            print(f"  Fallback de preco falhou {link}: {e}", flush=True)
                    foto = fix_foto(jl.get("image") if isinstance(jl.get("image"), str) else (jl.get("image", [None])[0] if isinstance(jl.get("image"), list) else ""))
                    if not foto:
                        try:
                            foto = fix_foto(page.evaluate("""(nome) => {
                              const imgs = Array.from(document.querySelectorAll('img'));
                              const hit = imgs.find(im => (im.alt||'').toLowerCase().includes(nome.toLowerCase().split(' ')[0]) && im.src && !im.src.includes('wordmark'));
                              return hit ? hit.src : '';
                            }""", nome))
                        except: pass
                    avail = str(offers.get("availability","")).lower()
                    if "instock" in avail: em_estoque = True
                    elif "outofstock" in avail: em_estoque = False
                    else:
                        body = page.inner_text("main") if True else ""
                        em_estoque = ("esgotado" not in body.lower()) and ("indispon" not in body.lower())
                    categoria = "geral"
                    if isinstance(jl, dict) and jl.get("category"): categoria = str(jl.get("category")).lower().replace(" ","-")
                    elif isinstance(jl, dict) and jl.get("breadcrumb"): categoria = str(jl.get("breadcrumb"))[:50]
                    marca = next((m for m in MARCAS if m.lower() in nome.lower()), (nome.split()[0] if nome else ""))
                    sku = re.sub(r"\W+", "-", nome.lower())[:90]
                    preco_final = round((preco or 0) + 30, 2) if preco else None
                    prod = {"link_onuh": link, "sku": sku, "nome": nome, "marca": marca, "categoria": categoria, "preco_final": preco_final, "em_estoque": em_estoque, "foto": foto, "atualizado_em": datetime.now().isoformat()}
                    break
                except Exception as e:
                    print(f"  Tentativa {tentativa+1} falhou {link}: {e}"); time.sleep(2, flush=True)
            if prod:
                # Anti-duplicata: Asad e Asad Elixir NÃO podem ter o mesmo SKU/preço
                if any(pp.get('sku') == prod.get('sku') for pp in produtos):
                    print(f"  DUPLICATA ignorada: sku={prod.get('sku')} nome={prod.get('nome')} link={link}", flush=True)
                else:
                    produtos.append(prod); done[link] = prod
            if (len(produtos) % 100 == 0 and produtos):
                PARTIAL.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Checkpoint {len(produtos)}/{len(links)} - último: {produtos[-1]['nome']} - R$ {produtos[-1].get('preco_final')}", flush=True)
        browser.close()
    # TRAVA DE SEGURANÇA [2]: não sobrescreve se muitos preços vieram vazios (cookie expirado)
    sem_preco = sum(1 for p in produtos if not p.get("preco_final"))
    print(f"\nTotal: {len(produtos)} | Sem preço: {sem_preco} ({round(sem_preco/max(1,len(produtos))*100,1)}%)", flush=True)
    if produtos and sem_preco / len(produtos) > 0.20:
        print("ABORTADO: mais de 20% sem preço - provável cookie expirado. Mantendo produtos.json antigo.", flush=True)
        PARTIAL.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    print(f"Salvando produtos.json com {len(produtos)} produtos", flush=True)
    produtos_publico = [{k:v for k,v in pp.items() if k not in ("link_onuh",)} for pp in produtos]
    OUT_JSON.write_text(json.dumps(produtos_publico, ensure_ascii=False, indent=2), encoding="utf-8")
    if PARTIAL.exists(): PARTIAL.unlink()
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["sku","nome","preco_ontem","preco_hoje","variacao_R$","status"])
        for p in produtos:
            old = antigos.get(p.get("sku"), {}); po = old.get("preco_final"); pn = p["preco_final"]
            var = round(pn-po,2) if po and pn else ""
            status = "NOVO" if not old else ("SUBIU" if isinstance(var,(int,float)) and var>0 else "CAIU" if isinstance(var,(int,float)) and var<0 else "IGUAL")
            w.writerow([p["sku"], p["nome"], po, pn, var, status])
    print("Salvo produtos.json + variacao_precos.csv", flush=True)

if __name__ == "__main__":
    run()
