# Central API overlay

These files are installed into the existing Smart House FastAPI tree on
`192.168.0.201`; they do not start a second service or create a second
database.

```text
central_api/app/api/scale.py       -> /opt/smart-house/api/app/api/scale.py
central_api/app/schemas/scale.py   -> /opt/smart-house/api/app/schemas/scale.py
central_api/app/services/scale.py  -> /opt/smart-house/api/app/services/scale.py
```

The central `app/main.py` imports `scale.router` and includes it with the
other routers. The Alembic migration is copied to
`/opt/smart-house/migrations/versions/` and is chained after the current
`b62d4f9a7e31` head.

The API reuses the existing SQLAlchemy session, Bearer authentication and
PostgreSQL connection. Home Assistant calls the LAN reverse proxy at
`http://192.168.0.201/api`; the FastAPI process itself remains bound to
`127.0.0.1:8000`.
