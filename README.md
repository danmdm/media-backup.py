# 📸 Media Backup Script

Script Python pentru backup automat de poze și videoclipuri.

## ✨ Funcționalități

- ✅ Copiază sau mută poze și videoclipuri din mai multe directoare sursă
- 🔍 Detectează duplicatele folosind hash MD5, cu **index persistent** — la rulările următoare nu recalculează hash-ul întregului backup, doar al fișierelor noi, lipsă sau modificate manual
- 📅 Redenumește fișierele folosind data din EXIF (`DateTimeOriginal`), metadata video (via `ffprobe`) sau data de modificare
- 🏷️ Suportă adăugarea unui nume de eveniment la fișiere
- 📝 Opțiune de log pentru fișierele sărite (duplicate)
- 🎯 Filtrare: doar poze sau doar videoclipuri
- 🔄 Păstrare nume originale (opțional)
- 🧪 **Mod simulare (`--dry-run`)** — arată ce s-ar copia/muta, fără să scrie sau șteargă nimic
- ✔️ **Verificare post-copiere** — recalculează hash-ul fișierului copiat înainte de a-l considera reușit; la `--move`, sursa e ștearsă doar după verificare
- 💾 **Verificare spațiu pe disc** — estimează necesarul înainte de a începe și oprește rularea dacă spațiul liber pare insuficient
- ⚡ **Procesare paralelă** — hash-urile și extragerea datei EXIF/video rulează pe mai multe thread-uri simultan, mult mai rapid pe biblioteci mari (mii de fișiere)
- 📊 Bară de progres în timp real

## 📦 Dependințe

```
sudo apt install exiftool imagemagick ffmpeg python3
```

`exiftool`, `identify` (ImageMagick) și `ffprobe` (ffmpeg) sunt opționale — dacă lipsesc, scriptul detectează asta o singură dată la pornire și trece automat pe data de modificare a fișierului.

## 🚀 Utilizare

```
python3 media_backup.py sursa1 sursa2 ... destinatie [opțiuni]
```

### Exemple

Copiere poze dintr-un singur director:
```
python3 media_backup.py ~/Pictures ~/BackupMedia
```

Copiere din mai multe directoare:
```
python3 media_backup.py ~/Pictures ~/Downloads/photos /media/usb ~/BackupMedia
```

Simulare, fără să scrie nimic pe disc (recomandat înainte de o rulare mare sau de un `--move`):
```
python3 media_backup.py ~/Pictures ~/BackupMedia --dry-run
```

Mutare (fișierele sunt șterse din sursă doar după ce copia a fost verificată):
```
python3 media_backup.py ~/Pictures ~/BackupMedia --move
```

Adăugare eveniment la numele fișierelor:
```
python3 media_backup.py ~/Pictures ~/BackupMedia --event plimbare-bicicleta
```

Log pentru fișierele sărite:
```
python3 media_backup.py ~/Pictures ~/BackupMedia --log backup.log
```

Doar poze:
```
python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only
```

Doar videoclipuri:
```
python3 media_backup.py ~/Videos ~/BackupMedia --videos-only
```

Păstrează numele originale:
```
python3 media_backup.py ~/Pictures ~/BackupMedia --keep-original-names
```

Mod verbose:
```
python3 media_backup.py ~/Pictures ~/BackupMedia -v
```

Bibliotecă mare (mii de fișiere) — mai multe thread-uri în paralel (implicit 8):
```
python3 media_backup.py ~/Pictures ~/BackupMedia --workers 16
```

## 📋 Argumente

| Argument | Descriere |
|---|---|
| `paths` | Surse și destinație (ultimul argument) |
| `-e`, `--event` | Adaugă eveniment la numele fișierelor |
| `-f`, `--date-format` | Format dată personalizat |
| `-l`, `--log` | Salvează log într-un fișier |
| `-m`, `--move` | Mută fișierele în loc să le copieze (doar după verificare) |
| `-n`, `--dry-run` | Simulează rularea, fără să scrie/șteargă/mute niciun fișier real |
| `-j`, `--workers` | Nr. de thread-uri pentru hash și extragere dată în paralel (implicit: 8) |
| `-v`, `--verbose` | Afișează detalii per fișier |
| `-k`, `--keep-original-names` | Păstrează numele originale |
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

## 🗂️ Indexul de hash-uri

La fiecare rulare, scriptul salvează un fișier `.hash_index.json` în directorul de backup, cu hash-ul, data modificării și dimensiunea fiecărui fișier deja salvat. La rulările următoare:

- fișierele neschimbate sunt recunoscute instant, fără să fie recitite de pe disc;
- dacă un fișier a fost modificat manual direct în backup, e detectat (prin dimensiune/dată modificare) și hash-ul e recalculat doar pentru el;
- dacă un fișier a fost șters manual din backup, intrarea corespunzătoare e eliminată din index, iar fișierul poate fi recopiat automat din sursă la rularea următoare.

Indexul nu se salvează în modul `--dry-run`.

## ⚠️ Note de siguranță

- La `--move`, fișierul e întotdeauna **copiat și verificat** înainte ca originalul din sursă să fie șters — dacă verificarea eșuează, sursa rămâne neatinsă.
- Dacă spațiul liber estimat e insuficient, rularea reală se oprește automat înainte de a scrie ceva; folosește `--dry-run` pentru o estimare fără riscuri.
- Fișierele din directorul de backup sunt considerate gestionate de script — modificările manuale sunt detectate, dar comportamentul e gândit pentru un backup automat, nu pentru editare manuală în paralel.

---

Creat cu ❤️ pentru organizarea pozelor și videoclipurilor
<img width="2058" height="616" alt="image" src="https://github.com/user-attachments/assets/391c2a7a-fa28-419b-8f3c-711cc7aad280" />

