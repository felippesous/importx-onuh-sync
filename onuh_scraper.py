"""
ImportX - Robô Onuh V5.4 - LOG AO VIVO
Extrai o preço base da Onuh com precisão (JSON-LD + proximidade visual limpa),
salvando o valor original para que o frontend aplique a margem (+ R$ 30,00).
"""
import json, csv, re, os, time, sys
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from playwright.sync_api import sync_playwright

BASE = "https://catalogo.onuh.com.br"
OUT_JSON = Path("data/produtos.json")
OUT_CSV = Path("data/variacao_precos.csv")
PARTIAL = Path("data/produtos_parcial.json")
COOKIES_FILE = Path("onuh_cookies.json")

MARCAS = [
    "Lattafa", "Afnan", "Armaf", "Al Haramain", "Rasasi", "Maison Alhambra",
    "Al Wataniah", "Fragrance World", "Orientica", "Paris Corner",
    "French Avenue", "Rayhaan", "Maison Asrar", "Arabiyat", "Aurora Scents",
    "Zimaya", "Taif Al Emarat", "Gulf Orchid", "Khadlaj", "Dumont",
    "Bharara", "Amaran", "Le Chameau", "Mawwal", "Xerjoff", "Creed",
    "Medicube", "Celimax", "Jollyour", "Isabelle La Belle"
]


def fix_nome(slug):
    parts = slug.split("/produto/")[-1].split("?")[0].strip("/").split("-")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    nome = " ".join(parts).strip().title()
    nome = re.sub(r"(\d+)Ml\b", r"\1ml", nome)
    nome = (
        nome.replace(" Edp", " EDP")
        .replace(" Edt", " EDT")
        .replace(" Eau De ", " Eau de ")
    )
    return nome


def fix_foto(raw):
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("/_next/image"):
        try:
            q = parse_qs(urlparse(raw).query)
            if "url" in q:
                raw = unquote(q["url"][0])
        except Exception:
            pass
    if raw.startswith("/"):
        raw = BASE + raw
    if "wordmark" in raw or ("logo" in raw.lower() and "produto" not in raw.lower()):
        return ""
    return raw


def extract_jsonld(page):
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
                if not isinstance(it, dict):
                    continue
                t = it.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return it
                if "@graph" in it and isinstance(it["@graph"], list):
                    for g in it["@graph"]:
                        if isinstance(g, dict) and g.get("@type") == "Product":
                            return g
        return {}
    except Exception:
        return {}


def parse_jsonld_price(offers):
    if not offers:
        return None
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None

    for key in ("price", "lowPrice", "highPrice"):
        raw = offers.get(key)
        if raw is not None and raw != "":
            try:
                v = float(str(raw).replace("R$", "").strip().replace(",", "."))
                if 20 <= v <= 10000:
                    return round(v, 2)
            except Exception:
                pass
    return None


def parse_price_text(txt):
    vals = []
    txt = (txt or "").replace("\n", " ")
    for m in re.finditer(r"R\$\s*([\d\.]+,\d{2})", txt):
        try:
            start = max(0, m.start() - 25)
            context = txt[start:m.start()].lower()
            if (
                re.search(r"\d+\s*x\s*(de|sem)?", context)
                or "vezes" in context
                or "frete" in context
                or "mínimo" in context
                or "minimo" in context
                or "economize" in context
                or "desconto" in context
            ):
                continue

            v = float(m.group(1).replace(".", "").replace(",", "."))
            if 20 <= v <= 10000:
                vals.append(round(v, 2))
        except Exception:
            pass
    return vals


def collect_sitemap(page):
    links = set()
    to_visit = [
        BASE + "/sitemap.xml",
        BASE + "/sitemap_index.xml",
        BASE + "/sitemap-0.xml",
    ]
    seen_xml = set()
    while to_visit:
        url = to_visit.pop(0)
        if url in seen_xml:
            continue
        seen_xml.add(url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)
            content = page.content()
            for sm in re.findall(r"<loc>\s*(https://[^<]*sitemap[^<]*)\s*</loc>", content):
                if sm not in seen_xml:
                    to_visit.append(sm)
            for u in re.findall(
                r"<loc>\s*(https://catalogo\.onuh\.com\.br/produto/[^<\s\"']+)\s*</loc>",
                content,
            ):
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
        except Exception:
            pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            viewport={"width": 1366, "height": 900},
            locale="pt-BR",
        )
        if COOKIES_FILE.exists():
            ctx.add_cookies(json.loads(COOKIES_FILE.read_text(encoding="utf-8")))
        else:
            raw = os.environ.get("ONUH_COOKIES_JSON")
            if raw:
                ctx.add_cookies(json.loads(raw))
        page = ctx.new_page()

        links = collect_sitemap(page)
        print(f"Sitemap -> {len(links)} links", flush=True)

        if len(links) < 100:
            print("Sitemap trouxe poucos links, usando fallback por categorias...", flush=True)
            for url in [
                BASE + "/",
                BASE + "/categoria/perfumes-arabes",
                BASE + "/categoria/nicho",
                BASE + "/categoria/k-beauty",
                BASE + "/categoria/skincare",
            ]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(2)
                    for _ in range(6):
                        page.mouse.wheel(0, 4000)
                        time.sleep(1)
                    hrefs = page.evaluate(
                        "() => Array.from(document.querySelectorAll('a[href*=\"/produto/\"]')).map(a=>a.href)"
                    )
                    for h in hrefs:
                        links.add(h.split("?")[0].rstrip("/"))
                except Exception as e:
                    print(f"  Fallback {url}: {e}", flush=True)

        print(f"Total links únicos: {len(links)}", flush=True)
        links = sorted(links)

        done = {}
        if PARTIAL.exists():
            try:
                for p in json.loads(PARTIAL.read_text(encoding="utf-8")):
                    done[p["link_onuh"]] = p
                print(f"Retomando checkpoint: {len(done)} já feitos", flush=True)
            except Exception:
                pass

        produtos = list(done.values())

        for i, link in enumerate(links):
            if link in done:
                continue
            prod = None

            for tentativa in range(2):
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(0.6)
                    jl = extract_jsonld(page)
                    offers = jl.get("offers", {}) if isinstance(jl, dict) else {}
                    nome = jl.get("name") or fix_nome(link)

                    # 1. Tenta preço estruturado (JSON-LD) primeiro
                    preco = parse_jsonld_price(offers)

                    # 2. Fallback: busca visual próxima ao H1 ignorando preços riscados/ocultos
                    if preco is None:
                        try:
                            txt_precos = page.evaluate("""() => {
                                const h1 = document.querySelector('h1');
                                if (!h1) return '';
                                const els = Array.from(document.querySelectorAll('*')).filter(el => {
                                    if (el.children.length !== 0) return false;
                                    const txt = (el.innerText || '').trim();
                                    if (!txt.includes('R$')) return false;
                                    if (el.closest('del, s, strike, header, nav, footer')) return false;
                                    const st = window.getComputedStyle(el);
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    if ((st.textDecorationLine || '').includes('line-through')) return false;
                                    return true;
                                });
                                if (!els.length) return '';
                                const h1Rect = h1.getBoundingClientRect();
                                els.sort((a, b) => {
                                    const aRect = a.getBoundingClientRect();
                                    const bRect = b.getBoundingClientRect();
                                    return Math.abs(aRect.top - h1Rect.bottom) - Math.abs(bRect.top - h1Rect.bottom);
                                });
                                return els.slice(0, 4).map(el => el.innerText.trim()).join(' | ');
                            }""")
                            vals = parse_price_text(txt_precos)
                            if vals:
                                preco = vals[0]
                        except Exception:
                            pass

                    foto = fix_foto(
                        jl.get("image")
                        if isinstance(jl.get("image"), str)
                        else (
                            jl.get("image", [None])[0]
                            if isinstance(jl.get("image"), list)
                            else ""
                        )
                    )
                    if not foto:
                        try:
                            foto = fix_foto(
                                page.evaluate(
                                    """(nome) => {
                                      const imgs = Array.from(document.querySelectorAll('img'));
                                      const hit = imgs.find(im => (im.alt||'').toLowerCase().includes(nome.toLowerCase().split(' ')[0]) && im.src && !im.src.includes('wordmark'));
                                      return hit ? hit.src : '';
                                    }""",
                                    nome,
                                )
                            )
                        except Exception:
                            pass

                    offer_obj = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else {})
                    avail = str(offer_obj.get("availability", "")).lower()
                    if "instock" in avail:
                        em_estoque = True
                    elif "outofstock" in avail:
                        em_estoque = False
                    else:
                        body = page.inner_text("main")
                        em_estoque = ("esgotado" not in body.lower()) and (
                            "indispon" not in body.lower()
                        )

                    categoria = "geral"
                    if isinstance(jl, dict) and jl.get("category"):
                        categoria = str(jl.get("category")).lower().replace(" ", "-")
                    elif isinstance(jl, dict) and jl.get("breadcrumb"):
                        categoria = str(jl.get("breadcrumb"))[:50]

                    marca = next(
                        (m for m in MARCAS if m.lower() in nome.lower()),
                        (nome.split()[0] if nome else ""),
                    )
                    sku = re.sub(r"\W+", "-", nome.lower())[:90]

                    # Salva o preço base puro da Onuh (o index.html soma + R$ 30,00)
                    preco_base = round(preco, 2) if preco else None

                    prod = {
                        "link_onuh": link,
                        "sku": sku,
                        "nome": nome,
                        "marca": marca,
                        "categoria": categoria,
                        "preco_base": preco_base,
                        "preco_final": preco_base,
                        "em_estoque": em_estoque,
                        "foto": foto,
                        "atualizado_em": datetime.now().isoformat(),
                    }
                    break
                except Exception as e:
                    print(f"  Tentativa {tentativa+1} falhou {link}: {e}", flush=True)
                    time.sleep(2)

            if prod:
                produtos.append(prod)
                done[link] = prod

            if len(produtos) % 100 == 0 and produtos:
                PARTIAL.write_text(
                    json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    f"  Checkpoint {len(produtos)}/{len(links)} - último: {produtos[-1]['nome']} - Base Onuh: R$ {produtos[-1].get('preco_base')}",
                    flush=True,
                )

        browser.close()

    sem_preco = sum(1 for p in produtos if not p.get("preco_base"))
    print(
        f"\nTotal: {len(produtos)} | Sem preço: {sem_preco} ({round(sem_preco/max(1,len(produtos))*100,1)}%)",
        flush=True,
    )

    if produtos and sem_preco / len(produtos) > 0.20:
        print(
            "ABORTADO: mais de 20% sem preço - provável cookie expirado. Mantendo produtos.json antigo.",
            flush=True,
        )
        PARTIAL.write_text(
            json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    print(f"Salvando produtos.json com {len(produtos)} produtos", flush=True)
    produtos_publico = [
        {k: v for k, v in pp.items() if k not in ("link_onuh",)} for pp in produtos
    ]
    OUT_JSON.write_text(
        json.dumps(produtos_publico, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if PARTIAL.exists():
        PARTIAL.unlink()

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["link", "nome", "preco_onuh_ontem", "preco_onuh_hoje", "variacao_R$", "status"]
        )
        for p in produtos:
            old = antigos.get(p.get("sku"), {})
            po = old.get("preco_base") if old.get("preco_base") is not None else old.get("preco_final")
            pn = p["preco_base"]
            var = round(pn - po, 2) if po and pn else ""
            status = (
                "NOVO"
                if not old
                else (
                    "SUBIU"
                    if isinstance(var, (int, float)) and var > 0
                    else "CAIU"
                    if isinstance(var, (int, float)) and var < 0
                    else "IGUAL"
                )
            )
            w.writerow([p["link_onuh"], p["nome"], po, pn, var, status])

    print("Salvo produtos.json + variacao_precos.csv", flush=True)


if __name__ == "__main__":
    run()
