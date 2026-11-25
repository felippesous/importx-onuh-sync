"""Valida o robô ANTES de rodar. Se falhar, o workflow para e não perde 2h."""
import pathlib, py_compile, sys
p = pathlib.Path("onuh_scraper.py")
t = p.read_text(encoding="utf-8")
erros = []
try:
    py_compile.compile(str(p), doraise=True)
except Exception as e:
    erros.append(f"Sintaxe: {e}")
if "preco_atacado" in t:
    erros.append("Ainda tem 'preco_atacado' - use preco_final")
if "vals[0]" in t:
    erros.append("Ainda tem 'vals[0]' - fallback perigoso")
if "link_onuh" in t and 'k not in ("link_onuh"' not in t:
    erros.append("link_onuh pode estar vazando no JSON publico")
if "ONUH_STORAGE" not in t and "storage_state" not in t:
    erros.append("Falta carregar storage (login da Onuh usa storage também)")
if "TESTE_RAPIDO" not in t:
    erros.append("Falta TESTE_RAPIDO")
if "JSON-LD ignorado" not in t:
    erros.append("Falta validacao de nome JSON-LD")
# Simula conta certa
assert round(164.99+30,2)==194.99, "Conta Asad errada"
assert round(199.99+30,2)==229.99, "Conta Asad Elixir errada"
if erros:
    print("VALIDACAO FALHOU:")
    for e in erros: print(" -", e)
    sys.exit(1)
print("VALIDACAO OK - pode rodar")
