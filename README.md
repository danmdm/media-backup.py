# 📸 Media Backup Script

Script Python pentru backup automat de poze și videoclipuri.

---

## ✨ Funcționalități

✅ Copiază sau mută poze și videoclipuri din mai multe directoare sursă

🔍 Detectează duplicatele folosind hash MD5. 

📅 Redenumește fișierele folosind data din EXIF (DateTimeOriginal) sau data de modificare
🏷️ Suportă adăugarea unui nume de eveniment la fișiere
📝 Opțiune de log pentru fișierele sărite (duplicate)
🎯 Filtrare: doar poze sau doar videoclipuri
🔄 Păstrare nume originale (opțional)

---

## 📦 Dependințe

`sudo apt install exiftool imagemagick ffmpeg python3`

---

## 🚀 Utilizare

`python3 media_backup.py sursa1 sursa2 ... destinatie [opțiuni]`



Exemple

Copiere poze dintr-un singur director:

`python3 media_backup.py ~/Pictures ~/BackupMedia`

Copiere din mai multe directoare:

`python3 media_backup.py ~/Pictures ~/Downloads/photos /media/usb ~/BackupMedia`

Mutare (șterge fișierele din sursă după copiere):

`python3 media_backup.py ~/Pictures ~/BackupMedia --move`

Adăugare eveniment la numele fișierelor:

`python3 media_backup.py ~/Pictures ~/BackupMedia --event plimbare-bicicleta`

Log pentru fișierele sărite:

`python3 media_backup.py ~/Pictures ~/BackupMedia --log backup.log`

Doar poze:

`python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only`

Doar videoclipuri:

`python3 media_backup.py ~/Videos ~/BackupMedia --videos-only`

Păstrează numele originale:

`python3 media_backup.py ~/Pictures ~/BackupMedia --keep-original-names`

Mod verbose: 

`python3 media_backup.py ~/Pictures ~/BackupMedia -v`

## 📋Argumente
---

| Argument                    | Descriere                              |
| --------------------------- | -------------------------------------- |
| `paths`                     | Surse și destinație (ultimul argument) |
| `-e, --event`               | Adaugă eveniment la numele fișierelor  |
| `-f, --date-format`         | Format dată personalizat               |
| `-l, --log`                 | Salvează log într-un fișier            |
| `-m, --move`                | Mută fișierele în loc să le copieze    |
| `-v, --verbose`             | Afișează detalii                       |
| `-k, --keep-original-names` | Păstrează numele originale             |
| `--photos-only`             | Doar poze                              |
| `--videos-only`             | Doar videoclipuri                      |

---

## 📅 Format dată

Implicit: `%Y_%m_%d_%H%M%S` → `2024_08_10_153045.jpg`

| Format     | Rezultat          |
| ---------- | ----------------- |
| `%Y_%m_%d` | `2024_08_10.jpg`  |
| `%Y-%m-%d` | `2024-08-10.jpg`  |
| `%d_%m_%Y` | `10_08_2024.jpg`  |
| `%Y%m%d`   | `20240810.jpg`    |
| `%B_%Y`    | `August_2024.jpg` |

---

**Creat cu ❤️ pentru organizarea pozelor și videoclipurilor**
