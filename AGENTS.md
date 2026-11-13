# AGENTS.md - 台股五大前景供應鏈 LLM Wiki 自動化知識庫

## 1. 專案目標與設計規範
本專案旨在建立一個「自動化累積的台股供應鏈 LLM Wiki 知識庫」，並透過純靜態網頁提供線上瀏覽成果。
- **核心運作流程**：每日透過爬蟲收集五大類股新聞（`raw_news/`）→ 交由 Gemini 依據本文件規則編譯為結構化 Markdown 筆記（`wiki_knowledge/`）→ 透過 GitHub Pages 網頁即時展示。
- **網頁視覺風格（乾淨淺色筆記風 / Notion Style）**：
  - 頁面背景使用柔和淺灰白（`bg-slate-50`），內容卡片使用純白底色搭配細邊框（`bg-white border border-slate-200`）。
  - 知識圖譜雙向連結 `[[實體名稱]]` 統一渲染為淺藍色膠囊標籤（`bg-blue-50 text-blue-700 border-blue-200`）。

---

## 2. 專案目錄結構規範
```text
tw-stock-llm-wiki/
├── AGENTS.md                        # 【核心規則】專案結構、類股定義與 Wiki 撰寫規範
├── crawler.py                       # 【資料收集】自動抓取五大類股最新新聞存成 raw_news/
├── wiki_builder.py                  # 【知識編譯】讀取 AGENTS.md 與原始新聞，更新 wiki_knowledge/
├── requirements.txt                 # Python 套件清單
├── .github/
│   └── workflows/
│       └── daily_wiki.yml           # GitHub Actions 每日雲端自動排程
├── raw_news/                        # 每日原始新聞存檔（格式：YYYY-MM-DD.json）
├── wiki_knowledge/                  # 【核心知識庫】按類股分類的 .md 筆記資料夾
│   ├── manifest.json                # 自動生成的目錄索引（供前端網頁讀取資料夾結構）
│   ├── 01_先進製程與CoWoS/
│   ├── 02_AI伺服器與散熱/
│   ├── 03_矽光子與CPO/
│   ├── 04_邊緣AI與機器人/
│   └── 05_重電與綠能儲能/
└── index.html                       # 【網頁成果】淺色筆記風 Wiki 資料夾線上閱讀器