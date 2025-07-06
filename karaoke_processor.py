import sys
import os
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QCheckBox, QTextEdit,
    QFileDialog, QGroupBox, QProgressBar, QMessageBox,
    QGridLayout
)
from PyQt6.QtCore import QThread, pyqtSignal
import concurrent.futures
import struct
import zipfile
import io
import json
import datetime
from dataclasses import dataclass, asdict

# ==============================================================================
# Data Structures (ไม่เปลี่ยนแปลง)
# ==============================================================================

@dataclass
class DBFField:
    name: str
    type: str
    length: int

@dataclass
class DBFHeader:
    record_count: int
    header_length: int
    record_length: int
    fields: List[DBFField]

@dataclass
class ITrackData:
    TITLE: str = ""
    ARTIST: str = ""
    AUTHOR: str = ""
    LYR_TITLE: str = ""
    CODE: str = ""
    TYPE: str = "MIDI"
    SUB_TYPE: str = ""
    _originalIndex: Optional[int] = None
    _superIndex: Optional[int] = None

@dataclass
class ISearchRecordPreview:
    t: str
    a: str
    i: int
    s: int

@dataclass
class MasterIndex:
    totalRecords: int
    words: List[str]
    wordToChunkMap: Dict[str, int]
    buildTime: int
    lastBuilt: str

# ==============================================================================
# Backend Logic (ไม่เปลี่ยนแปลง)
# ==============================================================================

class DBFParser:
    def parse_header(self, file_buffer: bytes) -> DBFHeader:
        if len(file_buffer) < 32: raise ValueError("DBF header too small.")
        record_count = struct.unpack('<I', file_buffer[4:8])[0]
        header_length = struct.unpack('<H', file_buffer[8:10])[0]
        record_length = struct.unpack('<H', file_buffer[10:12])[0]
        field_count = (header_length - 32 - 1) // 32
        fields = []
        offset = 32
        for i in range(max(0, field_count)):
            if offset + 32 > len(file_buffer): break
            name = file_buffer[offset:offset + 11].split(b'\x00')[0].decode('ascii', errors='ignore')
            field_type = chr(file_buffer[offset + 11])
            length = file_buffer[offset + 16]
            fields.append(DBFField(name=name, type=field_type, length=length))
            offset += 32
        return DBFHeader(record_count=record_count, header_length=header_length, record_length=record_length, fields=fields)

    def try_decode(self, field_bytes: bytes) -> str:
        for encoding in ['tis-620', 'cp874', 'utf-8', 'latin1']:
            try: return field_bytes.decode(encoding).strip()
            except UnicodeDecodeError: continue
        return ""

    def parse_records(self, file_buffer: bytes, header: DBFHeader, status_callback: Optional[callable] = None) -> List[ITrackData]:
        records = []
        if header.record_length == 0:
            if status_callback: status_callback("Warning: Record length is 0.")
            return []
        for i in range(header.record_count):
            record_offset = header.header_length + i * header.record_length
            if record_offset + header.record_length > len(file_buffer): break
            if file_buffer[record_offset] == 0x2A: continue
            if status_callback and (i % 2000 == 0 or i == header.record_count - 1):
                status_callback(f"Parsing DBF: Record {i + 1}/{header.record_count}")

            record_data = {}
            field_offset = record_offset + 1
            for field in header.fields:
                field_bytes = file_buffer[field_offset : field_offset + field.length]
                record_data[field.name] = self.try_decode(field_bytes)
                field_offset += field.length
            records.append(ITrackData(**{k: v for k, v in record_data.items() if k in ITrackData.__annotations__}))
        return records

    def _get_file_content(self, path: str, base_dir: str) -> Optional[bytes]:
        try:
            with open(os.path.join(base_dir, path), 'rb') as f: return f.read()
        except: return None

    def get_song_files_raw(self, track: ITrackData, base_dir: str) -> Optional[Dict[str, bytes]]:
        if not all([track, track.CODE, track.TYPE, track.SUB_TYPE]): return None
        code, t_type, s_type = track.CODE, track.TYPE, track.SUB_TYPE
        folder = code[0] if code else None
        if not folder: return None
        
        primary_path = os.path.join("Songs", t_type, s_type)
        if s_type == "EMK":
            path1 = os.path.join(primary_path, folder, f"{code}.emk")
            path2 = os.path.join(primary_path, f"{code}.emk")
            emk = self._get_file_content(path1, base_dir) or self._get_file_content(path2, base_dir)
            return {"emk": emk} if emk else None
        elif s_type == "NCN":
            midi = self._get_file_content(os.path.join(primary_path, "Song", folder, f"{code}.mid"), base_dir) or self._get_file_content(os.path.join(primary_path, "Song", f"{code}.mid"), base_dir)
            lyr = self._get_file_content(os.path.join(primary_path, "Lyrics", folder, f"{code}.lyr"), base_dir) or self._get_file_content(os.path.join(primary_path, "Lyrics", f"{code}.lyr"), base_dir)
            cur = self._get_file_content(os.path.join(primary_path, "Cursor", folder, f"{code}.cur"), base_dir) or self._get_file_content(os.path.join(primary_path, "Cursor", f"{code}.cur"), base_dir)
            return {"midi": midi, "lyr": lyr, "cur": cur} if all([midi, lyr, cur]) else None
        return None

class SongProcessor:
    def __init__(self, batch_size: int, large_zip_size_limit_mb: int, output_dir: str, create_zips: bool, status_callback: Optional[callable]):
        self.batch_size = batch_size
        self.limit_bytes = large_zip_size_limit_mb * 1024 * 1024
        self.output_dir = output_dir
        self.create_zips = create_zips
        self.log = status_callback or (lambda msg: None)
        if self.create_zips: os.makedirs(self.output_dir, exist_ok=True)
        self.current_original_index = 0
        self.current_super_index = 0
        self._reset_batch()
        self.log(f"Processor init: Batch {self.batch_size}, Limit {large_zip_size_limit_mb}MB")

    def _compress_midi_files(self, midi: bytes, lyr: bytes, cur: bytes) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.writestr('song.mid', midi)
            zf.writestr('song.lyr', lyr)
            zf.writestr('song.cur', cur)
        return buf.getvalue()

    def process_song(self, track: ITrackData, files: Optional[Dict[str, bytes]]) -> bool:
        if not files: return False
        content, filename_in_batch = None, ""
        if track.SUB_TYPE == "NCN" and all(k in files for k in ['midi', 'lyr', 'cur']):
            content = self._compress_midi_files(files['midi'], files['lyr'], files['cur'])
            filename_in_batch = f"{self.current_original_index}.zip"
        elif track.SUB_TYPE == "EMK" and 'emk' in files:
            content = files['emk']
            filename_in_batch = f"{self.current_original_index}.emk"
        else: return False
        
        if content is None: return False
        track._originalIndex = self.current_original_index
        self.current_batch_songs.append((track, content))
        if self.create_zips and self.zip_writer:
            self.zip_writer.writestr(filename_in_batch, content)
            self.current_zip_size += len(content)
        self.current_original_index += 1
        if len(self.current_batch_songs) >= self.batch_size or (self.create_zips and self.current_zip_size >= self.limit_bytes):
            self._finalize_batch()
        return True

    def _finalize_batch(self):
        if not self.current_batch_songs: return
        for track, _ in self.current_batch_songs:
            track._superIndex = self.current_super_index
        if self.create_zips and self.zip_writer:
            self.zip_writer.close()
            zip_bytes = self.zip_buffer.getvalue()
            zip_filename = os.path.join(self.output_dir, f"{self.current_super_index}.zip")
            with open(zip_filename, 'wb') as f: f.write(zip_bytes)
            self.log(f" > Batch {self.current_super_index} saved: {len(self.current_batch_songs)} songs ({len(zip_bytes)/1e6:.2f}MB)")
        self.current_super_index += 1
        self._reset_batch()

    def _reset_batch(self):
        self.current_batch_songs = []
        if self.create_zips:
            self.zip_buffer = io.BytesIO()
            self.zip_writer = zipfile.ZipFile(self.zip_buffer, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)
            self.current_zip_size = 0

    def finalize_remaining_batch(self):
        if self.current_batch_songs:
            self.log("Finalizing remaining songs...")
            self._finalize_batch()

    def create_karaoke_archives(self):
        if not self.create_zips: return
        self.log("Creating karaoke archives...")
        zips = sorted([f for f in os.listdir(self.output_dir) if f.endswith('.zip') and f.split('.')[0].isdigit()], key=lambda x: int(x.split('.')[0]))
        if not zips: return
        
        archive_files, archive_size, archive_count = [], 0, 0
        for zip_name in zips:
            path = os.path.join(self.output_dir, zip_name)
            size = os.path.getsize(path)
            if archive_size + size > self.limit_bytes and archive_files:
                self._create_single_archive(archive_count, archive_files)
                archive_count += 1
                archive_files, archive_size = [], 0
            archive_files.append(path)
            archive_size += size
        if archive_files:
            self._create_single_archive(archive_count, archive_files)

    def _create_single_archive(self, id: int, files: List[str]):
        archive_name = os.path.join(self.output_dir, f"karaoke_{id}.zip")
        self.log(f" > Archiving: creating karaoke_{id}.zip from {len(files)} files...")
        with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as kz:
            for f_path in files:
                kz.write(f_path, os.path.basename(f_path))
        for f_path in files: os.remove(f_path)


class IndexBuilder:
    def __init__(self, output_dir: str, status_callback: Optional[callable]):
        self.output_dir = output_dir
        self.log = status_callback or (lambda msg: None)
        os.makedirs(os.path.join(self.output_dir, "Data", "preview_chunk_v6"), exist_ok=True)

    def _extract_words(self, text: str) -> List[str]:
        import re
        return [w for w in re.findall(r'[a-zA-Z\d\u0e00-\u0e7f]+', text.lower()) if len(w) > 1]

    def build_index(self, all_records: List[ITrackData], progress_callback: Optional[callable]):
        self.log("Building search index...")
        start_time = datetime.datetime.now()
        total_records = len(all_records)
        word_map = {}
        for i, record in enumerate(all_records):
            if progress_callback and (i % 500 == 0 or i == total_records - 1):
                progress_callback(int((i / total_records) * 50)) # 0-50%
                self.log(f"Analyzing for index: {i+1}/{total_records}")

            if record._originalIndex is not None and record._superIndex is not None:
                preview = asdict(ISearchRecordPreview(t=record.TITLE, a=record.ARTIST, i=record._originalIndex, s=record._superIndex))
                text = f"{record.TITLE} {record.ARTIST}"
                for word in self._extract_words(text):
                    if word not in word_map: word_map[word] = []
                    word_map[word].append(preview)

        self.log("Sorting words and creating chunks...")
        sorted_words = sorted(word_map.keys())
        word_to_chunk, chunk, chunk_size, chunk_id = {}, {}, 0, 0
        total_words = len(sorted_words)

        for i, word in enumerate(sorted_words):
            if progress_callback and (i % 1000 == 0 or i == total_words - 1):
                progress_callback(50 + int((i / total_words) * 50)) # 50-100%
            
            entry_size = len(json.dumps(word_map[word]).encode('utf-8'))
            if chunk_size + entry_size > 5 * 1024 * 1024 and chunk:
                self._save_chunk(chunk_id, chunk)
                chunk_id += 1
                chunk, chunk_size = {}, 0
            chunk[word] = word_map[word]
            word_to_chunk[word] = chunk_id
            chunk_size += entry_size
        if chunk: self._save_chunk(chunk_id, chunk)

        self.log("Saving master index...")
        master_index = MasterIndex(totalRecords=total_records, words=sorted_words, wordToChunkMap=word_to_chunk,
                                   buildTime=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                                   lastBuilt=datetime.datetime.now().isoformat())
        with open(os.path.join(self.output_dir, "Data", "master_index_v6.json"), 'w', encoding='utf-8') as f:
            json.dump(asdict(master_index), f, separators=(',', ':'))
        self.log(f"Index built: {len(sorted_words)} words, {chunk_id+1} chunks.")

    def _save_chunk(self, id: int, data: dict):
        path = os.path.join(self.output_dir, "Data", "preview_chunk_v6", f"{id}.json")
        with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, separators=(',',':'))

# ==============================================================================
# GUI Application
# ==============================================================================

class ProcessingThread(QThread):
    progress_update = pyqtSignal(int)
    status_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.should_stop = False

    def stop(self):
        self.status_update.emit("Stopping...")
        self.should_stop = True

    # [+] เพิ่มเมธอดสำหรับสร้าง index.zip
    def _create_index_archive(self, output_dir: str):
        self.status_update.emit("--- Creating final index archive (index.zip) ---")
        zip_output_path = os.path.join(output_dir, 'index.zip')
        master_index_path = os.path.join(output_dir, 'Data', 'master_index_v6.json')
        chunks_dir_path = os.path.join(output_dir, 'Data', 'preview_chunk_v6')

        if not os.path.exists(master_index_path) or not os.path.isdir(chunks_dir_path):
            raise FileNotFoundError("Index data not found. Cannot create index.zip.")

        with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            # ใช้ os.path.relpath เพื่อให้ได้ path ภายใน zip ที่ถูกต้อง (เช่น Data/master_index_v6.json)
            arcname_master = os.path.relpath(master_index_path, output_dir)
            self.status_update.emit(f"Adding: {arcname_master}")
            zf.write(master_index_path, arcname=arcname_master)

            self.status_update.emit(f"Adding files from: {os.path.relpath(chunks_dir_path, output_dir)}")
            for filename in os.listdir(chunks_dir_path):
                file_on_disk = os.path.join(chunks_dir_path, filename)
                if os.path.isfile(file_on_disk):
                    arcname_chunk = os.path.relpath(file_on_disk, output_dir)
                    zf.write(file_on_disk, arcname=arcname_chunk)
        
        self.status_update.emit(f"Successfully created '{zip_output_path}'")


    def run(self):
        try:
            def scaled_updater(start, end):
                return lambda p: self.progress_update.emit(start + int((p / 100) * (end - start))) if not self.should_stop else None

            # 1. DBF Read (0-5%)
            self.status_update.emit("Reading DBF file...")
            self.progress_update.emit(2)
            dbf_path = os.path.join(self.config['main_folder_path'], "Data", "SONG.DBF")
            if not os.path.exists(dbf_path):
                self.finished.emit(False, f"DBF file not found at: {dbf_path}")
                return
            with open(dbf_path, 'rb') as f: file_buffer = f.read()
            if self.should_stop: return

            # 2. DBF Parse (5-15%)
            self.progress_update.emit(5)
            parser = DBFParser()
            header = parser.parse_header(file_buffer)
            self.status_update.emit(f"Parsing {header.record_count} records from DBF...")
            all_records = parser.parse_records(file_buffer, header, self.status_update.emit)
            self.progress_update.emit(15)
            if self.should_stop: return

            # 3. Song Processing (15-80%)
            processor_config = {
                'batch_size': self.config['batch_size'],
                'large_zip_size_limit_mb': self.config['large_zip_size_limit_mb'],
                'output_dir': self.config['output_folder_path'],
                'create_zips': self.config['create_zips'],
                'status_callback': self.status_update.emit
            }
            processor = SongProcessor(**processor_config)
            
            song_updater = scaled_updater(15, 80)
            processed_count, total_songs = 0, len(all_records)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
                futures = {executor.submit(parser.get_song_files_raw, r, self.config['main_folder_path']): r for r in all_records}
                for future in concurrent.futures.as_completed(futures):
                    if self.should_stop: break
                    track_data = futures[future]
                    try:
                        files = future.result()
                        if processor.process_song(track_data, files):
                            processed_count += 1
                        if processed_count % 100 == 0 or processed_count == total_songs:
                            self.status_update.emit(f"Processing songs: {processed_count}/{total_songs}")
                        song_updater(int((processed_count / total_songs) * 100))
                    except Exception as e:
                        self.status_update.emit(f"Error processing {track_data.TITLE}: {e}")
            
            if self.should_stop:
                self.finished.emit(False, "Processing stopped by user.")
                return

            processor.finalize_remaining_batch()
            
            # 4. Archiving (80-90%)
            if self.config['create_zips']:
                self.progress_update.emit(85)
                processor.create_karaoke_archives()
            
            # [*] 5. Indexing (90-98%) - ปรับ Progress bar
            self.progress_update.emit(90)
            builder = IndexBuilder(self.config['output_folder_path'], self.status_update.emit)
            builder.build_index(all_records, scaled_updater(90, 98))
            
            # [+] 6. Final Index Zipping (98-100%) - ขั้นตอนใหม่
            if self.config['create_index_zip']:
                self.progress_update.emit(98)
                self._create_index_archive(self.config['output_folder_path'])
            
            self.progress_update.emit(100)
            self.finished.emit(True, f"Successfully processed {processed_count} songs.")
        except Exception as e:
            import traceback
            self.finished.emit(False, f"A critical error occurred: {e}\n{traceback.format_exc()}")

class KaraokeGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processing_thread = None
        self.init_ui()
        self.load_defaults_to_ui()

    def init_ui(self):
        self.setWindowTitle("Karaoke Processor")
        self.setGeometry(100, 100, 550, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        settings_group = QGroupBox("Settings")
        settings_layout = QGridLayout()
        settings_layout.addWidget(QLabel("Karaoke Folder:"), 0, 0)
        self.main_folder_edit = QLineEdit()
        self.main_folder_edit.textChanged.connect(self.update_output_path)
        settings_layout.addWidget(self.main_folder_edit, 0, 1)
        self.browse_main_btn = QPushButton("Browse...")
        self.browse_main_btn.clicked.connect(self.browse_main_folder)
        settings_layout.addWidget(self.browse_main_btn, 0, 2)

        settings_layout.addWidget(QLabel("Output Folder:"), 1, 0)
        self.output_folder_edit = QLineEdit()
        settings_layout.addWidget(self.output_folder_edit, 1, 1)
        self.browse_output_btn = QPushButton("Browse...")
        self.browse_output_btn.clicked.connect(self.browse_output_folder)
        settings_layout.addWidget(self.browse_output_btn, 1, 2)
        
        # [*] แก้ไขคำอธิบายให้ชัดเจนขึ้น
        self.create_zips_checkbox = QCheckBox("Create song batch ZIPs (karaoke_*.zip)")
        settings_layout.addWidget(self.create_zips_checkbox, 2, 0, 1, 3)

        settings_layout.addWidget(QLabel("Batch Size:"), 3, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 1000)
        settings_layout.addWidget(self.batch_size_spin, 3, 1)
        
        settings_layout.addWidget(QLabel("ZIP Size Limit (MB):"), 4, 0)
        self.zip_size_spin = QSpinBox()
        self.zip_size_spin.setRange(50, 5000)
        settings_layout.addWidget(self.zip_size_spin, 4, 1)
        
        settings_layout.addWidget(QLabel("Worker Threads:"), 5, 0)
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, os.cpu_count() * 4 if os.cpu_count() else 16)
        settings_layout.addWidget(self.max_workers_spin, 5, 1)
        
        # [+] เพิ่ม Checkbox สำหรับสร้าง index.zip
        self.create_index_zip_checkbox = QCheckBox("Create final index archive (index.zip)")
        settings_layout.addWidget(self.create_index_zip_checkbox, 6, 0, 1, 3)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        log_group = QGroupBox("Processing Status")
        log_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        log_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready.")
        log_layout.addWidget(self.status_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        main_layout.setStretch(1, 1)

        button_layout = QHBoxLayout()
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.log_text.clear)
        button_layout.addWidget(self.clear_log_btn)
        button_layout.addStretch()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_processing)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        main_layout.addLayout(button_layout)

    def browse_main_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Karaoke Folder")
        if folder: self.main_folder_edit.setText(folder)

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder: self.output_folder_edit.setText(folder)

    def update_output_path(self, main_path):
        if main_path and os.path.isdir(main_path):
            self.output_folder_edit.setText(os.path.join(main_path, "processed_karaoke"))

    def get_config_from_ui(self) -> Dict:
        return {
            'main_folder_path': self.main_folder_edit.text(),
            'output_folder_path': self.output_folder_edit.text(),
            'create_zips': self.create_zips_checkbox.isChecked(),
            'batch_size': self.batch_size_spin.value(),
            'large_zip_size_limit_mb': self.zip_size_spin.value(),
            'max_workers': self.max_workers_spin.value(),
            'create_index_zip': self.create_index_zip_checkbox.isChecked() # [+] เพิ่ม config
        }
        
    def load_defaults_to_ui(self):
        if getattr(sys, 'frozen', False):
            executable_path = sys.executable
            if sys.platform == 'darwin':
                script_dir = os.path.abspath(os.path.join(os.path.dirname(executable_path), "../../.."))
            else:
                script_dir = os.path.dirname(executable_path)
        else:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            except NameError:
                script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

        self.main_folder_edit.setText(script_dir)
        self.create_zips_checkbox.setChecked(True)
        self.batch_size_spin.setValue(100)
        self.zip_size_spin.setValue(500)
        self.max_workers_spin.setValue(os.cpu_count() * 2 if os.cpu_count() else 8)
        self.create_index_zip_checkbox.setChecked(True) # [+] ตั้งค่าเริ่มต้น
        
    def validate_config(self) -> bool:
        if not os.path.isdir(self.main_folder_edit.text()):
            QMessageBox.warning(self, "Config Error", "Main Karaoke Folder path is invalid.")
            return False
        if not self.output_folder_edit.text().strip():
            QMessageBox.warning(self, "Config Error", "Output Folder path cannot be empty.")
            return False
        return True

    def start_processing(self):
        if not self.validate_config(): return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_message("Processing started...")
        self.processing_thread = ProcessingThread(self.get_config_from_ui())
        self.processing_thread.progress_update.connect(self.progress_bar.setValue)
        self.processing_thread.status_update.connect(self.update_status)
        self.processing_thread.finished.connect(self.processing_finished)
        self.processing_thread.start()

    def stop_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.stop_btn.setEnabled(False)

    def update_status(self, message):
        self.status_label.setText(message)
        self.log_message(message)

    def processing_finished(self, success, message):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_message(f"Finished: {message}")
        if success:
            self.status_label.setText("Completed!")
            QMessageBox.information(self, "Success", message)
        else:
            self.status_label.setText("Finished with errors.")
            QMessageBox.warning(self, "Processing Finished", message)

    def log_message(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def closeEvent(self, event):
        if self.processing_thread and self.processing_thread.isRunning():
            reply = QMessageBox.question(self, "Confirm Exit", "Processing is active. Are you sure you want to exit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_processing()
                if self.processing_thread: self.processing_thread.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = KaraokeGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()