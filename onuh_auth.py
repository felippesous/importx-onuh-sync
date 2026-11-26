"""Autenticacao e leitura basica do catalogo Onuh.

Usado por testar_login.py e onuh_scraper.py.
NUNCA imprime valores de cookies, tokens ou senhas.
"""
import json, os, re, time
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

BASE = "https://catalogo.onuh.com.br"
PRODUTO_TESTE = BASE + "/produto/lattafa-asad-edp-100ml"
COOKIE_LOGIN = "__Secure-better-auth.session_token"
ESTADO_RENOVADO = Path("data/.onuh_auth_state.json")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def normalizar_preco(txt):
    """Converte 'R$ 164,99' ou '164.99' em float. Ignora lixo."""
    if not txt:
        return None
    txt = str(txt).replace("\xa0", " ")
    m = re.search(r"(\d[\d\.]*,\d{2})", txt)
    if not m:
        m = re.search(r"\d+(?:\.\d+)?", txt)
    if not m:
        return None
    try:
        valor = float(m.group(1).replace(".", "").replace(",", "."))
    except Exception:
        return None
    return valor if 1 <= valor <= 10000 else None


def _carregar_objeto(nome, raw):
    try:
        return json.loads(raw)
    except Exception as exc:
        print(f"  Aviso: {nome} nao e JSON valido ({exc})", flush=True)
        return None


def carregar_estado():
    """Monta um storage_state do Playwright a partir de todas as fontes disponiveis.

    Prioridade: estado renovado > ONUH_STORAGE_STATE_JSON > onuh_storage.json >
    ONUH_STORAGE_JSON > ONUH_COOKIES_JSON > onuh_cookies.json. Cookies de todas
    as fontes sao mesclados (o login da Onuh usa cookie + localStorage).
    """
    brutos = []
    if ESTADO_RENOVADO.exists():
        brutos.append(("estado renovado", ESTADO_RENOVADO.read_text(encoding="utf-8")))
    for env in ("ONUH_STORAGE_STATE_JSON", "ONUH_STORAGE_JSON", "ONUH_COOKIES_JSON"):
        valor = os.environ.get(env)
        if valor and valor.strip():
            brutos.append((env, valor))
    for arquivo in ("onuh_storage.json", "onuh_cookies.json"):
        p = Path(arquivo)
        if p.exists():
            brutos.append((arquivo, p.read_text(encoding="utf-8")))

    cookies, origins = [], []
    vistos = set()
    for nome, raw in brutos:
        obj = _carregar_objeto(nome, raw)
        if obj is None:
            continue
        itens = obj if isinstance(obj, list) else (obj.get("cookies", []) if isinstance(obj, dict) else [])
        for cookie in itens or []:
            if not isinstance(cookie, dict) or not cookie.get("name"):
                continue
            if "value" not in cookie:
                continue
            # descarta cookie vencido (evita testar um login que já morreu)
            exp = cookie.get("expires")
            if exp not in (None, -1):
                try:
                    if float(exp) < time.time():
                        continue
                except Exception:
                    pass
            chave = (cookie.get("name"), cookie.get("domain", ""), cookie.get("path", "/"))
            if chave in vistos:
                continue
            vistos.add(chave)
            cookies.append(cookie)
        if isinstance(obj, dict):
            for origin in obj.get("origins", []) or []:
                if not isinstance(origin, dict) or not origin.get("origin"):
                    continue
                existe = next((o for o in origins if o.get("origin") == origin["origin"]), None)
                if existe is None:
                    origins.append(origin)
                else:
                    locais = {i.get("name"): i for i in existe.get("localStorage", [])}
                    for item in origin.get("localStorage", []) or []:
                        if isinstance(item, dict) and item.get("name"):
                            locais[item["name"]] = item
                    existe["localStorage"] = list(locais.values())

    estado = {"cookies": cookies, "origins": origins}
    tem_login = any(c.get("name") == COOKIE_LOGIN for c in cookies)
    print(f"Auth: {len(cookies)} cookie(s), {len(origins)} origin(s) | "
          f"cookie de sessao: {'sim' if tem_login else 'NAO'}", flush=True)
    return estado


def criar_contexto(browser, estado):
    """Cria o contexto já com cookies E localStorage aplicados antes de qualquer pagina."""
    return browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 900},
        locale="pt-BR",
        storage_state=estado,
    )


def extrair_preco(page):
    """Preço principal do produto: dentro do artigo, ao lado do H1 (não relacionados)."""
    try:
        bruto = page.evaluate("""() => {
          const art = document.querySelector('article[data-testid="pagina-produto"]');
          if (!art) return '';
          const h1 = art.querySelector('h1');
          const sec = h1 ? (h1.closest('section') || h1.parentElement) : null;
          let txt = sec ? (sec.innerText || '') : '';
          // Ignora a linha de pedido minimo (R$ 1.500,00), que nao e preco do produto
          txt = txt.split(/\\n/).filter(l => !/m[ií]nimo/i.test(l)).join('\\n');
          let m = txt.match(/R\\$\\s*([\\d.]+,\\d{2})/);
          if (m) return m[0];
          const antes = (art.innerText || '').split(/Sobre\\s/i)[0]
            .split(/\\n/).filter(l => !/m[ií]nimo/i.test(l)).join('\\n');
          m = antes.match(/R\\$\\s*([\\d.]+,\\d{2})/);
          return m ? m[0] : '';
        }""")
    except Exception:
        return None
    return normalizar_preco(bruto)


def extrair_estoque(page):
    try:
        return page.evaluate("""() => {
          const art = document.querySelector('article[data-testid="pagina-produto"]');
          if (!art) return true;
          const txt = (art.innerText || '').toLowerCase();
          if (/esgotad|indispon/.test(txt)) return false;
          return /em estoque|comprar/.test(txt);
        }""")
    except Exception:
        return True


def nome_usuario(page):
    """Nome do lojista no cabecalho, se estiver logado (link 'Minha conta')."""
    try:
        return page.evaluate("""() => {
          const a = document.querySelector('a[title^="Minha conta"]');
          if (!a) return '';
          const direto = (a.innerText || '').trim();
          if (direto) return direto;
          const partes = Array.from(a.querySelectorAll('span'))
            .map(s => (s.innerText || '').trim()).filter(Boolean);
          return partes.length ? partes[partes.length - 1] : '';
        }""")
    except Exception:
        return ""


def fazer_login(ctx, page):
    """Renova o login via e-mail/senha quando os secrets estao disponiveis."""
    email = (os.environ.get("ONUH_EMAIL") or "").strip()
    senha = os.environ.get("ONUH_PASSWORD") or ""
    if not email or not senha:
        return False
    print("Cookie invalido: tentando login com ONUH_EMAIL / ONUH_PASSWORD...", flush=True)
    try:
        page.goto(BASE + "/entrar", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        page.fill("#campo-email", email)
        page.fill("#campo-senha", senha)
        page.get_by_role("button", name="Entrar", exact=True).click()
        page.wait_for_timeout(3000)
        if "/entrar" in page.url:
            print("Login nao concluido (pode exigir codigo por e-mail).", flush=True)
            return False
        novo = ctx.storage_state()
        ESTADO_RENOVADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO_RENOVADO.write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Login renovado com sucesso (estado salvo fora do git).", flush=True)
        return True
    except Exception as exc:
        print(f"Falha no login automatico: {type(exc).__name__}: {exc}", flush=True)
        return False


def verificar_login(page, ctx=None):
    """Teste real de login: checa a home e o preco de um produto conhecido."""
    res = {"ok": False, "usuario": "", "preco_teste": None, "motivo": ""}
    try:
        resp = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1800)
        body = page.inner_text("body").lower()
        res["usuario"] = nome_usuario(page)
        visitante = ("entrar para ver o preco" in body or
                     "entrar para ver o preço" in body)
        if resp is None or resp.status >= 400:
            res["motivo"] = f"home retornou status {getattr(resp, 'status', '?')}"
            return res
        if visitante:
            res["motivo"] = "home mostra 'Entrar para ver o preço' (sessao de visitante)"
            # ainda tenta o produto, pode ser cache da home
    except Exception as exc:
        res["motivo"] = f"falha ao abrir a home: {type(exc).__name__}: {exc}"
        return res

    try:
        page.goto(PRODUTO_TESTE, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_selector('article[data-testid="pagina-produto"]', timeout=15000)
        page.wait_for_timeout(700)
        preco = extrair_preco(page)
        res["preco_teste"] = preco
        if preco is not None:
            res["ok"] = not visitante or bool(res["usuario"])
            res["motivo"] = "" if res["ok"] else "preco visivel, mas a home indicou visitante"
            return res
        res["motivo"] = res["motivo"] or "produto de teste nao mostrou preco de lojista"
    except Exception as exc:
        res["motivo"] = res["motivo"] or f"falha no produto de teste: {type(exc).__name__}: {exc}"

    if ctx is not None and fazer_login(ctx, page):
        return verificar_login(page, ctx=None)
    return res


def fix_foto(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
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
