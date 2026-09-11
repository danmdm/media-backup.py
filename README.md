# 📸 Media Backup Script

Script Python pentru backup automat de poze și videoclipuri.

## ✨ Funcționalități

- ✅ Copiază sau mută poze și videoclipuri dintr-un director sursă, opțional recursiv (`--recursive`)
- 🔍 Detectează duplicatele folosind hash MD5, cu **index persistent** — la rulările următoare nu recalculează hash-ul întregului backup, doar al fișierelor noi, lipsă sau modificate manual
- 📅 Redenumește fișierele folosind data din EXIF (`DateTimeOriginal`), metadata video (via `ffprobe`) sau data de modificare
- 🏷️ Adaugă un eveniment la numele fișierelor — manual (`--event`) sau **extras automat din numele folderului** (`--event-from-folder`)
- 🧼 **Sanitizare automată** a numelui de eveniment: diacritice și alte caractere unicode transliterate în ASCII, caractere interzise pe Windows înlocuite, nume rezervate (`CON`, `COM1` etc.) evitate, trunchiere la 100 caractere
- 📝 Opțiune de log pentru fișierele sărite (duplicate)
- 🎯 Filtrare: doar poze sau doar videoclipuri
- 🔄 Păstrare nume originale (opțional)
- 🧪 **Mod simulare (`--dry-run`)** — arată ce s-ar copia/muta, fără să scrie sau șteargă nimic
- ✔️ **Verificare post-copiere** — recalculează hash-ul fișierului copiat înainte de a-l considera reușit; la `--move`, sursa e ștearsă doar după verificare
- 💾 **Verificare spațiu pe disc** — estimează necesarul (doar pentru fișierele noi, nu și duplicatele) și oprește rularea dacă spațiul liber pare insuficient
- ⚡ **Procesare paralelă** — hash-urile și extragerea datei EXIF/video rulează pe mai multe thread-uri simultan, mult mai rapid pe biblioteci mari (mii de fișiere)
- 📊 Bară de progres în timp real
- 🛡️ Ignoră symlink-urile la scanare; refuză să ruleze dacă sursa și destinația sunt același director

## 📦 Dependințe

```
sudo apt install exiftool imagemagick ffmpeg python3
```

`exiftool`, `identify` (ImageMagick) și `ffprobe` (ffmpeg) sunt opționale — dacă lipsesc, scriptul detectează asta o singură dată la pornire și trece automat pe data de modificare a fișierului.

## 🚀 Utilizare

```
python3 media_backup.py sursă destinație [opțiuni]
```

> Notă: scriptul procesează **un singur director sursă**. Pentru sub-foldere, folosește `--recursive`.

### Exemple

Backup simplu (doar fișierele directe din sursă):
```
python3 media_backup.py ~/Poze/Vacanta ~/Backup
```

Recursiv, tot arborele de foldere:
```
python3 media_backup.py ~/Poze ~/Backup --recursive
```

Extrage automat evenimentul din numele folderului sursă:
```
python3 media_backup.py ~/Poze/Vacanta_Grecia ~/Backup --event-from-folder
```

Recursiv, cu eveniment extras din fiecare sub-folder parcurs:
```
python3 media_backup.py ~/Poze ~/Backup --recursive --event-from-folder
```

Eveniment manual (sanitizat automat — diacritice, spații, caractere interzise):
```
python3 media_backup.py ~/Poze ~/Backup --event "Vacanță: Grecia"
```

Simulare, fără să scrie nimic pe disc (recomandat înainte de o rulare mare sau de un `--move`):
```
python3 media_backup.py ~/Poze ~/Backup --dry-run
```

Mutare (fișierele sunt șterse din sursă doar după ce copia a fost verificată), cu event din folder:
```
python3 media_backup.py ~/Poze/Vacanta ~/Backup --move --event-from-folder
```

Log pentru fișierele sărite:
```
python3 media_backup.py ~/Poze ~/Backup --log backup.log
```

Doar poze / doar videoclipuri:
```
python3 media_backup.py ~/Poze ~/Backup --photos-only
python3 media_backup.py ~/Videos ~/Backup --videos-only
```

Păstrează numele originale (ignoră evenimentul):
```
python3 media_backup.py ~/Poze ~/Backup --keep-original-names
```

Format de dată personalizat:
```
python3 media_backup.py ~/Poze ~/Backup --date-format "%Y-%m-%d"
```

Mod verbose:
```
python3 media_backup.py ~/Poze ~/Backup -v
```

Bibliotecă mare (mii de fișiere) — mai multe thread-uri în paralel (implicit 8):
```
python3 media_backup.py ~/Poze ~/Backup --recursive --workers 16
```

## 📋 Argumente

| Argument | Descriere |
|---|---|
| `source` | Directorul sursă (unul singur) |
| `backup_dir` | Directorul destinație |
| `-r`, `--recursive` | Procesează recursiv tot arborele sursei (implicit: doar fișierele directe) |
| `-e`, `--event` | Adaugă un eveniment la numele fișierelor (sanitizat automat) |
| `--event-from-folder` | Extrage evenimentul din numele folderului (mutual exclusiv cu `--event`) |
| `-f`, `--date-format` | Format dată personalizat (refuzat dacă produce `/` sau `\`) |
| `-l`, `--log` | Salvează log într-un fișier |
| `-m`, `--move` | Mută fișierele în loc să le copieze (doar după verificare) |
| `-n`, `--dry-run` | Simulează rularea, fără să scrie/șteargă/mute niciun fișier real |
| `-j`, `--workers` | Nr. de thread-uri pentru hash și extragere dată în paralel (implicit: 8) |
| `-v`, `--verbose` | Afișează detalii per fișier |
| `-k`, `--keep-original-names` | Păstrează numele originale (ignoră evenimentul) |
| `--photos-only` | Doar poze |
| `--videos-only` | Doar videoclipuri |

## 📅 Format dată

Implicit: `%Y_%m_%d_%H%M%S` → `2024_08_10_153045.jpg`

| Format | Rezultat |
|---|---|
| `%Y_%m_%d` | `2024_08_10.jpg` |
| `%Y-%m-%d` | `2024-08-10.jpg` |
| `%d_%m_%Y` | `10_08_2024.jpg` |
| `%Y%m%d` | `20240810.jpg` |
| `%B_%Y` | `August_2024.jpg` |

Un format care ar produce separatori de cale (`/` sau `\`) e refuzat la pornire, ca să nu spargă structura de foldere din destinație.

## 🏷️ Evenimente și sanitizare

- `--event NUME` — folosește `NUME` ca eveniment pentru toate fișierele din rulare.
- `--event-from-folder` — evenimentul e extras din calea fișierului:
  - **fără** `--recursive`: numele folderului sursă;
  - **cu** `--recursive`: numele folderului sursă + sub-folderele intermediare, concatenate (util ca fișierele din sub-foldere diferite să primească evenimente diferite, dar traceable la sursă).
- Orice text de eveniment (manual sau extras) trece prin sanitizare: spațiile devin `_`, diacriticele și alte caractere unicode sunt transliterate în ASCII (`ă`→`a`, `ș`→`s` etc.), caracterele interzise pe Windows sunt înlocuite, numele rezervate (`CON`, `PRN`, `COM1`...) sunt prefixate, iar rezultatul e trunchiat la 100 caractere. Dacă sanitizarea schimbă textul, scriptul afișează un mesaj informativ cu forma inițială și cea finală.
- `--event` și `--event-from-folder` sunt mutual exclusive.

## 🗂️ Indexul de hash-uri

La fiecare rulare, scriptul salvează un fișier `.hash_index.json` în directorul de backup, cu hash-ul, data modificării și dimensiunea fiecărui fișier deja salvat. La rulările următoare:

- fișierele neschimbate sunt recunoscute instant, fără să fie recitite de pe disc;
- dacă un fișier a fost modificat manual direct în backup, e detectat (prin dimensiune/dată modificare) și hash-ul e recalculat doar pentru el;
- dacă un fișier a fost șters manual din backup, intrarea corespunzătoare e eliminată din index, iar fișierul poate fi recopiat automat din sursă la rularea următoare.

Indexul nu se salvează în modul `--dry-run`.

## ⚠️ Note de siguranță

- Sursa și destinația nu pot fi același director — scriptul refuză să pornească.
- La `--move`, fișierul e întotdeauna **copiat și verificat** înainte ca originalul din sursă să fie șters — dacă verificarea eșuează, sursa rămâne neatinsă.
- Spațiul liber e verificat doar pentru fișierele noi (după filtrarea duplicatelor); dacă e insuficient, rularea reală se oprește automat înainte de a scrie ceva. Folosește `--dry-run` pentru o estimare fără riscuri.
- Symlink-urile sunt ignorate atât în sursă, cât și la scanarea backup-ului.
- Fișierele din directorul de backup sunt considerate gestionate de script — modificările manuale sunt detectate, dar comportamentul e gândit pentru un backup automat, nu pentru editare manuală în paralel.

---

Creat cu ❤️ pentru organizarea pozelor și videoclipurilor
