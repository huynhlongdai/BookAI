# 🗺️ Bản Đồ Ứng Dụng BookAI

Tài liệu này mô tả toàn bộ kiến trúc, luồng dữ liệu, quan hệ module, và API của BookAI.

---

## 1. Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            BOOKAI PLATFORM                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                           │
│  │ Streamlit│   │ FastAPI  │   │   CLI    │        ← Giao diện        │
│  │  WebUI   │   │ REST API │   │  Typer   │                           │
│  │ (9 tabs) │   │(30+ eps) │   │          │                           │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                           │
│       │              │              │                                   │
│       └──────────────┼──────────────┘                                   │
│                      │                                                  │
│  ┌───────────────────┴───────────────────┐                             │
│  │          CORE PIPELINE                 │                             │
│  │                                        │                             │
│  │  converter → chunker → analyzer        │       ← Đọc & Phân tích   │
│  │     ↓           ↓          ↓           │                             │
│  │  content_studio ← ← ← ← ←            │       ← Tạo Content        │
│  │     ↓                                  │                             │
│  │  video_pipeline ← video_presets        │       ← Video Engine       │
│  │     ├─ video_sections (hooks/intros)   │                             │
│  │     ├─ video_render (FFmpeg)           │                             │
│  │     ├─ video_effects + dynamic_effects │                             │
│  │     ├─ subtitle + subtitle_templates   │                             │
│  │     ├─ text_animations                 │                             │
│  │     ├─ tts ← tts_providers             │                             │
│  │     │       ← emotion_tags             │                             │
│  │     ├─ bgm                             │                             │
│  │     └─ stock_video + material_manager  │                             │
│  │               ↑         ↑              │                             │
│  │        keyword_gen  drive_material     │       ← Tư liệu            │
│  │                                        │                             │
│  │  blog + affiliate + social_post        │       ← Phân phối          │
│  │  calendar + social_metadata            │                             │
│  └────────────────────────────────────────┘                             │
│                                                                         │
│  ┌────────────────────────────────────────┐                             │
│  │          INFRASTRUCTURE                 │                             │
│  │  config + settings + state + i18n       │       ← Cấu hình          │
│  │  task_manager + file_security           │       ← Quản lý           │
│  │  llm_providers + batch + library        │       ← Tiện ích          │
│  └────────────────────────────────────────┘                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Luồng dữ liệu chính (Data Flow)

### 2.1. Pipeline đọc sách → phân tích

```
Input File                  Converter                    Chunker
┌────────────┐         ┌─────────────────┐         ┌──────────────────┐
│ PDF        │────────→│ converter.py    │────────→│ chunker.py       │
│ EPUB       │         │                 │         │                  │
│ Image      │         │ → Markdown text │         │ → Chunks (1200   │
│ Audio      │         │ + BookMetadata  │         │   tokens, chapter│
│ TXT        │         │                 │         │   aware, VN opt) │
└────────────┘         └─────────────────┘         └────────┬─────────┘
                                                            │
                       ┌─────────────────┐                  │
                       │ analyzer.py     │←─────────────────┘
                       │                 │
                       │ → 8 labels      │
                       │ → viral score   │
                       │ → summary       │
                       │ → AnalyzedChunk │
                       └────────┬────────┘
                                │
                                ↓
                       ┌─────────────────┐
                       │ content_studio   │
                       │                 │
                       │ → RadioScript   │
                       │ → QuoteCard     │
                       │ → Listicle      │
                       │ → TikTokCaption │
                       │ → Storyboard    │
                       └────────┬────────┘
                                │
                    ┌───────────┼───────────┐
                    ↓           ↓           ↓
              ┌──────────┐ ┌────────┐ ┌──────────┐
              │ Video    │ │ Blog   │ │ Social   │
              │ Pipeline │ │ SEO    │ │ Posts    │
              └──────────┘ └────────┘ └──────────┘
```

### 2.2. Pipeline tạo video

```
Script Text
     │
     ├──→ keyword_generator.py ──→ Keywords ──→ stock_video.py ──→ Stock clips
     │                                          material_manager ──→ Local files
     │                                          drive_material   ──→ Drive files
     │
     ├──→ emotion_tags.py ──→ Tagged Script
     │         │
     │         ↓
     ├──→ tts.py ← tts_providers.py ──→ Audio (.mp3/.wav)
     │         │                              │
     │         ↓                              │
     ├──→ subtitle.py ──→ SRT (word-level sync)
     │         │
     │         ↓
     ├──→ subtitle_templates.py ──→ Styled frames
     │
     ├──→ video_presets.py ──→ Config (resolution, sections, style)
     │
     ├──→ video_sections.py ──→ Intro + Hook + Title + Outro clips
     │
     ├──→ video_effects.py + dynamic_effects.py ──→ Effects
     │
     ├──→ text_animations.py ──→ Animated text overlays
     │
     ├──→ bgm.py ──→ Background music
     │
     └──→ video_render.py (FFmpeg) ──→ Final MP4 ✅
```

---

## 3. Chi tiết từng module

### 3.1. Input Layer (Đọc dữ liệu)

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `converter.py` | ~800 | Chuyển file → Markdown | PDF/EPUB/TXT/Image/Audio | `(BookMetadata, markdown_text)` |
| `ocr.py` | ~300 | OCR cho PDF scan & ảnh | Scanned PDF, images | Markdown text |
| `audio.py` | ~200 | Transcribe audio (Whisper) | MP3/WAV/M4A | Markdown text |

### 3.2. Analysis Layer (Phân tích)

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `chunker.py` | ~400 | Chia text thành chunks | Markdown text | `list[Chunk]` (1200 tokens) |
| `analyzer.py` | ~500 | AI phân tích nội dung | Chunks | `list[AnalyzedChunk]` (labels, score) |
| `content_studio.py` | ~600 | Tạo content từ phân tích | AnalyzedChunks + Metadata | RadioScript, QuoteCard, ... |

### 3.3. Video Engine

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `video_pipeline.py` | ~500 | Orchestrator pipeline video | Script + Config | Final MP4 |
| `video_render.py` | ~600 | FFmpeg rendering | Clips + Audio + Subtitles | MP4 |
| `video_effects.py` | ~400 | Visual effects engine | Frames | Effected frames |
| `video_sections.py` | ~1,500 | 16 section styles | Text + Config | Video clips |
| `video_presets.py` | 471 | 6 video presets | Preset name | Config dict |
| `dynamic_effects.py` | ~300 | Runtime effects | Frames + params | Modified frames |
| `text_animations.py` | ~400 | 16 text animations | Text + timing | Animated frames |

### 3.4. TTS & Audio

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `tts.py` | ~300 | TTS orchestrator | Text + provider | Audio file |
| `tts_providers.py` | ~800 | 6 providers + key rotation | Text + config | Audio bytes |
| `emotion_tags.py` | 239 | Auto-insert cảm xúc | Script text | Tagged text |
| `bgm.py` | ~200 | Background music | Mood/genre | BGM audio path |

### 3.5. Subtitles & Text

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `subtitle.py` | ~400 | SRT generation | Audio + Text | SRT (word-level) |
| `subtitle_templates.py` | ~1,200 | 17 visual templates | SRT + Config | Styled frames |

### 3.6. Material Sources (Tư liệu)

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `stock_video.py` | ~400 | Stock API client | Keywords | Video/image URLs |
| `material_manager.py` | ~300 | Local material management | Folder path | File list |
| `drive_material.py` | 460 | Google Drive integration | Folder URL | Downloaded files |
| `keyword_generator.py` | ~300 | LLM keyword extraction | Script text | Keywords list |

### 3.7. Distribution (Phân phối)

| Module | LOC | Chức năng | Input | Output |
|--------|-----|-----------|-------|--------|
| `blog.py` | ~400 | Blog SEO generation | AnalyzedChunks | Markdown blog (800+ words) |
| `affiliate.py` | ~300 | Affiliate link injection | Content + links | Content with links |
| `social_post.py` | ~200 | Social media posts | Content | TikTok/IG captions |
| `social_metadata.py` | ~150 | Social metadata | Content | Meta tags |
| `calendar.py` | ~300 | Content calendar | Posts | Schedule |

### 3.8. Interface Layer (Giao diện)

| Module | LOC | Chức năng |
|--------|-----|-----------|
| `app.py` | ~1,200 | Streamlit WebUI — 9 tabs |
| `api.py` | ~790 | FastAPI REST API — 30+ endpoints |
| `cli.py` | ~300 | Typer CLI — 8 commands |

### 3.9. Infrastructure

| Module | LOC | Chức năng |
|--------|-----|-----------|
| `config.py` | ~200 | TOML configuration loader |
| `settings.py` | ~150 | App settings management |
| `models.py` | ~400 | Pydantic data models |
| `state.py` | ~100 | Session state management |
| `task_manager.py` | ~300 | Background task tracking |
| `file_security.py` | ~100 | File upload security |
| `batch.py` | ~200 | Batch processing |
| `llm_providers.py` | ~200 | LLM provider management |
| `library.py` | ~200 | Book library CRUD |
| `i18n/` | ~300 | Vietnamese + English |

---

## 4. API Map (30+ Endpoints)

### System
| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/v1/health` | Health check + system info |

### Templates
| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/v1/templates/subtitles` | 17 subtitle templates |
| GET | `/api/v1/templates/hooks` | 5 hook styles |
| GET | `/api/v1/templates/title-cards` | 4 title card styles |
| GET | `/api/v1/templates/outros` | 3 outro styles |
| GET | `/api/v1/templates/effects` | 8 glow presets + 7 overlays |
| GET | `/api/v1/templates/animations` | 16 text animations |
| GET | `/api/v1/templates/intros` | 4 intro styles + 6 genres |

### Video Presets
| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/v1/presets` | List 6 video presets |
| GET | `/api/v1/presets/{name}` | Chi tiết 1 preset |

### TTS & Emotions
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/api/v1/emotions/tag` | Auto-insert emotion tags |

### Keywords & Materials
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/api/v1/keywords/generate` | LLM keyword extraction |

### Google Drive
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/api/v1/drive/list` | List files in Drive folder |
| POST | `/api/v1/drive/sync` | Sync Drive folder to local |

### Files & Progress
| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/v1/stream/{path}` | Stream/download files |
| WS | `/api/v1/ws/progress/{task_id}` | WebSocket progress tracking |

---

## 5. Cấu hình (config.toml)

```toml
[app]
language = "vi"          # vi | en
theme = "dark"

[llm]
provider = "custom"
base_url = "https://api.tokenrouter.com/v1"
model = "openai/gpt-4o-mini"
api_key = "sk-..."

[tts]
default_provider = "edge-tts"
default_voice = "vi-VN-HoaiMyNeural"

[tts.edge_tts]
voices = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]

[tts.vieneu]
api_keys = ["vn_sk_..."]   # Supports multiple keys (rotation)
base_url = "https://vieneu.io/api/v1"

[tts.elevenlabs]
api_keys = ["..."]
default_model = "eleven_multilingual_v2"

[video]
default_aspect = "9:16"
default_resolution = [1080, 1920]
max_duration = 300
subtitle_template = "capcut_white_box"

[stock]
pexels_api_key = "..."
pixabay_api_key = "..."
coverr_api_key = "..."
prefer_source = "pixabay"

[drive]
credentials_path = "credentials.json"
```

---

## 6. WebUI Tab Map

```
┌─────────────────────────────────────────────────┐
│                 BookAI WebUI                     │
├─────────────────────────────────────────────────┤
│                                                  │
│  📤 Upload                                       │
│  ├─ Kéo thả file (PDF/EPUB/ảnh/audio)           │
│  ├─ Hiển thị metadata sách                       │
│  └─ Markdown preview                             │
│                                                  │
│  🔍 Analyze                                      │
│  ├─ Chọn LLM provider                           │
│  ├─ Phân tích chunks → labels + viral score      │
│  └─ Bảng kết quả có filter/sort                  │
│                                                  │
│  ✍️ Content Studio                                │
│  ├─ Chọn loại content (script/quote/listicle)    │
│  ├─ Cấu hình duration, số lượng                  │
│  └─ AI rewrite + storyboard preview              │
│                                                  │
│  🎥 Video Render                                 │
│  ├─ 🎬 Preset selector (6 presets)               │
│  ├─ Script input (hoặc dùng từ Content Studio)   │
│  ├─ TTS provider + voice selector                │
│  ├─ Subtitle template (17 mẫu)                   │
│  ├─ Video settings (aspect, resolution, BGM)     │
│  ├─ Material source (stock/local/drive)          │
│  └─ Render → preview → download                  │
│                                                  │
│  📅 Calendar                                     │
│  ├─ Lịch đăng theo tuần/tháng                    │
│  └─ Assign platform + time slot                  │
│                                                  │
│  📚 Library                                      │
│  ├─ Danh sách sách đã xử lý                     │
│  └─ Search + filter                              │
│                                                  │
│  💡 Prompts                                      │
│  ├─ Quản lý AI prompts                           │
│  └─ Template cho các loại content                │
│                                                  │
│  📦 Export                                       │
│  ├─ JSON / Markdown / ZIP export                 │
│  └─ Blog SEO export                              │
│                                                  │
│  ⚙️ Settings                                     │
│  ├─ API keys (LLM, TTS, Stock)                   │
│  ├─ TTS provider config                          │
│  ├─ Video defaults                               │
│  └─ Language (VI/EN)                             │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 7. TTS Provider Map

```
                    ┌─────────────────┐
                    │   tts.py        │
                    │  (orchestrator) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ↓              ↓              ↓
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ Edge-TTS   │  │  Azure     │  │ SiliconFlow│
     │ (Free)     │  │ Neural TTS │  │            │
     │ 2 VN voices│  │            │  │            │
     └────────────┘  └────────────┘  └────────────┘
              │              │              │
              ↓              ↓              ↓
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ ElevenLabs │  │  VieNeu    │  │  No-voice  │
     │ Clone + 29 │  │ 31 voices  │  │ (silent)   │
     │ languages  │  │ + emotions │  │            │
     │ 4 models   │  │ [cười] etc │  │            │
     └────────────┘  └────────────┘  └────────────┘

     Tất cả providers đều hỗ trợ KEY ROTATION
     (xoay vòng nhiều API keys tự động)
```

---

## 8. Subtitle Template Map

```
     17 Subtitle Templates
     ═══════════════════════

     Classic Styles          CapCut-Inspired         Advanced
     ─────────────          ────────────────         ────────
     1. classic              5. capcut_white_box     9. karaoke_word
     2. neon_glow             6. capcut_dark_box     10. word_by_word_highlight
     3. bold_impact           7. capcut_gradient     11. the_classic (cinema)
     4. minimal_clean         8. modern_pill         12. chat_bubble

     New Collection (5 mẫu mới)
     ──────────────────────────
     13. most_readable    → Dễ đọc nhất, chữ vàng đậm, mobile-first
     14. the_fancy        → Sang trọng, chữ nghiêng, gradient
     15. the_eccentric    → Cá tính, xanh dương đậm, radial highlight
     16. gen_z_bold       → Gen Z, hồng-tím, TikTok viral style
     17. poetry_script    → Thơ/Trích dẫn, thanh thoát, giữa màn hình
```

---

## 9. Video Sections Map

```
     16 Video Section Styles
     ════════════════════════

     Hooks (5)              Title Cards (4)         Outros (3)
     ─────────              ────────────────        ──────────
     • text_reveal          • gradient_bar          • subscribe_cta
     • zoom_impact          • corner_badge          • book_info
     • question_hook        • split_screen          • social_links
     • quote_flash          • animated_underline
     • mystery_fade

     Intros (4)
     ──────────
     • logo_reveal          → Logo zoom-in với glow
     • countdown            → Đếm ngược 3-2-1
     • channel_branding     → Tên kênh + tagline slide-in
     • genre_mood           → Intro theo thể loại sách
                              (fiction, business, self_help,
                               science, history, romance)
```

---

## 10. Video Presets Map

```
     6 Video Presets
     ═══════════════

     ┌─────────────────────────────────────────────────────────────┐
     │ Preset              │ Platform  │ Aspect │ Duration │ Style │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ 📱 BookTok Review   │ TikTok    │ 9:16   │ 30-60s   │ Hook  │
     │                     │           │        │          │ mạnh  │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ ▶️ YouTube Review   │ YouTube   │ 16:9   │ 3-5min   │ Chuyên│
     │                     │           │        │          │ sâu   │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ 🎬 Book Trailer     │ YouTube   │ 16:9   │ 30-60s   │ Cine  │
     │                     │           │        │          │ matic │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ 💎 Quote Compilation│ Instagram │ 9:16   │ 15-30s   │ Trích │
     │                     │           │        │          │ dẫn   │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ 📚 Recommendation   │ TikTok    │ 9:16   │ 60-90s   │ List  │
     │    List              │           │        │          │ icle  │
     ├─────────────────────┼───────────┼────────┼──────────┼───────┤
     │ 📢 Book Promo       │ TikTok    │ 9:16   │ 15-30s   │ CTA   │
     │                     │           │        │          │ mạnh  │
     └─────────────────────┴───────────┴────────┴──────────┴───────┘
```
