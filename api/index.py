import os
import json
import re
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from deep_translator import GoogleTranslator

# Static folder path fixed for Vercel directory structure
app = Flask(__name__, static_folder='../static', static_url_path='')
CORS(app)

# Vercel safe ephemeral /tmp storage
TEMP_BASE = tempfile.gettempdir()
HISTORY_FILE = os.path.join(TEMP_BASE, 'agent_session_history.json')
TRANSCRIPTS_DIR = os.path.join(TEMP_BASE, 'Automated_YT_Transcripts')

if not os.path.exists(TRANSCRIPTS_DIR):
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([], f)

def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

def generate_mock_summary(full_text):
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    if len(sentences) < 3:
        words = full_text.split()
        if len(words) < 20:
            return ["The video is very short and lacks sufficient spoken content for a deep summary."]
        sentences = [' '.join(words[i:i+30]) for i in range(0, len(words), 30)]
        
    bullets = []
    bullets.append(f"Introduction: {sentences[0]}")
    mid_idx = len(sentences) // 2
    bullets.append(f"Key Point: {sentences[mid_idx]}")
    bullets.append(f"Conclusion: {sentences[-1]}")
    bullets.append(f"The video contains approximately {len(full_text.split())} words in total.")
    return bullets

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/process', methods=['POST'])
def process_url():
    data = request.json or {}
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400
        
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript = next(iter(transcript_list))
        fetched_transcript = transcript.fetch()
        full_text = " ".join([item.text.replace('\n', ' ') for item in fetched_transcript])
        
        output_data = {
            "video_id": video_id,
            "transcript": full_text,
            "summary": []
        }
        
        output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4)
        
        # Read/write safely
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except Exception:
                    history = []
        
        history = [entry for entry in history if entry.get('id') != video_id]
        history.insert(0, {
            "id": video_id,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "output_path": output_path,
            "title": f"Video {video_id}"
        })
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
            
        return jsonify({"message": "Extraction complete", "id": video_id, "transcript": full_text})
        
    except (TranscriptsDisabled, NoTranscriptFound, StopIteration):
        error_msg = "Could not fetch transcript (captions might be disabled or unavailable)."
        save_error_history(video_id, url, error_msg)
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        save_error_history(video_id, url, str(e))
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

def save_error_history(video_id, url, error_msg):
    try:
        output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}_error.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({"error": error_msg}, f)
        
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except Exception:
                    history = []

        history = [entry for entry in history if entry.get('id') != f"{video_id}_error"]
        history.insert(0, {
            "id": f"{video_id}_error",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "output_path": output_path,
            "title": f"Failed: {video_id}",
            "is_error": True
        })
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
    except Exception:
        pass

@app.route('/api/summarize/<video_id>', methods=['POST'])
def summarize(video_id):
    data_req = request.json or {}
    target_lang = data_req.get('target_lang', 'en')
    if target_lang == 'zh-cn':
        target_lang = 'zh-CN'
        
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    if not os.path.exists(output_path):
        return jsonify({"error": "Transcript not found"}), 404
        
    with open(output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if not data.get("summary"):
        data["summary"] = generate_mock_summary(data["transcript"])
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
    summary_bullets = data["summary"]
    
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated_summary = [translator.translate(bullet) for bullet in summary_bullets]
        return jsonify({"summary": translated_summary})
    except Exception:
        return jsonify({"summary": summary_bullets})

@app.route('/api/history', methods=['GET'])
def get_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except Exception:
                history = []
        return jsonify(history)
    return jsonify([])

@app.route('/api/history/<video_id>', methods=['DELETE'])
def delete_history(video_id):
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except Exception:
                history = []
    
    initial_length = len(history)
    history = [entry for entry in history if entry.get('id') != video_id]
    
    if len(history) == initial_length:
        return jsonify({"error": "History item not found"}), 404
        
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4)
        
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    error_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}_error.json")
    
    if os.path.exists(output_path):
        os.remove(output_path)
    if os.path.exists(error_path):
        os.remove(error_path)
        
    return jsonify({"message": "Deleted successfully"})

@app.route('/api/chat/<video_id>', methods=['POST'])
def chat(video_id):
    data = request.json or {}
    query = data.get('query', '')
    target_lang = data.get('target_lang', 'en')
    if target_lang == 'zh-cn':
        target_lang = 'zh-CN'
        
    if not query:
        return jsonify({"error": "Query is required"}), 400
        
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    if not os.path.exists(output_path):
        return jsonify({"error": "Transcript not found"}), 404
        
    with open(output_path, 'r', encoding='utf-8') as f:
        t_data = json.load(f)
        
    full_text = t_data.get("transcript", "")
    words = full_text.split()
    chunk_size = 40
    overlap = 15
    sentences = [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), max(1, chunk_size - overlap))]
    
    query_words = set(re.findall(r'\w+', query))
    stop_words = {"what", "is", "the", "a", "an", "of", "and", "in", "to", "how", "why", "did", "does", "do", "can", "you", "tell", "me", "about", "for", "on", "with"}
    keywords = query_words - stop_words
    
    relevant_sentences = []
    if keywords:
        for chunk in sentences:
            s_lower = chunk.lower()
            score = sum(1 for kw in keywords if kw in s_lower.split())
            if score > 0:
                relevant_sentences.append((score, chunk))
                
    if relevant_sentences:
        relevant_sentences.sort(key=lambda x: x[0], reverse=True)
        best_matches = [s[1] for s in relevant_sentences[:2]]
        answer = "Based on the transcript: ... " + " ... ".join(best_matches) + " ..."
    else:
        summary_list = t_data.get("summary") or generate_mock_summary(full_text)
        answer = "I couldn't find exact keyword matches for your query, but here is a general summary of the video:\n\n" + "\n".join([f"• {b}" for b in summary_list])
        
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated_answer = translator.translate(answer)
        return jsonify({"answer": translated_answer})
    except Exception:
        return jsonify({"answer": answer})

@app.route('/api/translate/<video_id>', methods=['POST'])
def translate_transcript(video_id):
    data = request.json or {}
    target_lang = data.get('target_lang', 'en')
    if target_lang == 'zh-cn':
        target_lang = 'zh-CN'
    
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    if not os.path.exists(output_path):
        return jsonify({"error": "Transcript not found"}), 404
        
    with open(output_path, 'r', encoding='utf-8') as f:
        t_data = json.load(f)
        
    full_text = t_data.get("transcript", "")
    if not full_text:
        return jsonify({"error": "No transcript text available"}), 400
        
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        chunk_limit = 2500
        if len(full_text) > chunk_limit:
            words = full_text.split()
            chunks, current_chunk, current_length = [], [], 0
            for word in words:
                if current_length + len(word) + 1 > chunk_limit:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [word]
                    current_length = len(word)
                else:
                    current_chunk.append(word)
                    current_length += len(word) + 1
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                
            translated_chunks = [translator.translate(chunk) for chunk in chunks]
            translated_text = " ".join(translated_chunks)
        else:
            translated_text = translator.translate(full_text)
            
        return jsonify({"translated_text": translated_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
