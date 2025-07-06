# Karaoke Processor GUI - User Guide
==================================

A simple GUI tool to compress and index karaoke song files from legacy systems.
Designed to be placed directly inside the "Karaoke Extreme" software folder.

--------------------------------------------------------------------------------
How to Use
--------------------------------------------------------------------------------

1. Place this program (.exe) in the same folder where Karaoke Extreme is installed.
   - The input folder will be auto-filled.
   - The output folder will be auto-filled to "processed_karaoke".
   - You can change these paths manually if needed.

2. Launch the program.

3. Configure options:
   - Batch Size:
     - Number of songs to include per ZIP file.
     - Larger batches reduce file count but may slow down extraction.
   - ZIP Size Limit (MB):
     - When total size of batch ZIPs reaches this limit,
       the program groups them into larger archive ZIPs (karaoke_0.zip, karaoke_1.zip, etc.)
   - Create ZIP Files:
     - Enable to save the processed songs into compressed .zip format.
   - Worker Threads:
     - Higher thread count increases processing speed (recommended: CPU cores × 2)

4. Press [Start] to begin.
   - Logs are displayed in real-time.
   - You can press [Stop] to cancel anytime.

5. After processing:
   - Output is saved under the selected Output Folder.
   - Index files are created in:
     - Data/master_index_v6.json
     - Data/preview_chunk_v6/*.json

--------------------------------------------------------------------------------
Output Folder Structure
--------------------------------------------------------------------------------

Example (output_folder = "processed_karaoke/"):

processed_karaoke/
├── 0.zip
├── 1.zip
├── 2.zip
├── ...
├── karaoke_0.zip
├── karaoke_1.zip
└── Data/
    ├── master_index_v6.json
    └── preview_chunk_v6/
        ├── 0.json
        ├── 1.json
        └── ...

Explanation:

1. `0.zip`, `1.zip`, etc. → Batch ZIP files containing N songs each (based on Batch Size).
   - Inside each ZIP:
     - If song is type NCN:
       - Contains compressed files:
         ├── song.mid
         ├── song.lyr
         └── song.cur
     - If song is type EMK:
       - Contains the `.emk` file directly:
         └── 12.emk  (example name: [originalIndex].emk)

2. `karaoke_0.zip`, `karaoke_1.zip`, etc. → Large ZIP archives that group batch ZIPs.
   - These are generated when the ZIP Size Limit is reached.
   - Inside:
     ├── 0.zip
     ├── 1.zip
     ├── 2.zip
     └── ...

3. `Data/master_index_v6.json` → The main search index metadata file.
4. `Data/preview_chunk_v6/*.json` → Preview chunks storing searchable song info.

--------------------------------------------------------------------------------
Running from Python (Developer Mode)
--------------------------------------------------------------------------------

1. Install required packages:

    pip install PyQt6

2. Run the script:

    python karaoke_processor.py

--------------------------------------------------------------------------------
Building a Standalone Executable (with PyInstaller)
--------------------------------------------------------------------------------

1. Install PyInstaller:

    pip install pyinstaller

2. Build with:

    pyinstaller --noconfirm --onefile --windowed karaoke_processor.py

    (Optional: With icon)
    pyinstaller --noconfirm --onefile --windowed --icon=icon.ico karaoke_processor.py

3. Output will be available in the `dist/` folder.

--------------------------------------------------------------------------------
Additional Notes
--------------------------------------------------------------------------------

- The tool detects and processes only valid, complete songs.
- Songs missing any required file (.mid, .lyr, .cur, .emk) will be skipped.
- The output format is optimized for efficient search, storage, and transfer.

--------------------------------------------------------------------------------

Thank you for using Karaoke Processor GUI!
