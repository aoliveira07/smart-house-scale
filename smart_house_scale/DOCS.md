# Smart House Scale App

## Opções

- `api_url`: endereço HTTP do servidor Smart House, por padrão
  `http://192.168.0.201`.
- `api_token`: token Bearer dedicado para a API central. O valor é mantido nas
  opções protegidas do Home Assistant, não aparece no navegador e não é escrito
  em logs pela aplicação.

## Rede e segurança

O App expõe somente a interface Ingress e encaminha `/api/*` para o servidor
central. O navegador nunca fala diretamente com o PostgreSQL. A API central
continua na LAN e o token é anexado pelo proxy do App.

## Bluetooth

O App não faz descoberta BLE. A recepção passiva, a estabilização, a
deduplicação e a fila offline permanecem no componente `smart_house_scale` do
Home Assistant, usando o Bluetooth nativo ou um Bluetooth Proxy ESPHome.

## Atualização

Use o botão de atualização do App Store. A atualização do App não altera a
migration nem o PostgreSQL central. O componente Bluetooth deve ser atualizado
conforme o mecanismo de componentes do Home Assistant.
