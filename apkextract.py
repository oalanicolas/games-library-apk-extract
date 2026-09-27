#!/usr/bin/env python3
"""Safe unpack of APK / XAPK / APKS / APKM for studio libraries.

Nested APKs and ZIP OBBs are opened. DEX, ELF/.so and signing files are omitted.
The original package is never modified. Destinations refuse traversal, absolute
paths, colliding names and a second write over an existing tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MAX_ENTRIES = 100_000
MAX_UNPACKED = 20 * 1024**3
MAX_FILE = 4 * 1024**3
PACKAGE_SUFFIXES = {".apk", ".xapk", ".apks", ".apkm"}
ELF_MAGIC = b"\x7fELF"
DEX_NAME = re.compile(r"(^|/)classes\d*\.dex$", re.IGNORECASE)
SO_NAME = re.compile(r"(^|/)lib/[^/]+/[^/]+\.so$", re.IGNORECASE)


class ExtractError(ValueError):
    """Package refused or destination unsafe."""


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def portable_path(path: Path) -> str:
    path = Path(path).expanduser().resolve()
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        try:
            return "<repo-root>/" + path.relative_to(ROOT.parent.parent).as_posix()
        except ValueError:
            return path.name


def package_kind(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix not in PACKAGE_SUFFIXES:
        raise ExtractError("informe um arquivo .apk, .xapk, .apks ou .apkm")
    return "apk" if suffix == ".apk" else "xapk"


def archive_members(archive: zipfile.ZipFile, require: str | None = None) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ExtractError("pacote com entradas demais")
    seen: set[str] = set()
    total = 0
    names: list[str] = []
    for info in infos:
        name = info.filename
        parts = name.rstrip("/").split("/")
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or any(part in ("", ".", "..") for part in parts)
            or any(ord(char) < 32 for char in name)
        ):
            raise ExtractError(f"caminho ZIP inválido: {name!r}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ExtractError(f"entrada ZIP não regular: {name!r}")
        key = unicodedata.normalize("NFC", name.rstrip("/")).casefold()
        if key in seen:
            raise ExtractError(f"nomes ZIP em conflito: {name!r}")
        seen.add(key)
        if info.file_size > MAX_FILE:
            raise ExtractError(f"arquivo ZIP grande demais: {name!r}")
        total += info.file_size
        if total > MAX_UNPACKED:
            raise ExtractError("pacote excede o limite de 20 GiB descompactados")
        if not info.is_dir():
            names.append(name)
    if require == "apk" and "AndroidManifest.xml" not in names:
        raise ExtractError("APK sem AndroidManifest.xml")
    if require == "xapk":
        has_manifest = "manifest.json" in names
        has_apk = any(name.lower().endswith(".apk") for name in names)
        if not has_manifest and not has_apk:
            raise ExtractError("XAPK sem manifest.json nem APK interno")
    return infos


def is_signature_entry(name: str) -> bool:
    posix = name.replace("\\", "/")
    base = PurePosixPath(posix).name
    if base in {"MANIFEST.MF", "stamp-cert-sha256"}:
        return True
    if posix.upper().startswith("META-INF/") and base.upper().endswith((".SF", ".RSA", ".DSA", ".EC")):
        return True
    return False


def is_native_or_code(name: str) -> bool:
    posix = name.replace("\\", "/")
    return bool(DEX_NAME.search(posix) or SO_NAME.search(posix))


def is_apk_resource(name: str, skip_native: bool = True) -> bool:
    posix = name.replace("\\", "/")
    if is_signature_entry(posix):
        return False
    if skip_native and is_native_or_code(posix):
        return False
    return True


def nested_zip(archive: zipfile.ZipFile, name: str):
    tmp = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    with archive.open(name) as src:
        shutil.copyfileobj(src, tmp, 1024 * 1024)
    tmp.seek(0)
    return zipfile.ZipFile(tmp), tmp


def copy_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path, skip_native: bool) -> tuple[bool, bytes]:
    if dest.exists():
        raise ExtractError(f"destino já existe: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    if tmp.exists():
        tmp.unlink()
    with archive.open(info) as src, tmp.open("xb") as dst:
        magic = src.read(4)
        executable = magic in {ELF_MAGIC, b"dex\n"}
        if executable and skip_native:
            tmp.unlink()
            return False, magic
        dst.write(magic)
        shutil.copyfileobj(src, dst, 1024 * 1024)
    tmp.chmod(0o444)
    tmp.rename(dest)
    return True, magic


def extract_members(archive: zipfile.ZipFile, dest_root: Path, prefix: str, skip_native: bool) -> tuple[list[str], list[dict]]:
    extracted: list[str] = []
    skipped: list[dict] = []
    dest_root = dest_root.resolve()
    for info in archive.infolist():
        if info.is_dir():
            continue
        label = f"{prefix}{info.filename}" if prefix else info.filename
        if not is_apk_resource(info.filename, skip_native=skip_native):
            skipped.append({"path": label, "reason": "código nativo, DEX ou assinatura"})
            continue
        dest = dest_root.joinpath(*PurePosixPath(info.filename).parts)
        if not dest.resolve().is_relative_to(dest_root):
            skipped.append({"path": label, "reason": "destino fora da extração"})
            continue
        try:
            copied, magic = copy_zip_entry(archive, info, dest, skip_native)
        except (RuntimeError, zipfile.BadZipFile, OSError, ExtractError) as exc:
            if dest.exists():
                dest.unlink()
            skipped.append({"path": label, "reason": str(exc)[:300]})
            continue
        if not copied:
            skipped.append({"path": label, "reason": f"executável {magic[:4]!r}"})
            continue
        extracted.append(label)
    return extracted, skipped


def read_xapk_manifest(archive: zipfile.ZipFile, names: list[str]) -> dict:
    if "manifest.json" not in names:
        return {}
    info = archive.getinfo("manifest.json")
    if info.file_size > 2 * 1024 * 1024:
        return {"error": "manifest.json grande demais"}
    try:
        payload = json.loads(archive.read("manifest.json"))
    except (ValueError, TypeError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        return {"error": str(exc)[:200]}
    if not isinstance(payload, dict):
        return {"error": "manifest.json não é objeto"}
    keep = {}
    for key in (
        "xapk_version",
        "package_name",
        "name",
        "version_name",
        "version_code",
        "min_sdk_version",
        "target_sdk_version",
        "total_size",
        "icon",
        "split_apks",
        "expansions",
        "split_configs",
    ):
        if key in payload:
            keep[key] = payload[key]
    return keep


def inspect(source) -> dict:
    """Identity and inner containers, without writing files."""
    source = Path(source).expanduser().resolve(strict=True)
    kind = package_kind(source)
    with zipfile.ZipFile(source) as archive:
        infos = archive_members(archive, require=kind)
        names = [info.filename for info in infos if not info.is_dir()]
        identity = read_xapk_manifest(archive, names) if kind == "xapk" else {}
        apks = [name for name in names if name.lower().endswith(".apk")]
        obbs = [name for name in names if name.lower().endswith(".obb")]
    return {
        "kind": kind,
        "source": portable_path(source),
        "sha256": digest(source),
        "bytes": source.stat().st_size,
        "identity": identity,
        "outerFiles": len(names),
        "apks": apks,
        "obbs": obbs,
    }


def apk_role(stem: str, root: Path) -> str:
    lower = stem.lower()
    if lower.startswith("config."):
        return "config"
    compact = lower.replace("_", "").replace("-", "")
    if "assetpack" in compact or "installtime" in compact:
        return "asset-pack"
    if (root / "AndroidManifest.xml").is_file():
        return "base"
    return "other"


def resource_roots(extracted_root: Path) -> list[dict]:
    """Game-content directories inside an unpacked tree, deepest markers first."""
    extracted_root = Path(extracted_root).resolve()
    found: list[dict] = []
    seen: set[str] = set()

    def add(path: Path, reason: str) -> None:
        if not path.is_dir():
            return
        rel = path.relative_to(extracted_root).as_posix()
        if rel in seen:
            return
        seen.add(rel)
        found.append({"path": rel, "reason": reason, "files": sum(1 for item in path.rglob("*") if item.is_file())})

    for csv in extracted_root.rglob("csv_logic/characters.csv"):
        add(csv.parent.parent, "csv_logic")
    for catalog in extracted_root.rglob("aa/catalog.json"):
        add(catalog.parent, "addressables")
    for data in extracted_root.glob("apk/*/assets/bin/Data"):
        add(data, "unity-data")
    for data in extracted_root.glob("apk/*/assets/bin/data"):
        add(data, "unity-data")
    if not found:
        for assets in extracted_root.glob("apk/*/assets"):
            add(assets, "assets")
    found.sort(key=lambda row: (-row["files"], row["path"]))
    return found


def describe(extracted_root) -> dict:
    extracted_root = Path(extracted_root).expanduser().resolve(strict=True)
    apks = []
    apk_root = extracted_root / "apk"
    if apk_root.is_dir():
        for child in sorted(apk_root.iterdir()):
            if not child.is_dir():
                continue
            files = sum(1 for item in child.rglob("*") if item.is_file())
            apks.append({
                "stem": child.name,
                "role": apk_role(child.name, child),
                "root": child.relative_to(extracted_root).as_posix(),
                "files": files,
            })
    roots = resource_roots(extracted_root)
    return {
        "extractedRoot": portable_path(extracted_root),
        "apks": apks,
        "resourceRoots": roots,
        "primaryResourceRoot": roots[0]["path"] if roots else None,
    }


def unpack(source, dest, *, skip_native: bool = True, apk_stem: str | None = None) -> dict:
    """Unpack a package into a new directory. Nested APK blobs stay uncopied."""
    source = Path(source).expanduser().resolve(strict=True)
    dest = Path(dest).expanduser()
    if dest.exists():
        raise FileExistsError(dest)
    kind = package_kind(source)
    dest.mkdir(parents=True)
    extracted: list[str] = []
    skipped: list[dict] = []
    identity: dict = {}
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive_members(archive, require=kind)
            names = [info.filename for info in infos if not info.is_dir()]
            if kind == "xapk":
                identity = read_xapk_manifest(archive, names)
            if kind == "apk":
                dest_root = dest / "apk" / (apk_stem or source.stem)
                dest_root.mkdir(parents=True)
                inner_extracted, inner_skipped = extract_members(archive, dest_root, prefix="", skip_native=skip_native)
                extracted.extend(inner_extracted)
                skipped.extend(inner_skipped)
            else:
                for info in infos:
                    if info.is_dir():
                        continue
                    name = info.filename
                    lower = name.lower()
                    if lower.endswith(".apk"):
                        dest_root = dest / "apk" / PurePosixPath(name).stem
                        dest_root.mkdir(parents=True, exist_ok=True)
                        nested, tmp = nested_zip(archive, name)
                        try:
                            archive_members(nested, require="apk")
                            inner_extracted, inner_skipped = extract_members(
                                nested, dest_root, prefix=f"{name}!/", skip_native=skip_native
                            )
                        finally:
                            nested.close()
                            tmp.close()
                        extracted.extend(inner_extracted)
                        skipped.extend(inner_skipped)
                        continue
                    if lower.endswith(".obb"):
                        dest_root = dest / "obb" / PurePosixPath(name).stem
                        dest_root.mkdir(parents=True, exist_ok=True)
                        try:
                            nested, tmp = nested_zip(archive, name)
                            try:
                                archive_members(nested)
                                inner_extracted, inner_skipped = extract_members(
                                    nested, dest_root, prefix=f"{name}!/", skip_native=skip_native
                                )
                            finally:
                                nested.close()
                                tmp.close()
                            extracted.extend(inner_extracted)
                            skipped.extend(inner_skipped)
                        except zipfile.BadZipFile:
                            skipped.append({"path": name, "reason": "OBB não é ZIP; não copiado como blob"})
                        continue
                    target = dest.joinpath(*PurePosixPath(name).parts)
                    if not target.resolve().is_relative_to(dest.resolve()):
                        skipped.append({"path": name, "reason": "destino fora da extração"})
                        continue
                    try:
                        copied, magic = copy_zip_entry(archive, info, target, skip_native)
                    except (RuntimeError, zipfile.BadZipFile, OSError, ExtractError) as exc:
                        if target.exists():
                            target.unlink()
                        skipped.append({"path": name, "reason": str(exc)[:300]})
                        continue
                    if not copied:
                        skipped.append({"path": name, "reason": f"executável {magic[:4]!r}"})
                        continue
                    extracted.append(name)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    layout = describe(dest)
    report = {
        "kind": kind,
        "source": portable_path(source),
        "sha256": digest(source),
        "identity": identity,
        "extracted": extracted,
        "skipped": skipped,
        "layout": layout,
        "extensions": dict(Counter(PurePosixPath(name.split("!/")[-1]).suffix.lower() or "[none]" for name in extracted).most_common()),
    }
    (dest / "layout.json").write_text(json.dumps({
        "kind": kind,
        "sha256": report["sha256"],
        "identity": identity,
        "layout": layout,
        "extracted": len(extracted),
        "skipped": len(skipped),
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser("inspect")
    inspect_cmd.add_argument("package")
    unpack_cmd = commands.add_parser("unpack")
    unpack_cmd.add_argument("package")
    unpack_cmd.add_argument("--out", required=True, type=Path)
    layout_cmd = commands.add_parser("layout")
    layout_cmd.add_argument("extracted")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            print(json.dumps(inspect(args.package), ensure_ascii=False, indent=2))
        elif args.command == "unpack":
            report = unpack(args.package, args.out)
            print(json.dumps({
                "extracted": len(report["extracted"]),
                "skipped": len(report["skipped"]),
                "primaryResourceRoot": report["layout"]["primaryResourceRoot"],
                "apks": report["layout"]["apks"],
                "out": portable_path(args.out),
            }, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(describe(args.extracted), ensure_ascii=False, indent=2))
    except (OSError, ExtractError, zipfile.BadZipFile, FileExistsError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
