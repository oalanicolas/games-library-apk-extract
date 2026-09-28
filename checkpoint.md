# Checkpoint — extração de APK

Atualizado em: 2026-09-27
Estado: concluído (G0–G1 local).

## Identidade
- Módulo: `libraries/apk-extract` (`library-apk-extract`)
- Consumidores: `libraries/android-asset-workspace` (`extract`) e `libraries/brawl-stars` (`describe` da pasta `assets/`)

## Última etapa CONCLUÍDA
`python3 validate.py` 5/5. Testes da bancada Android 5/5. `primaryResourceRoot` do Brawl Stars 69.252 = `apk/install_time_asset_pack/assets`.

## Próxima ação exata
Commit inicial neste módulo; remoto GitHub e gitlink no hub só com pedido de push.

## Preservação
O extrator nunca altera o original. A cópia completa do pacote (extração e original) vai para a biblioteca de cada jogo, pelo Git LFS nos arquivos grandes.
