# Mandato — extração de APK

Estado: em execução. Não é evidência de aprovação.

## Resultado de uma frase
Uma biblioteca do estúdio entrega um APK/XAPK e recebe a árvore extraída com todos os arquivos do pacote (DEX, `.so`, assinaturas e OBB inclusive), os APKs internos separados, a pasta de recursos do jogo e o original em `original/`, sem alterar a fonte.

## Fonte e contexto
- Projeto/ID: `apk-extract`; módulo `library-apk-extract`.
- Registro canônico: skill `game-library-studio` (security-and-publishing) e a bancada `libraries/android-asset-workspace`.
- Modo: ferramenta. Este repositório guarda o extrator; cada biblioteca de jogo guarda 100% do pacote na própria pasta (imagens, áudio, modelos 3D, código, assinaturas e o original), com Git LFS nos arquivos grandes.
- Raízes autorizadas de leitura: o arquivo informado na chamada.
- Raízes autorizadas de escrita: o `--out` informado; nunca o pacote de origem.
- Autoridade para publicar: nenhuma nesta rodada.

## Fatia e orçamento
- Intenção: criar.
- Profundidade: Standard (G0 repositório + G1 unpack/layout + testes).
- Gate: `python3 validate.py`.
- Fora de escopo: executar o cliente, descompilar DEX (trabalho do `code-anatomist`), UnityPy e viewer HTTP.

## Aceite observável
1. `python3 validate.py` passa.
2. XAPK sintético com `install_time_asset_pack` aponta `primaryResourceRoot` para `assets/` com `csv_logic`.
3. DEX, `.so`, assinaturas e OBB que não é ZIP aparecem no destino; o original fica em `original/`, em partes de até 1,9 GB com SHA-256 quando é maior (`join` remonta e confere).
4. `androidlab.py extract` usa este módulo e os testes da bancada Android continuam passando.

## Decisões do usuário ainda necessárias
Push do remoto GitHub e gitlink no hub.
