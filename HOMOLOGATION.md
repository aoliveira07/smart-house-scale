# Checklist de homologação física — SH-SCALE V1

- [ ] Confirmar o host correto do PostgreSQL/FastAPI; `192.168.0.201` está divergente nesta entrega.
- [ ] Aplicar a migration no Alembic central com o `down_revision` real.
- [ ] Configurar autenticação LAN/token sem gravar segredo no Git.
- [ ] Instalar a integração e confirmar Bluetooth nativo/Proxy ESPHome.
- [ ] Identificar e cadastrar a MAC normalizada.
- [ ] Cadastrar usuários, altura e peso inicial pela UI.
- [ ] Fazer primeira pesagem e confirmar estabilização.
- [ ] Confirmar um único registro no PostgreSQL.
- [ ] Confirmar atribuição automática de uma leitura dentro de ±3 kg.
- [ ] Testar segundo usuário com baseline distinto.
- [ ] Simular visitante/discrepância e confirmar `pending/unknown_or_visitor`.
- [ ] Atribuir manualmente e confirmar histórico/indicadores.
- [ ] Descartar uma pendência e confirmar histórico intacto.
- [ ] Restaurar/reatribuir medição descartada.
- [ ] Derrubar a API, fazer pesagem e confirmar fila local.
- [ ] Restaurar a API, confirmar sincronização sem duplicidade.
- [ ] Conferir sensores HA, unique IDs, histórico, gráficos e origem dos indicadores.
- [ ] Observar logs por um ciclo e confirmar ausência de erros recorrentes.
