Media Backup Script

Script Python pentru backup automat de poze și videoclipuri cu detectare duplicate.
Funcționalități

    Detectare duplicate prin hash MD5

    Extragere data din EXIF (poze) și metadata (video)

    Adăugare evenimente la numele fișierelor (--event)

    Organizare automată în backup

    Log detaliat (opțional)

    Filtrare: doar poze sau doar videoclipuri

    Păstrare nume originale (opțional)

Dependințe
text

sudo apt install exiftool imagemagick ffmpeg python3

Utilizare
text

# Backup simplu
python3 media_backup.py ~/Pictures ~/BackupMedia

# Backup cu eveniment
python3 media_backup.py ~/Pictures ~/BackupMedia --event plimbare-bicicleta

# Backup cu eveniment + log
python3 media_backup.py ~/Pictures ~/BackupMedia -e "gratar-munte" -l backup.log

# Format personalizat
python3 media_backup.py ~/Pictures ~/BackupMedia -e vacanta -f "%Y_%m_%d"

# Doar poze
python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only

# Doar videoclipuri
python3 media_backup.py ~/Videos ~/BackupMedia --videos-only

# Păstrează numele originale
python3 media_backup.py ~/Pictures ~/BackupMedia --keep-original-names

# Mod verbose
python3 media_backup.py ~/Pictures ~/BackupMedia -v

Argumente
Argument	Descriere
paths	Surse și destinație (ultimul argument)
-e, --event	Adaugă eveniment la numele fișierelor
-f, --date-format	Format dată personalizat
-l, --log	Salvează log într-un fișier
-v, --verbose	Afișează detalii
-k, --keep-original-names	Păstrează numele originale
--photos-only	Doar poze
--videos-only	Doar videoclipuri
Format dată

Implicit: %Y_%m_%d_%H_%M_%S -> 2024_08_10_15_30_45.jpg
Format	Rezultat
%Y_%m_%d	2024_08_10.jpg
%Y-%m-%d	2024-08-10.jpg
%d_%m_%Y	10_08_2024.jpg
%Y%m%d	20240810.jpg
%B_%Y	August_2024.jpg
Exemple practice
text

# Poze din 2012 - plimbare cu bicicleta
cd ~/Pictures/Poze/Anul\ 2012/
python3 ~/media_backup.py . /media/backup/Poze/ -e plimbare-bicicleta

# Backup săptămânal automat
DATE=$(date +%Y_%m_%d)
python3 ~/media_backup.py ~/Pictures ~/Videos /media/backup/ -l "backup_$DATE.log"

Depanare
text

sudo apt install exiftool imagemagick ffmpeg
chmod +x media_backup.py

Licență

MIT

Creat cu ❤️ pentru organizarea pozelor și videoclipurilor
