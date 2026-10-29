#!/usr/bin/env python3
"""
Scan seluruh PC untuk cari:
  1. Backup iPhone di mana-mana drive (termasuk hard disk luar)
  2. Folder yang mengandungi gambar & video (terutama dari iPhone: HEIC, MOV, IMG_1234)
  3. Gambar & video dalam Recycle Bin, dengan nama asal

Cara guna:
    py cari_gambar_pc.py                       # scan semua drive
    py cari_gambar_pc.py --folder D:\\         # scan satu tempat sahaja
    py cari_gambar_pc.py --salin D:\\Pulih     # salin gambar dari Recycle Bin ke folder ini
"""

import argparse
import datetime
import os
import re
import shutil
import string
import struct
import sys
from pathlib import Path

from iphone_backup_extract import IMG, VID, describe

MEDIA = IMG | VID
MIN_SIZE = 30 * 1024  # abaikan ikon dan gambar kecil
IPHONE_NAME = re.compile(r"^IMG_E?\d{4}", re.IGNORECASE)
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "windowsapps",
             "system volume information", "$windows.~bt", "$windows.~ws", "$winreagent",
             "$recycle.bin", "recovery", "node_modules", ".git", "site-packages", "temp", "tmp"}


def drives():
    if os.name == "nt":
        return [Path(f"{d}:\\") for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    return [Path("/")]


def fmt_date(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def scan(roots):
    backups, folders, seen = [], {}, 0
    for root in roots:
        print(f"Scan {root} ...")
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
            seen += 1
            if seen % 5000 == 0:
                print(f"  ... {seen} folder diperiksa")
            if "Manifest.db" in filenames and ("Info.plist" in filenames or "Manifest.plist" in filenames):
                backups.append(describe(Path(dirpath)))
                dirnames[:] = []  # isi backup bukan gambar biasa
                continue
            for name in filenames:
                if os.path.splitext(name)[1].lower().lstrip(".") not in MEDIA:
                    continue
                try:
                    st = os.stat(os.path.join(dirpath, name))
                except OSError:
                    continue
                if st.st_size < MIN_SIZE:
                    continue
                f = folders.setdefault(dirpath, {"count": 0, "iphone": 0, "size": 0,
                                                 "first": st.st_mtime, "last": st.st_mtime})
                f["count"] += 1
                f["size"] += st.st_size
                f["first"] = min(f["first"], st.st_mtime)
                f["last"] = max(f["last"], st.st_mtime)
                if IPHONE_NAME.match(name) or name.lower().endswith((".heic", ".mov")):
                    f["iphone"] += 1
    return backups, folders


def read_recycle_info(path):
    """Baca fail $I dalam Recycle Bin: pulangkan (nama asal, masa dipadam)."""
    data = path.read_bytes()
    version, _size, filetime = struct.unpack_from("<qqq", data, 0)
    if version == 1:
        raw = data[24:24 + 520]
    else:
        length = struct.unpack_from("<i", data, 24)[0]
        raw = data[28:28 + length * 2]
    name = raw.decode("utf-16-le", errors="replace").split("\x00")[0]
    deleted = (filetime - 116444736000000000) / 1e7
    return name, deleted


def scan_recycle_bin(roots):
    found = []
    bins = {Path(root.anchor or root) / "$Recycle.Bin" for root in roots} | {root / "$Recycle.Bin" for root in roots}
    for rb in bins:
        try:
            sids = [p for p in rb.iterdir() if p.is_dir()]
        except OSError:
            continue
        for sid in sids:
            try:
                infos = list(sid.glob("$I*"))
            except OSError:
                continue
            for info in infos:
                content = sid / ("$R" + info.name[2:])
                try:
                    original, deleted = read_recycle_info(info)
                except (OSError, struct.error):
                    continue
                if content.is_dir():
                    for dirpath, _, filenames in os.walk(content, onerror=lambda e: None):
                        for name in filenames:
                            if os.path.splitext(name)[1].lower().lstrip(".") in MEDIA:
                                rel = os.path.relpath(os.path.join(dirpath, name), content)
                                found.append((Path(dirpath) / name, os.path.join(original, rel), deleted))
                elif content.exists() and os.path.splitext(original)[1].lower().lstrip(".") in MEDIA:
                    found.append((content, original, deleted))
    return found


def copy_recycled(items, dest):
    dest = Path(dest) / "Dari Recycle Bin"
    copied = 0
    for src, original, _ in items:
        rel = re.sub(r'^[A-Za-z]:[\\/]*', "", original).replace("\\", "/")
        rel = "/".join(p for p in rel.split("/") if p not in ("", ".", ".."))
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, target)
            copied += 1
        except OSError as e:
            print(f"  Gagal salin {original}: {e}")
    return dest, copied


def main():
    ap = argparse.ArgumentParser(description="Cari backup iPhone, gambar & video dalam PC.")
    ap.add_argument("--folder", help="Scan folder/drive ini sahaja (default: semua drive)")
    ap.add_argument("--salin", metavar="FOLDER", help="Salin gambar & video dari Recycle Bin ke folder ini")
    ap.add_argument("--laporan", default="laporan_gambar.txt", help="Fail laporan penuh")
    args = ap.parse_args()

    roots = [Path(args.folder)] if args.folder else drives()
    backups, folders = scan(roots)
    recycled = scan_recycle_bin(roots)

    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("\n=== 1. BACKUP IPHONE ===")
    if backups:
        for b in backups:
            lock = " [ber-password]" if b["encrypted"] else ""
            out(f"  {b['name']} ({b['model']}, iOS {b['ios']}) - backup {b['date']}{lock}")
            out(f"    Keluarkan dengan:  py iphone_backup_extract.py --backup \"{b['path']}\"")
    else:
        out("  Tiada backup iPhone dalam PC ini.")

    out("\n=== 2. GAMBAR & VIDEO DALAM RECYCLE BIN ===")
    if recycled:
        for _, original, deleted in sorted(recycled, key=lambda r: r[2]):
            out(f"  dipadam {fmt_date(deleted)}  {original}")
        out(f"  Jumlah: {len(recycled)} fail. Untuk salin keluar:  py cari_gambar_pc.py --salin D:\\Pulih")
    else:
        out("  Tiada gambar/video dalam Recycle Bin.")

    out("\n=== 3. FOLDER YANG ADA GAMBAR & VIDEO ===")
    if folders:
        ranked = sorted(folders.items(), key=lambda kv: (kv[1]["iphone"], kv[1]["count"]), reverse=True)
        total = sum(f["count"] for f in folders.values())
        out(f"  {total} gambar/video dalam {len(folders)} folder. Folder paling mungkin dari iPhone dahulu:")
        out(f"  {'iPhone':>6} {'Semua':>6} {'Saiz':>9}  {'Tarikh':23}  Folder")
        for i, (path, f) in enumerate(ranked):
            row = (f"  {f['iphone']:>6} {f['count']:>6} {fmt_size(f['size']):>9}  "
                   f"{fmt_date(f['first'])} - {fmt_date(f['last'])}  {path}")
            if i < 30:
                print(row)
            lines.append(row)
        if len(ranked) > 30:
            print(f"  ... dan {len(ranked) - 30} folder lagi (lihat laporan)")
    else:
        out("  Tiada gambar/video dijumpai.")

    Path(args.laporan).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nLaporan penuh: {Path(args.laporan).resolve()}")

    if args.salin and recycled:
        dest, copied = copy_recycled(recycled, args.salin)
        print(f"{copied} fail dari Recycle Bin disalin ke: {dest.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan.")
        sys.exit(1)
