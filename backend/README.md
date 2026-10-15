# Smart House Scale backend

O backend expõe o router `app.routes.router` para ser incluído no FastAPI central
existente. O entry point `app.main:app` também permite executar a API isoladamente
durante desenvolvimento, sempre usando PostgreSQL via `SMART_HOUSE_DATABASE_URL`
ou `DATABASE_URL`.

```python
from backend.app.routes import router as scale_router
app.include_router(scale_router)
```

O servidor central deve fornecer a dependência de autenticação já usada pelos
demais apps. Para o modo standalone, configure `SMART_HOUSE_SCALE_API_TOKEN` no
proxy/API conforme a política local; nenhum token deve entrar no repositório.
