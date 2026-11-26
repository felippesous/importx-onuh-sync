"""
ImportX - Robo Onuh V6 - login confiavel + precos corretos

Auditoria V5 -> V6 corrigiu:
[1] LOGIN: o teste antigo procurava palavras do cabecalho e sempre acusava
    'cookie expirado' (a home logada nao tem essas palavras). Agora valida o
    preco de lojista num produto real e renova o login via e-mail/senha.
[2] SITEMAP: o conteudo renderizado retornava o visualizador XML do Chromium
    e nao trazia links. Agora le o XML bruto com ctx.request.get().
[3] PRECO: o fallback pegava precos de produtos relacionados. Agora le o
    preco dentro de article[data-testid="pagina-produto"], ao lado do H1.
[4] JSON-LD: precedencia do OR fazia retornar o no errado do @graph.
[5] TESTE RAPIDO: sobrescrevia o CSV de producao e comparava com produtos_teste.
[6] CHECKPOINT: gravava produtos sem preco e os reaproveitava na proxima rodada.
[7] o retry chamava sleep com um argumento invalido e estourava TypeError.
[8] STORAGE: localStorage era apenas impresso, nunca aplicado.
"""
import json, csv, re, os, sys, time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from playwright.sync_api import sync_playwright

from onuh_auth import (
    BASE, carregar_estado, criar_contexto, verificar_login,
    extrair_preco, extrair_estoque, fix_foto, normalizar_preco,
)

TESTE_RAPIDO = os.environ.get("TESTE_RAPIDO") == "1"
OUT_JSON = Path("data/produtos_teste.json") if TESTE_RAPIDO else Path("data/produtos.json")
OUT_CSV = Path("data/variacao_teste.csv") if TESTE_RAPIDO else Path("data/variacao_precos.csv")
ANTIGOS_JSON = Path("data/produtos.json")     # comparacao sempre contra o catalogo real
PARTIAL = (Path("data/produtos_parcial_teste.json") if TESTE_RAPIDO
           else Path("data/produtos_parcial.json"))

TESTE_LINKS = {
    BASE + "/produto/lattafa-asad-edp-100ml",
    BASE + "/produto/lattafa-asad-elixir-edp-100ml",
    BASE + "/produto/afnan-9-am-dive-edp-100ml",
}

MARCAS = [
    "Lattafa", "Afnan", "Armaf", "Al Haramain", "Rasasi", "Maison Alhambra",
    "Al Wataniah", "Fragrance World", "Orientica", "Paris Corner", "French Avenue",
    "Rayhaan", "Maison Asrar", "Arabiyat", "Aurora Scents", "Zimaya", "Taif Al Emarat",
    "Gulf Orchid", "Khadlaj", "Dumont", "Bharara", "Amaran", "Le Chameau", "Mawwal",
    "Xerjoff", "Creed", "Medicube", "Celimax", "Jollyour", "Isabelle La Belle",
]


def fix_nome(slug):
    partes = slug.split("/produto/")[-1].split("?")[0].strip("/").split("-")
    if partes and partes[-1].isdigit():
        partes = partes[:-1]
    nome = " ".join(partes).strip().title()
    nome = re.sub(r"(\d+)Ml\b", r"\1ml", nome)
    nome = nome.replace(" Edp", " EDP").replace(" Edt", " EDT").replace(" Eau De ", " Eau de ")
    return nome


def limpar_nome(nome):
    nome = re.sub(r"\s+", " ", str(nome or "")).strip()
    # JSON-LD as vezes repete a palavra ("Asad Elixir Elixir 100 ml")
    nome = re.sub(r"\b(\w+)\s+\1\b", r"\1", nome, flags=re.IGNORECASE)
    nome = re.sub(r"\bAl Hambra\b", "Alhambra", nome, flags=re.IGNORECASE)
    # e repete a marca inteira ("Mercedes Benz Mercedes Benz Select EDT")
    nome = re.sub(r"\b((?:\w+\s+){1,3}?)\1\b", r"\1", nome, flags=re.IGNORECASE)
    return nome


def normalizar_categoria(cat):
    if not cat:
        return "geral"
    partes = [p.strip() for p in str(cat).split(">") if p.strip()]
    if not partes:
        return "geral"
    alvo = next((p for p in partes if "arab" in p.lower()), None)
    if alvo is None:
        alvo = partes[1] if len(partes) > 1 else partes[0]
    slug = re.sub(r"[^a-z0-9]+", "-", alvo.lower()).strip("-")
    return slug or "geral"


def extrair_jsonld(page):
    """Retorna o no Product do JSON-LD (inclusive dentro de @graph)."""
    try:
        dados = page.evaluate("""() => {
          const out = [];
          document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
            try { out.push(JSON.parse(s.textContent)); } catch (e) {}
          });
          return out;
        }""")
        for item in dados:
            nos = item if isinstance(item, list) else [item]
            for no in nos:
                if not isinstance(no, dict):
                    continue
                if "Product" in str(no.get("@type", "")):
                    return no
                grafo = no.get("@graph")
                if isinstance(grafo, list):
                    for filho in grafo:
                        if isinstance(filho, dict) and "Product" in str(filho.get("@type", "")):
                            return filho
        return {}
    except Exception:
        return {}


def collect_sitemap(ctx):
    """Le sitemap.xml cru (nao o visualizador XML do navegador) e segue index."""
    links, fila, vistos = set(), [BASE + "/sitemap.xml"], set()
    while fila:
        url = fila.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        try:
            resp = ctx.request.get(url, timeout=45000)
            if resp.status >= 400:
                print(f"  Sitemap {url}: HTTP {resp.status}", flush=True)
                continue
            xml = resp.text()  # XML bruto: o HTML renderizado nao serve aqui
            for sub in re.findall(r"<loc>\s*(https://[^<]*sitemap[^<]*)\s*</loc>", xml, re.I):
                if sub not in vistos:
                    fila.append(sub)
            for link in re.findall(
                r"<loc>\s*(https://catalogo\.onuh\.com\.br/produto/[^<\s\"']+)\s*</loc>",
                xml, re.I,
            ):
                links.add(link.split("?")[0].rstrip("/"))
        except Exception as exc:
            print(f"  Sitemap {url} falhou: {type(exc).__name__}: {exc}", flush=True)
    return links


def dados_produto(page, link):
    jl = extrair_jsonld(page)
    preco = extrair_preco(page)

    if preco is None:
        ofertas = jl.get("offers")
        if isinstance(ofertas, list) and ofertas:
            ofertas = ofertas[0]
        if isinstance(ofertas, dict):
            preco = normalizar_preco(str(ofertas.get("price") or ""))

    h1 = ""
    try:
        h1 = page.locator('article[data-testid="pagina-produto"] h1').first.inner_text(timeout=3000)
    except Exception:
        pass
    nome = limpar_nome(jl.get("name") or h1 or fix_nome(link))

    imagem = jl.get("image")
    if isinstance(imagem, list) and imagem:
        imagem = imagem[0]
    elif not isinstance(imagem, str):
        imagem = ""
    foto = fix_foto(imagem)
    if not foto:
        try:
            foto = fix_foto(page.evaluate("""() => {
              const art = document.querySelector('article[data-testid="pagina-produto"]');
              const img = art ? art.querySelector('img') : null;
              return img ? img.src : '';
            }"""))
        except Exception:
            pass

    categoria = normalizar_categoria(jl.get("category") or "")
    marca = next((m for m in MARCAS if m.lower() in nome.lower()), nome.split()[0] if nome else "")
    sku = re.sub(r"\W+", "-", nome.lower()).strip("-")[:90]
    em_estoque = extrair_estoque(page)
    preco_final = round(preco + 30, 2) if preco is not None else None

    # O index.html da ImportX tem CFG.margem = 30 e soma sozinho no preco_base.
    # Por isso o JSON publico leva o preco BRUTO em preco_base. preco_final
    # fica apenas como referencia para outros consumidores (ja com a margem).
    return {
        "link_onuh": link, "sku": sku, "nome": nome, "marca": marca,
        "categoria": categoria, "preco_base": preco, "preco_final": preco_final,
        "em_estoque": em_estoque, "foto": foto,
        "atualizado_em": datetime.now().isoformat(),
    }


def run():
    for p in (OUT_JSON.parent, PARTIAL.parent):
        p.mkdir(exist_ok=True, parents=True)

    antigos = {}
    if ANTIGOS_JSON.exists():
        try:
            for p in json.loads(ANTIGOS_JSON.read_text(encoding="utf-8")):
                if p.get("sku"):
                    antigos[p["sku"]] = p
        except Exception:
            pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        estado = carregar_estado()
        ctx = criar_contexto(browser, estado)
        page = ctx.new_page()

        # TESTE REAL DE LOGIN: falha rapido, sem gerar precos de visitante
        resultado = verificar_login(page, ctx)
        if resultado["ok"]:
            quem = resultado["usuario"] or "lojista"
            print(f"LOGIN Onuh: LOGADO como {quem} | produto-teste R$ {resultado['preco_teste']:.2f}",
                  flush=True)
        else:
            print(f"LOGIN Onuh: FALHOU - {resultado['motivo']}", flush=True)
            print("Acao: rode salvar_login.py e atualize ONUH_STORAGE_STATE_JSON, "
                  "ou configure ONUH_EMAIL/ONUH_PASSWORD.", flush=True)
            browser.close()
            sys.exit(1)

        links = collect_sitemap(ctx)
        print(f"Sitemap -> {len(links)} links", flush=True)
        if len(links) < 100:
            print("Sitemap com poucos links; usando fallback por categorias...", flush=True)
            for url in [BASE + "/", BASE + "/categoria/perfumes-arabes",
                        BASE + "/categoria/nicho", BASE + "/categoria/k-beauty",
                        BASE + "/categoria/skincare"]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    for _ in range(6):
                        page.mouse.wheel(0, 4000)
                        page.wait_for_timeout(700)
                    hrefs = page.evaluate(
                        '() => Array.from(document.querySelectorAll(a[href*="/produto/"])).map(a=>a.href)'
                    )
                    for href in hrefs:
                        links.add(href.split("?")[0].rstrip("/"))
                except Exception as exc:
                    print(f"  Fallback {url}: {type(exc).__name__}: {exc}", flush=True)

        if TESTE_RAPIDO:
            links = sorted(l for l in links if l in TESTE_LINKS)
            print(f"TESTE RAPIDO: {len(links)} links de teste", flush=True)
        else:
            links = sorted(links)
        print(f"Total links unicos: {len(links)}", flush=True)

        done = {}
        if PARTIAL.exists():
            try:
                for p in json.loads(PARTIAL.read_text(encoding="utf-8")):
                    # Nao retoma item sem preco: isso era o que travava os precos
                    if p.get("link_onuh") and p.get("preco_final") is not None:
                        done[p["link_onuh"]] = p
                print(f"Retomando checkpoint: {len(done)} ja feitos", flush=True)
            except Exception:
                pass

        produtos = list(done.values())
        for link in links:
            if link in done:
                continue
            prod = None
            for tentativa in range(2):
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_selector('article[data-testid="pagina-produto"]', timeout=12000)
                    except Exception:
                        pass
                    page.wait_for_timeout(500)
                    prod = dados_produto(page, link)
                    break
                except Exception as exc:
                    print(f"  Tentativa {tentativa + 1} falhou {link}: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    time.sleep(2)

            if prod:
                if any(p.get("sku") == prod.get("sku") for p in produtos):
                    print(f"  DUPLICATA ignorada: {prod['nome']} ({link})", flush=True)
                else:
                    produtos.append(prod)
                    done[link] = prod
            if produtos and len(produtos) % 100 == 0:
                PARTIAL.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Checkpoint {len(produtos)}/{len(links)} - "
                      f"ultimo: {produtos[-1]['nome']} - R$ {produtos[-1].get('preco_final')}", flush=True)
        browser.close()

    sem_preco = sum(1 for p in produtos if p.get("preco_final") is None)
    total = len(produtos)
    pct = round(sem_preco / max(1, total) * 100, 1)
    print(f"\nTotal: {total} | Sem preco: {sem_preco} ({pct}%)", flush=True)
    if total and sem_preco / total > 0.20:
        print("ABORTADO: mais de 20% sem preco. Produtos.json antigo foi mantido "
              "e o checkpoint invalido nao sera reaproveitado.", flush=True)
        if PARTIAL.exists():
            PARTIAL.rename(PARTIAL.with_suffix(".invalido.json"))
        sys.exit(2)

    print(f"Salvando {OUT_JSON} com {total} produtos", flush=True)
    publico = [{k: v for k, v in p.items() if k != "link_onuh"} for p in produtos]
    OUT_JSON.write_text(json.dumps(publico, ensure_ascii=False, indent=2), encoding="utf-8")
    if PARTIAL.exists():
        PARTIAL.unlink()

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "nome", "preco_ontem", "preco_hoje", "variacao_R$", "status"])
        for p in produtos:
            anterior = antigos.get(p.get("sku"), {})
            antes = anterior.get("preco_final")
            if antes is None and anterior.get("preco_base") is not None:
                antes = round(anterior["preco_base"] + 30, 2)
            agora = p["preco_final"]
            variacao = round(agora - antes, 2) if antes and agora else ""
            status = ("NOVO" if not anterior else
                      "SUBIU" if isinstance(variacao, (int, float)) and variacao > 0 else
                      "CAIU" if isinstance(variacao, (int, float)) and variacao < 0 else "IGUAL")
            w.writerow([p["sku"], p["nome"], antes, agora, variacao, status])
    print(f"Salvo {OUT_JSON} + {OUT_CSV}", flush=True)


if __name__ == "__main__":
    run()
