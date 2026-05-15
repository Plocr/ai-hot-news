"""
AI 热点资讯 — RSS 抓取与解析
"""
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import feedparser
import httpx
import yaml

CST = timezone(timedelta(hours=8))
CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "data.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def load_feeds() -> list[dict[str, Any]]:
    feeds_path = Path(__file__).resolve().parent / "feeds.yaml"
    with open(feeds_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return [f for f in config["feeds"] if f.get("enabled", True)]


def fetch_feed(feed_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """抓取单个 RSS 源，返回条目列表。"""
    url = feed_cfg["url"]
    log.info("Fetching: %s (%s)", feed_cfg["name"], url)

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "AI-Hot-News/1.0"},
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return []

    feed = feedparser.parse(resp.text)
    items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue

        title = entry.get("title", "").strip()
        if not title:
            continue

        # 发布时间
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        pub_time = None
        if published:
            try:
                pub_time = datetime(*published[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        # 摘要 — 清理 HTML tag
        summary = entry.get("summary", "") or entry.get("description", "")
        summary = re.sub(r"<[^>]+>", "", summary)
        summary = re.sub(r"\s+", " ", summary).strip()
        if len(summary) > 300:
            summary = summary[:297] + "..."

        items.append({
            "id": hashlib.md5(link.encode()).hexdigest()[:12],
            "title": title,
            "url": link,
            "summary": summary,
            "source": feed_cfg["name"],
            "source_id": feed_cfg["id"],
            "category": feed_cfg.get("category", "other"),
            "published": pub_time.isoformat() if pub_time else None,
            "timestamp": int(pub_time.timestamp()) if pub_time else 0,
        })

    # 限制每个源的最大条目数
    max_items = feed_cfg.get("max_items", 0)
    if max_items > 0 and len(items) > max_items:
        log.info("  → Truncated from %d to %d items", len(items), max_items)
        items = items[:max_items]

    log.info("  → Got %d items from %s", len(items), feed_cfg["name"])
    return items


def deduplicate(all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 URL 去重，保留最先出现的。"""
    seen: set[str] = set()
    result = []
    for item in all_items:
        if item["url"] not in seen:
            seen.add(item["url"])
            result.append(item)
    return result


def load_history() -> set[str]:
    """读取历史条目 ID，用于去重。"""
    if not CACHE_FILE.exists():
        return set()
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return {item["id"] for item in data.get("items", [])}
    except Exception:
        return set()


def save_data(items: list[dict[str, Any]]):
    """保存数据到 JSON。"""
    now = datetime.now(CST)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": now.isoformat(),
        "updated_at_cn": now.strftime("%Y-%m-%d %H:%M"),
        "item_count": len(items),
        "items": items,
    }
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved %d items to %s", len(items), CACHE_FILE)


def main():
    feeds = load_feeds()
    log.info("Loaded %d enabled feeds", len(feeds))

    # 读取已有历史，保留旧条目
    history_ids = load_history()
    old_items = []
    old_data_path = CACHE_FILE
    if old_data_path.exists():
        try:
            old_data = json.loads(old_data_path.read_text(encoding="utf-8"))
            old_items = [i for i in old_data.get("items", []) if i["id"] in history_ids]
        except Exception:
            pass

    # 并发请求所有 RSS
    all_items = []
    for feed_cfg in feeds:
        items = fetch_feed(feed_cfg)
        all_items.extend(items)
        time.sleep(0.5)  # 礼貌间隔

    # 去重 + 合并历史
    all_items = deduplicate(all_items)

    # 合并旧条目（保留不在新结果中的历史）
    new_ids = {item["id"] for item in all_items}
    for old in old_items:
        if old["id"] not in new_ids:
            all_items.append(old)

    # 按时间排序（最新的在前）
    all_items.sort(key=lambda x: x["timestamp"], reverse=True)

    save_data(all_items)


# ============================================================
# 平台热榜抓取（uapis.cn + X/Twitter）
# ============================================================

HOTLIST_API_BASE = "https://uapis.cn/api/v1/misc/hotboard"
HOTLIST_CACHE = Path(__file__).resolve().parent.parent / "data" / "hotlist.json"

# 要抓取的热榜平台 — 所有平台都取 TOP 50
HOTLIST_PLATFORMS = [
    {"id": "weibo",    "name": "微博"},
    {"id": "douyin",   "name": "抖音"},
    {"id": "zhihu",    "name": "知乎"},
    {"id": "baidu",    "name": "百度"},
    {"id": "bilibili", "name": "B站"},
    {"id": "toutiao",  "name": "头条"},
    {"id": "thepaper", "name": "澎湃"},
    {"id": "36kr",     "name": "36氪"},
    {"id": "v2ex",     "name": "V2EX"},
]

# AI 相关关键词（扩展版）
AI_KEYWORDS = [
    "ai", "人工智能", "大模型", "gpt", "chatgpt", "openai", "claude",
    "gemini", "llama", "deepseek", "文心一言", "通义千问", "通义", "星火",
    "机器学习", "深度学习", "神经网络", "transformer", "diffusion",
    "agent", "智能体", "多模态", "机器人", "自动驾驶", "具身智能",
    "copilot", "codex", "sora", "grok", "mistral", "qwen", "kimi",
    "ai搜索", "ai助手", "ai编程", "ai绘画", "ai视频", "ai芯片",
    "llm", "大语言模型", "多模态", "aigc", "生成式",
    "数据科学", "推荐算法", "强化学习",
    "算力", "gpu", "h100", "h200", "b200", "芯片",
    "数字人", "人形机器人", "ai pc",
    "苹果ai", "华为ai", "百度ai", "阿里ai",
    "英伟达", "nvidia", "hugging face", "hf ",
    "ai安全", "ai监管", "ai治理",
]

# Twitter API 常量（保留备用，但目前所有公共 Twitter API 均已封锁）
# TWITTER_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


def fetch_platform_hotlist(platform: dict) -> list[dict]:
    """从 uapis.cn 获取单个平台的热榜数据。"""
    plat_id = platform["id"]
    url = f"{HOTLIST_API_BASE}?type={plat_id}&size=50"
    log.info("Fetching hotlist: %s", platform["name"])

    try:
        resp = httpx.get(url, headers={"User-Agent": "AI-Hot-News/1.0"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Failed to fetch hotlist %s: %s", plat_id, e)
        return []

    items = []
    raw_list = data.get("list", [])
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("title") or "").strip()
        url_link = (entry.get("url") or "").strip()
        if not title:
            continue

        hot = entry.get("hot_value", entry.get("hot", 0))
        rank = entry.get("index", 0)

        items.append({
            "title": title,
            "url": url_link,
            "hot": str(hot),
            "rank": int(rank),
        })

    log.info("  → Got %d items from %s", len(items), platform["name"])
    return items


def fetch_twitter_trends() -> list[dict]:
    """通过 Twitter API 获取趋势话题（无需 guest token）。"""
    log.info("Fetching hotlist: X/Twitter")
    try:
        resp = httpx.get(
            "https://api.twitter.com/1.1/trends/place.json?id=1",
            headers={"Authorization": f"Bearer {TWITTER_BEARER}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        trends = data[0].get("trends", [])
    except Exception as e:
        log.warning("Failed to fetch Twitter trends: %s", e)
        return []

    items = []
    for i, t in enumerate(trends[:50], 1):
        name = t.get("name", "").strip()
        url = t.get("url", "")
        volume = t.get("tweet_volume")
        if not name:
            continue
        items.append({
            "title": name,
            "url": f"https://twitter.com/search?q={urllib.parse.quote(name)}" if not url else url,
            "hot": str(volume) if volume else "",
            "rank": i,
        })

    log.info("  → Got %d items from X/Twitter", len(items))
    return items


def filter_ai_items(items: list[dict]) -> list[dict]:
    """过滤出 AI 相关的热榜条目。"""
    pattern = re.compile("|".join(AI_KEYWORDS), re.IGNORECASE)
    filtered = []
    for it in items:
        title = it.get("title", "")
        if pattern.search(title):
            filtered.append(it)
    log.info("  → AI-filtered: %d / %d items", len(filtered), len(items))
    return filtered


def save_hotlist(platforms_data: dict):
    """保存热榜数据。"""
    now = datetime.now(CST)
    HOTLIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": now.isoformat(),
        "updated_at_cn": now.strftime("%Y-%m-%d %H:%M"),
        "platforms": platforms_data,
    }
    HOTLIST_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(p["items"]) for p in platforms_data.values())
    log.info("Saved hotlist: %d platforms, %d items to %s", len(platforms_data), total, HOTLIST_CACHE)


def run_hotlist():
    """运行热榜抓取流程 — 只保留 AI/科技相关内容。"""
    platforms_data = {}
    for plat in HOTLIST_PLATFORMS:
        items = fetch_platform_hotlist(plat)
        ai_items = filter_ai_items(items)
        platforms_data[plat["id"]] = {
            "name": plat["name"],
            "items": ai_items[:20],
        }
    save_hotlist(platforms_data)


if __name__ == "__main__":
    import sys
    if "--hotlist" in sys.argv:
        run_hotlist()
    else:
        main()
