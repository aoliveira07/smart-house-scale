# Tecnohead Scale — SH-SCALE

V1 local para balanças Xiaomi Bluetooth no ecossistema Smart House/Home
Assistant. O Bluetooth e a descriptografia ficam na integração nativa do Home
Assistant; este App ouve a entidade de peso escolhida, persiste a fila local e
envia medições para o FastAPI central e PostgreSQL.

## Estado da entrega

O servidor central foi integrado ao FastAPI existente em `192.168.0.201`. A
migration `c4a9f1e2b7d0` é encadeada após o head `b62d4f9a7e31`; o PostgreSQL
oficial continua sendo o único histórico.

O FastAPI escuta internamente em `127.0.0.1:8000` e o Nginx expõe a API LAN em
`http://192.168.0.201/api`. O App encaminha as chamadas pelo proxy autenticado
e nunca expõe o token no navegador.

## Instalação como App

1. Em **Configurações → Apps → App Store → Repositórios**, adicione
   `https://github.com/aoliveira07/smart-house-scale`.
2. Instale e inicie **Tecnohead Scale**.
3. Nas opções do App, informe `api_url` (`http://192.168.0.201`), o token
   Bearer dedicado e, inicialmente, `weight_entity_id`. Mantenha o broker
   MQTT do Home Assistant instalado e em execução para publicar as entidades
   dos moradores.
4. Abra o App pelo painel lateral via Ingress e entre em **Configuração**.
5. Selecione a entidade de peso publicada pelo Home Assistant, por exemplo
   `sensor.casal_balanca_peso`, ou informe o entity ID manualmente.
6. Confirme que a integração nativa da balança (por exemplo `xiaomi_ble`) está
   ativa e publica um valor numérico em kg, lb ou jin.
7. Cadastre os moradores pela interface com altura, peso inicial e, quando
   necessário para o metabolismo basal, sexo biológico.

O App não instala, copia ou atualiza `custom_components` e não depende do HACS.
Uma instalação nova precisa somente do App e da integração nativa que já
produz a entidade de peso.

## Origem do peso e fluxo

O App usa `homeassistant_api: true` e o proxy oficial do Supervisor. Ele abre
`ws://supervisor/core/websocket`, autentica com o `SUPERVISOR_TOKEN` fornecido
ao App e assina eventos `state_changed`. Ao conectar, também lê o estado atual
pela rota REST `/core/api/states/<entity_id>`.

```text
Xiaomi BLE → Bluetooth nativo HA/ESPHome Proxy → sensor de peso do HA
          → App (WebSocket + fila offline) → API FastAPI central → PostgreSQL / health
                                                        ↘ UI Tecnohead Scale
```

O Home Assistant não acessa PostgreSQL. A integração nativa recebe o BLE e
descriptografa os modelos Xiaomi que exigem bind key; o App recebe somente o
valor da entidade já pronto. Assim qualquer integração que publique uma
entidade de peso compatível pode ser selecionada sem alterar o código do App.

Cada mudança numérica é tratada como uma leitura final publicada pelo HA. A
janela de sessão configurável é de 30 segundos e gera um único
`measurement_uuid`; a API é idempotente por esse UUID. Se a API central ficar
indisponível, a medição fica na fila persistente de `/data` e é reenviada.

## Entidades dos moradores para Alexa e HomeKit

O App publica MQTT Discovery retido no broker oficial do Home Assistant. Para
cada morador ativo é criado um dispositivo Home Assistant com entidades
estáveis de peso, IMC e sua classificação, tendência, variações de 7/30/90 dias,
variação em kg e percentual desde o início, média, mediana, mínimo, máximo,
frequência e quantidade de pesagens, meta, progresso da meta e metabolismo
basal estimado. O estado compartilhado é somente o resumo do morador; não são
criadas entidades de balança, Bluetooth, API, fila ou pendências por esse
mecanismo.

As entidades aparecem no registro do Home Assistant depois que o broker recebe
o Discovery. Para compartilhar com Alexa ou HomeKit, ainda é necessário
expor/selecionar essas entidades nas configurações da integração Alexa ou
Apple Home; o App não altera essa política de privacidade automaticamente.
O diagnóstico do App informa se o MQTT está conectado, quantas entidades
foram publicadas e quando ocorreu a última sincronização.

## Configuração da entidade

`weight_entity_id` inicia com `sensor.casal_balanca_peso` e pode ser alterado
pela aba **Configuração**. A escolha da interface tem prioridade e é preservada
em `/data/settings.json`. A mesma tela mostra o estado do WebSocket, o último
valor recebido, a fila e erros relevantes.

## Interface

Na Visão geral, cada morador aparece primeiro em cartão sempre expandido com peso,
meta, IMC, variação, tendência e gráfico. A comunicação técnica da balança,
Home Assistant, PostgreSQL e pendências fica abaixo. A aba Usuários permite
cadastro, edição, avatar, histórico e evolução.

## Backend central

O overlay instalado no servidor está documentado em
[`backend/central_api/README.md`](backend/central_api/README.md). Ele reaproveita
o FastAPI, autenticação Bearer, Alembic e schema PostgreSQL `health` existentes.

## API central

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
Os estados MQTT preservam essas origens no atributo `metric_origins`.

## Testes

No ambiente de desenvolvimento com Python 3.12+:

```powershell
$env:PYTHONPATH = "$PWD;.test-deps"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest -q tests/scale
```

Os testes cobrem o parser de entidades, unidades, estabilização, deduplicação,
baseline, atribuição automática, múltiplos/nenhum candidato, descarte,
reatribuição, IMC, fila offline, idempotência e a autenticação/assinatura do
WebSocket do Home Assistant.

## Licença e créditos

O projeto é MIT. O App não incorpora scanner BLE nem código HACS. As referências
Xiaomi estão registradas em [CREDITS.md](CREDITS.md) para documentar o protocolo
que é processado pela integração nativa do Home Assistant.

## Limitações conhecidas

- Entidades que não expõem MAC usam um identificador local determinístico
  derivado do entity ID; o endereço físico é usado quando o HA o publica.
- Impedância e composição corporal continuam `NULL` quando a balança não as
  mede de verdade.
- A homologação física deve confirmar o entity ID e a estabilidade da entidade
  escolhida antes de retirar definitivamente qualquer configuração antiga.
