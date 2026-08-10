import os
import json
import re
import time
import urllib.request
import hashlib
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google import genai
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from deep_translator import GoogleTranslator

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

HISTORY_FILE = 'agent_session_history.json'
TRANSCRIPTS_DIR = 'Automated_YT_Transcripts'
USERS_FILE = 'users.json'

if not os.path.exists(TRANSCRIPTS_DIR):
    os.makedirs(TRANSCRIPTS_DIR)

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w') as f:
        json.dump([], f)

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({}, f)

def extract_video_id(url):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

def get_video_title(url):
    try:
        html = urllib.request.urlopen(url).read().decode('utf-8')
        match = re.search(r'<title>(.*?)</title>', html)
        if match:
            return match.group(1).replace(" - YouTube", "").strip()
    except Exception:
        pass
    return "Unknown Video"

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

# --- AUTHENTICATION ENDPOINTS ---

# WARNING: TO ENABLE REAL EMAILS, UPDATE THESE CREDENTIALS
SMTP_EMAIL = "your-email@gmail.com"
SMTP_PASSWORD = "your-app-password" # E.g., Gmail App Password

# WARNING: TO ENABLE REAL GOOGLE SSO, UPDATE THIS CLIENT ID
GOOGLE_CLIENT_ID = "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com"

def send_otp_email(to_email, otp):
    if SMTP_EMAIL == "your-email@gmail.com":
        print(f"\n--- MOCK EMAIL (SMTP NOT CONFIGURED) ---")
        print(f"To: {to_email}")
        print(f"OTP: {otp}\n--------------------------------------\n")
        return
        
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = "Your Transcriber Pro Verification Code"
        
        body = f"Hello,\n\nYour OTP verification code is: {otp}\n\nThis code will expire shortly."
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(SMTP_EMAIL, to_email, text)
        server.quit()
        print(f"Real OTP email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
        
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
        
    if email in users and users[email].get('verified'):
        return jsonify({"error": "User already exists"}), 400
        
    otp = str(random.randint(100000, 999999))
    send_otp_email(email, otp)
    
    users[email] = {
        "password": hash_password(password),
        "otp": otp,
        "verified": False
    }
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
        
    return jsonify({"message": "OTP sent successfully"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
        
    user = users.get(email)
    if not user or user['password'] != hash_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
        
    if not user.get('verified'):
        return jsonify({"error": "Account not verified"}), 401
        
    otp = str(random.randint(100000, 999999))
    send_otp_email(email, otp)
    
    user['otp'] = otp
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
        
    return jsonify({"message": "OTP sent successfully"})

@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    email = data.get('email')
    otp = data.get('otp')
    
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
        
    user = users.get(email)
    if not user or user.get('otp') != otp:
        return jsonify({"error": "Invalid OTP code"}), 401
        
    user['verified'] = True
    user['otp'] = None
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
        
    # Generate mock JWT
    token = f"mock_jwt_{hash_password(email + str(time.time()))}"
    return jsonify({"message": "Success", "token": token})

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    token = request.json.get('token')
    try:
        if GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com":
            # Mock verification since client ID is not set
            print("\n--- MOCK GOOGLE SSO VERIFICATION ---")
            print("Token bypass successful (No Client ID provided)")
            return jsonify({"token": f"mock_google_jwt_{time.time()}", "email": "mock-sso-user@gmail.com"})
            
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo['email']
        
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            
        if email not in users:
            users[email] = {
                "password": hash_password(str(time.time())),
                "verified": True,
                "sso": True
            }
            with open(USERS_FILE, 'w') as f:
                json.dump(users, f, indent=4)
                
        jwt_token = f"mock_jwt_{hash_password(email + str(time.time()))}"
        return jsonify({"token": jwt_token, "email": email})
    except ValueError:
        return jsonify({"error": "Invalid token"}), 401
    
# --- END AUTHENTICATION ---

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
        
        # Fetch video title
        video_title = get_video_title(url)
        if video_title == "Unknown Video":
            video_title = f"Video {video_id}"
            
        history = [entry for entry in history if entry['id'] != video_id]
        
        history.insert(0, {
            "id": video_id,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "output_path": output_path,
            "title": video_title
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
    gemini_key = data_req.get('gemini_key')
    
    if target_lang == 'zh-cn':
        target_lang = 'zh-CN'
        
    output_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.json")
    if not os.path.exists(output_path):
        return jsonify({"error": "Transcript not found"}), 404
        
    with open(output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    needs_new_summary = not data.get("summary")
    
    if needs_new_summary:
        if gemini_key:
            try:
                client = genai.Client(api_key=gemini_key)
                prompt = f"Summarize the following video transcript. Return ONLY a JSON list of strings, where each string is a bullet point summary (e.g. [\"Point 1\", \"Point 2\"]). Do not wrap in markdown blocks. Transcript:\\n{data['transcript'][:30000]}"
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt
                )
                text_resp = response.text.strip()
                if text_resp.startswith('```json'):
                    text_resp = text_resp[7:]
                if text_resp.endswith('```'):
                    text_resp = text_resp[:-3]
                data["summary"] = json.loads(text_resp.strip())
            except Exception as e:
                print("Gemini summary error:", str(e))
                data["summary"] = generate_mock_summary(data["transcript"])
        else:
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
    app.run(debug=True, host='0.0.0.0', port=5000)