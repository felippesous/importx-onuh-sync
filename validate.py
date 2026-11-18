#!/usr/bin/env python3
"""
Valida data/produtos.json antes do commit no GitHub Actions.
Exit 0 = ok | Exit 1 = inválido (aborta o commit).
"""
import json, sys, os
from datetime import datetime, timezone

MIN_PRODUTOS = 10               # ajuste ao tamanho real do catálogo
CAMPOS_OBRIGATORIOS = ("nome",)

def main(path="data/produtos.json"):
    if not os.path.exists(path):
        print(f"[ERRO] Não encontrado: {path}", file=sys.stderr); return 1
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        print(f"[ERRO] JSON inválido: {e}", file=sys.stderr); return 1
    if not isinstance(dados, list):
        print("[ERRO] O JSON deve ser uma lista de produtos.", file=sys.stderr); return 1

    validos = []
    for i, p in enumerate(dados):
        if not isinstance(p, dict):
            print(f"[AVISO] Item {i} não é objeto.", file=sys.stderr); continue
        if any(not p.get(c) for c in CAMPOS_OBRIGATORIOS):
            print(f"[AVISO] Item {i} sem campos obrigatórios.", file=sys.stderr); continue
        validos.append(p)

    if len(validos) < MIN_PRODUTOS:
        print(f"[ERRO] Apenas {len(validos)} produtos válidos (mínimo {MIN_PRODUTOS}).", file=sys.stderr)
        print("       O scraper provavelmente falhou — abortando commit.", file=sys.stderr)
        return 1

    com_preco = sum(1 for p in validos if p.get("preco_final") or p.get("preco_atacado"))
    com_foto  = sum(1 for p in validos if p.get("foto"))
    print(f"[OK] {len(validos)} produtos válidos | com preço: {com_preco} | com foto: {com_foto}")
    print(f"     Verificado em {datetime.now(timezone.utc).isoformat()}")
    return 0

if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))