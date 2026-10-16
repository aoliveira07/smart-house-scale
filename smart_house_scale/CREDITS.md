# Créditos e licenças

O Smart House Scale não incorpora scanner BLE nem código HACS dos projetos
abaixo. O App consome a entidade pronta do Bluetooth nativo do Home Assistant.
As referências são mantidas para documentar o protocolo Xiaomi usado pela
integração nativa e para os testes de compatibilidade:

- [ermarmon/xiaomi-scale-ha](https://github.com/ermarmon/xiaomi-scale-ha), MIT,
  copyright 2020 lolouk44 / 2024 ermarmon. A documentação confirma o uso do
  Bluetooth nativo do Home Assistant, os UUIDs `181b`/`181d` e compatibilidade
  com ESP32 Bluetooth Proxy.
- [lolouk44/xiaomi_mi_scale](https://github.com/lolouk44/xiaomi_mi_scale), MIT,
  copyright 2020 lolouk44. Referência histórica para os bytes de peso/unidade
  dos anúncios Xiaomi.

Quando houver reutilização futura de trechos de código, os avisos MIT completos
devem acompanhar os arquivos derivados. Consulte os `LICENSE` originais antes de
copiar qualquer implementação.
