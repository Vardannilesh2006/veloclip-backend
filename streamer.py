import re
import subprocess
import requests
from flask import Response, stream_with_context
from typing import Generator
from anti_ban import anti_ban

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

def clean_filename(filename: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return cleaned[:100]

def stream_media(media_url: str, filename: str, content_type: str = "video/mp4", convert_to_mp3: bool = False, start_time: str = None, duration: str = None, request_range: str = None):
    """
    Zero-Storage Streaming Proxy:
    Streams media chunks directly from upstream CDN to the client browser.
    Zero disk storage used on server.
    """
    clean_name = clean_filename(filename)
    headers = anti_ban.get_generic_headers()

    if convert_to_mp3:
        # On-the-fly audio extraction & trimming using FFmpeg pipe (Zero disk storage)
        cmd = [FFMPEG_BIN]
        if start_time:
            cmd.extend(["-ss", str(start_time)])
        cmd.extend([
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", media_url,
        ])
        if duration:
            cmd.extend(["-t", str(duration)])
        cmd.extend([
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", "320k",
            "-f", "mp3",
            "pipe:1"
        ])

        def generate_audio_stream() -> Generator[bytes, None, None]:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=64 * 1024)
            try:
                while True:
                    chunk = proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                proc.stdout.close()
                proc.kill()

        audio_name = f"{clean_name.rsplit('.', 1)[0]}.mp3"
        return Response(
            stream_with_context(generate_audio_stream()),
            content_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{audio_name}"',
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*"
            }
        )

    # Standard Direct Video/Photo Chunked Streaming
    try:
        if request_range:
            headers["Range"] = request_range
        req = requests.get(media_url, headers=headers, stream=True, timeout=30)
        if not req.ok:
            return Response("Upstream media is unavailable", status=req.status_code)
        upstream_type = req.headers.get("Content-Type", "").lower()
        if upstream_type.startswith("text/") or "json" in upstream_type or "html" in upstream_type:
            req.close()
            return Response("Upstream did not return a media file", status=502)
        response_headers = {
            "Content-Disposition": f'attachment; filename="{clean_name}"',
            "Content-Type": req.headers.get("Content-Type", content_type),
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=7200",
            "Accept-Ranges": req.headers.get("Accept-Ranges", "bytes"),
        }
        if "Content-Length" in req.headers:
            response_headers["Content-Length"] = req.headers["Content-Length"]
        if "Content-Range" in req.headers:
            response_headers["Content-Range"] = req.headers["Content-Range"]

        def generate_chunks() -> Generator[bytes, None, None]:
            for chunk in req.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

        return Response(
            stream_with_context(generate_chunks()),
            status=req.status_code if req.status_code == 206 else 200,
            headers=response_headers
        )
    except Exception as e:
        return Response(f"Stream error: {str(e)}", status=502)
