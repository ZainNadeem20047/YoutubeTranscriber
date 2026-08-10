import os
import json
import re
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from deep_translator import GoogleTranslator
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
HISTORY_FILE = 'agent_session_history.json'
TRANSCRIPTS_DIR = 'Automated_YT_Transcripts'
if not os.path.exists(TRANSCRIPTS_DIR):
    os.makedirs(TRANSCRIPTS_DIR)
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w') as f:
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
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400
        
    try:
        # Fast native extraction - fetch the first available transcript (any language)
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript = next(iter(transcript_list))
        fetched_transcript = transcript.fetch()
        full_text = " ".join([item.text.replace('\n', ' ') for item in fetched_transcript])
        
        output_data = {
            "video_id": video_id,
            "transcript": full_text,
            "summary": [] # Summary is generated separately
        }
        
        output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4)
        
        # Update history synchronously
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        history = [entry for entry in history if entry['id'] != video_id]
        
        history.insert(0, {
            "id": video_id,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "output_path": output_path,
            "title": f"Video {video_id}"
        })
        
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=4)
            
        return jsonify({"message": "Extraction complete", "id": video_id, "transcript": full_text})
        
    except (TranscriptsDisabled, NoTranscriptFound, StopIteration) as e:
        error_msg = "Could not fetch transcript (captions might be disabled or unavailable)."
        save_error_history(video_id, url, error_msg)
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        save_error_history(video_id, url, str(e))
        return jsonify({"error": "An unexpected error occurred."}), 500
def save_error_history(video_id, url, error_msg):
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}_error.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"error": error_msg}, f)
    
    with open(HISTORY_FILE, 'r') as f:
        history = json.load(f)
    history = [entry for entry in history if entry['id'] != f"{video_id}_error"]
    history.insert(0, {
        "id": f"{video_id}_error",
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "output_path": output_path,
        "title": f"Failed: {video_id}",
        "is_error": True
    })
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)
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
    
    # Translate the summary bullets on the fly
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated_summary = []
        for bullet in summary_bullets:
            translated_summary.append(translator.translate(bullet))
            time.sleep(1) # rate limit protection
        return jsonify({"summary": translated_summary})
    except Exception as e:
        return jsonify({"summary": summary_bullets}) # fallback to original on error
@app.route('/api/history', methods=['GET'])
def get_history():
    with open(HISTORY_FILE, 'r') as f:
        history = json.load(f)
    return jsonify(history)
@app.route('/api/history/<video_id>', methods=['DELETE'])
def delete_history(video_id):
    # Remove from history file
    with open(HISTORY_FILE, 'r') as f:
        history = json.load(f)
    
    initial_length = len(history)
    history = [entry for entry in history if entry['id'] != video_id]
    
    if len(history) == initial_length:
        return jsonify({"error": "History item not found"}), 404
        
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)
        
    # Remove from disk
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    error_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}_error.json")
    
    if os.path.exists(output_path):
        os.remove(output_path)
    if os.path.exists(error_path):
        os.remove(error_path)
        
    return jsonify({"message": "Deleted successfully"})
@app.route('/api/chat/<video_id>', methods=['POST'])
def chat(video_id):
    data = request.json
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
    
    # YouTube transcripts often lack punctuation. 
    # Instead of splitting by punctuation, split into overlapping chunks of words.
    words = full_text.split()
    chunk_size = 40
    overlap = 15
    sentences = [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size - overlap)]
    
    # Simple NLP: find chunks that contain keywords from the query
    query_words = set(re.findall(r'\w+', query))
    stop_words = {"what", "is", "the", "a", "an", "of", "and", "in", "to", "how", "why", "did", "does", "do", "can", "you", "tell", "me", "about", "for", "on", "with"}
    keywords = query_words - stop_words
    
    relevant_sentences = []
    if keywords:
        for chunk in sentences:
            s_lower = chunk.lower()
            # Score chunk by how many keywords it contains
            score = sum(1 for kw in keywords if kw in s_lower.split())
            if score > 0:
                relevant_sentences.append((score, chunk))
                
    if relevant_sentences:
        # Sort by score descending
        relevant_sentences.sort(key=lambda x: x[0], reverse=True)
        # Take the top 2 relevant chunks and combine them
        best_matches = [s[1] for s in relevant_sentences[:2]]
        answer = "Based on the transcript: ... " + " ... ".join(best_matches) + " ..."
    else:
        summary_list = t_data.get("summary")
        if not summary_list:
            summary_list = generate_mock_summary(full_text)
        answer = "I couldn't find exact keyword matches for your query, but here is a general summary of the video:\n\n" + "\n".join([f"• {b}" for b in summary_list])
        
    # Translate answer
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        # The answer is relatively short, so we don't need chunking here
        translated_answer = translator.translate(answer)
        return jsonify({"answer": translated_answer})
    except Exception as e:
        return jsonify({"answer": answer})
@app.route('/api/translate/<video_id>', methods=['POST'])
def translate_transcript(video_id):
    data = request.json
    target_lang = data.get('target_lang', 'en')
    
    # map zh-cn to zh-CN for deep-translator
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
        
        # Deep translator scraping endpoint fails on payloads that are too large (even under 5000 chars).
        # We must chunk the text into smaller, safe blocks of 1500 characters.
        chunk_limit = 1500
        if len(full_text) > chunk_limit:
            chunks = []
            words = full_text.split()
            current_chunk = []
            current_length = 0
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
                
            translated_chunks = []
            for chunk in chunks:
                translated_chunks.append(translator.translate(chunk))
                time.sleep(1.5) # Prevent Google Translate API rate limits
                
            translated_text = " ".join(translated_chunks)
        else:
            translated_text = translator.translate(full_text)
            
        return jsonify({"translated_text": translated_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/api/transcript/<video_id>', methods=['GET'])
def get_transcript(video_id):
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
        
    error_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}_error.json")
    if os.path.exists(error_path):
        with open(error_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data), 400
        
    return jsonify({"error": "Transcript not found"}), 404
if __name__ == '__main__':
    app.run(debug=True, port=5000)
