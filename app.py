import os
import urllib.parse
import re
import shutil
import tempfile
import ipaddress
import socket
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

from extractors import extractor, detect_platform
from streamer import stream_media
from ai_features import analyze_viral_metadata, generate_mock_subtitles

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

app = Flask(__name__)
# Enable CORS for Next.js frontend running locally or in production
CORS(app, resources={r"/api/*": {"origins": "*"}}, expose_headers=["Content-Disposition", "Content-Length"])

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Range, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length, Content-Range, Accept-Ranges"
    return response


def is_public_http_url(url: str) -> bool:
    """Reject local/private targets so download proxy endpoints cannot be used for SSRF."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".local"):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False
    try:
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "online",
        "service": "VeloClip Core Engine (2026 Edition)",
        "version": "2.6.0",
        "supported_platforms": ["instagram", "youtube", "facebook", "whatsapp", "twitter", "tiktok"],
        "features": ["temporary_media_processing", "audio_video_muxing", "ai_subtitles", "audio_extract", "full_hd_dp"]
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
                    
                    format_id = str(stream.get("format_id") or "")
                    is_youtube = result.get("platform") == "youtube"
                    is_hls = ".m3u8" in raw_url or "manifest.googlevideo.com" in raw_url
                    
                    # Formats resolved by yt-dlp, HLS manifests, or YouTube videos must be
                    # re-resolved and muxed with audio in the backend process using FFmpeg.
                    # This ensures the user downloads a real, playable .mp4 with sound, never a silent track or .m3u8 text file.
                    if (format_id or is_youtube or is_hls) and result.get("original_url"):
                        target_fid = format_id if format_id else ("bestaudio/best" if stream_type == "audio" else "bestvideo+bestaudio/best")
                        download_query = {
                            "source_url": result["original_url"],
                            "format_id": target_fid,
                            "filename": filename,
                            "audio_only": "1" if stream_type == "audio" else "0",
                        }
                        stream["download_url"] = f"/api/download?{urllib.parse.urlencode(download_query)}"
                    else:
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
    if not is_public_http_url(media_url):
        return jsonify({"success": False, "error": "Only public HTTP(S) media URLs are allowed."}), 400

    content_type = "audio/mpeg" if convert_mp3 else "video/mp4"
    return stream_media(media_url, filename=filename, content_type=content_type, convert_to_mp3=convert_mp3, start_time=start_time, duration=duration)

@app.route('/api/download', methods=['GET'])
def verified_download():
    """Resolve and download a public source in the same backend process.

    This deliberately avoids sending browser clients stale, IP-bound CDN URLs.
    Temporary files are deleted when Flask finishes the response.
    """
    source_url = request.args.get("source_url", "").strip()
    format_id = request.args.get("format_id", "").strip()
    filename = request.args.get("filename", "veloclip_media.mp4")
    audio_only = request.args.get("audio_only") == "1"
    if not source_url or not format_id:
        return jsonify({"success": False, "error": "Missing source URL or format."}), 400
    if not re.fullmatch(r"[A-Za-z0-9+._-]+", format_id):
        return jsonify({"success": False, "error": "Invalid media format."}), 400
    if not is_public_http_url(source_url):
        return jsonify({"success": False, "error": "Invalid media source URL."}), 400

    workdir = Path(tempfile.mkdtemp(prefix="veloclip_"))
    output_template = str(workdir / "media.%(ext)s")
    output_path: Path | None = None
    try:
        common_args = {
            "nocheckcertificate": True,
            "remote_components": ["ejs:github"],
            "js_runtimes": {"node": {}},
            "ffmpeg_location": FFMPEG_BIN,
        }
        is_ig = "instagram.com" in source_url or "instagr.am" in source_url
        cookie_file = "ig_cookies.txt" if is_ig else "cookies.txt"
        if is_ig and os.environ.get("INSTAGRAM_COOKIES_FILE"):
            cookie_file = os.environ["INSTAGRAM_COOKIES_FILE"]
        elif not is_ig and os.environ.get("YOUTUBE_COOKIES_FILE"):
            cookie_file = os.environ["YOUTUBE_COOKIES_FILE"]

        if os.path.exists(cookie_file):
            common_args["cookiefile"] = cookie_file
        elif is_ig and os.environ.get("INSTAGRAM_COOKIES"):
            temp_cookie_path = os.path.join(tempfile.gettempdir(), "veloclip_ig_cookies.txt")
            with open(temp_cookie_path, "w", encoding="utf-8") as f:
                f.write(os.environ["INSTAGRAM_COOKIES"])
            common_args["cookiefile"] = temp_cookie_path
        elif not is_ig and os.environ.get("YOUTUBE_COOKIES"):
            temp_cookie_path = os.path.join(tempfile.gettempdir(), "veloclip_yt_cookies.txt")
            with open(temp_cookie_path, "w", encoding="utf-8") as f:
                f.write(os.environ["YOUTUBE_COOKIES"])
            common_args["cookiefile"] = temp_cookie_path

        if audio_only:
            options = {
                **common_args,
                "format": f"{format_id}/bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "max_filesize": 250 * 1024 * 1024,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            }
        else:
            options = {
                **common_args,
                "format": f"{format_id}+bestaudio/best/{format_id}/best",
                "outtmpl": output_template,
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "max_filesize": 250 * 1024 * 1024,
            }
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([source_url])
        preferred_extension = ".mp3" if audio_only else ".mp4"
        candidates = sorted(workdir.glob("media.*"), key=lambda path: path.stat().st_size, reverse=True)
        if not candidates:
            raise RuntimeError("The source did not produce a downloadable media file.")
        output_path = next((path for path in candidates if path.suffix.lower() == preferred_extension), candidates[0])
        download_name = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
        if audio_only:
            download_name = str(Path(download_name).with_suffix(".mp3"))

        response = send_file(output_path, as_attachment=True, download_name=download_name, conditional=True, max_age=0)
        response.call_on_close(lambda: shutil.rmtree(workdir, ignore_errors=True))
        return response
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        return jsonify({"success": False, "error": "The source video could not be prepared. Please retry with a public link.", "details": str(exc)}), 502

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
