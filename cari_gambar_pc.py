#!/usr/bin/env python3
"""
Scan seluruh PC untuk cari gambar, video dan dokumen lama:
  1. Backup iPhone di mana-mana drive (termasuk hard disk luar)
  2. Gambar, video & dokumen dalam Recycle Bin, dengan nama asal
  3. Jumlah fail mengikut tahun
  4. Folder yang mengandungi fail-fail tersebut
Setiap fail juga disenaraikan dalam senarai_fail.csv (boleh dibuka dengan Excel).

Cara guna:
    py cari_gambar_pc.py                       # scan semua drive
    py cari_gambar_pc.py --sebelum 2022        # fail yang bertarikh sebelum 2022 sahaja
    py cari_gambar_pc.py --jenis gambar,video  # jenis tertentu sahaja
    py cari_gambar_pc.py --folder D:\\         # scan satu tempat sahaja
    py cari_gambar_pc.py --salin D:\\Pulih     # salin fail dari Recycle Bin ke folder ini
"""

import argparse
import csv
import datetime
import os
import re
import shutil
import string
import struct
import sys
from pathlib import Path

from iphone_backup_extract import DOC, IMG, VID, describe

KINDS = {"gambar": IMG, "video": VID, "dokumen": DOC - {"txt", "csv", "zip"}}
MIN_SIZE = {"gambar": 30 * 1024, "video": 1024, "dokumen": 1024}  # abaikan ikon dan gambar kecil
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "windowsapps",
             "system volume information", "$windows.~bt", "$windows.~ws", "$winreagent",
             "$recycle.bin", "recovery", "node_modules", ".git", "site-packages", "temp", "tmp"}


def kind_of(name, wanted):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for kind in wanted:
        if ext in KINDS[kind]:
            return kind
    return None


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


def scan(roots, wanted, before, writer):
    backups, folders, years, seen = [], {}, {}, 0
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
                kind = kind_of(name, wanted)
                if not kind:
                    continue
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                    year = datetime.datetime.fromtimestamp(st.st_mtime).year
                except (OSError, OverflowError, ValueError):  # tarikh rosak pada sesetengah fail lama
                    continue
                if st.st_size < MIN_SIZE[kind] or (before and year >= before):
                    continue
                writer.writerow([fmt_date(st.st_mtime), kind, round(st.st_size / 1024), name, dirpath])
                years.setdefault(year, dict.fromkeys(wanted, 0))[kind] += 1
                f = folders.setdefault(dirpath, {"count": 0, "size": 0,
                                                 "first": st.st_mtime, "last": st.st_mtime,
                                                 **dict.fromkeys(wanted, 0)})
                f[kind] += 1
                f["count"] += 1
                f["size"] += st.st_size
                f["first"] = min(f["first"], st.st_mtime)
                f["last"] = max(f["last"], st.st_mtime)
    return backups, folders, years


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


def scan_recycle_bin(roots, wanted):
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
                            if kind_of(name, wanted):
                                rel = os.path.relpath(os.path.join(dirpath, name), content)
                                found.append((Path(dirpath) / name, os.path.join(original, rel), deleted))
                elif content.exists() and kind_of(original, wanted):
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
    ap = argparse.ArgumentParser(description="Cari gambar, video & dokumen lama dalam PC.")
    ap.add_argument("--folder", help="Scan folder/drive ini sahaja (default: semua drive)")
    ap.add_argument("--jenis", default=",".join(KINDS), help=f"Dipisah koma: {','.join(KINDS)} (default: semua)")
    ap.add_argument("--sebelum", type=int, metavar="TAHUN", help="Hanya fail bertarikh sebelum tahun ini")
    ap.add_argument("--salin", metavar="FOLDER", help="Salin fail dari Recycle Bin ke folder ini")
    ap.add_argument("--laporan", default="laporan_gambar.txt", help="Fail laporan ringkas")
    ap.add_argument("--csv", default="senarai_fail.csv", help="Senarai setiap fail (untuk Excel)")
    args = ap.parse_args()

    wanted = [k.strip().lower() for k in args.jenis.split(",") if k.strip()]
    unknown = set(wanted) - set(KINDS)
    if unknown:
        ap.error(f"Jenis tak dikenali: {', '.join(sorted(unknown))}. Pilihan: {', '.join(KINDS)}")

    roots = [Path(args.folder)] if args.folder else drives()
    # utf-8-sig supaya Excel baca nama fail Melayu/Arab/Cina dengan betul
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["Tarikh", "Jenis", "Saiz (KB)", "Nama fail", "Folder"])
        backups, folders, years = scan(roots, wanted, args.sebelum, writer)
    recycled = scan_recycle_bin(roots, wanted)

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

    out("\n=== 2. DALAM RECYCLE BIN ===")
    if recycled:
        for _, original, deleted in sorted(recycled, key=lambda r: r[2]):
            out(f"  dipadam {fmt_date(deleted)}  {original}")
        out(f"  Jumlah: {len(recycled)} fail. Untuk salin keluar:  py cari_gambar_pc.py --salin D:\\Pulih")
    else:
        out("  Tiada fail berkaitan dalam Recycle Bin.")

    out("\n=== 3. JUMLAH FAIL MENGIKUT TAHUN ===")
    if years:
        out("  Tahun " + "".join(f"{k.capitalize():>9}" for k in wanted))
        for year in sorted(years):
            out(f"  {year} " + "".join(f"{years[year][k]:>9}" for k in wanted))
    else:
        out("  Tiada fail dijumpai.")

    out("\n=== 4. FOLDER (paling lama dahulu) ===")
    if folders:
        ranked = sorted(folders.items(), key=lambda kv: kv[1]["first"])
        total = sum(f["count"] for f in folders.values())
        out(f"  {total} fail dalam {len(folders)} folder.")
        out("  " + "".join(f"{k.capitalize():>8}" for k in wanted) + f" {'Saiz':>9}  {'Tarikh':23}  Folder")
        for i, (path, f) in enumerate(ranked):
            row = ("  " + "".join(f"{f[k]:>8}" for k in wanted) + f" {fmt_size(f['size']):>9}  "
                   f"{fmt_date(f['first'])} - {fmt_date(f['last'])}  {path}")
            if i < 30:
                print(row)
            lines.append(row)
        if len(ranked) > 30:
            print(f"  ... dan {len(ranked) - 30} folder lagi (lihat laporan)")
    else:
        out("  Tiada fail dijumpai.")

    Path(args.laporan).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nLaporan ringkas: {Path(args.laporan).resolve()}")
    print(f"Senarai setiap fail (buka dengan Excel, boleh susun ikut tarikh): {Path(args.csv).resolve()}")

    if args.salin and recycled:
        dest, copied = copy_recycled(recycled, args.salin)
        print(f"{copied} fail dari Recycle Bin disalin ke: {dest.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan.")
        sys.exit(1)
