import os
import time
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory
from main import download_profile_picture, normalize_username

app = Flask(__name__)

# Directory where images will be saved
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

# --- Auto-cleanup: delete files older than 3 hours ---
MAX_AGE_SECONDS = 3 * 60 * 60        # 3 hours
CLEANUP_INTERVAL_SECONDS = 10 * 60   # check every 10 minutes

def cleanup_old_downloads():
    """Delete files in DOWNLOAD_FOLDER older than MAX_AGE_SECONDS."""
    while True:
        try:
            now = time.time()
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > MAX_AGE_SECONDS:
                        os.remove(filepath)
                        print(f"[Cleanup] Deleted {filename} (age: {file_age/3600:.1f}h)")
        except Exception as e:
            print(f"[Cleanup] Error: {e}")
        time.sleep(CLEANUP_INTERVAL_SECONDS)

# Start the cleanup thread (daemon so it exits with the app)
_cleanup_thread = threading.Thread(target=cleanup_old_downloads, daemon=True)
_cleanup_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    raw_username = data.get('username')
    
    if not raw_username:
        return jsonify({"status": "error", "message": "Username is required."}), 400
    
    try:
        username = normalize_username(raw_username)
        result = download_profile_picture(username, output_dir=DOWNLOAD_FOLDER)
        
        if result["status"] == "success":
            filename = os.path.basename(result["path"])
            return jsonify({
                "status": "success",
                "username": username,
                "url": result["url"],
                "filename": filename,
                "resolution": result["resolution"]
            })
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/downloads/<filename>')
def downloaded_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)

