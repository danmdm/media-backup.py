#!/usr/bin/env python3
"""
Script de backup pentru poze și videoclipuri
Fișierele sărite apar doar în log dacă specifici --log
"""

import os
import hashlib
import shutil
import sys
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime
import logging

class MediaBackup:
    def __init__(self, source_dirs, backup_dir, log_file=None, verbose=False, event=None, move=False):
        self.source_dirs = [Path(d) for d in source_dirs]
        self.backup_dir = Path(backup_dir)
        self.verbose = verbose
        self.log_file = log_file
        self.event = event  # Evenimentul de adăugat
        self.move = move  # True = mută, False = copiază (implicit)
        
        # Extensii pentru poze
        self.photo_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', 
                                '.tiff', '.raw', '.cr2', '.nef', '.arw', 
                                '.dng', '.heic', '.webp', '.svg', '.ico'}
        
        # Extensii pentru videoclipuri
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', 
                                '.flv', '.webm', '.m4v', '.mpg', '.mpeg', 
                                '.3gp', '.3g2', '.mts', '.m2ts', '.ts', 
                                '.vob', '.ogv', '.divx'}
        
        self.media_extensions = self.photo_extensions | self.video_extensions
        
        # Verifică disponibilitatea ffprobe
        self.ffprobe_available = self.check_ffprobe()
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        
        if log_file:
            # Logging în fișier + consolă
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler(sys.stdout)
                ]
            )
        else:
            # Doar consolă
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.StreamHandler(sys.stdout)]
            )
        
        self.existing_hashes = {}
        self.skipped_files = []  # Listă în memorie pentru fișierele sărite
        self.stats = {'photos': 0, 'videos': 0, 'exif_date': 0, 
                     'video_metadata': 0, 'file_date': 0, 'current_date': 0,
                     'skipped': 0, 'copied': 0, 'moved': 0}
    
    def check_ffprobe(self):
        """Verifică dacă ffprobe este disponibil"""
        try:
            result = subprocess.run(['ffprobe', '-version'], 
                                   capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def calculate_md5(self, file_path, chunk_size=8192):
        """Calculează hash-ul MD5 pentru un fișier"""
        md5_hash = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            logging.error(f"Eroare la calcularea MD5 pentru {file_path}: {e}")
            return None
    
    def get_photo_date_exif(self, file_path):
        """Extrage data EXIF folosind exiftool sau identify din ImageMagick"""
        try:
            result = subprocess.run(
                ['exiftool', '-DateTimeOriginal', '-d', '%Y-%m-%d %H:%M:%S', 
                 '-s', '-s', '-s', str(file_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                date_str = result.stdout.strip()
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except:
                    pass
        except:
            pass
        
        try:
            result = subprocess.run(
                ['identify', '-format', '%[EXIF:DateTimeOriginal]', str(file_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                date_str = result.stdout.strip()
                try:
                    return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except:
                    try:
                        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    except:
                        pass
        except:
            pass
        
        return None
    
    def get_video_date_ffprobe(self, file_path):
        """Extrage data creării din metadata video folosind ffprobe"""
        if not self.ffprobe_available:
            return None
        
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_entries', 'format_tags=creation_time',
                 str(file_path)],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                format_tags = data.get('format', {}).get('tags', {})
                
                for key in ['creation_time', 'date', 'com.apple.quicktime.creationdate']:
                    if key in format_tags:
                        date_str = format_tags[key]
                        for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ',
                                   '%Y-%m-%dT%H:%M:%SZ',
                                   '%Y-%m-%d %H:%M:%S',
                                   '%Y-%m-%dT%H:%M:%S']:
                            try:
                                clean_date = date_str.split('.')[0].replace('Z', '')
                                return datetime.strptime(clean_date, fmt.replace('.%f', ''))
                            except:
                                continue
        except Exception as e:
            logging.debug(f"Eroare la citirea metadata video: {e}")
        
        return None
    
    def get_media_date(self, file_path):
        """Determină data pentru fișierul media"""
        is_photo = file_path.suffix.lower() in self.photo_extensions
        is_video = file_path.suffix.lower() in self.video_extensions
        
        if is_photo:
            self.stats['photos'] += 1
            exif_date = self.get_photo_date_exif(file_path)
            if exif_date:
                self.stats['exif_date'] += 1
                return exif_date
        elif is_video:
            self.stats['videos'] += 1
            video_date = self.get_video_date_ffprobe(file_path)
            if video_date:
                self.stats['video_metadata'] += 1
                return video_date
        
        try:
            mtime = os.path.getmtime(file_path)
            self.stats['file_date'] += 1
            return datetime.fromtimestamp(mtime)
        except:
            pass
        
        self.stats['current_date'] += 1
        return datetime.now()
    
    def generate_filename(self, file_path, media_date):
        """Generează numele fișierului bazat pe dată și eveniment"""
        extension = file_path.suffix.lower()
        # Format implicit: YYYY_mm_dd_HHMMSS
        base_name = media_date.strftime("%Y_%m_%d_%H%M%S")
        
        # Dacă avem eveniment, îl adăugăm la nume
        if self.event:
            dest_name = f"{base_name}_{self.event}{extension}"
        else:
            dest_name = f"{base_name}{extension}"
        
        dest_path = self.backup_dir / dest_name
        
        counter = 1
        while dest_path.exists():
            if self.event:
                dest_name = f"{base_name}_{self.event}_{counter}{extension}"
            else:
                dest_name = f"{base_name}_{counter}{extension}"
            dest_path = self.backup_dir / dest_name
            counter += 1
        
        return dest_name, dest_path
    
    def scan_existing_backup(self):
        """Scanează backup-ul existent pentru hash-uri"""
        logging.info("Scanare backup existent...")
        
        if not self.backup_dir.exists():
            return
        
        file_count = 0
        for file_path in self.backup_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.media_extensions:
                file_hash = self.calculate_md5(file_path)
                if file_hash:
                    self.existing_hashes[file_hash] = file_path
                    file_count += 1
        
        logging.info(f"Găsite {file_count} fișiere media în backup")
    
    def backup_media(self):
        """Realizează backup-ul fișierelor media (copiere sau mutare)"""
        self.scan_existing_backup()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        total_copied = 0
        total_skipped = 0
        total_errors = 0
        total_moved = 0
        
        # Afișează evenimentul dacă există
        if self.event:
            logging.info(f"🏷️  Eveniment adăugat: {self.event}")
        
        # Afișează modul de operare
        if self.move:
            logging.info("📦 Mod: MUTARE (fișierele vor fi mutate din sursă)")
        else:
            logging.info("📋 Mod: COPIERE (fișierele rămân în sursă)")
        
        for source_dir in self.source_dirs:
            if not source_dir.exists():
                logging.warning(f"Directorul {source_dir} nu există!")
                continue
            
            logging.info(f"Procesare director: {source_dir}")
            
            for file_path in source_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix.lower() not in self.media_extensions:
                    continue
                
                try:
                    # Calculează hash
                    file_hash = self.calculate_md5(file_path)
                    if not file_hash:
                        total_errors += 1
                        continue
                    
                    # Verifică duplicate
                    if file_hash in self.existing_hashes:
                        total_skipped += 1
                        self.stats['skipped'] += 1
                        
                        # Salvează în memorie pentru log
                        self.skipped_files.append({
                            'filename': file_path.name,
                            'full_path': str(file_path),
                            'source_dir': str(source_dir),
                            'hash': file_hash,
                            'existing_in_backup': str(self.existing_hashes[file_hash].name)
                        })
                        
                        # Loghează doar în fișier dacă există --log
                        if self.log_file:
                            logging.info(f"Sărit (duplicat): {file_path.name} -> {self.existing_hashes[file_hash].name}")
                        continue
                    
                    # Determină data
                    media_date = self.get_media_date(file_path)
                    
                    # Generează nume
                    dest_name, dest_path = self.generate_filename(file_path, media_date)
                    
                    # Copiază sau mută fișierul
                    if self.move:
                        shutil.move(str(file_path), str(dest_path))
                        operation = "Mutat"
                        total_moved += 1
                        self.stats['moved'] += 1
                    else:
                        shutil.copy2(file_path, dest_path)
                        operation = "Copiat"
                        total_copied += 1
                        self.stats['copied'] += 1
                    
                    # Actualizează hash-urile
                    self.existing_hashes[file_hash] = dest_path
                    
                    # Logging
                    icon = "📷" if file_path.suffix.lower() in self.photo_extensions else "🎬"
                    if self.verbose:
                        logging.info(f"{icon} {operation}: {file_path.name} -> {dest_name} ({media_date.strftime('%Y-%m-%d %H:%M:%S')})")
                    else:
                        logging.info(f"{icon} {operation}: {file_path.name} -> {dest_name}")
                    
                except Exception as e:
                    logging.error(f"Eroare la {file_path}: {e}")
                    total_errors += 1
        
        # Rezumat
        logging.info("=" * 60)
        logging.info("BACKUP COMPLETAT")
        logging.info(f"📷 Poze: {self.stats['photos']}, 🎬 Videoclipuri: {self.stats['videos']}")
        
        if self.move:
            logging.info(f"📦 Mutate: {total_moved}, ⏭️  Sărite: {total_skipped}, ❌ Erori: {total_errors}")
        else:
            logging.info(f"✅ Copiate: {total_copied}, ⏭️  Sărite: {total_skipped}, ❌ Erori: {total_errors}")
        
        if self.event:
            logging.info(f"🏷️  Eveniment: {self.event}")
        
        if self.verbose:
            logging.info(f"Surse dată: EXIF={self.stats['exif_date']}, "
                        f"Video={self.stats['video_metadata']}, "
                        f"Fișier={self.stats['file_date']}, "
                        f"Curent={self.stats['current_date']}")
        
        logging.info("=" * 60)
        
        # Scrie fișierele sărite DOAR în fișierul de log dacă există
        if self.log_file and self.skipped_files:
            self.write_skipped_to_log()
        
        return total_copied, total_skipped, total_errors
    
    def write_skipped_to_log(self):
        """Scrie fișierele sărite în fișierul de log"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FIȘIERE SĂRITE (DUPLICATE)\n")
                f.write("=" * 80 + "\n\n")
                
                # Grupează pe directoare
                current_source = None
                for skipped in self.skipped_files:
                    if skipped['source_dir'] != current_source:
                        current_source = skipped['source_dir']
                        f.write(f"\n📁 Director sursă: {current_source}\n")
                        f.write("-" * 60 + "\n")
                    
                    f.write(f"  • {skipped['filename']}\n")
                    f.write(f"    → există deja ca: {skipped['existing_in_backup']}\n")
                
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Total fișiere sărite: {len(self.skipped_files)}\n")
                f.write("=" * 80 + "\n")
                
        except Exception as e:
            logging.error(f"Eroare la scrierea în log: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Backup media cu MD5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemple:
  # Backup simplu (copiere)
  python3 media_backup.py ~/Pictures ~/Videos ~/BackupMedia

  # Mutare (șterge din sursă)
  python3 media_backup.py ~/Pictures ~/BackupMedia --move

  # Cu eveniment și mutare
  python3 media_backup.py ~/Pictures ~/BackupMedia --move --event plimbare-bicicleta

  # Cu log
  python3 media_backup.py ~/Pictures ~/BackupMedia --log backup.log

  # Doar poze
  python3 media_backup.py ~/Pictures ~/BackupMedia --photos-only
        """
    )
    
    parser.add_argument('paths', nargs='+', 
                       help='Surse și destinație (ultimul argument)')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Mod verbose')
    parser.add_argument('--log', '-l', 
                       help='Fișier de log (opțional)')
    parser.add_argument('--move', '-m', action='store_true',
                       help='Mută fișierele în loc să le copieze')
    parser.add_argument('--photos-only', action='store_true', 
                       help='Procesează doar poze')
    parser.add_argument('--videos-only', action='store_true', 
                       help='Procesează doar videoclipuri')
    parser.add_argument('--keep-original-names', '-k', action='store_true',
                       help='Păstrează numele originale ale fișierelor')
    parser.add_argument('--date-format', '-f', default="%Y_%m_%d_%H%M%S",
                       help='Format dată personalizat')
    parser.add_argument('--event', '-e',
                       help='Adaugă un eveniment la numele fișierelor (ex: --event plimbare-bicicleta)')
    
    args = parser.parse_args()
    
    if len(args.paths) < 2:
        parser.error("Trebuie să specifici cel puțin o sursă și destinația!")
    
    source_dirs = args.paths[:-1]
    backup_dir = args.paths[-1]
    
    # Verifică dacă destinația nu e aceeași cu sursele
    backup_path = Path(backup_dir).resolve()
    for src in source_dirs:
        if Path(src).resolve() == backup_path:
            parser.error(f"Destinația '{backup_dir}' nu poate fi și sursă!")
    
    backup = MediaBackup(source_dirs, backup_dir, log_file=args.log, verbose=args.verbose, event=args.event, move=args.move)
    
    # Aplică filtre
    if args.photos_only:
        backup.media_extensions = backup.photo_extensions
    elif args.videos_only:
        backup.media_extensions = backup.video_extensions
    
    # Modifică generarea numelui dacă e nevoie
    if args.keep_original_names:
        def keep_names(file_path, media_date):
            dest_path = backup.backup_dir / file_path.name
            counter = 1
            while dest_path.exists():
                stem = file_path.stem
                dest_path = backup.backup_dir / f"{stem}_{counter}{file_path.suffix}"
                counter += 1
            return dest_path.name, dest_path
        backup.generate_filename = keep_names
    elif args.date_format != "%Y_%m_%d_%H%M%S" or args.event:
        # Dacă avem eveniment sau format personalizat, suprascriem funcția
        def custom_format(file_path, media_date):
            extension = file_path.suffix.lower()
            base_name = media_date.strftime(args.date_format)
            
            # Adaugă evenimentul dacă există
            if args.event:
                dest_name = f"{base_name}_{args.event}{extension}"
            else:
                dest_name = f"{base_name}{extension}"
            
            dest_path = backup.backup_dir / dest_name
            counter = 1
            while dest_path.exists():
                if args.event:
                    dest_name = f"{base_name}_{args.event}_{counter}{extension}"
                else:
                    dest_name = f"{base_name}_{counter}{extension}"
                dest_path = backup.backup_dir / dest_name
                counter += 1
            return dest_name, dest_path
        backup.generate_filename = custom_format
    
    try:
        backup.backup_media()
    except KeyboardInterrupt:
        print("\n⚠ Backup întrerupt!")
        sys.exit(130)

if __name__ == "__main__":
    main()
