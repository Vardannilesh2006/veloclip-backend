import os
import urllib.parse
from flask import Flask, request, jsonify
from flask_cors import CORS

from extractors import extractor, detect_platform
from streamer import stream_media
from ai_features import analyze_viral_metadata, generate_mock_subtitles

app = Flask(__name__)
# Enable CORS for Next.js frontend running locally or in production
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "service": "VeloClip Core Engine (2026 Edition)",
        "version": "2.4.0",
        "supported_platforms": ["instagram", "youtube", "facebook", "whatsapp", "twitter", "tiktok"],
        "features": ["zero_storage_streaming", "anti_ban_rotation", "ai_subtitles", "stem_audio_extract", "full_hd_dp"]
    })

@app.route('/api/extract', methods=['POST'])
def extract_media():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400

    try:
        result = extractor.extract(url)
        
        if result.get("success"):
            # Append AI Viral Analytics to result
            title = result.get("title", "")
            caption = result.get("caption", "")
            hashtags = result.get("hashtags", [])
            duration = result.get("duration", 30)

            result["viral_analytics"] = analyze_viral_metadata(title, caption, hashtags, duration)

            # Transform raw streams into proxied streaming URLs for guaranteed CORS and Zero-Storage download
            for stream in result.get("streams", []):
                raw_url = stream.get("url")
                if raw_url:
                    stream_type = stream.get("type", "video")
                    fmt = stream.get("format", "mp4")
                    filename = f"veloclip_{result.get('platform')}_{stream.get('quality', 'hd')}.{fmt}"
                    
                    # Direct download proxy link
                    proxy_query = {
                        "url": raw_url,
                        "filename": filename,
                        "convert_mp3": "1" if stream_type == "audio" else "0"
                    }
                    stream["download_url"] = f"/api/stream?{urllib.parse.urlencode(proxy_query)}"

            return jsonify(result)
        else:
            return jsonify(result), 422
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Server encountered an error while analyzing this media link.",
            "details": str(e)
        }), 500

@app.route('/api/stream', methods=['GET'])
def proxy_stream():
    media_url = request.args.get("url")
    filename = request.args.get("filename", "veloclip_media.mp4")
    convert_mp3 = request.args.get("convert_mp3") == "1"
    start_time = request.args.get("ss")
    duration = request.args.get("t")

    if not media_url:
        return "Missing media URL", 400

    content_type = "audio/mpeg" if convert_mp3 else "video/mp4"
    return stream_media(media_url, filename=filename, content_type=content_type, convert_to_mp3=convert_mp3, start_time=start_time, duration=duration)

@app.route('/api/dp', methods=['POST'])
def get_instagram_dp():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()

    if not username:
        return jsonify({"success": False, "error": "Username or profile URL is required"}), 400

    result = extractor.fetch_instagram_dp(username)
    if result.get("success"):
        dp_url = result.get("dp_url")
        if dp_url:
            filename = f"veloclip_{result.get('username')}_dp_hd.jpg"
            proxy_query = {"url": dp_url, "filename": filename, "convert_mp3": "0"}
            result["download_url"] = f"/api/stream?{urllib.parse.urlencode(proxy_query)}"
        return jsonify(result)
    else:
        return jsonify(result), 404

@app.route('/api/ai/subtitles', methods=['POST'])
def get_subtitles():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "")
    caption = data.get("caption", "")
    duration = int(data.get("duration", 20))

    result = generate_mock_subtitles(title, caption, duration)
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"[VeloClip Engine] starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)

