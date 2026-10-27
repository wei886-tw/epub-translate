# epub-translate

本地 AI epub 翻譯原型（進行中）。
Local epub translation prototype built with Python and Ollama (work in progress).

> 狀態 / Status：原型，尚未完成。Prototype, not finished.

## 重要聲明 / Notice

- 本專案僅供個人閱讀用途。請自備合法取得的 epub，本 repo 不包含任何書籍內容。
- 翻譯進度檔含整章原文與譯文，已列入 `.gitignore`，請勿上傳。
- 授權：尚未指定授權，保留所有權利。

English: Personal-use tool. Bring your own legally obtained epub; this repo contains no book content. Progress files contain full chapter text and are git-ignored, so do not commit them. License: none specified (all rights reserved).

## 目前可以做什麼 / What works

1. 讀取 epub 的章節順序，用 BeautifulSoup 與 lxml 抽出文字區塊（p、h1 到 h6、li、blockquote、figcaption、dt、dd、td、th、div 中最內層的區塊）。容器自己直接寫、外層又包著子區塊的文字，會另外包成區塊，避免漏字。
2. 透過本機 Ollama 的 `/api/generate` 逐區塊翻譯，每章存成一個 JSON 進度檔。中斷後重跑會從還沒翻完的區塊接續。
3. 覆蓋檢查：比對每章區塊字元數與全文字元數，不一致會印出警告。在一本測試用的書上，檢查全部 42 章，修正後不一致為 0。
4. `glossary.json`：用語對照（避免用詞與建議用詞）與專有名詞譯法，會被帶進提示詞。小模型不一定遵守。
5. `ab_compare_v2.py`：在溫度 0 下，比較多個模型對同一批區塊的輸出，產生並排的 markdown 與簡單指標。

English: reads the epub spine, extracts innermost text blocks, translates block by block through a local Ollama server with resumable per-chapter JSON progress files, and checks text coverage per chapter (0 mismatches across 42 chapters of one test book after a fix). `glossary.json` feeds terminology into the prompt. `ab_compare_v2.py` compares models side by side at temperature 0.

## 尚未完成 / Not done

- 打包成雙語 epub：尚未實作。
- 後處理（OpenCC 簡轉繁、用詞替換）：目前只在 `ab_compare_v2.py` 使用，尚未接進 `chapter_translate.py`。
- 依模型比較的結果調整主程式（模型、`think: false`、溫度 0、人稱提示詞）：待辦。
- 沒有整本跑過。多章行為只驗證過前 5 個項目，重試與失敗標記的程式已寫好，但沒有實際測過。

English: bilingual epub packaging is not implemented; post-processing (OpenCC, term replacement) exists only in `ab_compare_v2.py`; updating the main script with the comparison results is a to-do; no full-book run has been done, and the retry and failure-marking paths are written but untested.

## 使用方式 / Usage

環境：在 macOS（Apple Silicon）上以 Python 3.12 開發，Ollama 版本為 0.40.11。其他版本沒有測過。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen2.5:3b   # 預設模型，名稱需與 chapter_translate.py 的 MODEL 一致
python3 chapter_translate.py "/path/to/book.epub" --limit 3
```

- 進度檔預設放在 `progress_v2/`，可用 `--progress-dir` 更改。
- `--limit N` 只跑前 N 個未完成章節，測試用。
- 目前預設模型是 `qwen2.5:3b`（`MODEL` 常數），這是第一輪測試用的。比較後表現較好的 qwen3.5:9b 尚未設為預設。
- 在 Apple Silicon 上，請確認 Ollama 是原生 arm64 版本。我曾遇到以 Intel 版 Homebrew（`/usr/local`）安裝的 x86 版本在 Rosetta 下只用 CPU。可用 `file "$(which ollama)"` 檢查，模型載入後 `ollama ps` 的 PROCESSOR 欄應顯示 GPU。
- `ab_compare_v2.py` 用來比較多個模型的翻譯結果，執行時帶入三個參數：epub 路徑、導言檔與第一章檔在 epub 內的路徑，例如 python3 ab_compare_v2.py book.epub OEBPS/text/intro.xhtml OEBPS/text/chapter1.xhtml。章節檔的內部路徑可用 unzip -l book.epub 查詢。輸出的 ab_compare_v2.md 含書籍原文，已列入 .gitignore，請勿上傳。

English: developed on macOS (Apple Silicon) with Python 3.12 and Ollama 0.40.11; other versions are untested. Make sure Ollama is the native arm64 build, otherwise it falls back to CPU under Rosetta. `ab_compare_v2.py` takes the epub path and two in-epub chapter paths as arguments.

## 模型比較（小樣本）/ Model comparison (small sample)

在同一本書的少數區塊（不超過 20 個）上，比較 qwen2.5（3B 與 7.6B）、translategemma:12b、qwen3.5:9b。以下是我實際看到的現象，樣本太小，不能當排名：

- 第一輪沒有固定溫度，同一句的錯誤時有時無。例如 qwen2.5:latest 曾把「食指和中指」翻成「拇指和食指」，溫度設為 0 之後翻對了，很可能是取樣隨機造成。所以第一輪的比較不可靠。
- qwen2.5:3b 會把第一人稱「我」翻成「你」，可能與我加的人稱提示詞有關，未驗證。
- qwen2.5:latest 有英文單字殘留。
- translategemma:12b 輸出簡體字，需要 OpenCC 轉換。沒有人稱規定時會用「您」，速度也較慢。
- qwen3.5:9b 需要傳入 `think: false` 關閉思考。在我檢視的區塊裡品質較好，但比 qwen2.5:latest 慢，並把 programming 譯成「程式碼」。
- OpenCC 的 `s2twp` 能轉簡繁與多數台灣用詞，但「高亮」「下劃線」不會被轉換。
- 自動指標抓不到意思上的錯誤，例如把 fell in love 譯成「相遇」，仍需人工校對。

English: in a sample of at most 20 blocks from one book, results varied by model: unfixed temperature made the first round unreliable, qwen2.5:3b confused first-person pronouns, qwen2.5:latest left English words, translategemma:12b output Simplified Chinese and was slower, and qwen3.5:9b needed `think: false` and looked best in the blocks I read but was slower. Automatic metrics cannot catch meaning errors, so human review is still needed.

## 已知限制 / Known limitations

- 只用一本書測試，樣本很小。
- 沒有整本書的實測耗時。
- 自動指標很粗略：英文殘留會把合理保留的英文也算進去，簡體字數是逐字比對的近似值。
- 翻譯品質需要人工校對。

最後更新 / Last updated: 2026-10
