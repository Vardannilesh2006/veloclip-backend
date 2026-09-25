import random
import os
import time
from typing import Dict, List, Optional, Any

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
    Manages stealth headers, burner session rotation, auto-quarantine, and anti-ban safeguards.
    """
    def __init__(self):
        self.proxy_list = self._load_proxies()
        self._session_pool: List[str] = self._load_sessions()
        self._quarantined_sessions: Dict[str, float] = {}  # session_id -> unquarantine_timestamp
        self._pool_index = 0

    def _load_proxies(self):
        proxy_env = os.environ.get("PROXIES_LIST", "")
        if proxy_env:
            return [p.strip() for p in proxy_env.split(",") if p.strip()]
        return []

    def _load_sessions(self) -> List[str]:
        sessions = []
        pool_env = os.environ.get("INSTAGRAM_SESSIONS_POOL", "")
        if pool_env:
            sessions.extend([s.strip() for s in pool_env.split(",") if s.strip()])
        single_sess = os.environ.get("INSTAGRAM_SESSION_ID", "").strip()
        if single_sess and single_sess not in sessions:
            sessions.append(single_sess)
        return sessions

    def add_session(self, session_id: str):
        session_id = session_id.strip()
        if session_id and session_id not in self._session_pool:
            self._session_pool.append(session_id)
            if session_id in self._quarantined_sessions:
                del self._quarantined_sessions[session_id]

    def set_session_pool(self, sessions: List[str]):
        self._session_pool = [s.strip() for s in sessions if s.strip()]
        self._quarantined_sessions.clear()
        self._pool_index = 0

    def get_instagram_session(self) -> Optional[str]:
        """Returns the next healthy, non-quarantined session id via round-robin."""
        now = time.time()
        # Clean expired quarantines
        expired = [s for s, expire_time in self._quarantined_sessions.items() if now > expire_time]
        for s in expired:
            del self._quarantined_sessions[s]

        # Available sessions
        available = [s for s in self._session_pool if s not in self._quarantined_sessions]
        if not available:
            return None

        self._pool_index = (self._pool_index + 1) % len(available)
        return available[self._pool_index]

    def quarantine_session(self, session_id: str, duration_seconds: int = 3600):
        """Quarantine a flagged session for duration_seconds (default 1 hour)."""
        if session_id:
            self._quarantined_sessions[session_id] = time.time() + duration_seconds

    def get_session_pool_status(self) -> Dict[str, Any]:
        now = time.time()
        active = [s for s in self._session_pool if s not in self._quarantined_sessions or now > self._quarantined_sessions.get(s, 0)]
        quarantined = [s for s in self._session_pool if s in self._quarantined_sessions and now <= self._quarantined_sessions[s]]
        return {
            "total_configured": len(self._session_pool),
            "active_healthy": len(active),
            "quarantined": len(quarantined),
            "has_available_session": len(active) > 0,
        }

    def get_random_user_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def get_instagram_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
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
