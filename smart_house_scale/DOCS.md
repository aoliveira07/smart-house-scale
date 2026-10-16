# Tecnohead Scale App

## Opções

- `api_url`: endereço HTTP do servidor Smart House, por padrão
  `http://192.168.0.201`.
- `api_token`: token Bearer dedicado para a API central. O valor fica nas
  opções protegidas do Home Assistant e não aparece no navegador nem nos logs.
- `weight_entity_id`: entidade `sensor` que publica o peso. O padrão é
  `sensor.casal_balanca_peso` e pode ser alterado pela aba Configuração.
- `mqtt_discovery_prefix`: prefixo MQTT Discovery, normalmente
  `homeassistant`. O broker e as credenciais são fornecidos pelo serviço MQTT
  do Supervisor; não devem ser colocados no GitHub.

## Rede e segurança

O App expõe somente a interface Ingress e encaminha `/api/*` para o servidor
central. O navegador nunca fala diretamente com PostgreSQL. O App usa a API
oficial do Supervisor com o token de aplicação entregue pelo Home Assistant.

## Bluetooth e entidade de peso

O App não faz descoberta BLE, não descriptografa Xiaomi e não usa HACS. A
integração nativa do Home Assistant (ou outra integração que publique um
sensor de peso) recebe o Bluetooth, decodifica o valor e o disponibiliza como
entidade. O App assina `state_changed` no WebSocket `/core/websocket`, consulta
o estado inicial pela API REST e encaminha o valor à API central.

O entity ID pode ser selecionado pela interface. A escolha é preservada no
volume `/data/settings.json`; a fila de medições offline fica no mesmo volume.

## Entidades compartilháveis

Com o serviço MQTT disponível, o App publica entidades somente para moradores
ativos. O estado retido de cada morador alimenta sensores de peso, IMC,
tendência, alterações, estatísticas, quantidade de pesagens, meta e metabolismo
basal estimado. Os
IDs são derivados do UUID do usuário e não mudam quando o nome é editado.
Alexa e HomeKit exigem que essas entidades sejam expostas nas próprias
configurações do Home Assistant.

## Atualização

Use o botão de atualização do App Store. A atualização do App não altera a
migration nem o PostgreSQL central. A entidade escolhida e a fila offline são
mantidas no armazenamento persistente do App. Não há arquivos customizados do
Home Assistant para sincronizar ou reiniciar.
