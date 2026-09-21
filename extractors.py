import re
import json
import urllib.parse
from typing import Dict, Any, Optional, List
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
        }

    def extract(self, url: str) -> Dict[str, Any]:
        platform = detect_platform(url)
        if platform == "instagram":
            return self.extract_instagram(url)
        elif platform == "youtube":
            return self.extract_youtube(url)
        elif platform == "facebook":
            return self.extract_facebook(url)
        elif platform == "whatsapp":
            return self.extract_whatsapp(url)
        else:
            # Fallback to general yt-dlp extractor for any other supported site
            return self.extract_generic(url)

    def extract_instagram(self, url: str) -> Dict[str, Any]:
        shortcode = extract_instagram_shortcode(url)
        
        # Tier 1: Try Mobile Web GraphQL / Info API
        if shortcode:
            try:
                headers = anti_ban.get_instagram_headers(referer=url)
                api_url = f"https://www.instagram.com/graphql/query/?doc_id=17867956176966166&variables={{\"shortcode\":\"{shortcode}\"}}"
                resp = requests.get(api_url, headers=headers, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    shortcode_media = data.get("data", {}).get("xdt_shortcode_media") or data.get("data", {}).get("shortcode_media")
                    if shortcode_media:
                        return self._format_instagram_graphql_data(shortcode_media, url)
            except Exception as e:
                # Log and fallback to Tier 2
                pass

        # Tier 2: yt-dlp with anti-bot arguments
        try:
            ydl_opts = dict(self.ydl_opts_base)
            ydl_opts['http_headers'] = anti_ban.get_instagram_headers(referer=url)
            proxy_info = anti_ban.get_proxy()
            if proxy_info and 'https' in proxy_info:
                ydl_opts['proxy'] = proxy_info['https']

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform="instagram", original_url=url)
        except Exception as e:
            # Tier 3: Attempt direct webpage metadata scraping
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
        except Exception:
            pass

        return {
            "success": False,
            "platform": "instagram",
            "error": "Instagram extraction temporary restriction. Please ensure the link is public or retry with another link.",
            "details": err_msg
        }

    def extract_youtube(self, url: str) -> Dict[str, Any]:
        try:
            ydl_opts = dict(self.ydl_opts_base)
            ydl_opts['http_headers'] = anti_ban.get_generic_headers(referer="https://www.youtube.com/")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._format_ytdlp_info(info, platform="youtube", original_url=url)
        except Exception as e:
            # yt-dlp occasionally cannot obtain a player response from cloud
            # datacentres.  Keep the download service available by resolving
            # the public metadata through an Invidious instance instead.
            fallback = self._extract_youtube_invidious(url)
            if fallback:
                return fallback
            return {
                "success": False,
                "platform": "youtube",
                "error": "Failed to parse YouTube media. Please check URL.",
                "details": str(e)
            }

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
        return None

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
