# iPhone Backup Extractor

Tool ini mengeluarkan **gambar, video dan fail lama** dari backup iPhone yang tersimpan dalam
komputer (iTunes, Finder atau app Apple Devices), **tanpa perlu restore atau erase iPhone**.

Ia sesuai kalau gambar dah lama dipadam dari iPhone (lebih 30 hari, dah tiada dalam
"Recently Deleted") tetapi kau pernah backup iPhone ke laptop atau PC sebelum gambar tu dipadam.

> ⚠️ Tool ini **tidak boleh** scan iPhone secara terus untuk cari fail yang dipadam. iPhone
> encrypt storage dia, jadi tiada software yang boleh buat begitu dengan boleh dipercayai. Tool
> ini cuma membaca **backup yang dah sedia ada** dalam komputer.

## Apa yang dikeluarkan

| Kategori    | Isi                                                     |
|-------------|---------------------------------------------------------|
| `kamera`    | Camera Roll: gambar & video dalam app Photos            |
| `imessage`  | Gambar, video & dokumen yang dihantar/diterima di iMessage/SMS |
| `whatsapp`  | Media WhatsApp                                          |
| `fail`      | App Files, bahagian "On My iPhone"                      |
| `voicememo` | Rakaman Voice Memos                                     |
| `lain`      | Gambar/video dari app lain (Telegram dsb.). Tak termasuk secara default sebab banyak cache |

Hasil disimpan dalam folder `iPhone_Recovered/<nama iPhone> <tarikh backup>/<kategori>/`.
Tarikh asal fail dikekalkan, jadi kau boleh susun ikut tarikh.

## Cara guna

### 1. Pasang Python
- **Windows**: muat turun dari <https://www.python.org/downloads/>. Masa install, tanda
  **"Add Python to PATH"**.
- **Mac**: buka Terminal dan taip `python3`. Kalau belum ada, Mac akan tawarkan untuk install.

### 2. Muat turun tool ini
Muat turun `iphone_backup_extract.py` dari repo ini (butang **Code → Download ZIP**, kemudian extract).

### 3. Jalankan
Buka **Command Prompt** (Windows) atau **Terminal** (Mac) dalam folder tersebut, kemudian:

```bash
# Tengok backup apa yang ada dalam komputer
python iphone_backup_extract.py --senarai

# Keluarkan semua (akan tanya pilih backup kalau ada lebih dari satu)
python iphone_backup_extract.py

# Hanya gambar kamera & WhatsApp, simpan ke folder lain
python iphone_backup_extract.py --kategori kamera,whatsapp --out D:\GambarLama

# Termasuk gambar dari app lain
python iphone_backup_extract.py --kategori kamera,imessage,whatsapp,fail,voicememo,lain
```

Di Mac guna `python3` sebagai ganti `python`.

### Backup ber-password (encrypted)
Kalau backup kau ada password ("Encrypt local backup"), pasang library tambahan dulu:

```bash
pip install iphone_backup_decrypt
```

Tool akan tanya password tu. Password ni ialah password backup yang kau set dalam
iTunes/Finder, **bukan** passcode iPhone atau password Apple ID.

## Di mana backup disimpan

Tool ni cari backup di tempat-tempat ini secara automatik:

- **Windows (iTunes dari Microsoft Store / Apple Devices)**: `%USERPROFILE%\Apple\MobileSync\Backup`
- **Windows (iTunes dari apple.com)**: `%APPDATA%\Apple Computer\MobileSync\Backup`
- **Mac**: `~/Library/Application Support/MobileSync/Backup`

Kalau backup ada di tempat lain (contohnya hard disk luar), guna `--backup "E:\folder\backup"`.

**Mac:** kalau keluar mesej tiada backup walaupun ada, beri Terminal kebenaran
**Full Disk Access** di System Settings → Privacy & Security → Full Disk Access.

## Kenapa Camera Roll kosong?

Kalau **iCloud Photos** dihidupkan masa backup dibuat, gambar disimpan dalam iCloud dan
bukan dalam backup. Untuk kes ini, semak icloud.com → Photos → Recently Deleted (30 hari sahaja).
Lampiran iMessage dan WhatsApp masih mungkin ada dalam backup tu.

## Tips penting

- **Jangan sync iPhone ke komputer tu dulu.** Backup baru boleh tulis ganti backup lama, dan
  gambar yang dah dipadam akan hilang dari backup sekali.
- Tool ni hanya **membaca** backup. Backup asal tidak diubah.
