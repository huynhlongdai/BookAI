# 🔍 Keyword Generation & Material Search Upgrade Plan

> Nghiên cứu từ MoneyPrinterTurbo + nâng cấp BookAI pipeline
> Ngày: 2026-06-27

---

## I. PHÂN TÍCH CÁCH MPT TẠO KEYWORD TỪ SCRIPT

### Luồng xử lý MPT:
```
Video Subject + Video Script
    ↓
LLM Prompt (generate_terms)
    ↓
JSON array of English search terms (1-3 words each)
    ↓
Stock API search (Pexels/Pixabay/Coverr)
    ↓
Download + validate + resize
```

### Prompt chiến lược của MPT:
```
- Mỗi search term 1-3 từ tiếng Anh
- Luôn gắn chủ đề chính của video
- Hỗ trợ 2 mode:
  1. Random: lấy 5 keywords chung cho cả video
  2. Match Script Order: keywords theo thứ tự kịch bản
     → "keep terms in same order as script narration;
        earlier terms must describe earlier visual moments"
- BẮT BUỘC trả về tiếng Anh (Chinese/other is not accepted)
```

### Điểm mạnh MPT cần học:
1. **LLM-based keyword extraction** — không dùng regex, dùng AI để hiểu ngữ cảnh
2. **Match Script Order mode** — keywords theo đúng timeline kịch bản
3. **English-only enforcement** — prompt rõ ràng "must use English"
4. **Retry logic** — 3 lần thử lại nếu LLM trả sai format
5. **Material directory config** — `config.toml` → `material_directory = "task"` hoặc đường dẫn

---

## II. VẤN ĐỀ HIỆN TẠI CỦA BOOKAI

### `generate_search_terms()` hiện tại (regex-based):
```python
# CHỈ tìm English words bằng regex — KHÔNG hiểu ngữ cảnh
english_words = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', script_text)
tech_terms = re.findall(r'\b(?:AI|Machine Learning|...)\\b', script_text)
base_terms = ["reading book", "education", "knowledge"]
```

### Hạn chế:
- ❌ Không hiểu nội dung script tiếng Việt
- ❌ Không dịch keyword sang tiếng Anh
- ❌ Không match theo thứ tự kịch bản
- ❌ Không hỗ trợ nhiều ngôn ngữ (chỉ detect English words)
- ❌ Keyword luôn generic ("reading book", "education")
- ❌ Không hỗ trợ local material directory config

---

## III. KẾ HOẠCH NÂNG CẤP

### A. LLM-Based Keyword Generation (thay thế regex)

```python
def generate_search_terms_llm(
    script_text: str,
    book_title: str = "",
    book_genre: str = "",
    num_terms: int = 8,
    match_script_order: bool = True,
    llm_provider: str = "openai",
    llm_api_key: str = "",
    llm_base_url: str = "",
    llm_model: str = "gpt-4o-mini",
) -> list[str]:
```

**Prompt chiến lược cho BookAI:**
```
# Role: Book Video Search Terms Generator

## Goals:
Generate {num_terms} stock video search terms from a book review script.

## Constraints:
1. Return JSON array of English strings only
2. Each term: 1-3 words, descriptive visual concepts
3. MUST be in English (translate from Vietnamese/other languages)
4. Terms should describe VISUAL scenes, not abstract concepts
5. Include book-related terms: reading, bookshelf, library, etc.
6. Match the emotional tone of the script passage
7. {ordering_rule for match_script_order}

## Book Context:
- Title: {book_title}
- Genre: {book_genre}

## Script:
{script_text}

## Examples:
Input: "Cuốn sách này kể về hành trình vượt khó của một cô gái trẻ..."
Output: ["young woman journey", "overcoming challenges", "sunrise hope",
         "reading inspiration", "girl adventure"]
```

### B. Keyword Translation Pipeline

```python
def translate_keywords_to_english(
    keywords: list[str],
    source_language: str = "auto",
    llm_config: dict = None,
) -> list[str]:
    """
    Dịch keywords từ bất kỳ ngôn ngữ nào sang tiếng Anh.
    
    Chiến lược:
    1. Detect language (vi, zh, ja, ko, etc.)
    2. Nếu đã English → giữ nguyên
    3. Nếu non-English → LLM translate
    4. Fallback: googletrans library
    """
```

**Translation flow:**
```
Script (tiếng Việt/bất kỳ)
    ↓
LLM extract keywords (đã English sẵn)
    ↓ (nếu user manual keywords)
Detect language
    ↓
LLM translate → English keywords
    ↓
Search stock APIs
```

### C. Local Material Directory

```python
@dataclass
class PipelineConfig:
    # Material sources (có thể kết hợp)
    material_source: str = "pexels"  # "pexels", "pixabay", "coverr", "local", "mixed"
    local_material_dir: str = ""     # Folder local
    local_material_mode: str = "supplement"  # "only", "supplement", "priority"
    
    # Mixed mode: local trước, stock bổ sung
    # "only" — chỉ dùng local
    # "supplement" — dùng stock, bổ sung local nếu thiếu
    # "priority" — ưu tiên local, bổ sung stock
```

**Local material scanning:**
```python
def scan_local_materials(
    material_dir: str,
    recursive: bool = True,    # Scan thư mục con
    categories: dict = None,   # {"hook": "hooks/", "background": "bg/"}
) -> dict[str, list[str]]:
    """
    Scan thư mục local và phân loại materials.
    
    Cấu trúc thư mục gợi ý:
    materials/
    ├── hooks/          # Video/ảnh cho phần hook
    ├── backgrounds/    # Video nền
    ├── book_covers/    # Ảnh bìa sách
    ├── overlays/       # Text overlays, watermarks
    └── general/        # Tư liệu chung
    """
```

### D. Smart Material Matching

```python
def match_materials_to_script(
    script_sections: list[dict],  # [{text, start, end, keywords}]
    available_materials: list[str],
    search_terms: list[str],
    match_mode: str = "ordered",  # "ordered", "random", "smart"
) -> list[dict]:
    """
    Ghép material với từng đoạn script.
    
    Modes:
    - "ordered": materials theo thứ tự keywords (như MPT match_script_order)
    - "random": shuffle materials
    - "smart": AI phân tích nội dung material → ghép với script passage phù hợp
    """
```

---

## IV. KIẾN TRÚC MODULE MỚI

```
src/bookai/
├── keyword_generator.py    # 🆕 LLM-based keyword extraction + translation
│   ├── generate_search_terms_llm()    # AI keyword extraction
│   ├── translate_keywords_to_english() # Multi-language → English
│   ├── generate_search_terms_regex()   # Fallback regex (existing)
│   └── detect_language()               # Language detection
│
├── material_manager.py     # 🆕 Unified material management
│   ├── class MaterialManager           # Central manager
│   ├── scan_local_directory()          # Scan local folder
│   ├── collect_materials()             # Unified collection (stock + local)
│   ├── match_to_script_sections()      # Script-ordered matching
│   └── validate_material()             # Check resolution, format
│
├── stock_video.py          # ✅ Existing (enhanced)
├── video_pipeline.py       # ✅ Existing (updated to use new modules)
└── config.toml             # ✅ Enhanced with new settings
```

### config.toml additions:
```toml
[material]
# Keyword generation
keyword_mode = "llm"  # "llm" or "regex"
match_script_order = true
num_keywords = 8

# Translation
auto_translate_keywords = true
source_language = "auto"  # "auto", "vi", "zh", "ja", etc.

# Local materials
local_material_dir = ""  # Path to local material folder
local_mode = "supplement"  # "only", "supplement", "priority"
scan_recursive = true

# Material matching
material_match_mode = "ordered"  # "ordered", "random", "smart"
min_resolution = 480  # Minimum width/height in pixels
```

---

## V. ƯU TIÊN TRIỂN KHAI

### Phase 1 (ngay): keyword_generator.py
1. `generate_search_terms_llm()` — LLM-based keyword extraction
2. Tiếng Việt → English translation trong prompt
3. Match script order mode
4. Fallback to regex nếu không có LLM config

### Phase 2: material_manager.py
5. Scan local directory (recursive)
6. Mixed mode (local + stock)
7. Script-ordered material matching
8. Material validation (resolution, format)

### Phase 3: WebUI + Config
9. WebUI tab cho material settings
10. Local folder picker
11. Keyword preview & editing
12. Material preview grid
