"""
AI 热点资讯 — 三栏布局静态 HTML 生成
左栏: 热搜榜单 | 中栏: 公司卡片 | 右栏: 媒体混排
"""
import json
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from string import Template

CST = timezone(timedelta(hours=8))
log = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "data.json"
HOTLIST_FILE = Path(__file__).resolve().parent.parent / "data" / "hotlist.json"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "docs" / "index.html"

# ── 公司关键词映射（中栏分类用） ──
# 每个公司的 keywords 支持两种格式：
#   字符串 str → 大小写不敏感子串匹配
#   元组 (str, True) → 整词正则匹配 \bword\b
COMPANY_CONFIG = OrderedDict([
    ("OpenAI", {
        "icon": "🤖",
        "color": "#10b981",
        "keywords": ["openai", "gpt", "chatgpt", "codex", "sora", "altman"],
    }),
    ("Anthropic", {
        "icon": "🟣",
        "color": "#8b5cf6",
        "keywords": ["anthropic", "claude"],
    }),
    ("Google", {
        "icon": "🔵",
        "color": "#3b82f6",
        "keywords": ["google", "gemini", "deepmind", "notebooklm"],
    }),
    ("Meta", {
        "icon": "🔮",
        "color": "#06b6d4",
        "keywords": ["meta ai", "llama", "facebook ai", ("meta", True)],
    }),
    ("Microsoft", {
        "icon": "🟦",
        "color": "#00a4ef",
        "keywords": ["microsoft", "copilot", "azure"],
    }),
    ("Apple", {
        "icon": "🍎",
        "color": "#64748b",
        "keywords": ["apple intelligence", ("apple", True)],
    }),
    ("xAI", {
        "icon": "⚡",
        "color": "#f97316",
        "keywords": [("xai", True), "grok", "elon musk"],
    }),
    ("AWS", {
        "icon": "☁️",
        "color": "#f97316",
        "keywords": ["aws", "amazon bedrock"],
    }),
    ("NVIDIA", {
        "icon": "💚",
        "color": "#76b900",
        "keywords": ["nvidia"],
    }),
    ("DeepSeek", {
        "icon": "🧠",
        "color": "#14b8a6",
        "keywords": ["deepseek"],
    }),
    ("字节跳动", {
        "icon": "🎵",
        "color": "#1e80ff",
        "keywords": ["bytedance", "字节跳动", "字节", "豆包", "doubao",
                      "tiktok ai"],
    }),
    ("阿里巴巴", {
        "icon": "🛒",
        "color": "#ff6a00",
        "keywords": ["alibaba", "阿里巴巴", "通义千问", "qwen"],
    }),
    ("百度", {
        "icon": "🎯",
        "color": "#f59e0b",
        "keywords": ["百度", "baidu", "文心一言", "文心", "ernie"],
    }),
    ("腾讯", {
        "icon": "🐧",
        "color": "#07c160",
        "keywords": ["tencent", "腾讯"],
    }),
    ("华为", {
        "icon": "📱",
        "color": "#cf0a2c",
        "keywords": ["huawei", "华为", "昇腾"],
    }),
    ("智谱AI", {
        "icon": "🔬",
        "color": "#8b5cf6",
        "keywords": ["zhipu", "智谱", "glm"],
    }),
    ("月之暗面", {
        "icon": "🌙",
        "color": "#ec4899",
        "keywords": ["moonshot", "kimi", "月之暗面"],
    }),
    ("百川智能", {
        "icon": "🌊",
        "color": "#06b6d4",
        "keywords": ["baichuan", "百川智能", "百川"],
    }),
    ("零一万物", {
        "icon": "💫",
        "color": "#6366f1",
        "keywords": ["零一万物", "yi-ai"],
    }),
    ("阶跃星辰", {
        "icon": "⭐",
        "color": "#f59e0b",
        "keywords": ["阶跃星辰", "stepfun"],
    }),
    ("Mistral", {
        "icon": "🌬️",
        "color": "#6366f1",
        "keywords": ["mistral"],
    }),
    ("小米", {
        "icon": "📱",
        "color": "#ff6900",
        "keywords": ["xiaomi", "小米", "mimo"],
    }),
])

# ── 平台配色 ──
PLATFORM_COLORS = {
    "weibo": "#e6162d",
    "douyin": "#333333",
    "zhihu": "#0066ff",
    "baidu": "#4e6ef2",
    "bilibili": "#fb7299",
    "toutiao": "#f42b02",
    "thepaper": "#e60012",
    "36kr": "#1d8c9e",
    "v2ex": "#e2ab00",
    "twitter": "#1da1f2",
}


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def time_ago(pub_iso: str | None) -> str:
    if not pub_iso:
        return ""
    try:
        pub = datetime.fromisoformat(pub_iso)
        now = datetime.now(CST)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        delta = now - pub
        secs = int(delta.total_seconds())
        if secs < 0:
            return "刚刚"
        if secs < 60:
            return f"{secs}秒前"
        mins = secs // 60
        if mins < 60:
            return f"{mins}分钟前"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs}小时前"
        days = hrs // 24
        if days < 30:
            return f"{days}天前"
        return pub.strftime("%m-%d")
    except Exception:
        return ""


def detect_company(title: str) -> str | None:
    """检测文章标题所属的公司。"""
    title_lower = title.lower()
    for company, cfg in COMPANY_CONFIG.items():
        for kw in cfg["keywords"]:
            if isinstance(kw, tuple):
                # 整词匹配 \bword\b
                pattern = kw[0]
                if re.search(rf"\b{re.escape(pattern)}\b", title_lower):
                    return company
            else:
                if kw in title_lower:
                    return company
    return None


# ================================================================
# HTML 模板
# ================================================================

T = Template(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔥 AI 热点资讯</title>
<style>
  :root {
    --bg: #f1f5f9;
    --card-bg: #ffffff;
    --text: #0f172a;
    --text-secondary: #64748b;
    --text-tertiary: #94a3b8;
    --border: #e2e8f0;
    --accent: #3b82f6;
    --header-bg: rgba(255,255,255,.9);
    --hover-bg: #f8fafc;
    --shadow: 0 1px 3px rgba(0,0,0,.06);
  }
  [data-theme="dark"] {
    --bg: #0f172a;
    --card-bg: #1e293b;
    --text: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-tertiary: #64748b;
    --border: #334155;
    --accent: #60a5fa;
    --header-bg: rgba(15,23,42,.9);
    --hover-bg: #1e293b;
    --shadow: 0 1px 3px rgba(0,0,0,.2);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    transition: background .3s, color .3s;
  }
  a { color: inherit; text-decoration: none; }
  a:hover { color: var(--accent); }

  /* ── Header ── */
  header {
    position: sticky; top: 0; z-index: 50;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    background: var(--header-bg);
    border-bottom: 1px solid var(--border);
    padding: 12px 0;
  }
  .header-inner {
    max-width: 1440px; margin: 0 auto; padding: 0 20px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .logo { font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .logo span { background: linear-gradient(135deg,#3b82f6,#8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .header-right { display: flex; align-items: center; gap: 16px; font-size: 13px; color: var(--text-secondary); }
  .theme-btn {
    background: var(--border); border: none; color: var(--text);
    width: 32px; height: 32px; border-radius: 8px; cursor: pointer; font-size: 15px;
    display: flex; align-items: center; justify-content: center;
    transition: background .2s;
  }
  .theme-btn:hover { opacity: .8; }

  /* ── 3-Column Grid ── */
  .grid {
    max-width: 1440px; margin: 0 auto; padding: 20px;
    display: grid;
    grid-template-columns: 300px 1fr 1fr;
    gap: 20px;
    align-items: start;
  }
  .col { min-width: 0; }

  /* ── Section Headers ── */
  .section-title {
    font-size: 15px; font-weight: 700; margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
    padding-bottom: 8px; border-bottom: 2px solid var(--border);
  }

  /* ── Left: Hotlist ── */
  .hotlist-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; margin-bottom: 16px;
    box-shadow: var(--shadow);
  }
  .hotlist-header {
    font-size: 14px; font-weight: 700; margin-bottom: 10px;
    display: flex; align-items: center; gap: 8px;
  }
  .hotlist-dot {
    width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0;
  }
  .hotlist-item {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 6px 0; border-bottom: 1px solid var(--border);
    font-size: 13px; line-height: 1.5;
  }
  .hotlist-item:last-child { border-bottom: none; }
  .hotlist-item:hover { color: var(--accent); }
  .hotlist-rank {
    flex-shrink: 0; width: 22px; text-align: center;
    font-size: 12px; font-weight: 700; color: var(--text-tertiary);
  }
  .hotlist-rank.top3 { color: var(--accent); }
  .hotlist-item a { flex: 1; min-width: 0; }
  .hotlist-item a:hover { color: var(--accent); }

  .hotlist-empty {
    font-size: 13px; color: var(--text-tertiary); text-align: center; padding: 20px 0;
  }

  /* ── Middle: Company Cards ── */
  .company-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; margin-bottom: 16px;
    box-shadow: var(--shadow);
  }
  .company-header {
    display: flex; align-items: center; gap: 8px;
    font-size: 14px; font-weight: 700; margin-bottom: 10px;
    padding-bottom: 10px; border-bottom: 2px solid;
  }
  .company-item {
    padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px;
  }
  .company-item:last-child { border-bottom: none; }
  .company-item-title { font-weight: 500; display: block; line-height: 1.5; }
  .company-item-title:hover { color: var(--accent); }
  .company-item-meta { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; display: flex; gap: 8px; }
  .company-empty {
    font-size: 13px; color: var(--text-tertiary); text-align: center; padding: 12px 0;
  }

  /* ── Right: Media Feed ── */
  .media-item {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; margin-bottom: 10px;
    box-shadow: var(--shadow);
    transition: border-color .2s;
  }
  .media-item:hover { border-color: var(--accent); }
  .media-meta {
    display: flex; align-items: center; gap: 6px; font-size: 12px;
    color: var(--text-tertiary); margin-bottom: 4px; flex-wrap: wrap;
  }
  .media-source {
    font-weight: 600; color: var(--text-secondary);
  }
  .media-cat {
    font-size: 10px; padding: 1px 6px; border-radius: 999px; font-weight: 500;
  }
  .media-title {
    font-size: 14px; font-weight: 600; line-height: 1.5;
  }
  .media-title a:hover { color: var(--accent); }

  /* ── Responsive ── */
  @media (max-width: 1100px) {
    .grid { grid-template-columns: 1fr 1fr; }
    .col-left { display: none; }
    .mobile-toggle { display: flex !important; }
  }
  @media (max-width: 640px) {
    .grid { grid-template-columns: 1fr; padding: 12px; }
    .col-left { display: none; }
    .mobile-toggle { display: flex !important; }
  }

  /* ── Mobile toggle ── */
  .mobile-toggle {
    display: none !important;
    align-items: center; gap: 4px;
    font-size: 13px; color: var(--accent); cursor: pointer;
    background: none; border: none; padding: 4px 8px;
  }
  .mobile-toggle:hover { opacity: .8; }
</style>
</head>
<body>

<header>
  <div class="header-inner">
    <div style="display:flex;align-items:center;gap:12px;">
      <div class="logo">🔥 <span>AI 热点资讯</span></div>
      <button class="mobile-toggle" onclick="toggleLeft()">📋 热搜</button>
    </div>
    <div class="header-right">
      <span>${update_time}</span>
      <span>共 ${total_count} 条</span>
      <button class="theme-btn" onclick="toggleTheme()" id="themeBtn">🌙</button>
    </div>
  </div>
</header>

<div class="grid">
  <!-- ═══ 左栏: 热搜榜单 ═══ -->
  <div class="col col-left" id="leftCol">
    <div class="section-title">🔥 热搜榜单</div>
    ${hotlist_html}
  </div>

  <!-- ═══ 中栏: 公司卡片 ═══ -->
  <div class="col col-middle">
    <div class="section-title">🏢 AI 公司动态</div>
    ${company_html}
  </div>

  <!-- ═══ 右栏: 媒体混排 ═══ -->
  <div class="col col-right">
    <div class="section-title">📰 媒体速览</div>
    ${media_html}
  </div>
</div>

<footer style="text-align:center;padding:20px;font-size:13px;color:var(--text-tertiary);border-top:1px solid var(--border);">
  数据来源：AI 热点资讯 · 每天 06:00 / 12:00 更新 · Powered by GitHub Actions
</footer>

<script>
function toggleTheme() {
  const html = document.documentElement;
  const btn = document.getElementById('themeBtn');
  if (html.getAttribute('data-theme') === 'dark') {
    html.removeAttribute('data-theme');
    btn.textContent = '🌙';
    localStorage.setItem('theme', 'light');
  } else {
    html.setAttribute('data-theme', 'dark');
    btn.textContent = '☀️';
    localStorage.setItem('theme', 'dark');
  }
}
function toggleLeft() {
  const col = document.getElementById('leftCol');
  col.style.display = col.style.display === 'none' ? 'block' : 'none';
}
(function() {
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.getElementById('themeBtn').textContent = '☀️';
  }
})();
</script>
</body>
</html>""")


# ================================================================
# 构建函数
# ================================================================

def build_hotlist(hotlist_data: dict) -> str:
    """构建左栏热搜榜单 HTML。"""
    platforms = hotlist_data.get("platforms", {})
    parts = []

    for plat_id in ["weibo", "zhihu", "baidu", "douyin", "bilibili",
                     "toutiao", "thepaper", "36kr", "v2ex"]:
        pdata = platforms.get(plat_id)
        if not pdata:
            continue

        name = pdata["name"]
        color = PLATFORM_COLORS.get(plat_id, "#666")
        items = pdata.get("items", [])

        if not items:
            parts.append(
                f'<div class="hotlist-card">'
                f'<div class="hotlist-header">'
                f'<span class="hotlist-dot" style="background:{color}"></span>'
                f'{name} 热搜'
                f'</div>'
                f'<div class="hotlist-empty">暂无相关科技热搜</div>'
                f'</div>'
            )
            continue

        item_html = ""
        for it in items[:15]:  # 最多显示 15 条
            rank = it.get("rank", 0)
            title = escape(it.get("title", ""))
            url = it.get("url", "#")
            rank_cls = "hotlist-rank top3" if rank <= 3 else "hotlist-rank"

            item_html += (
                f'<div class="hotlist-item">'
                f'<span class="{rank_cls}">{rank}</span>'
                f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
                f'</div>'
            )

        parts.append(
            f'<div class="hotlist-card">'
            f'<div class="hotlist-header">'
            f'<span class="hotlist-dot" style="background:{color}"></span>'
            f'{name} 热搜'
            f'</div>'
            f'{item_html}'
            f'</div>'
        )

    if not parts:
        return '<div class="hotlist-empty">暂无热搜数据</div>'
    return "\n".join(parts)


def build_company(items: list[dict]) -> str:
    """构建中栏公司卡片 HTML。"""
    # 按公司归类
    company_articles: dict[str, list[dict]] = {}
    for item in items:
        title = item.get("title", "")
        company = detect_company(title)
        if company:
            company_articles.setdefault(company, []).append(item)

    parts = []
    for company_name, cfg in COMPANY_CONFIG.items():
        articles = company_articles.get(company_name, [])
        if not articles:
            continue
        icon = cfg["icon"]
        color = cfg["color"]
        # 最多显示 8 条
        articles = articles[:8]

        item_html = ""
        for a in articles:
            title = escape(a.get("title", ""))
            url = a.get("url", "#")
            source = escape(a.get("source", ""))
            t = time_ago(a.get("published", ""))
            item_html += (
                f'<div class="company-item">'
                f'<a class="company-item-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
                f'<div class="company-item-meta"><span>{source}</span><span>{t}</span></div>'
                f'</div>'
            )

        if not item_html:
            continue

        parts.append(
            f'<div class="company-card">'
            f'<div class="company-header" style="border-bottom-color:{color}40;color:{color}">'
            f'{icon} {company_name}'
            f'</div>'
            f'{item_html}'
            f'</div>'
        )

    if not parts:
        return '<div class="company-empty">暂无公司相关文章</div>'
    return "\n".join(parts)


def build_media(items: list[dict]) -> str:
    """构建右栏媒体速览 HTML。"""
    CAT_LABELS = {
        "industry": "行业", "community": "社区", "company": "公司",
        "research": "研究", "opinion": "观点", "other": "其他",
    }
    CAT_COLORS = {
        "industry": "#3b82f6", "community": "#f59e0b", "company": "#10b981",
        "research": "#8b5cf6", "opinion": "#ec4899", "other": "#6b7280",
    }

    # 过滤出 media column 和非公司专属的文章
    media_items = []
    for item in items:
        source_id = item.get("source_id", "")
        col = item.get("column", "media")
        if col == "media":
            media_items.append(item)

    if not media_items:
        return '<div class="hotlist-empty">暂无媒体文章</div>'

    parts = []
    for it in media_items[:60]:  # 最多 60 条
        title = escape(it.get("title", ""))
        url = it.get("url", "#")
        source = escape(it.get("source", ""))
        cat = it.get("category", "other")
        cat_label = CAT_LABELS.get(cat, "其他")
        cat_color = CAT_COLORS.get(cat, "#6b7280")
        t = time_ago(it.get("published", ""))

        parts.append(
            f'<div class="media-item">'
            f'<div class="media-meta">'
            f'<span class="media-source">{source}</span>'
            f'<span class="media-cat" style="background:{cat_color}18;color:{cat_color}">{cat_label}</span>'
            f'<span>{t}</span>'
            f'</div>'
            f'<div class="media-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>'
            f'</div>'
        )

    return "\n".join(parts)


# ================================================================
# Main
# ================================================================

def main():
    # 加载 RSS 数据
    if not DATA_FILE.exists():
        log.warning("No data file found at %s", DATA_FILE)
        html = T.safe_substitute(
            update_time=datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
            total_count="0",
            hotlist_html='<div class="hotlist-empty">暂无数据</div>',
            company_html='<div class="company-empty">暂无数据</div>',
            media_html='<div class="hotlist-empty">暂无数据</div>',
        )
    else:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        items = data.get("items", [])

        # 加载热榜数据
        hotlist_data = {}
        if HOTLIST_FILE.exists():
            hotlist_data = json.loads(HOTLIST_FILE.read_text(encoding="utf-8"))

        # 注入 column 信息（来自 RSS 条目存储时已带 source_id，但 column 未存）
        # 从 feeds.yaml 读取 column 映射
        feeds_path = Path(__file__).resolve().parent / "feeds.yaml"
        if feeds_path.exists():
            import yaml
            with open(feeds_path, encoding="utf-8") as f:
                feeds_cfg = yaml.safe_load(f)
            col_map = {f["id"]: f.get("column", "media") for f in feeds_cfg["feeds"] if f.get("enabled", True)}
            for item in items:
                item["column"] = col_map.get(item.get("source_id", ""), "media")

        html = T.safe_substitute(
            update_time=data.get("updated_at_cn", datetime.now(CST).strftime("%Y-%m-%d %H:%M")),
            total_count=str(len(items)),
            hotlist_html=build_hotlist(hotlist_data),
            company_html=build_company(items),
            media_html=build_media(items),
        )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    log.info("Generated %s", OUTPUT_FILE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
