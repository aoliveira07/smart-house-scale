# Smart House Scale — SH-SCALE

V1 local para balanças Xiaomi Bluetooth no ecossistema Smart House/Home
Assistant. O Bluetooth é tratado pelo stack nativo do Home Assistant; a API
central persiste no PostgreSQL e a interface acompanha a família visual Smart
House.

## Estado da entrega

O servidor central foi confirmado e o módulo foi integrado ao FastAPI existente
em `192.168.0.201`. A migration `c4a9f1e2b7d0` é encadeada após o head
`b62d4f9a7e31`; o PostgreSQL oficial continua sendo o único histórico.

O FastAPI escuta internamente em `127.0.0.1:8000` e o Nginx expõe a API LAN em
`http://192.168.0.201/api`. A integração Home Assistant usa essa URL e o token
dedicado configurado no fluxo da integração.

## Instalação como App

O painel administrativo é distribuído como um App oficial do repositório de
Apps do Home Assistant. Não é necessário cadastrar o projeto como repositório
personalizado do HACS para usar a interface.

1. Em **Configurações → Apps → App Store → Repositórios**, adicione
   `https://github.com/aoliveira07/smart-house-scale`.
2. Instale **Smart House Scale**.
3. Nas opções do App, informe `api_url` (`http://192.168.0.201`) e o token
   Bearer dedicado. O token é salvo somente nas opções protegidas do Home
   Assistant e não é publicado neste repositório.
4. Inicie o App e abra **Smart House Scale** pelo painel lateral via Ingress.
5. Na primeira inicialização, o App instala automaticamente a integração
   `smart_house_scale` em `custom_components` e solicita uma única reinicialização
   do Home Assistant Core. Não é necessário cadastrar o repositório no HACS.
6. Abra **Configurações → Dispositivos e serviços**, adicione a integração
   **Smart House Scale** e informe MAC, URL e token da balança. Essa etapa é a
   configuração da balança, não a instalação do código.
7. Cadastre moradores pela interface e informe altura, peso inicial e, quando
   necessário para o metabolismo basal, sexo biológico.

O App é o painel e o proxy autenticado para a API central. Ele não cria banco
local, não acessa PostgreSQL e não executa scanner Bluetooth paralelo.

## Componente Bluetooth do Home Assistant

O recebimento dos advertisements continua pertencendo ao componente nativo do
Home Assistant, conforme a arquitetura do V1. O App não substitui o stack
Bluetooth nem transforma a interface em um scanner independente. A imagem do
App contém o adaptador revisado e o instala no diretório
`custom_components/smart_house_scale` durante o bootstrap. O App usa o mount
`homeassistant_config` documentado pelo Supervisor apenas para essa finalidade.

Se a integração já existir por HACS ou por instalação manual, o bootstrap não a
substitui. Nesse caso o HACS continua sendo o responsável por aquela cópia e o
App apenas registra o estado `external_existing` no endpoint `/health`.

O Home Assistant não deve apontar para a porta `8000` nem acessar o PostgreSQL.
O acesso LAN usa o proxy HTTP em `/api`.

## Arquitetura

```text
Xiaomi BLE → Bluetooth nativo HA/ESPHome Proxy → integração custom_components
          → fila persistente local → API FastAPI central → PostgreSQL / schema health
                                                        ↘ UI Smart House Scale
```

O Home Assistant não acessa PostgreSQL. Cada sessão BLE mantém apenas o último
frame temporário, espera a indicação de estabilidade e cria um único
`measurement_uuid`. A API é idempotente por esse UUID.

## Configuração do componente Bluetooth

Depois do bootstrap automático, adicione a integração em **Configurações →
Dispositivos e serviços → Adicionar integração** e informe nome, MAC, URL da API
e token Bearer. Confirme que o Bluetooth nativo ou um Bluetooth Proxy ESPHome
está operacional.

A configuração de moradores é feita na interface do App; não existe JSON de
usuários no Home Assistant.

## Backend central

O overlay instalado no servidor está documentado em
[`backend/central_api/README.md`](backend/central_api/README.md). Ele adiciona
os endpoints ao processo `smart-house-api.service`, reaproveita a autenticação
Bearer existente e usa o schema PostgreSQL `health`.

O Home Assistant nunca acessa o PostgreSQL diretamente. A URL configurada na
integração é `http://192.168.0.201`; o prefixo `/api` é acrescentado pelos
endpoints do cliente.

## API

- `GET/POST/PATCH /api/v1/scales`
- `GET/POST/PATCH /api/v1/scale-users`
- `POST/GET /api/v1/scale-measurements`
- `GET /api/v1/scale-users/{id}/measurements`
- `GET /api/v1/scale-users/{id}/summary`
- `GET /api/v1/scale-measurements/pending`
- `POST /api/v1/scale-measurements/{id}/assign|discard|reassign`
- `GET /api/v1/scale/health`

As rotas de leitura usam `scale:read`; escrita, incluindo ingestão de medições,
usa `scale:write`. O cliente provisionado para o Home Assistant possui ambos.

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

- O modelo efetivo da balança e o layout de seus anúncios precisam ser
  confirmados com captura física; V1/V2 Xiaomi conhecidos estão cobertos.
- A interface administrativa do Scale continua no pacote web do projeto; a
  homologação deve confirmar a publicação dela no frontend Smart House.
- A balança atual pode não fornecer impedância; campos de bioimpedância ficam
  `NULL` até existirem dados reais.
