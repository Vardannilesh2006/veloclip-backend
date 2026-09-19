import re
from typing import Dict, Any, List

def analyze_viral_metadata(title: str, caption: str, hashtags: List[str], duration: int = 30) -> Dict[str, Any]:
    """
    AI Viral Strategy & Hook Analyzer:
    Analyzes engagement hooks, viral keywords, and gives creator repurposing recommendations.
    """
    full_text = f"{title} {caption}".lower()
    
    # Analyze hook strength
    hook_score = 75
    hook_tips = []
    
    if len(caption) > 100:
        hook_score += 10
        hook_tips.append("Strong narrative depth in caption (boosts watch time & save rate)")
    else:
        hook_tips.append("Short punchy punchline format (great for rapid loop reels)")

    if len(hashtags) >= 5:
        hook_score += 10
        hook_tips.append("Targeted multi-tier hashtag cluster detected")
    else:
        hook_tips.append("Broad reach focus (algorithm-first distribution)")

    # Suggest viral repurposing angles
    repurposing_angles = [
        "Create a reaction/commentary short using the 320kbps extracted audio",
        "Extract key quote and turn into a high-contrast Twitter/Threads carousel",
        "Repurpose for YouTube Shorts with 9:16 auto-captions"
    ]

    return {
        "hook_score": min(hook_score, 98),
        "viral_grade": "A+" if hook_score > 85 else "A",
        "tags_count": len(hashtags),
        "top_tags": hashtags[:10],
        "creator_tips": hook_tips,
        "repurpose_ideas": repurposing_angles,
        "suggested_hashtags": [f"#{t}" if not t.startswith('#') else t for t in hashtags[:8]]
    }

def generate_mock_subtitles(title: str, caption: str, duration: int = 15) -> Dict[str, Any]:
    """
    Fast AI Subtitle / Caption Generator (.SRT & Plain Text).
    Uses smart sentence segmenting to produce instant ready-to-use subtitles for creators.
    """
    # Clean text into sentences or chunks
    clean_text = re.sub(r'#\w+', '', caption).strip()
    if not clean_text:
        clean_text = title
    
    words = clean_text.split()
    if not words:
        words = ["Trending", "viral", "reel", "highlight", "video", "clip"]

    chunk_size = 4
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    
    srt_lines = []
    step = max(1, duration // max(1, len(chunks)))
    current_sec = 0

    for idx, chunk in enumerate(chunks[:12]):
        start_time = f"00:00:{current_sec:02d},000"
        end_sec = min(current_sec + step, duration)
        end_time = f"00:00:{end_sec:02d},900"
        srt_lines.append(f"{idx + 1}\n{start_time} --> {end_time}\n{chunk}\n")
        current_sec = end_sec

    srt_content = "\n".join(srt_lines)

    return {
        "success": True,
        "plain_text": clean_text,
        "srt_content": srt_content,
        "filename": "clipnova_subtitles.srt"
    }
