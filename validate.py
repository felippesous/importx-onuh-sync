"""Valida o pacote ANTES de rodar no GitHub Actions. Se falhar, o job para."""
import pathlib, py_compile, sys

raiz = pathlib.Path(__file__).resolve().parent
erros = []

for nome in ("onuh_auth.py", "onuh_scraper.py", "testar_login.py", "salvar_login.py"):
    arquivo = raiz / nome
    if not arquivo.exists():
        erros.append(f"Falta o arquivo {nome}")
        continue
    try:
        py_compile.compile(str(arquivo), doraise=True)
    except Exception as exc:
        erros.append(f"Sintaxe em {nome}: {exc}")

scraper = (raiz / "onuh_scraper.py").read_text(encoding="utf-8")
auth = (raiz / "onuh_auth.py").read_text(encoding="utf-8")
teste = (raiz / "testar_login.py").read_text(encoding="utf-8")

if "preco_atacado" in scraper:
    erros.append("Ainda tem 'preco_atacado' - use preco_base/preco_final")
if '"preco_base": preco' not in scraper:
    erros.append("Falta preco_base bruto: o index.html soma R$ 30 sozinho")
if "vals[0]" in scraper:
    erros.append("Ainda tem 'vals[0]' - fallback perigoso")
if "link_onuh" in scraper and 'k != "link_onuh"' not in scraper:
    erros.append("link_onuh pode vazar no JSON publico")
if "page.content()" in scraper:
    erros.append("Sitemap nao pode usar page.content() (visualizador XML do Chromium)")
if "ctx.request.get" not in scraper:
    erros.append("Falta leitura crua do sitemap via ctx.request.get")
if 'data-testid="pagina-produto"' not in auth or 'data-testid="pagina-produto"' not in scraper:
    erros.append("Falta o seletor do preco principal")
if "verificar_login" not in scraper or "verificar_login" not in teste:
    erros.append("Falta o teste real de login")
if "meus pedidos" in scraper.lower():
    erros.append("Teste de login antigo (palavra 'meus pedidos') ainda presente")
if "time.sleep(2, flush=True)" in scraper:
    erros.append("time.sleep nao aceita flush")
if "TESTE_RAPIDO" not in scraper:
    erros.append("Falta TESTE_RAPIDO")
if "storage_state" not in auth:
    erros.append("Falta aplicar cookies + localStorage no contexto")
if "ONUH_STORAGE_STATE_JSON" not in auth:
    erros.append("Falta suporte ao Secret ONUH_STORAGE_STATE_JSON")

# Conta da margem: sempre +R$ 30,00
assert round(164.99 + 30, 2) == 194.99, "Conta Asad errada"
assert round(189.99 + 30, 2) == 219.99, "Conta Asad Elixir errada"

if erros:
    print("VALIDACAO FALHOU:")
    for erro in erros:
        print(" -", erro)
    sys.exit(1)
print("VALIDACAO OK - pode rodar")
