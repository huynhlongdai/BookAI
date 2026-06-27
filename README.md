# 📚 BookAI — AI Book-to-Video Content Factory

<p align="center">
  <strong>Chuyển đổi sách thành video marketing chuyên nghiệp bằng AI</strong><br>
  Book (PDF/EPUB/Ảnh/Audio) → AI Analysis → Script → Video + TTS + Subtitles + BGM
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/streamlit-UI-red?logo=streamlit" alt="Streamlit">
  <img src="https://img.shields.io/badge/FastAPI-REST-green?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT License">
</p>

---

## 🎯 Tổng quan

BookAI là nền tảng AI tự động hóa toàn bộ quy trình từ **đọc sách** đến **xuất video marketing** — phục vụ affiliate marketing, review sách, và content creation trên TikTok, YouTube, Instagram.

### Pipeline hoàn chỉnh

```
📖 Book Input          → Markdown → Chunks → AI Analysis
📝 Content Studio      → Radio Scripts, Quotes, Listicles, Storyboard
🎬 Video Engine        → Stock Video/Ảnh + Local/Drive Materials
🗣️ TTS (6 providers)   → Edge-TTS, Azure, ElevenLabs, VieNeu, SiliconFlow
📐 Subtitles (17 mẫu) → CapCut-style, karaoke, word-by-word highlight
🎵 BGM + Effects       → 29 nhạc nền, glow, overlay, text animations
📤 Export              → MP4 video + Blog SEO + Social posts + Calendar
```

---

## ✨ Tính năng chính

### 📖 Đọc & Phân tích sách
- **Multi-format**: PDF, EPUB, ảnh (OCR), audio (Whisper)
- **Semantic chunking**: Chia chapter thông minh, tối ưu tiếng Việt
- **AI analysis**: 8 nhãn + viral score (0-10) + tóm tắt

### 🎬 Video Engine
- **6 Video Presets**: BookTok Review, YouTube Review, Book Trailer, Quote Compilation, Recommendation List, Book Promo
- **16 Video Sections**: 5 hook styles, 4 title cards, 3 outros, 4 intros (logo reveal, countdown, channel branding, genre mood)
- **LLM Keywords**: Tự động tạo keywords từ script → search stock phù hợp
- **3 nguồn tư liệu**: Stock API (Pexels, Pixabay, Coverr) + Local folder + Google Drive

### 🗣️ Text-to-Speech
- **6 providers**: Edge-TTS (free), Azure Neural, SiliconFlow, ElevenLabs (clone voice + 29 ngôn ngữ), VieNeu (tiếng Việt + cảm xúc), No-voice
- **Key rotation**: Xoay vòng API keys tự động cho mọi provider
- **Emotion tags**: Auto-insert `[cười]`, `[thở dài]`, `[hắng giọng]` cho VieNeu TTS

### 📐 Phụ đề (17 mẫu)
- **Classic styles**: Classic, Bold Impact, Minimal Clean, Neon Glow
- **CapCut-inspired**: White Box, Dark Box, Gradient Box, Modern Pill
- **Advanced**: Karaoke Word, Word-by-Word Highlight, Chat Bubble
- **New**: Most Readable, The Fancy, The Eccentric, Gen Z Bold, Poetry Script, The Classic (cinema)

### 🎨 Hiệu ứng
- **8 Glow presets**: Neon, fire, ice, electric, sunset, galaxy, nature, custom
- **7 Text overlays**: Gradient, shadow, outline, glow, glass, neon, 3D
- **16 Text animations**: Fade in, slide, zoom, pop, typewriter, blur reveal, pulse, highlight...
- **Dynamic effects**: Ken Burns, particle, light rays, vignette, grain

### 📤 Xuất & Phân phối
- Blog SEO tự động (Markdown, 800+ từ, meta tags)
- Social posts (TikTok caption, Instagram carousel)
- Content Calendar (lập lịch đăng)
- Affiliate link tự động

### 🖥️ Giao diện
- **Streamlit WebUI**: 9 tabs đầy đủ
- **REST API**: 30+ endpoints (FastAPI)
- **WebSocket**: Theo dõi tiến trình real-time
- **CLI**: Rich-formatted terminal interface

---

## 🚀 Cài đặt

### Yêu cầu
- Python 3.10+
- FFmpeg (cho video render)
- Tesseract (cho OCR, tùy chọn)

### Cài đặt nhanh

```bash
# Clone repo
git clone https://github.com/huynhlongdai/BookAI.git
cd BookAI

# Cài đặt dependencies
pip install -e ".[dev]"

# Cấu hình API keys
cp config.example.toml config.toml
# Sửa config.toml với API keys của bạn

# Chạy WebUI
streamlit run src/bookai/app.py

# Hoặc chạy API server
uvicorn bookai.api:app --reload --port 8000
```

### Docker

```bash
docker-compose up -d
# WebUI: http://localhost:8501
# API: http://localhost:8000
```

---

## 📋 Sử dụng

### CLI

```bash
# Full pipeline: sách → phân tích
bookai process book.pdf --provider custom \
  --base-url https://api.tokenrouter.com/v1 \
  --model openai/gpt-4o-mini --api-key $API_KEY

# Tạo content từ kết quả phân tích
bookai generate-ai results.json --duration 3 --storyboard -o content.json

# Render quote cards
bookai render-quotes results.json -o ./cards --theme warm

# OCR sách scan
bookai ocr scan.pdf -o output.md --lang vie+eng

# Transcribe audio
bookai transcribe audiobook.mp3 -o transcript.md
```

### WebUI (Streamlit)

| Tab | Chức năng |
|-----|-----------|
| 📤 Upload | Tải sách lên (PDF/EPUB/ảnh/audio) |
| 🔍 Analyze | AI phân tích: nhãn, viral score, tóm tắt |
| ✍️ Content Studio | Tạo scripts, quotes, listicles, storyboard |
| 🎥 Video Render | Chọn preset → render video hoàn chỉnh |
| 📅 Calendar | Lập lịch đăng content |
| 📚 Library | Quản lý sách đã xử lý |
| 💡 Prompts | Quản lý AI prompts |
| 📦 Export | Xuất content (JSON/Markdown/ZIP) |
| ⚙️ Settings | Cấu hình API keys, TTS, video |

### REST API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# List video presets
curl http://localhost:8000/api/v1/presets

# List subtitle templates
curl http://localhost:8000/api/v1/templates/subtitles

# Auto-tag emotions
curl -X POST "http://localhost:8000/api/v1/emotions/tag?text=Cuốn+sách+thú+vị&provider=vieneu"

# Generate keywords from script
curl -X POST http://localhost:8000/api/v1/keywords/generate \
  -H "Content-Type: application/json" \
  -d '{"script": "...", "max_keywords": 10}'

# WebSocket progress
wscat -c ws://localhost:8000/api/v1/ws/progress/{task_id}
```

---

## 🏗️ Kiến trúc

```
BookAI/
├── src/bookai/              # Source code chính (44 modules, ~25,300 LOC)
│   ├── models.py            # Pydantic data models
│   ├── converter.py         # EPUB/PDF/TXT → Markdown
│   ├── chunker.py           # Semantic chunking (chapter-aware)
│   ├── analyzer.py          # AI analysis (labels + viral score)
│   ├── content_studio.py    # Content generation engine
│   ├── quote_renderer.py    # PNG quote card renderer
│   ├── audio.py             # Whisper transcription
│   ├── ocr.py               # Tesseract OCR
│   │
│   ├── video_pipeline.py    # Pipeline orchestrator
│   ├── video_render.py      # FFmpeg video rendering
│   ├── video_effects.py     # Visual effects (Ken Burns, particles...)
│   ├── video_sections.py    # Hooks, titles, outros, intros (16 styles)
│   ├── video_presets.py     # 6 video presets (BookTok, YouTube...)
│   ├── dynamic_effects.py   # Runtime effect application
│   │
│   ├── tts.py               # TTS orchestrator
│   ├── tts_providers.py     # 6 TTS providers + key rotation
│   ├── emotion_tags.py      # Auto-insert VieNeu emotion tags
│   │
│   ├── subtitle.py          # SRT generation + word-level sync
│   ├── subtitle_templates.py # 17 subtitle visual templates
│   ├── text_animations.py   # 16 text animation effects
│   │
│   ├── stock_video.py       # Stock API (Pexels, Pixabay, Coverr)
│   ├── material_manager.py  # Local material management
│   ├── drive_material.py    # Google Drive integration
│   ├── keyword_generator.py # LLM keyword extraction
│   │
│   ├── bgm.py               # Background music management
│   ├── blog.py              # Blog SEO generation
│   ├── affiliate.py         # Affiliate link injection
│   ├── calendar.py          # Content calendar
│   ├── social_post.py       # Social media post generation
│   ├── social_metadata.py   # Social metadata
│   │
│   ├── api.py               # FastAPI REST API (30+ endpoints)
│   ├── app.py               # Streamlit WebUI (9 tabs)
│   ├── cli.py               # Typer CLI
│   ├── config.py            # TOML configuration
│   ├── settings.py          # App settings
│   ├── task_manager.py      # Background task management
│   ├── state.py             # Session state
│   ├── library.py           # Book library
│   ├── file_security.py     # File upload security
│   ├── batch.py             # Batch processing
│   ├── llm_providers.py     # LLM provider management
│   └── i18n/                # Internationalization (VI/EN)
│
├── tests/                   # Test suite (5 test files)
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md      # Technical architecture
│   ├── PLAN.md              # Full roadmap
│   ├── UPGRADE_PLAN_MPT.md  # MoneyPrinterTurbo upgrade plan
│   ├── CAPCUT_RESEARCH_PLAN.md # CapCut research & implementation
│   └── ...
├── assets/                  # BGM tracks, fonts
├── config.example.toml      # Example configuration
├── Dockerfile               # Docker image
├── docker-compose.yml       # Docker Compose
├── AGENTS.md                # AI IDE development guide
└── pyproject.toml           # Python project config
```

---

## 🗺️ Bản đồ ứng dụng

Xem chi tiết tại [`docs/APP_MAP.md`](docs/APP_MAP.md) — bao gồm:

- **Bản đồ module**: Quan hệ giữa 44 modules
- **Data flow**: Dòng dữ liệu từ input → output
- **API map**: 30+ REST endpoints
- **Mindmaps**: Sơ đồ tư duy tổng thể

---

## 📊 Thống kê

| Metric | Số liệu |
|--------|---------|
| Python modules | 44 |
| Lines of code | ~25,300 |
| Video presets | 6 |
| Subtitle templates | 17 |
| Video section styles | 16 |
| Text animations | 16 |
| TTS providers | 6 |
| REST API endpoints | 30+ |
| Test files | 5 |
| i18n languages | 2 (VI, EN) |

---

## 🗓️ Roadmap

- [x] **MVP-1**: Core pipeline (EPUB/PDF → Markdown → Chunk → AI Analysis)
- [x] **MVP-2**: OCR (scan PDF/images) + Whisper (audio)
- [x] **MVP-3**: Content Studio (radio scripts, quotes, listicles, storyboard)
- [x] **MVP-4**: TTS + Video render + Affiliate links + Calendar
- [x] **Phase 1**: Video Engine Upgrade (effects, subtitles, stock video, BGM)
- [x] **Phase 2**: TTS providers + Task management + Material manager
- [x] **Phase 3**: Distribution + Config + Blog SEO + i18n
- [x] **CapCut Research**: Hooks, titles, outros, intros, glow, overlays, animations
- [x] **Video Presets**: 6 preset templates cho các loại video khác nhau
- [x] **Emotion Tags**: Auto-insert cảm xúc cho VieNeu TTS
- [x] **ElevenLabs**: Clone voice + multilingual + voice settings
- [x] **VieNeu TTS**: 31 voices + emotions + key rotation
- [ ] **Auto-post**: Tự động đăng lên TikTok/YouTube/Instagram
- [ ] **A/B Testing**: So sánh hiệu quả content
- [ ] **Vector DB**: Tìm kiếm ngữ nghĩa trong thư viện sách
- [ ] **Mobile App**: Ứng dụng di động

---

## 🤝 Phát triển

```bash
# Chạy tests
pytest tests/

# Lint
ruff check src/ tests/

# Auto-fix lint
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/
```

Xem thêm `AGENTS.md` để phát triển với AI IDE.

## 📄 License

MIT
