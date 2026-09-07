Media Backup Script

Script Python pentru backup automat de poze si videoclipuri cu detectare duplicate si organizare inteligenta.

Funcționalitati:
- Detectare duplicate - foloseste hash MD5 pentru a evita copierea fisierelor existente
- Extragere data EXIF - pentru poze (foloseste exiftool sau identify)
- Extragere metadata video - pentru videoclipuri (foloseste ffprobe)
- Adaugare evenimente - poti adauga evenimente la numele fisierelor (--event)
- Organizare automata - redenumeste fisierele dupa data lor reala
- Log detaliat - optional, salveaza toate operatiile intr-un fisier
- Suport pentru filtre - poti procesa doar poze sau doar videoclipuri
- Pastrare nume originale - optional, poti pastra numele original

Dependinte:
sudo apt install exiftool imagemagick ffmpeg python3

Utilizare:

Backup simplu:
python3 media_backup.py ~/Pictures ~/Videos ~/BackupMedia

Cu eveniment:
python3 media_backup.py ~/Pictures ~/BackupMedia --event plimbare-bicicleta

Cu eveniment + log:
python3 media_backup.py ~/Pictures ~/BackupMedia -e "gratar-munte" -l backup.log

Format personalizat:
python3 media_backup.py ~/Pictures ~/BackupMedia -e vacanta -f "%Y_%m_%d"

Doar poze:
python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only

Doar videoclipuri:
python3 media_backup.py ~/Videos ~/BackupMedia --videos-only

Pastreaza numele originale:
python3 media_backup.py ~/Pictures ~/BackupMedia --keep-original-names

Mod verbose:
python3 media_backup.py ~/Pictures ~/BackupMedia -v

Argumente:
paths - Surse si destinatie (ultimul argument)
-e, --event - Adauga un eveniment la numele fisierelor
-f, --date-format - Format data personalizat (implicit: %Y_%m_%d_%H_%M_%S)
-l, --log - Salveaza log-ul intr-un fisier
-v, --verbose - Afiseaza informatii detaliate
-k, --keep-original-names - Pastreaza numele originale ale fisierelor
--photos-only - Proceseaza doar fisiere imagine
--videos-only - Proceseaza doar fisiere video

Format data:
%Y_%m_%d_%H_%M_%S -> 2024_08_10_15_30_45.jpg
%Y_%m_%d -> 2024_08_10.jpg
%Y-%m-%d -> 2024-08-10.jpg
%d_%m_%Y -> 10_08_2024.jpg
%Y%m%d -> 20240810.jpg
%B_%Y -> August_2024.jpg

Exemple practice:

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

Depanare:
sudo apt install exiftool
sudo apt install imagemagick
sudo apt install ffmpeg
chmod +x media_backup.py

Licenta: MIT

Creat cu ❤️ pentru organizarea pozelor si videoclipurilor
