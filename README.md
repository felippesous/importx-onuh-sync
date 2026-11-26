# ImportX Atacado - Sync Onuh

Robô que lê os preços de lojista do catálogo da Onuh e publica no site com **+ R$ 30,00** em cada produto.

## Arquivos
- `onuh_auth.py` — login (cookies + localStorage), teste real de sessão e renovação por e-mail/senha.
- `testar_login.py` — teste de cookies usado pelo GitHub Actions (falha rápido se não estiver logado).
- `onuh_scraper.py` — varredura do sitemap, leitura dos preços e geração de `data/produtos.json` + `data/variacao_precos.csv`.
- `salvar_login.py` — rode **no seu PC** para gerar a sessão e copiar para o Secret.

## Configuração no GitHub

> O repo precisa estar **público** para o `index.html` conseguir ler o JSON via `raw.githubusercontent.com`. Os Secrets ficam criptografados e não são expostos.
1. Rode `salvar_login.py` no seu computador, faça login na janela do Chromium que abrir e aperte ENTER.
2. GitHub > Settings > Secrets and variables > Actions > New repository secret:
   - `ONUH_STORAGE_STATE_JSON` = conteúdo **inteiro** de `onuh_storage.json` (recomendado; contém cookies + localStorage).
   - Opcional: `ONUH_EMAIL` e `ONUH_PASSWORD` — se o cookie expirar, o robô faz login sozinho e renova a sessão.
   - Legado: `ONUH_COOKIES_JSON` = conteúdo de `onuh_cookies.json` (ainda é aceito).
3. Actions > Sincronizar Onuh -> ImportX > Run workflow:
   - `teste_rapido = true` valida o login e processa 3 produtos (Asad, Asad Elixir, Afnan 9 AM Dive) **sem sobrescrever** o catálogo.
   - `teste_rapido = false` roda o completo (~2.600 produtos).

## Teste de cookies
O passo **Testar cookies / login Onuh** abre a home e um produto real. Ele só passa se o preço de lojista estiver visível. Em caso de falha, o log diz o motivo e o job para antes de propagar preço de visitante.

Exemplo de sucesso:
```
TESTE DE COOKIES: OK
LOGADO como: Felippe
Produto de teste: lattafa-asad-edp-100ml = R$ 164.99
Preco final no site apos margem: R$ 194.99
```
> Os preços do fornecedor mudam; o robô sempre usa o preço atual do site + R$ 30,00 (não valores fixos).

## Regras
- Repo **sempre privado**.
- Nunca subir `onuh_cookies.json`, `onuh_storage.json` nem `data/.onuh_auth_state.json` — o `.gitignore` já bloqueia. Use Secrets.
- O `index.html` da ImportX tem `CFG.margem = 30` e **soma R$ 30 sozinho**. Por isso o JSON público leva o preço bruto da Onuh em `preco_base` (o site transforma 164,99 em 194,99). O campo `preco_final` (já com margem) fica apenas como referência para outros consumidores.
- `link_onuh` é removido do JSON público.
- O site carrega `https://raw.githubusercontent.com/felippesous/importx-onuh-sync/main/data/produtos.json` — esse URL só funciona se o repositório estiver **público**. Se o repo estiver privado, o site não carrega o catálogo.
- Se mais de 20% dos produtos ficarem sem preço, o robô aborta e mantém o `produtos.json` anterior.
