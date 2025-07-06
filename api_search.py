import os
import json
import zipfile
import io
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

DATA_PATH = "/processed_karaoke/Data"
MASTER_INDEX_PATH = os.path.join(DATA_PATH, 'master_index_v6.json')
CHUNK_PATH = os.path.join(DATA_PATH, 'preview_chunk_v6')


app = Flask(__name__)
master_index = None
chunk_cache = {}


origins_regex = r"http://localhost:300[0-9]" 
CORS(app, origins=origins_regex)


def load_master_index():
    global master_index
    try:
        with open(MASTER_INDEX_PATH, 'r', encoding='utf-8') as f:
            master_index = json.load(f)
        print("Master Index loaded successfully.")
    except FileNotFoundError:
        print(f"CRITICAL ERROR: Master index file not found at '{MASTER_INDEX_PATH}'")
        master_index = None
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load or parse master index: {e}")
        master_index = None

def get_chunk(chunk_id: int):
    if chunk_id in chunk_cache:
        return chunk_cache[chunk_id]
    
    chunk_file_path = os.path.join(CHUNK_PATH, f"{chunk_id}.json")
    try:
        with open(chunk_file_path, 'r', encoding='utf-8') as f:
            chunk_data = json.load(f)
            chunk_cache[chunk_id] = chunk_data
            return chunk_data
    except FileNotFoundError:
        return None
    except Exception:
        return None

def calculate_score(preview, original_query, search_terms):
    """
    คำนวณคะแนนความเกี่ยวข้องของผลลัพธ์การค้นหา (เลียนแบบ calculateV6Score)
    คะแนนน้อย = ความเกี่ยวข้องสูง
    """
    title = preview.get('t', '').lower()
    artist = preview.get('a', '').lower()
    query = original_query.lower().strip()

    if title == query: return 1
    if title.startswith(query): return 2
    if all(term in title for term in search_terms): return 3
    if all(term in artist for term in search_terms): return 4

    full_text = f"{title} {artist}"
    if all(term in full_text for term in search_terms): return 5

    return 99





@app.route('/search')
def search():
    """
    Endpoint สำหรับค้นหาเพลง (ปรับปรุงใหม่)
    - รับ 'q' สำหรับคำค้นหา
    - รับ 'maxResults' (optional) สำหรับจำกัดจำนวนผลลัพธ์
    """
    if not master_index:
        return jsonify({"error": "Server is not ready. Master Index not loaded."}), 503

    query = request.args.get('q', '').lower().strip()
    
    try:
        max_results = int(request.args.get('maxResults', 50))
    except ValueError:
        max_results = 50
        
    if len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters long."}), 400

    
    search_terms = [word for word in query.split(' ') if word]
    prefix = search_terms[0]

    matching_words = [word for word in master_index['words'] if word.startswith(prefix)]
    
    required_chunks = {master_index['wordToChunkMap'].get(word) for word in matching_words}
    required_chunks.discard(None)

    unique_scored_results = {}
    
    for chunk_id in required_chunks:
        chunk_data = get_chunk(chunk_id)
        if not chunk_data:
            continue
        
        for word in matching_words:
            if word in chunk_data:
                for preview in chunk_data[word]:
                    
                    full_text_preview = f"{preview.get('t','')} {preview.get('a','')}".lower()
                    if all(term in full_text_preview for term in search_terms):
                        score = calculate_score(preview, query, search_terms)
                        original_index = preview['i']
                        
                        
                        if original_index not in unique_scored_results or score < unique_scored_results[original_index]['score']:
                            unique_scored_results[original_index] = {'preview': preview, 'score': score}

    
    sorted_results = sorted(unique_scored_results.values(), key=lambda item: item['score'])

    
    limited_results = sorted_results[:max_results]

    
    final_records = [
        {
            "TITLE": item['preview']['t'],
            "ARTIST": item['preview']['a'],
            "_originalIndex": item['preview']['i'],
            "_superIndex": item['preview']['s'],
            "_priority": item['score']
        }
        for item in limited_results
    ]

    return jsonify(final_records)



@app.route('/get_song')
def get_song():
    try:
        super_index = int(request.args.get('superIndex'))
        original_index = int(request.args.get('originalIndex'))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid 'superIndex' or 'originalIndex'. They must be integers."}), 400

    super_zip_path = os.path.join("/Users/digixtwo/Desktop/karaoke_API/karaoke.env/dbf-karaoke-last/processed_karaoke", f"{super_index}.zip")

    if not os.path.exists(super_zip_path):
        return jsonify({"error": f"Super ZIP for index {super_index} not found."}), 404

    try:
        with zipfile.ZipFile(super_zip_path, 'r') as zf:
            filename_zip = f"{original_index}.zip"
            filename_emk = f"{original_index}.emk"
            song_data, target_filename, mime_type = None, "", ""

            if filename_zip in zf.namelist():
                song_data = zf.read(filename_zip)
                target_filename = f"song_{original_index}.zip"
                mime_type = "application/zip"
            elif filename_emk in zf.namelist():
                song_data = zf.read(filename_emk)
                target_filename = f"song_{original_index}.emk"
                mime_type = "application/octet-stream"
            
            if song_data:
                return send_file(io.BytesIO(song_data), mimetype=mime_type, as_attachment=True, download_name=target_filename)
            else:
                return jsonify({"error": f"Song with originalIndex {original_index} not found inside super zip {super_index}."}), 404
    except Exception as e:
        print(f"Error processing /get_song: {e}")
        return jsonify({"error": "An internal error occurred while retrieving the file."}), 500

@app.route('/')
def index():
    return """<h1>Karaoke API is Running</h1>..."""




if __name__ == '__main__':
    load_master_index()
    app.run(host='0.0.0.0', port=5005, debug=True)