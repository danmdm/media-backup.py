# ============================================
# MEDIA BACKUP SCRIPT
# ============================================

Script Python pentru backup automat de poze si videoclipuri.


# ============================================
# FUNCȚIONALITĂȚI
# ============================================

- Detectare duplicate prin hash MD5
- Extragere data din EXIF (poze) si metadata (video)
- Adaugare evenimente la numele fisierelor
- Organizare automata in backup
- Log detaliat (optional)
- Filtrare: doar poze sau doar videoclipuri
- Pastrare nume originale (optional)


# ============================================
# DEPENDINȚE
# ============================================

sudo apt install exiftool imagemagick ffmpeg python3


# ============================================
# UTILIZARE
# ============================================

COMENZI DE BAZĂ:

  Backup simplu:
    python3 media_backup.py ~/Pictures ~/BackupMedia

  Backup cu eveniment:
    python3 media_backup.py ~/Pictures ~/BackupMedia --event plimbare-bicicleta

  Backup cu eveniment + log:
    python3 media_backup.py ~/Pictures ~/BackupMedia -e "gratar-munte" -l backup.log

  Format personalizat:
    python3 media_backup.py ~/Pictures ~/BackupMedia -e vacanta -f "%Y_%m_%d"

  Doar poze:
    python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only

  Doar videoclipuri:
    python3 media_backup.py ~/Videos ~/BackupMedia --videos-only

  Pastreaza numele originale:
    python3 media_backup.py ~/Pictures ~/BackupMedia --keep-original-names

  Mod verbose (detalii):
    python3 media_backup.py ~/Pictures ~/BackupMedia -v


# ============================================
# ARGUMENTE
# ============================================

  paths                    Surse si destinatie (ultimul argument)
  -e, --event              Adauga eveniment la numele fisierelor
  -f, --date-format        Format data personalizat
  -l, --log                Salveaza log intr-un fisier
  -v, --verbose            Afiseaza detalii
  -k, --keep-original-names Pastreaza numele originale
  --photos-only            Doar poze
  --videos-only            Doar videoclipuri


# ============================================
# FORMAT DATĂ
# ============================================

Implicit: %Y_%m_%d_%H_%M_%S -> 2024_08_10_15_30_45.jpg

Alte formate:
  %Y_%m_%d        -> 2024_08_10.jpg
  %Y-%m-%d        -> 2024-08-10.jpg
  %d_%m_%Y        -> 10_08_2024.jpg
  %Y%m%d          -> 20240810.jpg
  %B_%Y           -> August_2024.jpg


# ============================================
# EXEMPLE PRACTICE
# ============================================

Poze din 2012 - plimbare cu bicicleta:
  cd ~/Pictures/Poze/Anul\ 2012/
  python3 ~/media_backup.py . /media/backup/Poze/ -e plimbare-bicicleta

Poze din 2012 - gratar la munte:
  cd ~/Pictures/Poze/Anul\ 2012/
  python3 ~/media_backup.py . /media/backup/Poze/ -e gratar-munte

Backup saptamanal automat:
  #!/bin/bash
  DATE=$(date +%Y_%m_%d)
  python3 ~/media_backup.py ~/Pictures ~/Videos /media/backup/ -l "backup_$DATE.log"


# ============================================
# DEPANARE
# ============================================

  sudo apt install exiftool
  sudo apt install imagemagick
  sudo apt install ffmpeg
  chmod +x media_backup.py


# ============================================
# LICENȚĂ
# ============================================

MIT License


# ============================================
# CREAT CU ❤️ PENTRU ORGANIZAREA POZELOR
# ============================================
