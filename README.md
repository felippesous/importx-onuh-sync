
# ImportX Atacado — Sincronização Onuh (100% Grátis)

## Arquivos
- `salvar_login.py` — roda 1x no seu PC para salvar login (cookies)
- `onuh_scraper.py` — robô que extrai preço/estoque
- `.github/workflows/sync-onuh.yml` — automação diária 07h Brasília
- `data/produtos.json` — arquivo que seu site na Cloudflare vai ler

## Passo a passo (15 min)

### 1. No seu PC
```
pip install playwright
playwright install chromium
python salvar_login.py
```
- Vai abrir o navegador na Onuh. Faça login normal.
- Volte no terminal, aperte ENTER. Vai criar `onuh_cookies.json`.

### 2. No GitHub (grátis)
1. Crie um repositório privado, ex: `importx-onuh-sync`
2. Suba todos esses arquivos para ele
3. Vá em Settings > Secrets and variables > Actions > New repository secret
   - Nome: `ONUH_COOKIES_JSON`
   - Valor: cole o conteúdo INTEIRO do arquivo `onuh_cookies.json`
4. Vá em Actions > Sincronizar Onuh > Run workflow — para testar agora

### 3. Na Cloudflare (seu site)
Seu site ImportX Atacado vai buscar `https://SEU-DOMINIO/data/produtos.json`
ou você publica esse JSON via Cloudflare Pages / R2.
O site já está pronto para trocar o array de exemplo por esse JSON.

### Se o cookie expirar
Repita o passo 1 e atualize o Secret. Normal: a cada 15-30 dias.

### Se o site da Onuh mudar o layout
Me avise e eu ajusto os seletores em `onuh_scraper.py` — são só 3 linhas.

## Custo
GitHub Actions: 2.000 min/mês grátis (vamos usar ~300)
Cloudflare Pages + R2: plano free
Total: R$ 0
