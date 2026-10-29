#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python belum dipasang. Muat turun dari https://www.python.org/downloads/"
  open https://www.python.org/downloads/
  read -r -p "Tekan Enter untuk tutup..."
  exit 1
fi
echo "Menyediakan sokongan backup ber-password..."
python3 -m pip install --quiet --user iphone_backup_decrypt >/dev/null 2>&1
python3 iphone_backup_extract.py "$@"
echo
read -r -p "Tekan Enter untuk tutup..."
