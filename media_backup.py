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
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

class MediaBackup:
    def __init__(self, source_dirs, backup_dir, log_file=None, verbose=False, event=None, move=False,
                 dry_run=False, workers=8):
        self.source_dirs = [Path(d) for d in source_dirs]
        self.backup_dir = Path(backup_dir)
        self.verbose = verbose
        self.log_file = log_file
        self.event = event  # Evenimentul de adăugat
        self.move = move  # True = mută, False = copiază (implicit)
        self.dry_run = dry_run  # True = doar simulează, nu scrie nimic
        self.workers = max(1, workers)  # nr. de thread-uri pt. hash/extragere dată în paralel
        
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
        
        # Verifică o singură dată disponibilitatea uneltelor externe (nu la fiecare fișier)
        self.ffprobe_available = self.check_tool(['ffprobe', '-version'])
        self.exiftool_available = self.check_tool(['exiftool', '-ver'])
        self.identify_available = self.check_tool(['identify', '-version'])
        
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
        
        self.existing_hashes = {}  # hash -> Path (folosit pt. detectarea duplicatelor)
        self.index = {}  # cale_relativă -> {'hash', 'mtime', 'size'} - persistat pe disc
        self.hash_index_file = self.backup_dir / ".hash_index.json"
        self.skipped_files = []  # Listă în memorie pentru fișierele sărite
        self.stats = {'photos': 0, 'videos': 0, 'exif_date': 0, 
                     'video_metadata': 0, 'file_date': 0, 'current_date': 0,
                     'skipped': 0, 'copied': 0, 'moved': 0}
    
    @staticmethod
    def check_tool(version_cmd):
        """Verifică o singură dată dacă o unealtă externă (ffprobe/exiftool/identify) e disponibilă"""
        try:
            result = subprocess.run(version_cmd, capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
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
    
    @staticmethod
    def human_size(num_bytes):
        """Formatează un număr de octeți într-un format lizibil (KB/MB/GB)"""
        size = float(num_bytes)
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if size < 1024 or unit == 'TB':
                return f"{size:.1f} {unit}"
            size /= 1024

    def verify_copy(self, dest_path, expected_hash):
        """Recalculează hash-ul destinației și îl compară cu cel al sursei"""
        actual_hash = self.calculate_md5(dest_path)
        return actual_hash == expected_hash

    def check_disk_space(self, total_size_needed):
        """
        Verifică dacă există spațiu suficient în destinație.
        Returnează True dacă e suficient (sau dacă verificarea nu s-a putut face),
        False dacă spațiul e insuficient.
        """
        check_dir = self.backup_dir if self.backup_dir.exists() else self.backup_dir.parent
        try:
            free_space = shutil.disk_usage(check_dir).free
        except OSError as e:
            logging.warning(f"Nu am putut verifica spațiul liber pe disc: {e}")
            return True
        if total_size_needed > free_space:
            note = ("(doar avertisment - modul --dry-run nu scrie nimic)" if self.dry_run
                    else "(rularea va fi oprită)")
            logging.warning(
                f"⚠️  Spațiu insuficient! Necesar (estimat, upper bound): "
                f"{self.human_size(total_size_needed)}, liber: {self.human_size(free_space)}. "
                f"Estimarea include și eventuale duplicate care ar putea fi sărite, deci "
                f"necesarul real poate fi mai mic. {note}"
            )
            return False
        logging.info(
            f"Spațiu liber: {self.human_size(free_space)} "
            f"(necesar estimat: {self.human_size(total_size_needed)})"
        )
        return True

    def get_photo_date_exif(self, file_path):
        """Extrage data EXIF folosind exiftool sau identify din ImageMagick (dacă sunt disponibile)"""
        if self.exiftool_available:
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
                    except ValueError:
                        pass
            except Exception:
                pass
        
        if self.identify_available:
            try:
                result = subprocess.run(
                    ['identify', '-format', '%[EXIF:DateTimeOriginal]', str(file_path)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    date_str = result.stdout.strip()
                    try:
                        return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        try:
                            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
            except Exception:
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
        """
        Determină data pentru fișierul media. Nu modifică self.stats direct
        (rulează și din thread-uri paralele) - returnează (dată, sursă_dată).
        """
        is_photo = file_path.suffix.lower() in self.photo_extensions
        is_video = file_path.suffix.lower() in self.video_extensions
        
        if is_photo:
            exif_date = self.get_photo_date_exif(file_path)
            if exif_date:
                return exif_date, 'exif_date'
        elif is_video:
            video_date = self.get_video_date_ffprobe(file_path)
            if video_date:
                return video_date, 'video_metadata'
        
        try:
            mtime = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mtime), 'file_date'
        except OSError:
            pass
        
        return datetime.now(), 'current_date'
    
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
    
    def load_index(self):
        """Încarcă indexul de hash-uri salvat anterior, dacă există și e valid"""
        if not self.hash_index_file.exists():
            return {}
        try:
            with open(self.hash_index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.warning(f"Index de hash-uri corupt/ilizibil ({e}), se reface de la zero")
            return {}

    def save_index(self):
        """Salvează indexul de hash-uri pe disc pentru rularea următoare"""
        try:
            with open(self.hash_index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logging.error(f"Nu am putut salva indexul de hash-uri: {e}")

    def scan_existing_backup(self):
        """
        Construiește harta hash -> fișier pentru backup-ul existent.
        Reutilizează indexul salvat anterior; recalculează MD5 doar pentru
        fișiere noi, lipsă (șterse manual) sau modificate (mtime/size diferit).
        """
        logging.info("Verificare backup existent...")

        if not self.backup_dir.exists():
            self.index = {}
            return

        self.index = self.load_index()
        reused = rehashed = removed = new_files = 0

        # 1. Validează intrările din index (detectează șterse/modificate manual)
        for rel_path in list(self.index.keys()):
            file_path = self.backup_dir / rel_path
            entry = self.index[rel_path]

            if not file_path.is_file():
                del self.index[rel_path]
                removed += 1
                continue

            try:
                st = file_path.stat()
            except OSError:
                del self.index[rel_path]
                removed += 1
                continue

            if st.st_mtime == entry.get('mtime') and st.st_size == entry.get('size'):
                # Neschimbat de la ultima rulare - avem încredere în hash-ul salvat
                self.existing_hashes[entry['hash']] = file_path
                reused += 1
            else:
                # mtime/size diferă -> fișierul a fost modificat direct în backup
                new_hash = self.calculate_md5(file_path)
                if new_hash:
                    self.index[rel_path] = {
                        'hash': new_hash, 'mtime': st.st_mtime, 'size': st.st_size
                    }
                    self.existing_hashes[new_hash] = file_path
                    rehashed += 1
                else:
                    del self.index[rel_path]
                    removed += 1

        # 2. Caută fișiere media din backup care nu sunt încă în index
        #    (prima rulare, sau fișiere adăugate manual în backup)
        for file_path in self.backup_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() not in self.media_extensions:
                continue

            rel_path = file_path.relative_to(self.backup_dir).as_posix()
            if rel_path in self.index:
                continue

            file_hash = self.calculate_md5(file_path)
            if file_hash:
                st = file_path.stat()
                self.index[rel_path] = {
                    'hash': file_hash, 'mtime': st.st_mtime, 'size': st.st_size
                }
                self.existing_hashes[file_hash] = file_path
                new_files += 1

        logging.info(
            f"Index backup: {reused} refolosite, {rehashed} recalculate (modificate), "
            f"{new_files} noi hash-uite, {removed} eliminate (lipsă)"
        )
    
    def collect_candidates(self):
        """Strânge lista fișierelor media din sursă, cu mărimea lor totală"""
        candidates = []  # listă de (source_dir, file_path)
        total_size = 0
        for source_dir in self.source_dirs:
            if not source_dir.exists():
                logging.warning(f"Directorul {source_dir} nu există!")
                continue
            for file_path in source_dir.rglob("*"):
                if not file_path.is_file() or file_path.suffix.lower() not in self.media_extensions:
                    continue
                candidates.append((source_dir, file_path))
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
        return candidates, total_size

    def _break_progress_line(self, show_progress):
        """Trece pe linie nouă înainte de un log important, ca să nu se suprapună peste bara de progres"""
        if show_progress:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def print_progress(self, current, total, label="Progres"):
        """Afișează o bară de progres simplă pe o singură linie (doar în mod non-verbose)"""
        if total == 0:
            return
        pct = current / total * 100
        bar_len = 30
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r{label}: |{bar}| {current}/{total} ({pct:.0f}%)")
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")

    def backup_media(self):
        """Realizează backup-ul fișierelor media (copiere sau mutare)"""
        self.scan_existing_backup()

        if self.dry_run:
            logging.info("🔍 MOD DRY-RUN: nu se scrie/șterge/mută niciun fișier real")
        else:
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
            logging.info("📦 Mod: MUTARE (fișierele vor fi mutate din sursă, doar după verificare)")
        else:
            logging.info("📋 Mod: COPIERE (fișierele rămân în sursă)")

        # Pre-scanare: listă completă + mărime totală (pt. spațiu pe disc și progres)
        candidates, total_size = self.collect_candidates()
        logging.info(f"Găsite {len(candidates)} fișiere media în sursă ({self.human_size(total_size)})")
        has_enough_space = self.check_disk_space(total_size)

        if not has_enough_space and not self.dry_run:
            logging.error(
                "🛑 Rulare oprită: spațiu insuficient pe disc. Eliberează spațiu, redu setul de "
                "fișiere procesate, sau rulează cu --dry-run pentru o estimare fără să scrii nimic."
            )
            return total_copied, total_skipped, total_errors, True  # aborted=True

        processed = 0
        total_candidates = len(candidates)
        show_progress = not self.verbose and total_candidates > 0

        # PAS 1: hash MD5 în paralel pentru TOATE candidatele (necesar oricum, duplicat sau nu)
        hashes = [None] * total_candidates
        if total_candidates:
            logging.info(f"Calculare hash-uri ({self.workers} thread-uri în paralel)...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                future_to_idx = {
                    executor.submit(self.calculate_md5, file_path): idx
                    for idx, (_, file_path) in enumerate(candidates)
                }
                completed = 0
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        hashes[idx] = future.result()
                    except Exception as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Eroare la hash pentru {candidates[idx][1]}: {e}")
                        hashes[idx] = None
                    completed += 1
                    if show_progress:
                        self.print_progress(completed, total_candidates, label="Hash")

        # PAS 2: filtrare rapidă a duplicatelor (fără subprocese), în ordinea originală din sursă
        seen_hashes = set(self.existing_hashes.keys())
        new_items = []  # (source_dir, file_path, file_hash) - fișiere noi, de procesat mai departe

        for (source_dir, file_path), file_hash in zip(candidates, hashes):
            if file_hash is None:
                total_errors += 1
                continue
            if file_hash in seen_hashes:
                total_skipped += 1
                self.stats['skipped'] += 1
                existing_ref = self.existing_hashes.get(file_hash)
                self.skipped_files.append({
                    'filename': file_path.name,
                    'full_path': str(file_path),
                    'source_dir': str(source_dir),
                    'hash': file_hash,
                    'existing_in_backup': existing_ref.name if existing_ref else '(alt fișier din aceeași rulare)'
                })
                if self.log_file:
                    ref_name = existing_ref.name if existing_ref else '(alt fișier din aceeași rulare)'
                    logging.info(f"Sărit (duplicat): {file_path.name} -> {ref_name}")
                continue
            seen_hashes.add(file_hash)
            new_items.append((source_dir, file_path, file_hash))

        total_new = len(new_items)
        logging.info(f"{total_new} fișiere noi de procesat, {total_skipped} duplicate sărite direct "
                     f"(fără extragere dată)")

        # PAS 3: extragere dată (EXIF/ffprobe) în paralel - DOAR pt. fișierele noi (partea costisitoare)
        dates = [None] * total_new
        date_sources = [None] * total_new
        if total_new:
            logging.info(f"Extragere date EXIF/video ({self.workers} thread-uri în paralel)...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                future_to_idx = {
                    executor.submit(self.get_media_date, file_path): idx
                    for idx, (_, file_path, _) in enumerate(new_items)
                }
                completed = 0
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        dates[idx], date_sources[idx] = future.result()
                    except Exception as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Eroare la extragerea datei pentru {new_items[idx][1]}: {e}")
                        dates[idx], date_sources[idx] = datetime.now(), 'current_date'
                    completed += 1
                    if show_progress:
                        self.print_progress(completed, total_new, label="Dată")

        # PAS 4: copiere/mutare secvențială (I/O pe disc; ordinea contează pt. denumire și logare)
        current_source = None
        for i, (source_dir, file_path, file_hash) in enumerate(new_items):
            if source_dir != current_source:
                current_source = source_dir
                if show_progress:
                    sys.stdout.write("\n")
                logging.info(f"Procesare director: {source_dir}")

            media_date = dates[i]
            date_source = date_sources[i]

            try:
                is_photo = file_path.suffix.lower() in self.photo_extensions
                self.stats['photos' if is_photo else 'videos'] += 1
                self.stats[date_source] += 1

                dest_name, dest_path = self.generate_filename(file_path, media_date)
                icon = "📷" if is_photo else "🎬"

                if self.dry_run:
                    operation = "Ar muta" if self.move else "Ar copia"
                    if self.move:
                        total_moved += 1
                        self.stats['moved'] += 1
                    else:
                        total_copied += 1
                        self.stats['copied'] += 1
                    if self.verbose:
                        logging.info(f"[DRY-RUN] {icon} {operation}: {file_path.name} -> {dest_name} "
                                     f"({media_date.strftime('%Y-%m-%d %H:%M:%S')})")
                    processed += 1
                    if show_progress:
                        self.print_progress(i + 1, total_new, label="Copiere")
                    continue

                # Copiază întotdeauna întâi (chiar și la --move), apoi verifică
                shutil.copy2(file_path, dest_path)

                if not self.verify_copy(dest_path, file_hash):
                    dest_path.unlink(missing_ok=True)
                    self._break_progress_line(show_progress)
                    logging.error(
                        f"❌ Verificare eșuată (hash diferit) pentru {file_path.name} - "
                        f"fișierul copiat a fost șters, sursa NU a fost atinsă"
                    )
                    total_errors += 1
                    processed += 1
                    if show_progress:
                        self.print_progress(i + 1, total_new, label="Copiere")
                    continue

                if self.move:
                    try:
                        file_path.unlink()
                        operation = "Mutat"
                    except OSError as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Copiat și verificat OK, dar nu am putut șterge sursa {file_path}: {e}")
                        operation = "Copiat (ștergere sursă eșuată)"
                    total_moved += 1
                    self.stats['moved'] += 1
                else:
                    operation = "Copiat"
                    total_copied += 1
                    self.stats['copied'] += 1

                # Actualizează hash-urile (memorie + index persistent)
                self.existing_hashes[file_hash] = dest_path
                try:
                    dest_stat = dest_path.stat()
                    rel_path = dest_path.relative_to(self.backup_dir).as_posix()
                    self.index[rel_path] = {
                        'hash': file_hash, 'mtime': dest_stat.st_mtime, 'size': dest_stat.st_size
                    }
                except OSError:
                    pass

                if self.verbose:
                    logging.info(f"{icon} {operation}: {file_path.name} -> {dest_name} "
                                 f"({media_date.strftime('%Y-%m-%d %H:%M:%S')})")

            except Exception as e:
                self._break_progress_line(show_progress)
                logging.error(f"Eroare la {file_path}: {e}")
                total_errors += 1

            processed += 1
            if show_progress:
                self.print_progress(i + 1, total_new, label="Copiere")
        
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

        # Salvează indexul de hash-uri pentru rularea următoare (nu în dry-run)
        if not self.dry_run:
            self.save_index()

        return total_copied, total_skipped, total_errors, False
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
    parser.add_argument('--dry-run', '-n', action='store_true',
                       help='Simulează backup-ul fără să scrie/șteargă/mute niciun fișier real')
    parser.add_argument('--workers', '-j', type=int, default=8,
                       help='Nr. de thread-uri pt. hash și extragere dată în paralel (implicit: 8)')
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
    
    backup = MediaBackup(source_dirs, backup_dir, log_file=args.log, verbose=args.verbose,
                         event=args.event, move=args.move, dry_run=args.dry_run, workers=args.workers)
    
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
        _, _, _, aborted = backup.backup_media()
        if aborted:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠ Backup întrerupt!")
        sys.exit(130)

if __name__ == "__main__":
    main()
