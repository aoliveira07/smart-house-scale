# Arquitetura e decisões V1

## Fronteiras

- A integração HA é dona de BLE, estabilização, sessão, UUID, fila offline e
  entidades.
- A API central é dona de usuários, atribuição, histórico, métricas, pendências,
  auditoria e PostgreSQL.
- O App publica, via MQTT Discovery oficial, somente sensores derivados dos
  usuários ativos. A balança e os diagnósticos não são expostos como sensores
  compartilháveis; Alexa/HomeKit continuam sob controle de exposição do HA.
- A UI é servida pela API central. O HA não consulta o banco.

## Identificação

Cada usuário ativo recebe baseline pela mediana de até cinco pesagens atribuídas
recentes. Sem histórico, usa-se `initial_reference_weight_kg`. Uma leitura dentro
da tolerância de exatamente um usuário é automática; zero ou múltiplos candidatos
ficam pendentes.

## Segurança e privacidade

Tokens só entram por configuração segura. Logs carregam nomes de exceção, nunca
headers de autorização ou payloads sensíveis completos. O backend deve permanecer
na LAN até decisão posterior.
