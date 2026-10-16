# Changelog

## 0.6.0 — 2026-10-16

- Publica entidades Home Assistant por morador usando MQTT Discovery retido.
- Expõe peso, IMC, tendência, variações, estatísticas, frequência, meta e
  metabolismo basal estimado com IDs estáveis e origem das métricas nos
  atributos.
- Mantém fora da superfície compartilhável os dados técnicos da balança, API,
  Bluetooth, fila e pendências.
- Usa o serviço MQTT oficial do Home Assistant, sem credenciais no repositório,
  e remove automaticamente entidades antigas de moradores inativos.

## 0.5.1 — 2026-10-16

- Usa o MAC e o modelo do Device Registry do Home Assistant quando a entidade
  não os publica nos próprios atributos.
- Não grava o snapshot antigo da entidade como nova pesagem ao reiniciar ou
  atualizar o App; somente mudanças posteriores geram medições.

## 0.5.0 — 2026-10-16

- Remove o componente customizado/HACS do App e do pacote publicado.
- Passa a ouvir diretamente uma entidade de peso configurável do Home
  Assistant pelo WebSocket oficial do Supervisor.
- Mantém a integração nativa Xiaomi BLE responsável por Bluetooth e
  descriptografia, sem scanner ou credencial duplicada no App.
- Adiciona seleção de sensor pela interface, leitura inicial via REST,
  diagnóstico de conexão e fila offline persistente no volume do App.

## 0.4.7 — 2026-10-16

- Adiciona suporte à Xiaomi Smart Scale S200 (MJTZC02YM), que transmite MiBeacon
  criptografado em `FE95`.
- Consome a entidade de peso da integração nativa `xiaomi_ble` do Home Assistant,
  sem scanner BLE paralelo e sem duplicar bind keys.
- Mantém a sessão, deduplicação, fila offline e envio idempotente para a API central.
- Atualiza a integração embarcada para 0.1.7.

## 0.4.6 — 2026-10-15

- Corrige o callback do dispatcher do Home Assistant que atualiza as entidades após uma medição.
- Permite que o evento Bluetooth entregue o identificador da entrada sem interromper o processamento do peso.
- Atualiza a integração embarcada para 0.1.5 e mantém a documentação da tela Usuários alinhada ao layout atual.

## 0.4.5 — 2026-10-15

- Reorganiza a aba Usuários para mostrar primeiro os moradores, evolução, metas e indicadores.
- Move a situação da balança, comunicação com a API, PostgreSQL e pendências para uma seção secundária.
- Mantém edição e cadastro abaixo do histórico pessoal e da situação técnica.

## 0.4.4 — visão geral centrada nos moradores

- Prioriza moradores, peso atual, histórico e evolução na entrada do App.
- Move os cartões técnicos da balança, última pesagem, PostgreSQL e pendências
  para uma seção secundária.
- Mostra peso e estado da última pesagem realmente registrada.
- Melhora o gráfico de evolução com pontos e datas no eixo horizontal.

## 0.4.3 — atualização de assets no navegador

- Versiona os URLs dos arquivos estáticos para impedir que navegadores mantenham
  uma interface antiga após a atualização do App.

## 0.4.2 — compatibilidade completa com Ingress

- Corrige as consultas de diagnóstico para usar o caminho relativo do App.
- Corrige o upload e a exibição de avatares quando o App é aberto pelo Ingress
  do Home Assistant.

## 0.4.1 — publicação da imagem multi-arquitetura

- Alinha a versão do App ao workflow de publicação do repositório.
- Mantém a interface de cartões expansíveis e avatares persistentes da 0.4.0.

## 0.4.0 — cartões de moradores e avatares persistentes

- Mostra os moradores cadastrados imediatamente no início da tela Usuários.
- Adiciona cartões expansíveis na Visão geral com peso, meta, IMC, variação e
  tendência, sempre identificando a origem do indicador.
- Permite enviar um avatar pela interface; a imagem fica no armazenamento
  persistente local do Add-on e não é publicada no repositório.
- Mantém avatar, lista e cadastro compatíveis com instalações existentes.

## 0.3.0 — instalação automatizada do componente Home Assistant

- Inclui a integração `smart_house_scale` na imagem do App.
- Instala o componente automaticamente em `custom_components` na primeira
  inicialização, sem exigir repositório personalizado no HACS.
- Preserva instalações existentes gerenciadas pelo HACS ou manualmente.
- Solicita uma única reinicialização do Home Assistant Core após instalação ou
  atualização gerenciada pelo App.
- Expõe o estado do bootstrap no endpoint `/health`.

## 0.1.3 — API central Smart House

- Integra o Scale ao FastAPI central existente, sem serviço ou banco paralelo.
- Adiciona migration Alembic encadeada no head `b62d4f9a7e31`.
- Adiciona usuários, balanças, sessões, medições, atribuição automática,
  pendências, reatribuição, métricas, saúde e auditoria mínima.
- Protege a API com os scopes `scale:read` e `scale:write`.
- Configuração HA exige token Bearer e envia o nome do dispositivo para o
  cadastro automático da balança.

## 0.1.2 — IDs de entidades

- Define `suggested_object_id` estável para as entidades por usuário e por dispositivo.

## 0.1.1 — compatibilidade HA

- Corrige a assinatura do callback de anúncios BLE nativo do Home Assistant.
- Mantém o callback passivo como fallback para versões sem o callback por pacote.

## 0.1.0 — V1 inicial

- Integração Home Assistant com Bluetooth nativo, Xiaomi V1/V2 e Bluetooth Proxy.
- Sessão de 30 segundos, estabilização, deduplicação e fila offline persistente.
- API FastAPI/PostgreSQL, migration `health`, atribuição automática e pendências.
- Dashboard responsivo, histórico, gráficos, metas, indicadores e diagnóstico.
## 0.2.3 — Porta exclusiva para host network

- Move o Ingress e o watchdog para a porta `8100`, evitando conflito com o Neocontrol Module Manager em `8099`.

## 0.2.4 — Porta exclusiva de alta faixa

- Move o Ingress e o watchdog para a porta `18099`, livre no host do Home Assistant.

