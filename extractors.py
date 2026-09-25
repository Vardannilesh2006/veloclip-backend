import re
import json
import urllib.parse
import os
import tempfile
import requests
import yt_dlp

from anti_ban import anti_ban

def detect_platform(url: str) -> str:
    url_lower = url.lower().strip()
    if "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        return "facebook"
    elif "whatsapp.com" in url_lower or "wa.me" in url_lower:
        return "whatsapp"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "snapchat.com" in url_lower or "snap.com" in url_lower:
        return "snapchat"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "pinterest"
    elif "reddit.com" in url_lower or "redd.it" in url_lower:
        return "reddit"
    return "unknown"

def extract_instagram_shortcode(url: str) -> Optional[str]:
    match = re.search(r'/(reel|p|tv|reels)/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(2)
    return None

class MediaExtractor:
    """
    Unified extraction engine with anti-ban fallback pipelines.
    """
    def __init__(self):
        self.ydl_opts_base = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'remote_components': ['ejs:github'],
            'js_runtimes': {'node': {}},
            'socket_timeout': 10,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'visionos', 'web'],
                }
            }
        }

    def extract(self, url: str) -> Dict[str, Any]:
        platform = detect_platform(url)
        if platform == "instagram":
            return self.extract_instagram(url)
        elif platform == "youtube":
            return self.extract_youtube(url)
        elif platform == "tiktok":
            return self.extract_tiktok(url)
        elif platform == "twitter":
            return self.extract_twitter(url)
        elif platform == "snapchat":
            return self.extract_snapchat(url)
        elif platform == "facebook":
            return self.extract_facebook(url)
        elif platform == "whatsapp":
            return self.extract_whatsapp(url)
        elif platform == "pinterest":
            return self.extract_pinterest(url)
        elif platform == "reddit":
            return self.extract_reddit(url)
        else:
            # Fallback to general yt-dlp extractor for any other supported site
            return self.extract_generic(url)

    def extract_instagram(self, url: str) -> Dict[str, Any]:
        shortcode = extract_instagram_shortcode(url)
        # Resolve active session from burner pool or env
        active_session = anti_ban.get_instagram_session()

        # Tier 1: Try Mobile Web GraphQL with 2026 doc_id & active burner session
        if shortcode:
            doc_ids = ["9510064595728286", "17867956176966166"]
            for doc_id in doc_ids:
                try:
                    headers = anti_ban.get_instagram_headers(referer=url)
                    cookies = {}
                    if active_session:
                        cookies["sessionid"] = active_session
                        headers["Cookie"] = f"sessionid={active_session}"

                    api_url = f"https://www.instagram.com/graphql/query/?doc_id={doc_id}&variables={{\"shortcode\":\"{shortcode}\"}}"
                    resp = requests.get(api_url, headers=headers, cookies=cookies, timeout=6)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("require_login") or data.get("message") == "checkpoint_required":
                            if active_session:
                                anti_ban.quarantine_session(active_session)
                                active_session = anti_ban.get_instagram_session()
                        else:
                            shortcode_media = data.get("data", {}).get("xdt_shortcode_media") or data.get("data", {}).get("shortcode_media")
                            if shortcode_media:
                                return self._format_instagram_graphql_data(shortcode_media, url)
                    elif resp.status_code in (401, 403):
                        if active_session:
                            anti_ban.quarantine_session(active_session)
                            active_session = anti_ban.get_instagram_session()
                except Exception:
                    continue

        # Tier 2: yt-dlp with session cookies, and automatic retry without cookies
        cookie_file = os.environ.get('INSTAGRAM_COOKIES_FILE') or 'ig_cookies.txt'
        if not os.path.exists(cookie_file) and os.path.exists('cookies.txt'):
            cookie_file = 'cookies.txt'

        has_ig_cookies = (os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 100) or bool(os.environ.get('INSTAGRAM_COOKIES')) or bool(active_session)

        if has_ig_cookies:
            try:
                ydl_opts = dict(self.ydl_opts_base)
                proxy_info = anti_ban.get_proxy()
                if proxy_info and 'https' in proxy_info:
                    ydl_opts['proxy'] = proxy_info['https']

                if active_session:
                    temp_cookie_path = os.path.join(tempfile.gettempdir(), f'veloclip_ig_sess_{active_session[:8]}.txt')
                    with open(temp_cookie_path, 'w', encoding='utf-8') as f:
                        f.write(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{active_session}\n")
                    ydl_opts['cookiefile'] = temp_cookie_path
                elif os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 100:
                    ydl_opts['cookiefile'] = cookie_file
                elif os.environ.get('INSTAGRAM_COOKIES'):
                    temp_cookie_path = os.path.join(tempfile.gettempdir(), 'veloclip_ig_cookies.txt')
                    with open(temp_cookie_path, 'w', encoding='utf-8') as f:
                        f.write(os.environ['INSTAGRAM_COOKIES'])
                    ydl_opts['cookiefile'] = temp_cookie_path

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return self._format_ytdlp_info(info, platform='instagram', original_url=url)
            except Exception as e:
                err_str = str(e).lower()
                if "login" in err_str or "checkpoint" in err_str or "401" in err_str or "403" in err_str:
                    if active_session:
                        anti_ban.quarantine_session(active_session)
                pass

        # Try yt-dlp without cookies
        try:
            ydl_opts_clean = dict(self.ydl_opts_base)
            proxy_info = anti_ban.get_proxy()
            if proxy_info and 'https' in proxy_info:
                ydl_opts_clean['proxy'] = proxy_info['https']

            with yt_dlp.YoutubeDL(ydl_opts_clean) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform='instagram', original_url=url)
        except Exception as e:
            # Tier 3: Attempt direct webpage metadata scraping & oEmbed fallback
            return self._scrape_instagram_meta(url, str(e))

    def _format_instagram_graphql_data(self, media: Dict[str, Any], original_url: str) -> Dict[str, Any]:
        is_video = media.get("is_video", True)
        video_url = media.get("video_url")
        display_url = media.get("display_url")
        
        # Caption & hashtags
        caption_edges = media.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else ""
        hashtags = re.findall(r'#(\w+)', caption)
        
        # Owner / Creator
        owner = media.get("owner", {})
        author_name = owner.get("username", "creator")
        author_avatar = owner.get("profile_pic_url", "")
        likes = media.get("edge_media_preview_like", {}).get("count", 0)
        views = media.get("video_view_count", likes * 3)

        # Multi-slide Carousel detection
        carousel_items = []
        sidecar_edges = media.get("edge_sidecar_to_children", {}).get("edges", [])
        if sidecar_edges:
            for edge in sidecar_edges:
                node = edge.get("node", {})
                carousel_items.append({
                    "is_video": node.get("is_video", False),
                    "url": node.get("video_url") if node.get("is_video") else node.get("display_url"),
                    "thumbnail": node.get("display_url")
                })

        streams = []
        if is_video and video_url:
            streams.append({
                "type": "video",
                "quality": "HD 1080p/Original",
                "format": "mp4",
                "url": video_url,
                "label": "Download High-Res Video"
            })
            # Also provide audio extraction link
            streams.append({
                "type": "audio",
                "quality": "320 kbps (High)",
                "format": "mp3",
                "url": video_url, # streamer pipe will transcode to mp3 on the fly
                "label": "Extract Audio (MP3)"
            })
        elif display_url:
            streams.append({
                "type": "image",
                "quality": "Full HD Original",
                "format": "jpg",
                "url": display_url,
                "label": "Download Photo"
            })

        return {
            "success": True,
            "platform": "instagram",
            "title": (caption[:80] + "...") if len(caption) > 80 else (caption or "Instagram Reel"),
            "caption": caption,
            "author": author_name,
            "author_avatar": author_avatar,
            "thumbnail": display_url,
            "duration": media.get("video_duration", 30),
            "views": views,
            "likes": likes,
            "hashtags": hashtags[:15],
            "is_carousel": len(carousel_items) > 0,
            "carousel_items": carousel_items,
            "streams": streams,
            "original_url": original_url
        }

    def _scrape_instagram_meta(self, url: str, err_msg: str) -> Dict[str, Any]:
        try:
            headers = anti_ban.get_generic_headers(referer="https://www.google.com/")
            resp = requests.get(url, headers=headers, timeout=6)
            html = resp.text
            
            # Find og:video
            video_match = re.search(r'<meta property="og:video" content="([^"]+)"', html)
            image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)

            if video_match:
                video_url = video_match.group(1).replace("&amp;", "&")
                thumb = image_match.group(1).replace("&amp;", "&") if image_match else ""
                title = title_match.group(1) if title_match else "Instagram Reel"
                return {
                    "success": True,
                    "platform": "instagram",
                    "title": title,
                    "caption": title,
                    "author": "instagram_user",
                    "thumbnail": thumb,
                    "duration": 30,
                    "streams": [
                        {"type": "video", "quality": "HD 1080p", "format": "mp4", "url": video_url, "label": "Download Video"},
                        {"type": "audio", "quality": "320 kbps", "format": "mp3", "url": video_url, "label": "Extract Audio"}
                    ],
                    "original_url": url
                }

            # Fallback to official oEmbed
            try:
                oe = requests.get(f"https://api.instagram.com/oembed?url={url}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                if oe.get("title") or oe.get("thumbnail_url"):
                    thumb = oe.get("thumbnail_url", "")
                    title = oe.get("title", "Instagram Post")
                    author = oe.get("author_name", "instagram_creator")
                    streams = []
                    if thumb:
                        streams.append({
                            "type": "image",
                            "quality": "Full HD Cover Art",
                            "format": "jpg",
                            "url": thumb,
                            "download_url": f"/api/stream?url={urllib.parse.quote(thumb)}&filename=veloclip_instagram_preview.jpg",
                            "label": "Download HD Cover Art (JPG)"
                        })
                    return {
                        "success": True,
                        "platform": "instagram",
                        "title": title,
                        "caption": title,
                        "author": f"@{author}",
                        "thumbnail": thumb,
                        "duration": 30,
                        "streams": streams,
                        "original_url": url
                    }
            except Exception:
                pass
        except Exception:
            pass

        return {
            "success": False,
            "platform": "instagram",
            "error": "Instagram extraction temporary restriction. Please ensure the link is public or retry with another link.",
            "details": err_msg
        }

    def extract_youtube(self, url: str) -> Dict[str, Any]:
        cookie_file = os.environ.get("YOUTUBE_COOKIES_FILE") or "cookies.txt"
        has_cookies = os.path.exists(cookie_file) or bool(os.environ.get("YOUTUBE_COOKIES"))
        
        # Tier 1: yt-dlp with authenticated session cookies (if available)
        if has_cookies:
            try:
                ydl_opts = dict(self.ydl_opts_base)
                ydl_opts['http_headers'] = anti_ban.get_generic_headers(referer="https://www.youtube.com/")
                if os.path.exists(cookie_file):
                    ydl_opts['cookiefile'] = cookie_file
                elif os.environ.get("YOUTUBE_COOKIES"):
                    temp_cookie_path = os.path.join(tempfile.gettempdir(), "veloclip_yt_cookies.txt")
                    if not os.path.exists(temp_cookie_path):
                        with open(temp_cookie_path, "w", encoding="utf-8") as f:
                            f.write(os.environ["YOUTUBE_COOKIES"])
                    ydl_opts['cookiefile'] = temp_cookie_path
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return self._format_ytdlp_info(info, platform="youtube", original_url=url)
            except Exception:
                # Expired or flagged cookies shouldn't block extraction; proceed to clean client
                pass

        # Tier 2: Resilient clean yt-dlp client without cookies (uses Android/iOS/VisionOS player APIs)
        try:
            ydl_opts_clean = dict(self.ydl_opts_base)
            ydl_opts_clean['http_headers'] = anti_ban.get_generic_headers(referer="https://www.youtube.com/")
            with yt_dlp.YoutubeDL(ydl_opts_clean) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform="youtube", original_url=url)
        except Exception as e_clean:
            # Tier 3: Piped API mirrors (with broken-URL filtering)
            piped_fallback = self._extract_youtube_piped(url)
            if piped_fallback and piped_fallback.get("streams"):
                return piped_fallback
            # Tier 4: Invidious instance
            fallback = self._extract_youtube_invidious(url)
            if fallback and fallback.get("streams"):
                return fallback

            # Tier 5: GUARANTEED fallback — extract video_id and return backend download endpoints.
            # The /api/download endpoint re-runs yt-dlp at download-time which is faster and
            # more reliable than extraction-time on a cold Render instance. NEVER return success:False
            # for a recognisable YouTube URL — that produces the "stream unavailable" error on the UI.
            vid_match = re.search(r'(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})', url)
            if vid_match:
                vid = vid_match.group(1)
                thumb = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
                # Fetch oEmbed title/author cheaply
                yt_title = "YouTube Video"
                yt_author = "YouTube Creator"
                try:
                    oe = requests.get(
                        f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json",
                        timeout=4
                    ).json()
                    yt_title = oe.get("title", yt_title)
                    yt_author = oe.get("author_name", yt_author)
                    if oe.get("thumbnail_url"):
                        thumb = oe["thumbnail_url"]
                except Exception:
                    pass
                return {
                    "success": True,
                    "platform": "youtube",
                    "title": yt_title,
                    "caption": f"By {yt_author}",
                    "author": yt_author,
                    "thumbnail": thumb,
                    "duration": 180,
                    "streams": [
                        {
                            "type": "video",
                            "quality": "720p HD Video",
                            "format": "mp4",
                            "url": url,
                            "format_id": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
                            "has_audio": True,
                            "label": "Download 720p HD (MP4)"
                        },
                        {
                            "type": "video",
                            "quality": "360p Standard Video",
                            "format": "mp4",
                            "url": url,
                            "format_id": "18",
                            "has_audio": True,
                            "label": "Download 360p (MP4)"
                        },
                        {
                            "type": "audio",
                            "quality": "320 kbps Audio",
                            "format": "mp3",
                            "url": url,
                            "format_id": "bestaudio/best",
                            "has_audio": True,
                            "label": "Extract Audio (MP3)"
                        }
                    ],
                    "original_url": url
                }
            return {
                "success": False,
                "platform": "youtube",
                "error": "Invalid YouTube URL. Please paste a valid youtube.com or youtu.be link.",
                "details": str(e_clean)
            }

    def _extract_youtube_piped(self, url: str) -> Optional[Dict[str, Any]]:
        parsed = urllib.parse.urlparse(url)
        video_id = ""
        if parsed.netloc.lower().endswith("youtu.be"):
            video_id = parsed.path.strip("/").split("/")[0]
        else:
            video_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
            if not video_id and "/shorts/" in parsed.path:
                video_id = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]

        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return None

        piped_mirrors = [
            "https://api.piped.private.coffee",
            # Other mirrors removed — all returning 502/503 as of Sept 2026
        ]
        for m in piped_mirrors:
            try:
                resp = requests.get(f"{m}/streams/{video_id}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                if resp.status_code == 200:
                    d = resp.json()
                    vstreams = d.get("videoStreams", [])
                    astreams = d.get("audioStreams", [])
                    streams = []
                    # BROKEN URL SOURCES: LBRY/Odysee require auth (401), Piped proxy URLs
                    # are IP-locked to the Piped server and fail (500) from any other server.
                    _BROKEN = ('odycdn.com', 'odysee.com', 'proxy.piped', 'piped.private.coffee')
                    for v in vstreams:
                        stream_url = v.get("url", "")
                        if not stream_url or any(p in stream_url for p in _BROKEN):
                            continue  # Skip broken/IP-locked URLs
                        if not v.get("videoOnly"):
                            streams.append({
                                "type": "video",
                                "quality": v.get("quality") or "720p",
                                "format": "mp4",
                                "url": stream_url,
                                "label": f"{v.get('quality', '720p')} MP4 (Audio + Video)"
                            })
                    for a in astreams[:2]:
                        audio_url = a.get("url", "")
                        if audio_url and not any(p in audio_url for p in _BROKEN):
                            streams.append({
                                "type": "audio",
                                "quality": "320 kbps Studio Audio",
                                "format": "mp3",
                                "url": audio_url,
                                "label": "Extract Audio (MP3)"
                            })
                    if streams:
                        return {
                            "success": True,
                            "platform": "youtube",
                            "title": d.get("title", "YouTube Video"),
                            "caption": d.get("description", "")[:200],
                            "author": d.get("uploader", "YouTube Creator"),
                            "thumbnail": d.get("thumbnailUrl") or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                            "duration": d.get("duration", 180),
                            "streams": streams,
                            "original_url": url
                        }
            except Exception:
                continue
        return None

    def _extract_youtube_invidious(self, url: str) -> Optional[Dict[str, Any]]:
        parsed = urllib.parse.urlparse(url)
        video_id = ""
        if parsed.netloc.lower().endswith("youtu.be"):
            video_id = parsed.path.strip("/").split("/")[0]
        else:
            video_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
            if not video_id and "/shorts/" in parsed.path:
                video_id = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]

        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return None

        instances = [
            "https://invidious.f5.si",
            "https://inv.vern.cc",
        ]
        for instance in instances:
            try:
                response = requests.get(
                    # Use the instance's playback proxy. Raw googlevideo URLs
                    # are signed to the resolver IP and otherwise fail later
                    # when the Render streaming worker fetches them.
                    f"{instance}/api/v1/videos/{video_id}?local=true",
                    headers=anti_ban.get_generic_headers(referer="https://www.youtube.com/"),
                    timeout=10,
                )
                if response.status_code != 200:
                    continue
                data = response.json()
                formats = data.get("formatStreams", []) + data.get("adaptiveFormats", [])
                streams = []
                seen = set()
                for item in formats:
                    media_url = item.get("url")
                    mime = item.get("type", "")
                    itag = item.get("itag")
                    if not media_url or itag in seen:
                        continue
                    seen.add(itag)
                    if mime.startswith("video/"):
                        try:
                            height = int(item.get("height") or 0)
                        except (TypeError, ValueError):
                            height = 0
                        streams.append({
                            "type": "video",
                            "quality": f"{height}p" if height else "HD",
                            "format": "mp4" if "mp4" in mime else "webm",
                            "url": media_url,
                            "height": height,
                            "label": f"Video {height}p" if height else "Video HD",
                        })
                    elif mime.startswith("audio/"):
                        try:
                            abr = int(item.get("bitrate") or 0)
                        except (TypeError, ValueError):
                            abr = 0
                        streams.append({
                            "type": "audio",
                            "quality": f"{int(abr / 1000)} kbps" if abr else "Audio",
                            "format": "mp3",
                            "url": media_url,
                            "label": "Extract Audio (MP3)",
                        })

                if streams:
                    streams.sort(key=lambda stream: (stream["type"] != "video", -stream.get("height", 0)))
                    return {
                        "success": True,
                        "platform": "youtube",
                        "title": data.get("title", "YouTube Video"),
                        "caption": data.get("description", "")[:300],
                        "author": data.get("author", "YouTube Creator"),
                        "thumbnail": (data.get("videoThumbnails") or [{}])[-1].get("url", ""),
                        "duration": data.get("lengthSeconds", 0),
                        "views": data.get("viewCount", 0),
                        "likes": data.get("likeCount", 0),
                        "hashtags": data.get("keywords", [])[:15],
                        "streams": streams,
                        "original_url": url,
                    }
            except (requests.RequestException, ValueError, TypeError):
                continue
    def extract_tiktok(self, url: str) -> Dict[str, Any]:
        # Tier 1: TikWM API — fastest, no-watermark, high-quality
        try:
            resp = requests.get(
                f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}",
                headers=anti_ban.get_generic_headers(),
                timeout=8
            )
            if resp.status_code == 200:
                d = resp.json().get('data', {})
                video_url = d.get('play') or d.get('wmplay')
                audio_url = d.get('music')
                cover = d.get('cover') or d.get('origin_cover')
                title = d.get('title') or 'TikTok Video Without Watermark'
                author = d.get('author', {}).get('unique_id') or 'tiktok_creator'
                streams = []
                if video_url:
                    clean_v = video_url.replace('&amp;', '&')
                    streams.append({
                        'type': 'video',
                        'quality': 'HD 1080p (No Watermark) ✓',
                        'format': 'mp4',
                        'url': clean_v,
                        'download_url': f"/api/stream?url={urllib.parse.quote(clean_v)}&filename=veloclip_tiktok_video.mp4",
                        'label': 'Download HD Video (No Watermark)'
                    })
                if audio_url:
                    clean_a = audio_url.replace('&amp;', '&')
                    streams.append({
                        'type': 'audio',
                        'quality': '320 kbps Original Audio',
                        'format': 'mp3',
                        'url': clean_a,
                        'download_url': f"/api/stream?url={urllib.parse.quote(clean_a)}&filename=veloclip_tiktok_audio.mp3",
                        'label': 'Extract Original Sound (MP3)'
                    })
                if streams:
                    return {
                        'success': True,
                        'platform': 'tiktok',
                        'title': title,
                        'caption': title,
                        'author': author,
                        'thumbnail': cover,
                        'duration': d.get('duration', 15),
                        'streams': streams,
                        'original_url': url
                    }
        except Exception:
            pass

        # Tier 2: SSSTik scraper (alternative public API)
        try:
            session = requests.Session()
            # Get token from SSSTik
            home_resp = session.get('https://ssstik.io/en', headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }, timeout=6)
            token_match = re.search(r'tt:"([^"]+)"', home_resp.text)
            if token_match:
                token = token_match.group(1)
                api_resp = session.post('https://ssstik.io/abc?url=dl', data={
                    'id': url,
                    'locale': 'en',
                    'tt': token
                }, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://ssstik.io/en',
                    'Content-Type': 'application/x-www-form-urlencoded',
                }, timeout=10)
                html = api_resp.text
                # Extract no-watermark download link
                nwm_match = re.search(r'href="(https://tikcdn[^"]+)"[^>]*>\s*Without watermark', html, re.IGNORECASE)
                if not nwm_match:
                    nwm_match = re.search(r'href="(https://[^"]+tikcdn[^"]+)"', html)
                if nwm_match:
                    video_url = nwm_match.group(1)
                    title_match = re.search(r'<p[^>]*class="[^"]*maintext[^"]*"[^>]*>([^<]+)</p>', html)
                    title = title_match.group(1).strip() if title_match else 'TikTok Video'
                    thumb_match = re.search(r'<img[^>]*src="(https://p[0-9]+[^"]+)"', html)
                    thumb = thumb_match.group(1) if thumb_match else ''
                    streams = [{
                        'type': 'video',
                        'quality': 'HD (No Watermark) ✓',
                        'format': 'mp4',
                        'url': video_url,
                        'download_url': f"/api/stream?url={urllib.parse.quote(video_url)}&filename=veloclip_tiktok_video.mp4",
                        'label': 'Download HD Video (No Watermark)'
                    }]
                    return {
                        'success': True,
                        'platform': 'tiktok',
                        'title': title,
                        'caption': title,
                        'author': 'TikTok Creator',
                        'thumbnail': thumb,
                        'duration': 15,
                        'streams': streams,
                        'original_url': url
                    }
        except Exception:
            pass

        # Tier 3: yt-dlp generic extractor (slow but reliable for most TikTok content)
        try:
            ydl_opts = dict(self.ydl_opts_base)
            ydl_opts['http_headers'] = anti_ban.get_generic_headers()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform='tiktok', original_url=url)
        except Exception as e:
            return {
                'success': False,
                'platform': 'tiktok',
                'error': 'TikTok video could not be extracted. The video may be private or the link may be invalid.',
                'details': str(e)
            }

    def extract_twitter(self, url: str) -> Dict[str, Any]:
        # Tier 1: FxTwitter High-Speed Cloud Engine
        try:
            tweet_match = re.search(r'(?:twitter\.com|x\.com)/(?:[^/]+)/status/(\d+)', url)
            tweet_id = tweet_match.group(1) if tweet_match else None
            if tweet_id:
                resp = requests.get(f"https://api.fxtwitter.com/i/status/{tweet_id}", headers=anti_ban.get_generic_headers(), timeout=6)
                if resp.status_code == 200:
                    d = resp.json().get("tweet", {})
                    title = d.get("text") or "Twitter / X Video"
                    author = d.get("author", {}).get("screen_name") or "x_creator"
                    media_list = d.get("media", {}).get("all", [])
                    streams = []
                    for m in media_list:
                        if m.get("type") in ("video", "gif"):
                            v_url = m.get("url") or (m.get("variants", [{}])[0].get("url"))
                            if v_url:
                                clean_v = v_url.replace("&amp;", "&")
                                streams.append({
                                    "type": "video",
                                    "quality": "HD 1080p Video ✓",
                                    "format": "mp4",
                                    "url": clean_v,
                                    "download_url": f"/api/stream?url={urllib.parse.quote(clean_v)}&filename=veloclip_twitter_{tweet_id}.mp4",
                                    "label": "Download HD Video (MP4)"
                                })
                                streams.append({
                                    "type": "audio",
                                    "quality": "320 kbps Audio",
                                    "format": "mp3",
                                    "url": clean_v,
                                    "download_url": f"/api/stream?url={urllib.parse.quote(clean_v)}&filename=veloclip_twitter_{tweet_id}_audio.mp3",
                                    "label": "Extract Audio (MP3)"
                                })
                        elif m.get("type") == "photo" and m.get("url"):
                            clean_img = m["url"].replace("&amp;", "&")
                            streams.append({
                                "type": "image",
                                "quality": "Full Resolution Photo",
                                "format": "jpg",
                                "url": clean_img,
                                "download_url": f"/api/stream?url={urllib.parse.quote(clean_img)}&filename=veloclip_twitter_{tweet_id}.jpg",
                                "label": "Download Photo (Full HD)"
                            })
                    if streams:
                        return {
                            "success": True,
                            "platform": "twitter",
                            "title": title[:100],
                            "caption": title,
                            "author": f"@{author}",
                            "thumbnail": media_list[0].get("thumbnail_url") or media_list[0].get("url"),
                            "duration": 20,
                            "streams": streams,
                            "original_url": url
                        }
        except Exception:
            pass
        return self.extract_generic(url)

    def extract_snapchat(self, url: str) -> Dict[str, Any]:
        # Tier 1: Direct HTML OpenGraph and Video Tags
        try:
            resp = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                'Accept': 'text/html,application/xhtml+xml',
            }, timeout=8, allow_redirects=True)
            html = resp.text
            v_match = re.search(r'<meta property="og:video(?::secure_url)?" content="([^"]+)"', html) or \
                      re.search(r'"contentUrl":"([^"]+)"', html) or \
                      re.search(r'<source[^>]+src="(https://[^"]*\.mp4[^"]*)"', html)
            img_match = re.search(r'<meta property="og:image(?::secure_url)?" content="([^"]+)"', html)
            t_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            a_match = re.search(r'<meta property="og:site_name" content="([^"]+)"', html)

            if v_match:
                video_url = v_match.group(1).replace('&amp;', '&').replace('\\u002F', '/')
                thumb = img_match.group(1).replace('&amp;', '&') if img_match else ''
                title = t_match.group(1) if t_match else 'Snapchat Spotlight Video'
                return {
                    'success': True,
                    'platform': 'snapchat',
                    'title': title,
                    'caption': title,
                    'author': a_match.group(1) if a_match else 'Snapchat Creator',
                    'thumbnail': thumb,
                    'duration': 20,
                    'streams': [
                        {
                            'type': 'video',
                            'quality': '1080p Full HD (No Watermark) ✓',
                            'format': 'mp4',
                            'url': video_url,
                            'download_url': f"/api/stream?url={urllib.parse.quote(video_url)}&filename=veloclip_snapchat.mp4",
                            'label': 'Download Spotlight Video'
                        },
                        {
                            'type': 'audio',
                            'quality': '320 kbps Audio',
                            'format': 'mp3',
                            'url': video_url,
                            'download_url': f"/api/stream?url={urllib.parse.quote(video_url)}&filename=veloclip_snapchat.mp3&convert_mp3=1",
                            'label': 'Extract Audio (MP3)'
                        }
                    ],
                    'original_url': url
                }
        except Exception:
            pass

        # Tier 2: yt-dlp Snapchat extractor
        try:
            ydl_opts = dict(self.ydl_opts_base)
            ydl_opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform='snapchat', original_url=url)
        except Exception as e:
            return {
                'success': False,
                'platform': 'snapchat',
                'error': 'Snapchat Spotlight/Story could not be extracted. Public Spotlight links are supported; Stories and DMs require authentication.',
                'details': str(e)
            }

    def extract_facebook(self, url: str) -> Dict[str, Any]:
        try:
            ydl_opts = dict(self.ydl_opts_base)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform="facebook", original_url=url)
        except Exception as e:
            return {
                "success": False,
                "platform": "facebook",
                "error": "Failed to extract Facebook Reel/Video.",
                "details": str(e)
            }

    def extract_whatsapp(self, url: str) -> Dict[str, Any]:
        # Parse phone and text if present in wa.me link
        parsed = urllib.parse.urlparse(url)
        phone = parsed.path.strip("/")
        query = urllib.parse.parse_qs(parsed.query)
        text = query.get("text", [""])[0]

        return {
            "success": True,
            "platform": "whatsapp",
            "title": f"WhatsApp Quick Connect ({phone or 'Direct'})",
            "caption": text or "Direct WhatsApp chat link without saving contact.",
            "phone": phone,
            "text": text,
            "streams": [],
            "tools": {
                "direct_chat_url": f"https://wa.me/{phone}?text={urllib.parse.quote(text)}" if phone else "",
                "web_url": f"https://web.whatsapp.com/send?phone={phone}&text={urllib.parse.quote(text)}" if phone else ""
            }
        }

    def extract_pinterest(self, url: str) -> Dict[str, Any]:
        canonical_url = url
        try:
            if "pin.it" in url:
                try:
                    head = requests.get(url, allow_redirects=True, timeout=5)
                    canonical_url = head.url
                except Exception:
                    pass

            pin_match = re.search(r'/pin/(\d+)', canonical_url)
            pin_id = pin_match.group(1) if pin_match else None

            title = "Pinterest Pin"
            author = "Pinterest Creator"
            video_url = None
            image_url = None

            if pin_id:
                try:
                    pidgets = requests.get(
                        f"https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}",
                        headers={"User-Agent": "Mozilla/5.0"},
                        timeout=5
                    ).json()
                    p = pidgets.get("data", [{}])[0]
                    if p and not p.get("error"):
                        title = p.get("description") or title
                        author = p.get("pinner", {}).get("full_name") or author
                        if p.get("videos", {}).get("video_list"):
                            vlist = p["videos"]["video_list"]
                            best_k = next(
                                (k for k in vlist if "720" in k or "EXP" in k or vlist[k].get("url", "").endswith(".mp4")),
                                list(vlist.keys())[0]
                            )
                            video_url = vlist[best_k].get("url")
                        if p.get("images"):
                            best_img = p["images"].get("564x", {}).get("url") or p["images"].get("236x", {}).get("url")
                            if best_img:
                                image_url = re.sub(r'/\d+x/', '/originals/', best_img)
                except Exception:
                    pass

            if not video_url and not image_url:
                try:
                    resp = requests.get(canonical_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                    html = resp.text
                    v_match = re.search(r'https://v\.pinimg\.com/[^\s"\'<>\)]+\.mp4', html) or re.search(r'<meta property="og:video(?::secure_url)?" content="([^"]+)"', html)
                    img_match = re.search(r'https://i\.pinimg\.com/originals/[^\s"\'<>\)]+', html) or re.search(r'<meta property="og:image(?::secure_url)?" content="([^"]+)"', html)
                    t_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                    if v_match:
                        video_url = v_match.group(1) if v_match.groups() else v_match.group(0)
                    if img_match:
                        image_url = img_match.group(1) if img_match.groups() else img_match.group(0)
                    if t_match:
                        title = t_match.group(1)
                except Exception:
                    pass

            streams = []
            if video_url:
                clean_vid = video_url.replace("&amp;", "&")
                streams.append({
                    "type": "video",
                    "quality": "HD 1080p / 720p Video ✓",
                    "format": "mp4",
                    "url": clean_vid,
                    "download_url": f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_pinterest_{pin_id or 'video'}.mp4",
                    "label": "Download HD Video (MP4)"
                })
                streams.append({
                    "type": "audio",
                    "quality": "320 kbps Audio",
                    "format": "mp3",
                    "url": clean_vid,
                    "download_url": f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_pinterest_{pin_id or 'audio'}.mp3&convert_mp3=1",
                    "label": "Extract Audio (MP3)"
                })
            if image_url:
                clean_img = image_url.replace("&amp;", "&")
                streams.append({
                    "type": "image",
                    "quality": "100% Original Master Resolution",
                    "format": "jpg",
                    "url": clean_img,
                    "download_url": f"/api/stream?url={urllib.parse.quote(clean_img)}&filename=veloclip_pinterest_{pin_id or 'photo'}.jpg",
                    "label": "Download Full-Res Master Image (Original)"
                })

            if streams:
                return {
                    "success": True,
                    "platform": "pinterest",
                    "title": title,
                    "caption": title,
                    "author": author,
                    "thumbnail": image_url or streams[0]["url"],
                    "duration": 20 if video_url else 0,
                    "streams": streams,
                    "original_url": url
                }
        except Exception as e:
            return {"success": False, "platform": "pinterest", "error": f"Pinterest extraction error: {e}"}

        return {"success": False, "platform": "pinterest", "error": "Could not extract media from Pinterest pin."}

    def extract_reddit(self, url: str) -> Dict[str, Any]:
        canonical_url = url
        try:
            if "redd.it/" in url:
                try:
                    head = requests.get(url, allow_redirects=True, timeout=5,
                                       headers={"User-Agent": "VeloClip/3.0 (media downloader)"})
                    canonical_url = head.url
                except Exception:
                    pass

            # Tier 1: Official Reddit JSON API (free, no auth needed for public posts)
            # Append .json to any reddit.com URL to get structured data
            json_url = re.sub(r'\?.*$', '', canonical_url.rstrip('/')) + '.json'
            try:
                resp = requests.get(
                    json_url,
                    headers={"User-Agent": "VeloClip/3.0 (media downloader)"},
                    timeout=8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Reddit JSON returns a list: [post_listing, comments_listing]
                    if isinstance(data, list) and data:
                        post_data = data[0].get('data', {}).get('children', [{}])[0].get('data', {})
                    elif isinstance(data, dict):
                        post_data = data.get('data', {}).get('children', [{}])[0].get('data', {})
                    else:
                        post_data = {}

                    title = post_data.get('title', 'Reddit Post')
                    author = f"u/{post_data.get('author', 'reddit_user')}"
                    thumbnail = post_data.get('thumbnail', '')
                    if thumbnail in ('self', 'default', 'nsfw', 'spoiler', ''):
                        thumbnail = ''

                    streams = []
                    video_url = None
                    image_url = None

                    # Check for Reddit-hosted video (v.redd.it)
                    secure_media = post_data.get('secure_media') or post_data.get('media') or {}
                    reddit_video = secure_media.get('reddit_video', {})
                    if reddit_video.get('fallback_url'):
                        video_url = reddit_video['fallback_url'].split('?')[0]  # Remove quality params

                    # Check for preview video
                    if not video_url:
                        preview = post_data.get('preview', {})
                        reddit_video_preview = preview.get('reddit_video_preview', {})
                        if reddit_video_preview.get('fallback_url'):
                            video_url = reddit_video_preview['fallback_url'].split('?')[0]

                    # Check for direct image
                    if post_data.get('post_hint') == 'image' and post_data.get('url'):
                        image_url = post_data['url']

                    # Check preview images for image posts
                    if not image_url:
                        preview_images = post_data.get('preview', {}).get('images', [])
                        if preview_images:
                            src = preview_images[0].get('source', {})
                            if src.get('url'):
                                image_url = src['url'].replace('&amp;', '&')

                    # Check for gallery
                    if not image_url and not video_url and post_data.get('is_gallery'):
                        gallery_data = post_data.get('gallery_data', {}).get('items', [])
                        media_metadata = post_data.get('media_metadata', {})
                        for item in gallery_data[:1]:  # First image from gallery
                            media_id = item.get('media_id', '')
                            if media_id and media_metadata.get(media_id):
                                meta = media_metadata[media_id]
                                if meta.get('s', {}).get('u'):
                                    image_url = meta['s']['u'].replace('&amp;', '&')

                    if video_url:
                        clean_vid = video_url.replace('&amp;', '&')
                        streams.append({
                            'type': 'video',
                            'quality': f"{reddit_video.get('height', 720)}p HD (Original)",
                            'format': 'mp4',
                            'url': clean_vid,
                            'download_url': f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_reddit_video.mp4",
                            'label': 'Download HD Video (MP4)'
                        })
                        streams.append({
                            'type': 'audio',
                            'quality': '320 kbps Audio',
                            'format': 'mp3',
                            'url': clean_vid,
                            'download_url': f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_reddit_audio.mp3&convert_mp3=1",
                            'label': 'Extract Audio (MP3)'
                        })

                    if image_url:
                        clean_img = image_url.replace('&amp;', '&')
                        streams.append({
                            'type': 'image',
                            'quality': 'Full Resolution Image',
                            'format': 'jpg',
                            'url': clean_img,
                            'download_url': f"/api/stream?url={urllib.parse.quote(clean_img)}&filename=veloclip_reddit_image.jpg",
                            'label': 'Download Full-Res Post Image'
                        })

                    if streams:
                        return {
                            'success': True,
                            'platform': 'reddit',
                            'title': title,
                            'caption': title,
                            'author': author,
                            'thumbnail': image_url or (streams[0]['url'] if streams else ''),
                            'duration': reddit_video.get('duration', 0) if video_url else 0,
                            'streams': streams,
                            'original_url': url
                        }
            except Exception:
                pass

            # Tier 2: Fallback to HTML scraping with facebookexternalhit UA
            title = 'Reddit Post'
            author = 'Reddit Creator'
            try:
                oe = requests.get(
                    f"https://www.reddit.com/oembed?url={urllib.parse.quote(canonical_url)}",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=5
                ).json()
                title = oe.get('title', title)
                author = f"u/{oe.get('author_name', author)}"
            except Exception:
                pass

            video_url = None
            image_url = None
            try:
                resp = requests.get(canonical_url, headers={"User-Agent": "facebookexternalhit/1.1"}, timeout=6)
                html = resp.text

                v_match = re.search(r'https?://(?:v\.redd\.it|packaged-media\.redd\.it)/[^\s"\'<>\)]+\.mp4', html) or re.search(r'<meta property="og:video(?::secure_url)?" content="([^"]+)"', html)
                if v_match:
                    video_url = v_match.group(1) if v_match.groups() else v_match.group(0)

                def is_logo(u: str) -> bool:
                    l = u.lower()
                    return "redditstatic" in l or "favicon" in l or "avatar" in l or "logo" in l or "/t5_" in l

                for pattern in [
                    r'https://i\.redd\.it/[^\s"\'<>\)]+\.(?:jpg|png|webp)',
                    r'https://preview\.redd\.it/[^\s"\'<>\)]+\.(?:jpg|png|webp)',
                    r'<meta property="og:image(?::secure_url)?" content="([^"]+)"'
                ]:
                    m = re.search(pattern, html)
                    if m:
                        u = m.group(1) if m.groups() else m.group(0)
                        if not is_logo(u):
                            image_url = u.replace('&amp;', '&')
                            break
            except Exception:
                pass

            streams = []
            if video_url:
                clean_vid = video_url.replace('&amp;', '&')
                streams.append({
                    'type': 'video',
                    'quality': 'HD Video (Original Quality) ✓',
                    'format': 'mp4',
                    'url': clean_vid,
                    'download_url': f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_reddit_video.mp4",
                    'label': 'Download HD Video (MP4)'
                })
                streams.append({
                    'type': 'audio',
                    'quality': '320 kbps Audio',
                    'format': 'mp3',
                    'url': clean_vid,
                    'download_url': f"/api/stream?url={urllib.parse.quote(clean_vid)}&filename=veloclip_reddit_audio.mp3&convert_mp3=1",
                    'label': 'Extract Audio (MP3)'
                })
            if image_url:
                streams.append({
                    'type': 'image',
                    'quality': 'Full Resolution Image',
                    'format': 'jpg',
                    'url': image_url,
                    'download_url': f"/api/stream?url={urllib.parse.quote(image_url)}&filename=veloclip_reddit_image.jpg",
                    'label': 'Download Full-Res Post Image'
                })

            if streams:
                return {
                    'success': True,
                    'platform': 'reddit',
                    'title': title,
                    'caption': title,
                    'author': author,
                    'thumbnail': image_url or streams[0]['url'],
                    'duration': 20 if video_url else 0,
                    'streams': streams,
                    'original_url': url
                }
        except Exception as e:
            return {'success': False, 'platform': 'reddit', 'error': f'Reddit extraction error: {e}'}

        return {'success': False, 'platform': 'reddit', 'error': 'Could not extract media from this Reddit post. Ensure the post is public and contains video or images.'}

    def extract_generic(self, url: str) -> Dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts_base) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform="generic", original_url=url)
        except Exception as e:
            return {
                "success": False,
                "platform": "generic",
                "error": "Unable to extract media from this URL.",
                "details": str(e)
            }

    def _format_ytdlp_info(self, info: Dict[str, Any], platform: str, original_url: str) -> Dict[str, Any]:
        title = info.get("title", "Social Video")
        description = info.get("description", "")
        author = info.get("uploader", "") or info.get("channel", "Creator")
        thumbnail = info.get("thumbnail", "")
        duration = info.get("duration", 0)
        views = info.get("view_count", 0)
        likes = info.get("like_count", 0)
        tags = info.get("tags", [])

        # Filter formats
        formats = info.get("formats", [])
        streams = []
        audio_streams = []

        for f in formats:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            ext = f.get("ext", "mp4")
            height = f.get("height")
            direct_url = f.get("url")
            format_id = str(f.get("format_id") or "")

            if not direct_url:
                continue

            # ── CRITICAL: Skip known-broken proxy/mirror URLs ──────────────────
            # These URL sources are IP-locked to the resolver's IP or require auth.
            # Serving them to users / other servers always results in 401/500 errors.
            _BROKEN_SOURCES = ('odycdn.com', 'odysee.com', 'proxy.piped', 'piped.private.coffee')
            if any(p in direct_url for p in _BROKEN_SOURCES):
                continue

            # Keep server-side merge jobs within the limits of the hosted worker.
            # Higher resolutions are often gigabytes for a short clip and make a
            # free/shared instance unavailable for every other download.
            if vcodec != "none" and height and height > 1080:
                continue

            # Adaptive video tracks do not contain audio. Keep that fact explicit
            # so the download endpoint can mux them with audio instead of serving
            # a misleading silent "MP4" file.
            if vcodec != "none" and direct_url:
                quality_label = f"{height}p" if height else "HD"
                streams.append({
                    "type": "video",
                    "quality": f"{quality_label} — Audio + Video" if acodec != "none" else f"{quality_label} — Video + Audio Merge",
                    "format": ext,
                    "url": direct_url,
                    "height": height or 720,
                    "format_id": format_id,
                    "has_audio": acodec != "none",
                    "label": f"Video {quality_label} ({ext.upper()})"
                })
            elif acodec != "none" and vcodec == "none" and direct_url:
                abr = f.get("abr", 128)
                audio_streams.append({
                    "type": "audio",
                    "quality": f"{int(abr)} kbps source" if abr else "Source audio",
                    "format": "mp3",
                    "url": direct_url,
                    "format_id": format_id,
                    "label": f"Audio MP3 ({int(abr) if abr else 128}k)"
                })

        # Sort video streams by height descending and deduplicate by resolution
        streams.sort(key=lambda x: x.get("height", 0), reverse=True)
        seen_res = set()
        clean_streams = []
        for s in streams:
            q = s["quality"]
            if q not in seen_res:
                seen_res.add(q)
                clean_streams.append(s)
            if len(clean_streams) >= 4:
                break

        # Best audio stream
        if audio_streams:
            clean_streams.append(audio_streams[0])
        elif clean_streams:
            # Add audio-extraction stream pointing to best video stream
            clean_streams.append({
                "type": "audio",
                "quality": "320 kbps (Studio MP3)",
                "format": "mp3",
                "url": clean_streams[0]["url"],
                "label": "Extract Audio (MP3 320kbps)"
            })

        # Clean hashtags
        hashtags = tags if tags else re.findall(r'#(\w+)', description)

        return {
            "success": True,
            "platform": platform,
            "title": title,
            "caption": description[:300] if description else "",
            "author": author,
            "thumbnail": thumbnail,
            "duration": duration,
            "views": views,
            "likes": likes,
            "hashtags": hashtags[:15],
            "streams": clean_streams,
            "original_url": original_url
        }

    def fetch_instagram_dp(self, username_or_url: str) -> Dict[str, Any]:
        username = username_or_url.strip().replace("@", "")
        if "instagram.com/" in username:
            match = re.search(r'instagram\.com/([^/?#]+)', username)
            if match:
                username = match.group(1)

        try:
            headers = anti_ban.get_instagram_headers(referer=f"https://www.instagram.com/{username}/")
            api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            resp = requests.get(api_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                user_data = resp.json().get("data", {}).get("user", {})
                if user_data:
                    hd_pic = user_data.get("profile_pic_url_hd") or user_data.get("profile_pic_url")
                    return {
                        "success": True,
                        "username": username,
                        "full_name": user_data.get("full_name", ""),
                        "biography": user_data.get("biography", ""),
                        "is_verified": user_data.get("is_verified", False),
                        "followers": user_data.get("edge_followed_by", {}).get("count", 0),
                        "following": user_data.get("edge_follow", {}).get("count", 0),
                        "posts_count": user_data.get("edge_owner_to_timeline_media", {}).get("count", 0),
                        "dp_url": hd_pic,
                        "streams": [
                            {
                                "type": "image",
                                "quality": "Full HD Original",
                                "format": "jpg",
                                "url": hd_pic,
                                "label": "Download Full HD Profile Picture"
                            }
                        ]
                    }
        except Exception as e:
            pass

        return {
            "success": False,
            "error": f"Could not find public profile for @{username}. Please ensure username is correct and public."
        }

extractor = MediaExtractor()
