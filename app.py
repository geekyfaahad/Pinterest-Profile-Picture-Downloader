import os
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
from main import download_profile_picture, normalize_username

app = Flask(__name__)

# Use /tmp on Vercel (serverless), local 'downloads' folder otherwise
IS_VERCEL = os.environ.get('VERCEL', False)
DOWNLOAD_FOLDER = '/tmp/downloads' if IS_VERCEL else 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

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
            filepath = result["path"]
            filename = os.path.basename(filepath)

            # Read image and encode as base64 for the response
            with open(filepath, "rb") as f:
                image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            # Determine mime type from extension
            ext = os.path.splitext(filename)[1].lower()
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")

            # Clean up the temp file immediately
            try:
                os.remove(filepath)
            except OSError:
                pass

            return jsonify({
                "status": "success",
                "username": username,
                "url": result["url"],
                "filename": filename,
                "resolution": result["resolution"],
                "image_data": f"data:{mime};base64,{image_b64}"
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
