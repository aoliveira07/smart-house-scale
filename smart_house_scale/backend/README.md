# Smart House Scale backend

Em produção, o Scale é um módulo do FastAPI central existente. Use os arquivos
em [`central_api/`](central_api/README.md), reaproveitando o SQLAlchemy,
Alembic, autenticação Bearer e PostgreSQL já instalados em
`192.168.0.201`. Não habilite um segundo serviço systemd nem crie um banco
paralelo.

O pacote `app/` continua disponível para testes unitários e desenvolvimento
isolado; a instalação oficial usa o overlay central.

O Home Assistant envia para `http://192.168.0.201/api` e fornece o token
dedicado na configuração da integração. O token é armazenado somente na
configuração segura do Home Assistant e no hash da tabela `core.api_keys`; ele
não deve entrar no GitHub, em logs ou neste repositório.
