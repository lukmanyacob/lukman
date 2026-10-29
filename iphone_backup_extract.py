#!/usr/bin/env python3
"""
Keluarkan gambar, video dan fail dari backup iPhone (iTunes / Finder / Apple Devices)
yang tersimpan dalam komputer, tanpa perlu restore atau erase iPhone.

Cara guna ringkas:
    python iphone_backup_extract.py              # pilih backup, keluarkan semua
    python iphone_backup_extract.py --senarai    # tengok backup yang ada sahaja
    python iphone_backup_extract.py --kategori kamera,whatsapp --out D:\\GambarLama

Backup yang ber-password (encrypted) perlukan:  pip install iphone_backup_decrypt
"""

import argparse
import getpass
import os
import plistlib
import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath

IMG = {"heic", "heif", "jpg", "jpeg", "png", "gif", "webp", "tif", "tiff", "bmp", "dng"}
VID = {"mov", "mp4", "m4v", "3gp", "avi"}
AUD = {"m4a", "mp3", "aac", "wav", "caf", "opus", "amr"}
DOC = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "csv",
       "pages", "numbers", "key", "zip"}

# (nama, keterangan, padan(domain, path), sambungan fail dibenarkan atau None untuk semua)
CATEGORIES = [
    ("kamera", "Camera Roll (gambar & video dalam app Photos)",
     lambda d, p: d == "CameraRollDomain" and p.startswith("Media/DCIM/"), IMG | VID),
    ("imessage", "Lampiran iMessage / SMS",
     lambda d, p: d == "MediaDomain" and p.startswith("Library/SMS/Attachments/"), IMG | VID | AUD | DOC),
    ("whatsapp", "Media WhatsApp",
     lambda d, p: "whatsapp" in d.lower() and "/Media/" in "/" + p, IMG | VID | AUD | DOC),
    ("fail", "App Files - 'On My iPhone'",
     lambda d, p: d == "AppDomainGroup-group.com.apple.FileProvider.LocalStorage", None),
    ("voicememo", "Voice Memos",
     lambda d, p: d == "MediaDomain" and p.startswith("Media/Recordings/"), AUD),
]
# Gambar/video dalam app lain (Telegram, Instagram cache dsb). Banyak sampah, jadi hanya bila diminta.
OTHER = ("lain", "Gambar & video dari app lain (banyak cache, saiz > 50KB sahaja)")
OTHER_MIN_SIZE = 50 * 1024


def backup_roots():
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library/Application Support/MobileSync/Backup"]
    if os.name == "nt":
        roots = [home / "Apple/MobileSync/Backup"]
        if os.environ.get("APPDATA"):
            roots.append(Path(os.environ["APPDATA"]) / "Apple Computer/MobileSync/Backup")
        return roots
    return [home / ".local/share/MobileSync/Backup"]


def read_plist(path):
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}


def describe(backup_dir):
    info = read_plist(backup_dir / "Info.plist")
    manifest = read_plist(backup_dir / "Manifest.plist")
    date = info.get("Last Backup Date")
    return {
        "path": backup_dir,
        "name": info.get("Device Name", "?"),
        "model": info.get("Product Type", "?"),
        "ios": info.get("Product Version", "?"),
        "date": date.strftime("%Y-%m-%d %H:%M") if date else "?",
        "encrypted": bool(manifest.get("IsEncrypted")),
    }


def find_backups(extra_root=None):
    roots = [Path(extra_root)] if extra_root else backup_roots()
    found = []
    for root in roots:
        if (root / "Manifest.db").exists():
            found.append(describe(root))
            continue
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if (d / "Manifest.db").exists():
                    found.append(describe(d))
    return sorted(found, key=lambda b: b["date"])


def print_backups(backups):
    for i, b in enumerate(backups, 1):
        lock = "  [ber-password]" if b["encrypted"] else ""
        print(f"  {i}. {b['name']} ({b['model']}, iOS {b['ios']}) - backup {b['date']}{lock}")
        print(f"     {b['path']}")


def choose_backup(backups):
    if len(backups) == 1:
        return backups[0]
    print("Backup yang dijumpai:")
    print_backups(backups)
    while True:
        ans = input(f"Pilih nombor backup (1-{len(backups)}): ").strip()
        if ans.isdigit() and 1 <= int(ans) <= len(backups):
            return backups[int(ans) - 1]


def file_meta(blob):
    """Saiz dan masa ubah suai dari rekod plist dalam Manifest.db."""
    try:
        plist = plistlib.loads(blob)
        obj = plist["$objects"][plist["$top"]["root"].data]
        return int(obj.get("Size", 0)), obj.get("LastModified")
    except Exception:
        return 0, None


def classify(domain, rel, size, wanted):
    ext = PurePosixPath(rel).suffix.lower().lstrip(".")
    for name, _, match, exts in CATEGORIES:
        if match(domain, rel):
            if name in wanted and (exts is None or ext in exts):
                return name
            return None
    if OTHER[0] in wanted and ext in IMG | VID and size >= OTHER_MIN_SIZE \
            and domain not in ("CameraRollDomain", "MediaDomain") and "/Thumbnails/" not in "/" + rel:
        return OTHER[0]
    return None


def safe_relpath(domain, rel, category):
    parts = [p for p in PurePosixPath(rel).parts if p not in ("", ".", "..", "/")]
    if category == "lain":
        parts.insert(0, domain)
    elif category == "kamera" and parts[:2] == ["Media", "DCIM"]:
        parts = parts[2:]
    return Path(*[re.sub(r'[<>:"|?*\\]', "_", p) for p in parts])


class PlainBackup:
    def __init__(self, path):
        self.path = path
        uri = (path / "Manifest.db").resolve().as_uri() + "?mode=ro&immutable=1"
        self.conn = sqlite3.connect(uri, uri=True)

    def rows(self):
        return self.conn.execute("SELECT fileID, domain, relativePath, file FROM Files WHERE flags = 1")

    def extract(self, file_id, domain, rel, dest):
        src = self.path / file_id[:2] / file_id
        if not src.exists():
            src = self.path / file_id  # format backup lama (iOS 9 ke bawah)
        with open(src, "rb") as fin, open(dest, "wb") as fout:
            while chunk := fin.read(1 << 20):
                fout.write(chunk)


class EncryptedBackupReader:
    def __init__(self, path, password):
        from iphone_backup_decrypt import EncryptedBackup
        self.backup = EncryptedBackup(backup_directory=str(path), passphrase=password)
        self.backup.test_decryption()

    def rows(self):
        with self.backup.manifest_db_cursor() as cur:
            cur.execute("SELECT fileID, domain, relativePath, file FROM Files WHERE flags = 1")
            return cur.fetchall()

    def extract(self, file_id, domain, rel, dest):
        self.backup.extract_file(relative_path=rel, domain_like=domain, output_filename=str(dest))


def open_backup(b, password=None):
    if not b["encrypted"]:
        return PlainBackup(b["path"])
    try:
        from iphone_backup_decrypt import IncorrectPassphraseError
    except ImportError:
        sys.exit("Backup ini ber-password. Pasang dulu:  pip install iphone_backup_decrypt")
    while True:
        pw = password or getpass.getpass("Password backup iPhone (yang ditetapkan dalam iTunes/Finder): ")
        try:
            return EncryptedBackupReader(b["path"], pw)
        except IncorrectPassphraseError:
            print("Password salah, cuba lagi.")
            if password:
                sys.exit(1)
        except Exception as e:
            sys.exit(f"Tak dapat buka backup ber-password ini (mungkin rosak atau tak lengkap): {e!r}")


def main():
    names = [c[0] for c in CATEGORIES] + [OTHER[0]]
    ap = argparse.ArgumentParser(description="Keluarkan gambar, video & fail dari backup iPhone dalam komputer.")
    ap.add_argument("--backup", help="Folder backup tertentu (atau folder yang mengandungi banyak backup)")
    ap.add_argument("--out", default="iPhone_Recovered", help="Folder simpan hasil (default: iPhone_Recovered)")
    ap.add_argument("--kategori", default=",".join(c[0] for c in CATEGORIES),
                    help=f"Senarai dipisah koma: {','.join(names)}. Default: semua kecuali 'lain'")
    ap.add_argument("--password", help="Password backup (kalau tak beri, akan ditanya)")
    ap.add_argument("--senarai", action="store_true", help="Senaraikan backup yang ada sahaja")
    args = ap.parse_args()

    wanted = {k.strip().lower() for k in args.kategori.split(",") if k.strip()}
    unknown = wanted - set(names)
    if unknown:
        ap.error(f"Kategori tak dikenali: {', '.join(sorted(unknown))}. Pilihan: {', '.join(names)}")

    backups = find_backups(args.backup)
    if not backups:
        print("Tiada backup iPhone dijumpai. Tempat yang diperiksa:")
        for r in ([Path(args.backup)] if args.backup else backup_roots()):
            print(f"  {r}")
        if sys.platform == "darwin":
            print("Di Mac, beri Terminal 'Full Disk Access' dalam System Settings > Privacy & Security.")
        sys.exit(1)

    if args.senarai:
        print_backups(backups)
        return

    b = choose_backup(backups)
    print(f"\nMembuka backup {b['name']} ({b['date']}) ...")
    reader = open_backup(b, args.password)
    out_root = Path(args.out) / f"{b['name']} {b['date'][:10]}"

    counts, failed = {}, 0
    for file_id, domain, rel, blob in reader.rows():
        size, mtime = file_meta(blob)
        cat = classify(domain, rel, size, wanted)
        if not cat:
            continue
        dest = out_root / cat / safe_relpath(domain, rel, cat)
        if dest.exists() and dest.stat().st_size == size:
            counts[cat] = counts.get(cat, 0) + 1  # dah dikeluarkan sebelum ini
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            reader.extract(file_id, domain, rel, dest)
            if mtime:
                os.utime(dest, (mtime, mtime))
            counts[cat] = counts.get(cat, 0) + 1
            if sum(counts.values()) % 200 == 0:
                print(f"  ... {sum(counts.values())} fail setakat ini")
        except Exception as e:
            failed += 1
            print(f"  Gagal: {domain}/{rel} ({e})")

    print("\nSelesai. Hasil:")
    descriptions = {c[0]: c[1] for c in CATEGORIES}
    descriptions[OTHER[0]] = OTHER[1]
    for cat in names:
        if cat in wanted:
            print(f"  {cat:10} {counts.get(cat, 0):6} fail  - {descriptions[cat]}")
    if failed:
        print(f"  {failed} fail gagal dikeluarkan (lihat mesej di atas).")
    print(f"\nFolder: {out_root.resolve()}")
    if not counts.get("kamera") and "kamera" in wanted:
        print("Nota: Camera Roll kosong biasanya bermaksud iCloud Photos 'on' masa backup dibuat -\n"
              "gambar disimpan dalam iCloud, bukan dalam backup.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan.")
