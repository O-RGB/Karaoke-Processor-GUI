<h1>Karaoke Processor GUI - User Guide</h1>

<p>A simple GUI tool to compress and index karaoke song files from legacy systems.<br>
Designed to be placed directly inside the "Karaoke Extreme" software folder.</p>

<hr>

<h2>How to Use</h2>

<ol>
  <li>
    Place this program (.exe) in the same folder where Karaoke Extreme is installed.<br>
    &nbsp;&nbsp;- The input folder will be auto-filled.<br>
    &nbsp;&nbsp;- The output folder will be auto-filled to "processed_karaoke".<br>
    &nbsp;&nbsp;- You can change these paths manually if needed.
  </li>
  <li>Launch the program.</li>
  <li>
    Configure options:<br>
    &nbsp;&nbsp;- <b>Batch Size:</b><br>
    &nbsp;&nbsp;&nbsp;&nbsp;Number of songs to include per ZIP file.<br>
    &nbsp;&nbsp;&nbsp;&nbsp;Larger batches reduce file count but may slow down extraction.<br>
    &nbsp;&nbsp;- <b>ZIP Size Limit (MB):</b><br>
    &nbsp;&nbsp;&nbsp;&nbsp;When total size of batch ZIPs reaches this limit,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;the program groups them into larger archive ZIPs (karaoke_0.zip, karaoke_1.zip, etc.)<br>
    &nbsp;&nbsp;- <b>Create ZIP Files:</b><br>
    &nbsp;&nbsp;&nbsp;&nbsp;Enable to save the processed songs into compressed .zip format.<br>
    &nbsp;&nbsp;- <b>Worker Threads:</b><br>
    &nbsp;&nbsp;&nbsp;&nbsp;Higher thread count increases processing speed (recommended: CPU cores × 2)
  </li>
  <li>
    Press <b>[Start]</b> to begin.<br>
    &nbsp;&nbsp;- Logs are displayed in real-time.<br>
    &nbsp;&nbsp;- You can press <b>[Stop]</b> to cancel anytime.
  </li>
  <li>
    After processing:<br>
    &nbsp;&nbsp;- Output is saved under the selected Output Folder.<br>
    &nbsp;&nbsp;- Index files are created in:<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<code>Data/master_index_v6.json</code><br>
    &nbsp;&nbsp;&nbsp;&nbsp;<code>Data/preview_chunk_v6/*.json</code>
  </li>
</ol>

<hr>

<h2>Output Folder Structure</h2>

<p>Example (output_folder = "processed_karaoke/"):</p>

<pre>
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
</pre>

<p>Explanation:</p>
<ol>
  <li><code>0.zip</code>, <code>1.zip</code>, etc. → Batch ZIP files containing N songs each (based on Batch Size).<br>
    &nbsp;&nbsp;- Inside each ZIP:<br>
    &nbsp;&nbsp;&nbsp;&nbsp;- If song is type NCN:<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Contains compressed files:<br>
    <pre>
├── song.mid
├── song.lyr
└── song.cur
    </pre>
    &nbsp;&nbsp;&nbsp;&nbsp;- If song is type EMK:<br>
    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Contains the <code>.emk</code> file directly:<br>
    <pre>
└── 12.emk  (example name: [originalIndex].emk)
    </pre>
  </li>
  <li><code>karaoke_0.zip</code>, <code>karaoke_1.zip</code>, etc. → Large ZIP archives that group batch ZIPs.<br>
    &nbsp;&nbsp;- These are generated when the ZIP Size Limit is reached.<br>
    &nbsp;&nbsp;- Inside:<br>
    <pre>
├── 0.zip
├── 1.zip
├── 2.zip
└── ...
    </pre>
  </li>
  <li><code>Data/master_index_v6.json</code> → The main search index metadata file.</li>
  <li><code>Data/preview_chunk_v6/*.json</code> → Preview chunks storing searchable song info.</li>
</ol>

<hr>

<h2>Running from Python (Developer Mode)</h2>

<ol>
  <li>Install required packages:
    <pre>pip install PyQt6</pre>
  </li>
  <li>Run the script:
    <pre>python karaoke_processor.py</pre>
  </li>
</ol>

<hr>

<h2>Building a Standalone Executable (with PyInstaller)</h2>

<ol>
  <li>Install PyInstaller:
    <pre>pip install pyinstaller</pre>
  </li>
  <li>Build with:
    <pre>pyinstaller --noconfirm --onefile --windowed karaoke_processor.py</pre>
    <p>(Optional: With icon)</p>
    <pre>pyinstaller --noconfirm --onefile --windowed --icon=icon.ico karaoke_processor.py</pre>
  </li>
  <li>Output will be available in the <code>dist/</code> folder.</li>
</ol>

<hr>

<h2>Additional Notes</h2>

<ul>
  <li>The tool detects and processes only valid, complete songs.</li>
  <li>Songs missing any required file (.mid, .lyr, .cur, .emk) will be skipped.</li>
  <li>The output format is optimized for efficient search, storage, and transfer.</li>
</ul>

<hr>

<p>Thank you for using Karaoke Processor GUI!</p>
