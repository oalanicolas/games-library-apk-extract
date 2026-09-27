# Mandato — extração de APK

Estado: em execução. Não é evidência de aprovação.

## Resultado de uma frase
Uma biblioteca do estúdio entrega um APK/XAPK obtido legitimamente e recebe uma árvore extraída, os APKs internos separados e a pasta de recursos do jogo, sem alterar o original e sem copiar DEX/SO.

## Fonte e contexto
- Projeto/ID: `apk-extract`; módulo `library-apk-extract`.
- Registro canônico: skill `game-library-studio` (security-and-publishing) e a bancada `libraries/android-asset-workspace`.
- Modo: ferramenta de estudo. Pacotes de terceiros não entram neste repositório.
- Raízes autorizadas de leitura: o arquivo informado na chamada.
- Raízes autorizadas de escrita: o `--out` informado; nunca o pacote de origem.
- Autoridade para publicar: nenhuma nesta rodada.

## Fatia e orçamento
- Intenção: criar.
- Profundidade: Standard (G0 repositório + G1 unpack/layout + testes).
- Gate: `python3 validate.py`.
- Fora de escopo: executar o cliente, descompilar DEX, UnityPy, viewer HTTP, ingestão permanente de originais (isso continua na bancada Android).

## Aceite observável
1. `python3 validate.py` passa.
2. XAPK sintético com `install_time_asset_pack` aponta `primaryResourceRoot` para `assets/` com `csv_logic`.
3. DEX e `.so` não aparecem no destino.
4. `androidlab.py extract` usa este módulo e os testes da bancada Android continuam passando.

## Decisões do usuário ainda necessárias
Push do remoto GitHub e gitlink no hub.
