import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# 台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

# 依照 AGENTS.md 定義的五大前景供應鏈與中英文搜尋關鍵字
SECTOR_KEYWORDS = {
    "01_先進製程與CoWoS": [
        {"q": "台積電 CoWoS OR 先進封裝 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "日月光 先進封裝 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "TSMC CoWoS OR NVIDIA packaging when:1d", "lang": "en-US", "gl": "US"},
    ],
    "02_AI伺服器與散熱": [
        {"q": "奇鋐 OR 雙鴻 水冷散熱 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "鴻海 AI伺服器 GB200 OR GB300 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "NVIDIA GB200 OR GB300 liquid cooling when:1d", "lang": "en-US", "gl": "US"},
    ],
    "03_矽光子與CPO": [
        {"q": "聯鈞 OR 波若威 OR 上詮 矽光子 OR CPO when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "Silicon Photonics CPO Broadcom when:1d", "lang": "en-US", "gl": "US"},
    ],
    "04_邊緣AI與機器人": [
        {"q": "研華 OR 所羅門 邊緣AI OR 機器人 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "NVIDIA Jetson OR humanoid robotics when:1d", "lang": "en-US", "gl": "US"},
    ],
    "05_重電與綠能儲能": [
        {"q": "華城 OR 中興電 重電 OR 變壓器 when:1d", "lang": "zh-TW", "gl": "TW"},
        {"q": "US power grid transformer GE Vernova when:1d", "lang": "en-US", "gl": "US"},
    ],
}


def clean_html(raw_html: str) -> str:
    """清除 RSS 摘要中的 HTML 標籤與多餘空白"""
    text = re.sub(r"<[^>]+>", " ", raw_html or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_google_news_rss(query: str, lang: str, gl: str) -> list[dict]:
    """抓取單一關鍵字的 Google News RSS 並過濾超過 36 小時的舊聞"""
    encoded_q = urllib.parse.quote(query)
    ceid = f"{gl}:{lang.split('-')[0]}"
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl={lang}&gl={gl}&ceid={ceid}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )

    articles = []
    now_tw = datetime.now(TW_TZ)
    cutoff_time = now_tw - timedelta(hours=36)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date_str = item.findtext("pubDate") or ""
            source = (item.findtext("source") or "未知來源").strip()
            description = clean_html(item.findtext("description") or "")

            # 解析並轉換為台灣時間
            try:
                pub_dt = parsedate_to_datetime(pub_date_str).astimezone(TW_TZ)
            except Exception:
                pub_dt = now_tw

            # 嚴格過濾超過 36 小時的舊新聞
            if pub_dt < cutoff_time:
                continue

            articles.append(
                {
                    "title": title,
                    "source": source,
                    "published_at": pub_dt.strftime("%Y-%m-%d %H:%M"),
                    "summary": description,
                    "link": link,
                    "region": "TW" if gl == "TW" else "US",
                }
            )
    except Exception as e:
        print(f"[警告] 抓取失敗 ({query}): {e}")

    return articles


def run_crawler():
    now_tw = datetime.now(TW_TZ)
    today_str = now_tw.strftime("%Y-%m-%d")

    os.makedirs("raw_news", exist_ok=True)
    result = {
        "crawled_at": now_tw.strftime("%Y-%m-%d %H:%M:%S CST"),
        "date": today_str,
        "sectors": {},
    }

    total_count = 0
    for sector, queries in SECTOR_KEYWORDS.items():
        print(f"正在抓取：{sector} ...")
        seen_titles = set()
        sector_articles = []

        for q_info in queries:
            fetched = fetch_google_news_rss(q_info["q"], q_info["lang"], q_info["gl"])
            for art in fetched:
                # 簡易標題去重（取前 18 個字元比對）
                title_key = art["title"][:18]
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    sector_articles.append(art)

        # 依發布時間由新到舊排序，每個類股最多保留 15 則精華新聞
        sector_articles.sort(key=lambda x: x["published_at"], reverse=True)
        sector_articles = sector_articles[:15]

        result["sectors"][sector] = sector_articles
        total_count += len(sector_articles)
        print(f"  -> 取得 {len(sector_articles)} 則最新新聞")

    output_path = os.path.join("raw_news", f"{today_str}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n完成！共收集 {total_count} 則新聞，已存檔至：{output_path}")


if __name__ == "__main__":
    run_crawler()