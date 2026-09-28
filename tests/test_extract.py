#!/usr/bin/env python3
import base64
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import apkextract  # noqa: E402


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0BEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_zip(self, path, files):
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return path

    def make_apk(self, path, extra=None):
        files = {
            "AndroidManifest.xml": b"<manifest package='example.test'/>",
            "res/drawable/pixel.png": PNG,
            "classes.dex": b"dex\n035\0code",
            "lib/arm64-v8a/libg.so": b"\x7fELFnative",
            "assets/csv_logic/characters.csv": b"Name\nHero\n",
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n",
            "META-INF/CERT.SF": b"signature",
            "META-INF/CERT.RSA": b"rsa",
        }
        if extra:
            files.update(extra)
        return self.make_zip(path, files)

    def make_xapk(self):
        base = self.root / "com.example.game.apk"
        pack = self.root / "install_time_asset_pack.apk"
        self.make_apk(base)
        self.make_zip(pack, {
            "AndroidManifest.xml": b"<manifest package='example.test.pack'/>",
            "assets/csv_logic/characters.csv": b"Name\nShotgunGirl\n",
            "assets/sc3d/hero.glb": b"glTFmesh",
            "classes.dex": b"dex\n035\0no",
        })
        xapk = self.root / "game.xapk"
        with zipfile.ZipFile(xapk, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "package_name": "com.example.game",
                "name": "Jogo de teste",
                "version_name": "69.252",
                "version_code": "69252",
                "split_apks": [
                    {"file": "com.example.game.apk", "id": "base"},
                    {"file": "install_time_asset_pack.apk", "id": "install_time_asset_pack"},
                ],
            }))
            archive.writestr("icon.png", PNG)
            archive.write(base, "com.example.game.apk")
            archive.write(pack, "install_time_asset_pack.apk")
        return xapk

    def test_unpack_xapk_finds_csv_logic_pack(self):
        xapk = self.make_xapk()
        info = apkextract.inspect(xapk)
        self.assertEqual(info["kind"], "xapk")
        self.assertEqual(info["identity"]["package_name"], "com.example.game")
        self.assertEqual(len(info["apks"]), 2)
        dest = self.root / "out"
        report = apkextract.unpack(xapk, dest)
        self.assertTrue((dest / "icon.png").is_file())
        self.assertFalse((dest / "com.example.game.apk").exists())
        self.assertTrue((dest / "apk/install_time_asset_pack/assets/csv_logic/characters.csv").is_file())
        self.assertTrue((dest / "apk/com.example.game/res/drawable/pixel.png").is_file())
        self.assertEqual((dest / "apk/com.example.game/classes.dex").read_bytes(), b"dex\n035\0code")
        self.assertEqual((dest / "apk/com.example.game/lib/arm64-v8a/libg.so").read_bytes(), b"\x7fELFnative")
        self.assertTrue((dest / "apk/com.example.game/META-INF/CERT.RSA").is_file())
        self.assertTrue((dest / "apk/install_time_asset_pack/classes.dex").is_file())
        layout = report["layout"]
        roles = {row["stem"]: row["role"] for row in layout["apks"]}
        self.assertEqual(roles["install_time_asset_pack"], "asset-pack")
        self.assertEqual(roles["com.example.game"], "base")
        self.assertEqual(layout["primaryResourceRoot"], "apk/install_time_asset_pack/assets")
        self.assertEqual((dest / "apk/install_time_asset_pack/assets/csv_logic/characters.csv").read_bytes(), b"Name\nShotgunGirl\n")
        self.assertEqual(report["skipped"], [])
        self.assertEqual(report["original"]["sha256"], apkextract.digest(xapk))
        self.assertEqual((dest / "original" / "game.xapk").read_bytes(), xapk.read_bytes())
        with self.assertRaises(FileExistsError):
            apkextract.unpack(xapk, dest)

    def test_resources_only_leaves_code_out(self):
        apk = self.make_apk(self.root / "solo.apk")
        dest = self.root / "res-only"
        report = apkextract.unpack(apk, dest, skip_native=True, keep_original=False)
        self.assertFalse((dest / "apk/solo/classes.dex").exists())
        self.assertFalse((dest / "apk/solo/lib/arm64-v8a/libg.so").exists())
        self.assertFalse((dest / "apk/solo/META-INF/CERT.SF").exists())
        self.assertTrue((dest / "apk/solo/res/drawable/pixel.png").is_file())
        self.assertFalse((dest / "original").exists())
        self.assertIsNone(report["original"])

    def test_original_split_in_parts_and_joined(self):
        xapk = self.make_xapk()
        dest = self.root / "split"
        report = apkextract.unpack(xapk, dest, part_size=700)
        parts = report["original"]["parts"]
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(row["bytes"] <= 700 for row in parts))
        self.assertFalse((dest / "original" / "game.xapk").exists())
        rebuilt = self.root / "rebuilt.xapk"
        apkextract.join_original(dest / "original", rebuilt)
        self.assertEqual(rebuilt.read_bytes(), xapk.read_bytes())
        (dest / "original" / parts[0]["file"]).chmod(0o644)
        (dest / "original" / parts[0]["file"]).write_bytes(b"x")
        with self.assertRaises(apkextract.ExtractError):
            apkextract.join_original(dest / "original", self.root / "bad.xapk")

    def test_non_zip_obb_is_copied(self):
        xapk = self.root / "obb.xapk"
        with zipfile.ZipFile(xapk, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"package_name": "com.example.obb"}))
            archive.write(self.make_apk(self.root / "base.apk"), "base.apk")
            archive.writestr("Android/obb/com.example.obb/main.1.com.example.obb.obb", b"RAWPAK\0data")
        dest = self.root / "obb-out"
        apkextract.unpack(xapk, dest, keep_original=False)
        self.assertEqual((dest / "obb/main.1.com.example.obb/main.1.com.example.obb.obb").read_bytes(), b"RAWPAK\0data")

    def test_plain_apk(self):
        apk = self.make_apk(self.root / "solo.apk")
        dest = self.root / "apk-out"
        report = apkextract.unpack(apk, dest)
        self.assertTrue((dest / "apk/solo/assets/csv_logic/characters.csv").is_file())
        self.assertEqual(report["layout"]["primaryResourceRoot"], "apk/solo/assets")

    def test_rejects_traversal(self):
        apk = self.root / "bad.apk"
        self.make_zip(apk, {"AndroidManifest.xml": b"a", "../outside": b"b"})
        with self.assertRaises(apkextract.ExtractError):
            apkextract.inspect(apk)

    def test_rejects_symlink(self):
        linked = self.root / "link.apk"
        with zipfile.ZipFile(linked, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"a")
            link = zipfile.ZipInfo("res/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, b"/etc/passwd")
        with self.assertRaises(apkextract.ExtractError):
            apkextract.inspect(linked)

    def test_describe_brawl_stars_run_if_present(self):
        run = (
            Path(__file__).resolve().parents[2]
            / "android-asset-workspace"
            / "runs"
            / "1d48c46df5ca-20260927T165432Z-86a9f40e"
            / "extracted"
        )
        if not run.is_dir():
            self.skipTest("extração Brawl Stars ausente")
        layout = apkextract.describe(run)
        self.assertEqual(layout["primaryResourceRoot"], "apk/install_time_asset_pack/assets")
        roles = {row["stem"]: row["role"] for row in layout["apks"]}
        self.assertEqual(roles.get("install_time_asset_pack"), "asset-pack")


if __name__ == "__main__":
    unittest.main()
