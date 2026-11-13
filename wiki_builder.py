import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# 台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))


def get_available_groq_model(api_key: str) -> str:
    """自動向 Groq 查詢目前帳號可用的最新對話模型"""
    url = "https://api.groq.com/openai/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # 排除語音轉文字、TTS 或安全過濾專用模型
    excluded = ("whisper", "guard", "tts", "playai", "orpheus", "compound")
    candidates = [
        m["id"]
        for m in data.get("data", [])
        if m.get("id") and not any(k in m["id"].lower() for k in excluded)
    ]

    if not candidates:
        raise RuntimeError("Groq 帳號下找不到可用的對話模型！")

    # 優先挑選推理能力較強的大型模型
    preferences = ["llama-4", "70b", "qwen", "gpt-oss", "32b", "llama-3.1-8b-instant"]
    for pref in preferences:
        for mid in candidates:
            if pref in mid.lower():
                return mid

    return candidates[0]


def call_groq(api_key: str, model_id: str, prompt: str) -> dict:
    """呼叫 Groq Chat Completions API 並要求回傳結構化 JSON"""
    url = "https://api.groq.com/openai/v1/chat/completions"

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "你是一位專業的台股供應鏈研究員，請嚴格遵守規則並只輸出合法的 JSON 格式資料。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw_text = result["choices"][0]["message"]["content"].strip()
    # 移除可能出現的 Markdown 程式碼區塊外框
    raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text)
    return json.loads(raw_text)


def sanitize_filename(name: str) -> str:
    """確保檔名安全且以 .md 結尾"""
    base = os.path.basename(name.strip())
    base = re.sub(r'[\\/*?:"<>|]', "_", base)
    if not base.endswith(".md"):
        base += ".md"
    return base


def build_manifest(wiki_root: str, now_tw: datetime):
    """掃描 wiki_knowledge 資料夾，生成目錄索引 manifest.json 供網頁讀取"""
    manifest = {
        "updated_at": now_tw.strftime("%Y-%m-%d %H:%M CST"),
        "sectors": {},
    }

    if os.path.exists(wiki_root):
        for sector in sorted(os.listdir(wiki_root)):
            sector_path = os.path.join(wiki_root, sector)
            if os.path.isdir(sector_path):
                md_files = sorted(
                    [f for f in os.listdir(sector_path) if f.endswith(".md")]
                )
                manifest["sectors"][sector] = md_files

    manifest_path = os.path.join(wiki_root, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"已更新知識庫目錄索引：{manifest_path}")


def run_builder():
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("找不到 GROQ_API_KEY 環境變數！請確認已在 GitHub Secrets 設定金鑰。")

    model_id = get_available_groq_model(api_key)
    print(f"自動選用 Groq 可用模型：{model_id}")

    now_tw = datetime.now(TW_TZ)
    today_str = now_tw.strftime("%Y-%m-%d")

    # 1. 讀取 AGENTS.md 規則
    if not os.path.exists("AGENTS.md"):
        raise FileNotFoundError("找不到 AGENTS.md 規則檔！")
    with open("AGENTS.md", "r", encoding="utf-8") as f:
        agents_rules = f.read()

    # 2. 讀取今日爬蟲抓到的新聞
    news_path = os.path.join("raw_news", f"{today_str}.json")
    if not os.path.exists(news_path):
        print(f"今日尚無新聞檔案 ({news_path})，結束編譯。")
        return

    with open(news_path, "r", encoding="utf-8") as f:
        news_data = json.load(f)

    wiki_root = "wiki_knowledge"
    os.makedirs(wiki_root, exist_ok=True)

    # 3. 逐一處理五大類股
    for sector, articles in news_data.get("sectors", {}).items():
        sector_dir = os.path.join(wiki_root, sector)
        os.makedirs(sector_dir, exist_ok=True)

        if not articles:
            print(f"[{sector}] 今日無新聞，跳過。")
            continue

        # 讀取該資料夾現有的 .md 筆記，讓 AI 能夠進行「增量累加更新」
        existing_notes = {}
        for fname in os.listdir(sector_dir):
            if fname.endswith(".md"):
                with open(os.path.join(sector_dir, fname), "r", encoding="utf-8") as f:
                    existing_notes[fname] = f.read()

        prompt = f"""
你是一位專業的台股供應鏈研究員，負責維護 LLM Wiki 知識庫。
請嚴格遵守以下《AGENTS.md 專案規則》來處理今日新聞：

=== AGENTS.md 規則開始 ===
{agents_rules}
=== AGENTS.md 規則結束 ===

目前處理的類股資料夾為：「{sector}」
今日日期為：「{today_str}」

【該資料夾目前已存在的筆記檔案內容】：
{json.dumps(existing_notes, ensure_ascii=False, indent=2) if existing_notes else "（目前尚無任何筆記，請依主題或代表個股建立新檔案，例如 `2330_台積電.md` 或 `CoWoS先進封裝動態.md`）"}

【今日抓到的原始新聞清單】：
{json.dumps(articles, ensure_ascii=False, indent=2)}

【任務要求】：
1. 依據 AGENTS.md 第 4 節的「資訊過濾守門員原則」，剔除純漲跌播報與無效雜訊，只萃取實質產業事件。
2. 若今日沒有任何具備實質產業價值的新聞，請回傳 `{{"updates": []}}`。
3. 若有實質事件，請將事件整理為「四段式解讀模板」，並由新到舊累加進對應的 `.md` 檔案中（保留原有舊日期內容，若新事件與舊事件相同則合併補充細節）。
4. 務必在文中標註 `[[實體或技術名稱]]` 雙向連結。
5. 請嚴格以以下 JSON 格式回傳結果（回傳更新後的完整檔案 Markdown 內容）：
{{
  "updates": [
    {{
      "filename": "檔案名稱.md",
      "markdown_content": "完整的 Markdown 筆記內容"
    }}
  ]
}}
"""

        print(f"正在呼叫 Groq 編譯：{sector} ...")
        try:
            response_json = call_groq(api_key, model_id, prompt)
            updates = response_json.get("updates", [])

            if not updates:
                print(f"  -> AI 判斷無實質產業事件，維持原狀。")
            for item in updates:
                safe_name = sanitize_filename(item.get("filename", "產業動態.md"))
                content = item.get("markdown_content", "").strip()
                if content:
                    target_file = os.path.join(sector_dir, safe_name)
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(content + "\n")
                    print(f"  -> 已更新筆記：{target_file}")

        except urllib.error.HTTPError as e:
            print(f"[API 錯誤] {sector} HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"[警告] {sector} 編譯失敗: {e}")

        # 間隔 5 秒，避免觸發 Groq 免費版每分鐘請求次數上限
        time.sleep(5)

    # 4. 更新目錄索引供前端網頁使用
    build_manifest(wiki_root, now_tw)
    print("\nLLM Wiki 編譯完成！")


if __name__ == "__main__":
    run_builder()
