# Changelog

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

