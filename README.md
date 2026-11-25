# ImportX Atacado - Sync Onuh
## Como atualizar (depois de deixar o repo PRIVADO)
1. Suba todos os arquivos deste pacote (substitua os antigos)
2. GitHub > Settings > Secrets > Actions > ONUH_COOKIES_JSON = conteúdo do onuh_cookies.json
3. Actions > Sincronizar Onuh -> ImportX > Run workflow > teste_rapido = true (testa Asad em 3 min)
4. Se o teste der Asad 194,99 e Asad Elixir 229,99, rode de novo com teste_rapido = false (completo, ~1h45)
## Regras
- Repo SEMPRE privado
- Nunca subir onuh_cookies.json, produtos_parcial.json, variacao_precos.csv (o .gitignore já bloqueia)
- Preço do site = preço Onuh + R$ 30,00. Só preco_final vai para o site.
