import random
import os
from typing import Dict, Optional

# Curated pool of modern 2026 realistic User-Agents across devices
USER_AGENTS = [
    # Modern Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Modern Mac Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    # Modern iPhone Safari (iOS 17.5)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    # Android Chrome (Pixel / Galaxy)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.122 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
]

# Instagram mobile web App ID (Official Meta public consumer app ID)
INSTAGRAM_APP_ID = "936619743392459"

class AntiBanManager:
    """
    Manages stealth headers, session rotation, and anti-ban safeguards.
    """
    def __init__(self):
        self.proxy_list = self._load_proxies()

    def _load_proxies(self):
        proxy_env = os.environ.get("PROXIES_LIST", "")
        if proxy_env:
            return [p.strip() for p in proxy_env.split(",") if p.strip()]
        return []

    def get_random_user_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def get_instagram_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        ua = self.get_random_user_agent()
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "X-IG-App-ID": INSTAGRAM_APP_ID,
            "X-ASBD-ID": "129477",
            "X-IG-WWW-Claim": "0",
            "Origin": "https://www.instagram.com",
            "Referer": referer or "https://www.instagram.com/",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        return headers

    def get_generic_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        ua = self.get_random_user_agent()
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer or "https://www.google.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Upgrade-Insecure-Requests": "1",
        }

    def get_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxy_list:
            return None
        proxy = random.choice(self.proxy_list)
        return {
            "http": proxy,
            "https": proxy
        }

anti_ban = AntiBanManager()
