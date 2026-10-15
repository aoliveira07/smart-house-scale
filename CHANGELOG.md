# Changelog

## 0.1.1 — compatibilidade HA

- Corrige a assinatura do callback de anúncios BLE nativo do Home Assistant.
- Mantém o callback passivo como fallback para versões sem o callback por pacote.

## 0.1.0 — V1 inicial

- Integração Home Assistant com Bluetooth nativo, Xiaomi V1/V2 e Bluetooth Proxy.
- Sessão de 30 segundos, estabilização, deduplicação e fila offline persistente.
- API FastAPI/PostgreSQL, migration `health`, atribuição automática e pendências.
- Dashboard responsivo, histórico, gráficos, metas, indicadores e diagnóstico.
