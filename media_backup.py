#!/usr/bin/env python3
"""
Script de backup pentru poze și videoclipuri
Fișierele sărite apar doar în log dacă specifici --log

Opțiuni noi:
  --event-from-folder   Extrage eventul din numele folderului
  --recursive           Procesează recursiv tot arborele sursei
"""

import os
import re
import hashlib
import shutil
import sys
import argparse
import subprocess
import json
import unicodedata
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


# ---------------------------------------------------------------------------
# Sanitizare
# ---------------------------------------------------------------------------

_WINDOWS_RESERVED = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}

_WINDOWS_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MULTI_UNDERSCORE = re.compile(r'_+')
MAX_EVENT_LENGTH = 100

# Tabel transliterare explicită pentru caractere pe care NFKD nu le descompune
_TRANSLITERATION_MAP = {
    # Românești (virguliță — formă modernă)
    'ă': 'a', 'Ă': 'A',
    'â': 'a', 'Â': 'A',
    'î': 'i', 'Î': 'I',
    'ș': 's', 'Ș': 'S',
    'ț': 't', 'Ț': 'T',
    # Românești (sedilă — formă veche)
    'ş': 's', 'Ş': 'S',
    'ţ': 't', 'Ţ': 'T',
    # Alte diacritice europene comune
    'ø': 'o', 'Ø': 'O',
    'đ': 'd', 'Đ': 'D',
    'ß': 'ss',
    'æ': 'ae', 'Æ': 'AE',
    'œ': 'oe', 'Œ': 'OE',
    'ł': 'l', 'Ł': 'L',
    'ð': 'd', 'Ð': 'D',
    'þ': 'th', 'Þ': 'TH',
}


def _transliterate(text):
    """Aplică transliterarea explicită înainte de NFKD."""
    return ''.join(_TRANSLITERATION_MAP.get(c, c) for c in text)


def sanitize_event(text):
    """
    Sanitizează un string pentru a fi folosit ca parte de nume de fișier.
    Aplică regulile în ordinea stabilită:
      1. Spații -> _
      2. Caractere Windows interzise -> _
      3. Caractere de control -> _ (deja incluse)
      4. Transliterare unicode -> ASCII (mapare explicită + NFKD)
      5. Punct/spațiu la final eliminate
      6. _ la final eliminate
      7. __ -> _ (normalizare)
      8. Trunchiere la 100
      9. _ la final eliminate (după trunchiere)
     10. Nume rezervate Windows -> prefix _
     11. Rezultat vid -> "unknown"
    Returnează (text_sanitizat, a_fost_modificat).
    """
    if text is None:
        return None, False

    original = text

    # 1. Spații -> _
    text = text.replace(' ', '_')

    # 2. + 3. Caractere Windows + control -> _
    text = _WINDOWS_FORBIDDEN.sub('_', text)

    # 4. Transliterare unicode -> ASCII
    text = _transliterate(text)
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')

    # 5. Punct/spațiu la final eliminate
    text = text.rstrip(' .')

    # 6. _ la final eliminate
    text = text.rstrip('_')

    # 7. __ -> _ (normalizare)
    text = _MULTI_UNDERSCORE.sub('_', text)

    # 8. Trunchiere
    if len(text) > MAX_EVENT_LENGTH:
        text = text[:MAX_EVENT_LENGTH]

    # 9. _ la final eliminate (după trunchiere)
    text = text.rstrip('_')

    # 10. Nume rezervate Windows
    if text.upper() in _WINDOWS_RESERVED:
        text = '_' + text

    # 11. Rezultat vid -> unknown
    if not text:
        text = 'unknown'

    return text, (text != original)


def validate_date_format(fmt):
    """Validează --date-format: refuză separatori de cale."""
    try:
        sample = datetime(2009, 7, 18, 10, 23, 27).strftime(fmt)
    except Exception as e:
        raise argparse.ArgumentTypeError(
            f"--date-format invalid: {e}"
        )
    if '/' in sample or '\\' in sample:
        raise argparse.ArgumentTypeError(
            f"--date-format produce separatori de cale ('{sample}'), "
            f"ceea ce ar sparge structura de foldere."
        )
    return fmt


# ---------------------------------------------------------------------------
# MediaBackup
# ---------------------------------------------------------------------------

class MediaBackup:
    def __init__(self, source_dir, backup_dir, log_file=None, verbose=False,
                 event=None, event_from_folder=False, recursive=False,
                 move=False, dry_run=False, workers=8):
        self.source_dir = Path(source_dir).resolve()
        self.backup_dir = Path(backup_dir)
        self.verbose = verbose
        self.log_file = log_file
        self.event = event
        self.event_from_folder = event_from_folder
        self.recursive = recursive
        self.move = move
        self.dry_run = dry_run
        self.workers = max(1, workers)

        # Extensii
        self.photo_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp',
                                 '.tiff', '.raw', '.cr2', '.nef', '.arw',
                                 '.dng', '.heic', '.webp', '.svg', '.ico'}
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv',
                                 '.flv', '.webm', '.m4v', '.mpg', '.mpeg',
                                 '.3gp', '.3g2', '.mts', '.m2ts', '.ts',
                                 '.vob', '.ogv', '.divx'}
        self.media_extensions = self.photo_extensions | self.video_extensions

        # Unelte externe
        self.ffprobe_available = self.check_tool(['ffprobe', '-version'])
        self.exiftool_available = self.check_tool(['exiftool', '-ver'])
        self.identify_available = self.check_tool(['identify', '-version'])

        # Logging
        log_level = logging.DEBUG if verbose else logging.INFO
        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file:
            handlers.insert(0, logging.FileHandler(log_file))
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers
        )

        # Stare
        self.existing_hashes = {}
        self.index = {}
        self.hash_index_file = self.backup_dir / ".hash_index.json"
        self.skipped_files = []
        self.stats = {'photos': 0, 'videos': 0, 'exif_date': 0,
                      'video_metadata': 0, 'file_date': 0, 'current_date': 0,
                      'skipped': 0, 'copied': 0, 'moved': 0}

        # Event manual — sanitizat o singură dată
        if self.event is not None:
            sanitized, changed = sanitize_event(self.event)
            if changed:
                logging.info(f"🏷️  Event sanitizat: '{self.event}' -> '{sanitized}'")
            self.event = sanitized
        elif self.event_from_folder:
            logging.info("🏷️  Event: extras din numele folderului")

    # ------------------------------------------------------------------
    # Utilitare
    # ------------------------------------------------------------------

    @staticmethod
    def check_tool(version_cmd):
        try:
            result = subprocess.run(version_cmd, capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def calculate_md5(self, file_path, chunk_size=8192):
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
        size = float(num_bytes)
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if size < 1024 or unit == 'TB':
                return f"{size:.1f} {unit}"
            size /= 1024

    def verify_copy(self, dest_path, expected_hash):
        return self.calculate_md5(dest_path) == expected_hash

    def check_disk_space(self, total_size_needed):
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
                f"⚠️  Spațiu insuficient! Necesar (estimat): "
                f"{self.human_size(total_size_needed)}, liber: {self.human_size(free_space)}. "
                f"{note}"
            )
            return False
        logging.info(
            f"Spațiu liber: {self.human_size(free_space)} "
            f"(necesar estimat: {self.human_size(total_size_needed)})"
        )
        return True

    # ------------------------------------------------------------------
    # Metadate
    # ------------------------------------------------------------------

    def get_photo_date_exif(self, file_path):
        if self.exiftool_available:
            try:
                result = subprocess.run(
                    ['exiftool', '-DateTimeOriginal', '-d', '%Y-%m-%d %H:%M:%S',
                     '-s', '-s', '-s', str(file_path)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        return datetime.strptime(result.stdout.strip(),
                                                 "%Y-%m-%d %H:%M:%S")
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
                    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
            except Exception:
                pass
        return None

    def get_video_date_ffprobe(self, file_path):
        if not self.ffprobe_available:
            return None
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_entries', 'format_tags=creation_time', str(file_path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                tags = data.get('format', {}).get('tags', {})
                for key in ['creation_time', 'date', 'com.apple.quicktime.creationdate']:
                    if key in tags:
                        date_str = tags[key]
                        clean = date_str.split('.')[0].replace('Z', '')
                        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                            try:
                                return datetime.strptime(clean, fmt)
                            except ValueError:
                                continue
        except Exception as e:
            logging.debug(f"Eroare la citirea metadata video: {e}")
        return None

    def get_media_date(self, file_path):
        is_photo = file_path.suffix.lower() in self.photo_extensions
        is_video = file_path.suffix.lower() in self.video_extensions

        if is_photo:
            d = self.get_photo_date_exif(file_path)
            if d:
                return d, 'exif_date'
        elif is_video:
            d = self.get_video_date_ffprobe(file_path)
            if d:
                return d, 'video_metadata'

        try:
            return datetime.fromtimestamp(os.path.getmtime(file_path)), 'file_date'
        except OSError:
            return datetime.now(), 'current_date'

    # ------------------------------------------------------------------
    # Extragere event din folder
    # ------------------------------------------------------------------

    def extract_event_from_path(self, file_path):
        """
        Extrage event din calea REALĂ a fișierului (nu din cum a fost scrisă sursa).
        - Fără --recursive: numele folderului părinte al fișierului
        - Cu --recursive: concatenare sursă + foldere intermediare
        """
        file_path = file_path.resolve()
        source = self.source_dir.resolve()

        try:
            rel = file_path.relative_to(source)
        except ValueError:
            return None

        parts = rel.parts[:-1]

        if not self.recursive:
            raw = file_path.parent.name
        else:
            if parts:
                raw = '_'.join([source.name] + list(parts))
            else:
                raw = source.name

        if not raw:
            logging.warning(f"⚠️  Nu pot extrage event pentru {file_path.name} -> 'unknown'")
            return 'unknown'

        sanitized, changed = sanitize_event(raw)
        if changed and self.verbose:
            logging.debug(f"🏷️  Event sanitizat: '{raw}' -> '{sanitized}'")
        return sanitized

    # ------------------------------------------------------------------
    # Nume destinație
    # ------------------------------------------------------------------

    def generate_filename(self, file_path, media_date, event=None):
        extension = file_path.suffix.lower()
        base_name = media_date.strftime("%Y_%m_%d_%H%M%S")

        if event:
            dest_name = f"{base_name}_{event}{extension}"
        else:
            dest_name = f"{base_name}{extension}"

        dest_path = self.backup_dir / dest_name
        counter = 1
        while dest_path.exists():
            if event:
                dest_name = f"{base_name}_{event}_{counter}{extension}"
            else:
                dest_name = f"{base_name}_{counter}{extension}"
            dest_path = self.backup_dir / dest_name
            counter += 1

        return dest_name, dest_path

    # ------------------------------------------------------------------
    # Index hash-uri
    # ------------------------------------------------------------------

    def load_index(self):
        if not self.hash_index_file.exists():
            return {}
        try:
            with open(self.hash_index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.warning(f"Index corupt/ilizibil ({e}), se reface de la zero")
            return {}

    def save_index(self):
        try:
            with open(self.hash_index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logging.error(f"Nu am putut salva indexul: {e}")

    def scan_existing_backup(self):
        logging.info("Verificare backup existent...")
        if not self.backup_dir.exists():
            self.index = {}
            return

        self.index = self.load_index()
        reused = rehashed = removed = new_files = 0

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
                self.existing_hashes[entry['hash']] = file_path
                reused += 1
            else:
                new_hash = self.calculate_md5(file_path)
                if new_hash:
                    self.index[rel_path] = {'hash': new_hash,
                                            'mtime': st.st_mtime,
                                            'size': st.st_size}
                    self.existing_hashes[new_hash] = file_path
                    rehashed += 1
                else:
                    del self.index[rel_path]
                    removed += 1

        for file_path in self.backup_dir.rglob("*"):
            if file_path.is_symlink():
                continue
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.media_extensions:
                continue
            rel_path = file_path.relative_to(self.backup_dir).as_posix()
            if rel_path in self.index:
                continue
            file_hash = self.calculate_md5(file_path)
            if not file_hash:
                continue
            try:
                st = file_path.stat()
            except OSError as e:
                logging.warning(f"Fișier dispărut în timpul scanării: {file_path} ({e})")
                continue
            self.index[rel_path] = {'hash': file_hash,
                                    'mtime': st.st_mtime,
                                    'size': st.st_size}
            self.existing_hashes[file_hash] = file_path
            new_files += 1

        logging.info(
            f"Index backup: {reused} refolosite, {rehashed} recalculate, "
            f"{new_files} noi, {removed} eliminate"
        )

    # ------------------------------------------------------------------
    # Colectare fișiere
    # ------------------------------------------------------------------

    def collect_candidates(self):
        """
        Returnează (listă file_path, total_size).
        Fără --recursive: doar fișiere directe în sursă.
        Cu --recursive: tot arborele, sortat, fără symlink-uri.
        """
        candidates = []
        total_size = 0

        if not self.source_dir.exists() or not self.source_dir.is_dir():
            logging.error(f"error: sursa '{self.source_dir}' nu există sau nu este director")
            return [], 0

        if self.recursive:
            for file_path in sorted(self.source_dir.rglob("*")):
                if file_path.is_symlink():
                    continue
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self.media_extensions:
                    continue
                candidates.append(file_path)
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass
        else:
            for file_path in sorted(self.source_dir.iterdir()):
                if file_path.is_symlink():
                    continue
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self.media_extensions:
                    continue
                candidates.append(file_path)
                try:
                    total_size += file_path.stat().st_size
                except OSError:
                    pass

        return candidates, total_size

    # ------------------------------------------------------------------
    # Progres
    # ------------------------------------------------------------------

    def _break_progress_line(self, show_progress):
        if show_progress:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def print_progress(self, current, total, label="Progres"):
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

    # ------------------------------------------------------------------
    # Backup principal
    # ------------------------------------------------------------------

    def backup_media(self):
        self.scan_existing_backup()

        if self.dry_run:
            logging.info("🔍 MOD DRY-RUN: nu se scrie/șterge/mută niciun fișier real")
        else:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

        if self.move:
            logging.info("📦 Mod: MUTARE")
        else:
            logging.info("📋 Mod: COPIERE")

        candidates, total_size = self.collect_candidates()
        logging.info(f"Găsite {len(candidates)} fișiere media în sursă "
                     f"({self.human_size(total_size)})")

        total_copied = total_skipped = total_errors = total_moved = 0
        total_candidates = len(candidates)
        show_progress = not self.verbose and total_candidates > 0

        # Hash-uri în paralel
        hashes = [None] * total_candidates
        if total_candidates:
            logging.info(f"Calculare hash-uri ({self.workers} thread-uri)...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                future_to_idx = {
                    executor.submit(self.calculate_md5, fp): idx
                    for idx, fp in enumerate(candidates)
                }
                completed = 0
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        hashes[idx] = future.result()
                    except Exception as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Eroare la hash pentru {candidates[idx]}: {e}")
                    completed += 1
                    if show_progress:
                        self.print_progress(completed, total_candidates, label="Hash")

        # Filtrare duplicate + calcul dimensiune fișiere noi
        seen_hashes = set(self.existing_hashes.keys())
        new_items = []
        total_new_size = 0
        for file_path, file_hash in zip(candidates, hashes):
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
                    'source_dir': str(self.source_dir),
                    'hash': file_hash,
                    'existing_in_backup': existing_ref.name if existing_ref else '(alt fișier)'
                })
                if self.log_file:
                    ref_name = existing_ref.name if existing_ref else '(alt fișier)'
                    logging.info(f"Sărit (duplicat): {file_path.name} -> {ref_name}")
                continue
            seen_hashes.add(file_hash)
            new_items.append((file_path, file_hash))
            try:
                total_new_size += file_path.stat().st_size
            except OSError:
                pass

        total_new = len(new_items)
        logging.info(f"{total_new} fișiere noi ({self.human_size(total_new_size)}), "
                     f"{total_skipped} duplicate sărite direct")

        # Verificare spațiu — DOAR pentru fișierele noi
        has_enough_space = self.check_disk_space(total_new_size)
        if not has_enough_space and not self.dry_run:
            logging.error("🛑 Rulare oprită: spațiu insuficient pe disc.")
            return total_copied, total_skipped, total_errors, True
 
        # Extragere dată (în paralel)
        dates = [None] * total_new
        date_sources = [None] * total_new
        if total_new:
            logging.info(f"Extragere date EXIF/video ({self.workers} thread-uri)...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                future_to_idx = {
                    executor.submit(self.get_media_date, fp): idx
                    for idx, (fp, _) in enumerate(new_items)
                }
                completed = 0
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        dates[idx], date_sources[idx] = future.result()
                    except Exception as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Eroare la dată pentru {new_items[idx][0]}: {e}")
                        dates[idx], date_sources[idx] = datetime.now(), 'current_date'
                    completed += 1
                    if show_progress:
                        self.print_progress(completed, total_new, label="Dată")

        # Copiere/mutare
        for i, (file_path, file_hash) in enumerate(new_items):
            media_date = dates[i]
            date_source = date_sources[i]

            try:
                is_photo = file_path.suffix.lower() in self.photo_extensions
                self.stats['photos' if is_photo else 'videos'] += 1
                self.stats[date_source] += 1
                icon = "📷" if is_photo else "🎬"

                if self.event is not None:
                    event = self.event
                elif self.event_from_folder:
                    event = self.extract_event_from_path(file_path)
                else:
                    event = None

                dest_name, dest_path = self.generate_filename(file_path, media_date, event)

                if self.dry_run:
                    op = "Ar muta" if self.move else "Ar copia"
                    if self.move:
                        total_moved += 1
                        self.stats['moved'] += 1
                    else:
                        total_copied += 1
                        self.stats['copied'] += 1
                    if self.verbose:
                        event_info = f" (event: {event})" if event else ""
                        logging.info(f"[DRY-RUN] {icon} {op}: {file_path.name} -> {dest_name}{event_info}")
                    if show_progress:
                        self.print_progress(i + 1, total_new, label="Copiere")
                    continue

                shutil.copy2(file_path, dest_path)

                if not self.verify_copy(dest_path, file_hash):
                    dest_path.unlink(missing_ok=True)
                    self._break_progress_line(show_progress)
                    logging.error(f"❌ Verificare eșuată pentru {file_path.name}")
                    total_errors += 1
                    if show_progress:
                        self.print_progress(i + 1, total_new, label="Copiere")
                    continue

                if self.move:
                    try:
                        file_path.unlink()
                        operation = "Mutat"
                        total_moved += 1
                        self.stats['moved'] += 1
                    except OSError as e:
                        self._break_progress_line(show_progress)
                        logging.error(f"Copiat OK, dar nu am putut șterge sursa: {e}")
                        operation = "Copiat (ștergere sursă eșuată)"
                        # Fișierul e copiat → îl numărăm ca „copiat"
                        total_copied += 1
                        self.stats['copied'] += 1
                else:
                    operation = "Copiat"
                    total_copied += 1
                    self.stats['copied'] += 1

                self.existing_hashes[file_hash] = dest_path
                try:
                    dest_stat = dest_path.stat()
                    rel = dest_path.relative_to(self.backup_dir).as_posix()
                    self.index[rel] = {'hash': file_hash,
                                       'mtime': dest_stat.st_mtime,
                                       'size': dest_stat.st_size}
                except OSError:
                    pass

                if self.verbose:
                    logging.info(f"{icon} {operation}: {file_path.name} -> {dest_name}")

            except Exception as e:
                self._break_progress_line(show_progress)
                logging.error(f"Eroare la {file_path}: {e}")
                total_errors += 1

            if show_progress:
                self.print_progress(i + 1, total_new, label="Copiere")

        # Rezumat
        logging.info("=" * 60)
        logging.info("BACKUP COMPLETAT")
        logging.info(f"📷 Poze: {self.stats['photos']}, 🎬 Video: {self.stats['videos']}")
        if self.move:
            logging.info(f"📦 Mutate: {total_moved}, ⏭️  Sărite: {total_skipped}, ❌ Erori: {total_errors}")
        else:
            logging.info(f"✅ Copiate: {total_copied}, ⏭️  Sărite: {total_skipped}, ❌ Erori: {total_errors}")
        if self.verbose:
            logging.info(f"Surse dată: EXIF={self.stats['exif_date']}, "
                         f"Video={self.stats['video_metadata']}, "
                         f"Fișier={self.stats['file_date']}, "
                         f"Curent={self.stats['current_date']}")
        logging.info("=" * 60)

        if self.log_file and self.skipped_files:
            self.write_skipped_to_log()

        if not self.dry_run:
            self.save_index()

        return total_copied, total_skipped, total_errors, False

    # ------------------------------------------------------------------
    # Log fișiere sărite
    # ------------------------------------------------------------------

    def write_skipped_to_log(self):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("FIȘIERE SĂRITE (DUPLICATE)\n")
                f.write("=" * 80 + "\n\n")
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


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Backup media cu MD5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemple:
  # Backup simplu (o singură sursă, doar fișierele directe)
  python3 media_backup.py ~/Poze/Vacanta ~/Backup

  # Extrage eventul din numele folderului sursă
  python3 media_backup.py ~/Poze/Vacanta_Grecia ~/Backup --event-from-folder

  # Recursiv, cu event extras din foldere
  python3 media_backup.py ~/Poze ~/Backup --recursive --event-from-folder

  # Event manual (sanitizat automat)
  python3 media_backup.py ~/Poze ~/Backup --event "Vacanță: Grecia"

  # Mutare cu event din folder
  python3 media_backup.py ~/Poze/Vacanta ~/Backup --move --event-from-folder
        """
    )

    parser.add_argument('source', help='Directorul sursă (o singură sursă)')
    parser.add_argument('backup_dir', help='Directorul destinație')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mod verbose')
    parser.add_argument('--log', '-l', help='Fișier de log (opțional)')
    parser.add_argument('--move', '-m', action='store_true',
                        help='Mută fișierele în loc să le copieze')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Simulează fără să scrie/șteargă/mute nimic')
    parser.add_argument('--workers', '-j', type=int, default=8,
                        help='Nr. thread-uri pentru hash/dată (implicit: 8)')
    parser.add_argument('--photos-only', action='store_true',
                        help='Procesează doar poze')
    parser.add_argument('--videos-only', action='store_true',
                        help='Procesează doar videoclipuri')
    parser.add_argument('--keep-original-names', '-k', action='store_true',
                        help='Păstrează numele originale (ignoră eventul)')
    parser.add_argument('--date-format', '-f', default="%Y_%m_%d_%H%M%S",
                        type=validate_date_format,
                        help='Format dată personalizat')
    parser.add_argument('--event', '-e',
                        help='Adaugă un eveniment la numele fișierelor')
    parser.add_argument('--event-from-folder', action='store_true',
                        help='Extrage evenimentul din numele folderului')
    parser.add_argument('--recursive', '-r', action='store_true',
                        help='Procesează recursiv tot arborele sursei')

    args = parser.parse_args()

    if args.event and args.event_from_folder:
        parser.error("--event și --event-from-folder sunt mutual exclusive")

    src_path = Path(args.source).resolve()
    dst_path = Path(args.backup_dir).resolve()
    if src_path == dst_path:
        parser.error(f"Destinația '{args.backup_dir}' nu poate fi și sursă!")

    if not src_path.is_dir():
        parser.error(f"sursa '{args.source}' nu există sau nu este director")

    backup = MediaBackup(
        args.source, args.backup_dir,
        log_file=args.log, verbose=args.verbose,
        event=args.event, event_from_folder=args.event_from_folder,
        recursive=args.recursive,
        move=args.move, dry_run=args.dry_run, workers=args.workers
    )

    if args.photos_only:
        backup.media_extensions = backup.photo_extensions
    elif args.videos_only:
        backup.media_extensions = backup.video_extensions

    if args.keep_original_names:
        def keep_names(file_path, media_date, event=None):
            dest_path = backup.backup_dir / file_path.name
            counter = 1
            while dest_path.exists():
                stem = file_path.stem
                dest_path = backup.backup_dir / f"{stem}_{counter}{file_path.suffix}"
                counter += 1
            return dest_path.name, dest_path
        backup.generate_filename = keep_names
    elif args.date_format != "%Y_%m_%d_%H%M%S":
        def custom_format(file_path, media_date, event=None):
            extension = file_path.suffix.lower()
            base_name = media_date.strftime(args.date_format)
            base_name, _ = sanitize_event(base_name)
            if event:
                dest_name = f"{base_name}_{event}{extension}"
            else:
                dest_name = f"{base_name}{extension}"
            dest_path = backup.backup_dir / dest_name
            counter = 1
            while dest_path.exists():
                if event:
                    dest_name = f"{base_name}_{event}_{counter}{extension}"
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
