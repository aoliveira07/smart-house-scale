# Smart House Scale — SH-SCALE

V1 local para balanças Xiaomi Bluetooth no ecossistema Smart House/Home
Assistant. O Bluetooth é tratado pelo stack nativo do Home Assistant; a API
central persiste no PostgreSQL e a interface acompanha a família visual Smart
House.

## Estado da entrega

Implementação local pronta para testes automatizados e revisão de integração.
A homologação física ainda depende de confirmar o servidor central correto e a
MAC real da balança. Durante esta execução, `192.168.0.201` respondeu como
controlador UniFi e não como o servidor PostgreSQL/FastAPI descrito no handoff;
nenhuma migration ou alteração remota foi aplicada.

## Arquitetura

```text
Xiaomi BLE → Bluetooth nativo HA/ESPHome Proxy → integração custom_components
          → fila persistente local → API FastAPI central → PostgreSQL / schema health
                                                        ↘ UI Smart House Scale
```

O Home Assistant não acessa PostgreSQL. Cada sessão BLE mantém apenas o último
frame temporário, espera a indicação de estabilidade e cria um único
`measurement_uuid`. A API é idempotente por esse UUID.

## Instalação no Home Assistant

### HACS

1. Adicione o repositório GitHub como repositório customizado do tipo
   **Integration**.
2. Instale `Smart House Scale` e reinicie o Home Assistant.
3. Em **Configurações → Dispositivos e serviços → Adicionar integração**, informe
   nome, MAC, URL da API e, se adotado pelo servidor, o token dedicado.
4. Confirme que o Bluetooth nativo ou um Bluetooth Proxy ESPHome está operacional.

### Manual

Copie `smart_house_scale/custom_components/smart_house_scale` para
`config/custom_components/smart_house_scale` e reinicie o Home Assistant.

A configuração de moradores é feita na interface web central; não existe JSON de
usuários no HA.

## Backend central

1. Verifique no servidor correto a árvore FastAPI/Alembic e o head atual.
2. Copie o router `backend/app/routes.py` para o pacote do servidor ou inclua-o
   via `app.include_router(router)`.
3. Copie a migration para o diretório Alembic existente e preencha `down_revision`
   com o head real, sem editar migrations já aplicadas.
4. Configure a URL existente em `SMART_HOUSE_DATABASE_URL`/`DATABASE_URL` e instale
   `backend/requirements.txt` no ambiente do servidor. Não use Docker no servidor.
5. Publique a UI pelo mesmo FastAPI/Ingress ou pelo reverse proxy LAN já usado
   pelos apps Smart House.

## API

- `GET/POST/PATCH /api/v1/scales`
- `GET/POST/PATCH /api/v1/scale-users`
- `POST/GET /api/v1/scale-measurements`
- `GET /api/v1/scale-users/{id}/measurements`
- `GET /api/v1/scale-users/{id}/summary`
- `GET /api/v1/scale-measurements/pending`
- `POST /api/v1/scale-measurements/{id}/assign|discard|reassign`
- `GET /api/v1/scale/health`

## Métricas

Peso é `measured`. IMC, alterações, médias, medianas, tendência e progresso são
`calculated`. Mifflin–St Jeor para adultos é `estimated` e explicitamente não é
uma medição da balança. Para menores, não são aplicadas faixas adultas de IMC.
Campos de bioimpedância permanecem `NULL` até existirem dados reais.

## Testes

No ambiente de desenvolvimento com Python 3.12+:

```powershell
$env:PYTHONPATH = "$PWD;.test-deps"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest -q tests/scale
```

Os testes cobrem parser V1/V2, unidade, estabilização, deduplicação, baseline,
atribuição automática, múltiplos/nenhum candidato, descarte, reatribuição,
IMC, fila offline e idempotência.

## Licença e créditos

O projeto é MIT. O decoder segue o protocolo público Xiaomi e foi implementado
com base em comportamento documentado nas referências, sem copiar um scanner
BLE paralelo. Os créditos e avisos MIT das referências estão em
[CREDITS.md](CREDITS.md).

## Limitações conhecidas

- O IP informado no handoff não apontou para o servidor central durante a
  execução; deployment da migration e smoke test contra PostgreSQL real aguardam
  o endereço/credencial corretos.
- A API não assume uma política de autenticação própria: em produção deve ser
  montada atrás da autenticação existente do Smart House ou de token dedicado.
- O modelo efetivo da balança e o layout de seus anúncios precisam ser confirmados
  com captura física; V1/V2 Xiaomi conhecidos estão cobertos.
