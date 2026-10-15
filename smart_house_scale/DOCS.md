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
Home Assistant, usando o Bluetooth nativo ou um Bluetooth Proxy ESPHome. A
imagem do App leva uma cópia versionada desse componente e, na primeira
inicialização, instala-a automaticamente em
`/homeassistant/custom_components/smart_house_scale`. O App solicita uma única
reinicialização do Core para que o componente seja carregado.

O bootstrap é idempotente: uma cópia gerenciada pelo App só é atualizada quando
a versão muda; uma instalação existente sem o marcador do App (por exemplo,
instalada pelo HACS) é preservada e não é sobrescrita.

## Atualização

Use o botão de atualização do App Store. A atualização do App não altera a
migration nem o PostgreSQL central. Se o componente Bluetooth estiver sendo
gerenciado pelo App, uma atualização com nova versão o sincroniza e solicita uma
reinicialização única do Core. Instalações externas gerenciadas pelo HACS
continuam sendo atualizadas pelo HACS.
