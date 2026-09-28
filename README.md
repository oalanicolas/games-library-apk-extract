# Extração de APK

Módulo local para **abrir APK, XAPK, APKS e APKM** e guardar 100% do pacote: recursos, DEX, bibliotecas `.so`, assinaturas, OBB e o original. O original não é alterado. A bancada com originais, `runs/` e viewer está em `libraries/android-asset-workspace`; a cópia completa de cada jogo vai para `libraries/<jogo>/`, com Git LFS nos arquivos grandes.

`--resources-only` deixa código e assinaturas de fora; `--no-original` não copia o pacote. Original acima de 1,9 GB sai em partes com SHA-256, abaixo do limite de 2 GB por arquivo do Git LFS no GitHub; `python3 apkextract.py join <out>/original --out jogo.xapk` remonta e confere.

## Abrir um pacote

```sh
python3 apkextract.py inspect "/caminho/Jogo.xapk"
python3 apkextract.py unpack "/caminho/Jogo.xapk" --out /tmp/jogo-extraido
python3 apkextract.py layout /tmp/jogo-extraido
```

`unpack` cria o destino. Um segundo unpack no mesmo caminho é recusado. A árvore fica:

```
out/
  layout.json
  manifest.json          # se o pacote for XAPK
  apk/<stem>/            # cada APK interno, já aberto
  obb/<stem>/            # OBB aberto, ou o arquivo como veio se não for ZIP
  original/              # o pacote, ou as partes .partNN, e original.json com os SHA-256
```

`layout.primaryResourceRoot` aponta a pasta de conteúdo do jogo (`assets/` com `csv_logic`, Addressables `aa/`, ou Unity `bin/Data`).

No Python:

```python
import apkextract
report = apkextract.unpack("jogo.xapk", dest)
root = dest / report["layout"]["primaryResourceRoot"]
```

## Gate

```sh
python3 validate.py
```

Os testes usam pacotes sintéticos. Se a extração do Brawl Stars 69.252 estiver na bancada Android, um teste extra confere o `install_time_asset_pack`.

## Limites

- 100 mil entradas, 4 GiB por arquivo, 20 GiB descompactados.
- Recusa `../`, caminho absoluto, symlink e nomes em conflito.
- Não executa o aplicativo e não desmonta código nativo.
