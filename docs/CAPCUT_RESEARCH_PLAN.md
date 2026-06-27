# 🎬 CapCut Deep Research & BookAI Integration Plan

> Nghiên cứu sâu về templates, effects, text animation của CapCut để bổ sung vào BookAI video pipeline.
> Ngày: 2026-06-27

---

## 📊 I. TỔNG QUAN NGHIÊN CỨU

### Nguồn Research:
- CapCut Templates Gallery (capcut.com/templates)
- CapCut Subtitle Templates (capcut.com/explore/Subtitle-template)
- CapCut Caption Style Guide (capcut.com/resource/caption-style)
- CapCut Intro/Outro Templates (capcut.com/explore/intro-outro-templates)
- CapCut Lower Third Templates
- CapCut Hot/Trending Templates
- FlexClip Book Review Templates (12 templates)
- Canva Book Review Templates (25+ templates)
- YouTube CapCut Text Effects tutorials (10 viral effects)
- BookTok/TikTok book review best practices

---

## 🎨 II. PHÂN TÍCH TEMPLATE CATEGORIES CỦA CAPCUT

### A. Danh mục Template chính:
| Category | Mô tả | Áp dụng cho BookAI |
|----------|--------|-------------------|
| **Intro** | Mở đầu video với text animation | ✅ Hook + Book Title |
| **Outro** | Kết thúc với CTA, subscribe | ✅ CTA + Follow |
| **Logo Reveal** | Hiệu ứng logo xuất hiện | ✅ Branding BookAI |
| **Business** | Professional, 16:9 | ✅ Book Promo |
| **Daily VLOG** | Casual, 9:16 | ✅ Book Review |
| **Collage** | Nhiều hình ghép | ✅ Book Collection |
| **Editor's Picks** | Templates hot nhất | Tham khảo |
| **Gaming** | Dynamic effects | Tham khảo |

### B. 5 Caption Styles Trending 2025 (từ CapCut):

| Style | Font | Màu text | Background | Use case |
|-------|------|----------|------------|----------|
| **The Classic** | Roboto | Trắng | Đen solid | YouTube tutorials, sách non-fiction |
| **Most Readable** | Open Sans Bold | Vàng | Đen | Mobile, TikTok, sách ngắn |
| **The Fancy One** | Lato Italic | Trắng | Grey gradient | Vlogs, lifestyle, sách fiction |
| **The Eccentric** | Lora Bold | Xanh dương | Radial highlight | Storytelling, sách sáng tạo |
| **Checksub Original** | Arial | Rose-violet | Radial đen | Gen Z, Reels, BookTok |

### C. Subtitle Template Patterns (từ CapCut Gallery):

| Pattern | Lượt dùng | Đặc điểm |
|---------|-----------|----------|
| **Word-by-word highlight** | 958K | Từng từ sáng lên theo audio |
| **Bold impact text** | 707K | Text lớn, đậm, chiếm 1/3 màn hình |
| **Karaoke word-by-word** | 270K | Đổi màu từng từ khi đọc |
| **Chat/Message style** | 148K | Giả tin nhắn iMessage |
| **Neon glow text** | 137K | Text phát sáng neon |
| **Poetry/Shayari** | ~100K | Text nghệ thuật, script font |
| **3D emoji text** | ~80K | Text kết hợp emoji 3D |

---

## 🎥 III. CẤU TRÚC VIDEO BOOK REVIEW TỐI ƯU

### Cấu trúc BookTok/TikTok đã được chứng minh hiệu quả:

```
┌─────────────────────────────────────────────────┐
│  HOOK (0-2s)          │  Text lớn + Sound effect │
│  ↓                    │  "Cuốn sách này thay đổi│
│  Bold opinion/promise │   cách tôi nghĩ về..."  │
├─────────────────────────────────────────────────┤
│  TITLE CARD (2-4s)    │  Book cover + tên sách  │
│  ↓                    │  Animation zoom/slide    │
│  Giới thiệu sách      │  Rating stars ⭐⭐⭐⭐⭐  │
├─────────────────────────────────────────────────┤
│  PREMISE (4-8s)       │  1 câu tóm tắt nội dung│
│  ↓                    │  Stock video nền         │
│  Nội dung chính       │  Subtitle overlay        │
├─────────────────────────────────────────────────┤
│  KEY POINTS (8-20s)   │  3-5 điểm nổi bật       │
│  ↓                    │  Bullet points animated  │
│  Phân tích/Review     │  Quote highlights        │
├─────────────────────────────────────────────────┤
│  RATING (20-25s)      │  Score card + stars      │
│  ↓                    │  Comparison bar          │
│  Đánh giá tổng        │  Pros/Cons split         │
├─────────────────────────────────────────────────┤
│  CTA (25-30s)         │  "Follow để xem thêm"   │
│  ↓                    │  Subscribe animation     │
│  Kết thúc             │  Link/QR code            │
└─────────────────────────────────────────────────┘
```

---

## 🎯 IV. KẾ HOẠCH TÍCH HỢP VÀO BOOKAI

### Phase 1: Video Section Templates (Hook, Title, Intro, Outro, Text)

#### 1.1 Hook Templates (6 kiểu)

| ID | Tên | Mô tả | Kỹ thuật |
|----|-----|-------|----------|
| `hook_bold_question` | Bold Question | Câu hỏi lớn + zoom in | PIL text → FFmpeg scale animation |
| `hook_shocking_fact` | Shocking Fact | Số liệu gây sốc + shake | PIL text + FFmpeg shake filter |
| `hook_book_rating` | Book Rating | ⭐ rating lớn + slide in | PIL stars + slide transition |
| `hook_quote_reveal` | Quote Reveal | Trích dẫn hay → typewriter | PIL frame-by-frame typewriter |
| `hook_controversy` | Hot Take | Ý kiến trái chiều, bold text đỏ | PIL red text + pulse |
| `hook_mystery` | Mystery Tease | Blur → reveal effect | FFmpeg blur→sharp transition |

#### 1.2 Title Card Templates (5 kiểu)

| ID | Tên | Mô tả | Kỹ thuật |
|----|-----|-------|----------|
| `title_book_cover` | Book Cover Spotlight | Cover sách + tên tác giả | PIL composite + vignette |
| `title_minimalist` | Minimalist | Text trắng trên nền tối | PIL simple render |
| `title_split_screen` | Split Screen | Cover trái + info phải | PIL 2-panel layout |
| `title_gradient_card` | Gradient Card | Card gradient + shadow | PIL gradient bg + text |
| `title_3d_text` | 3D Text | Text có depth/shadow | PIL multi-layer text |

#### 1.3 Intro Templates (4 kiểu)

| ID | Tên | Mô tả | Kỹ thuật |
|----|-----|-------|----------|
| `intro_logo_reveal` | Logo Reveal | BookAI logo animation | FFmpeg fade + scale |
| `intro_channel_brand` | Channel Branding | Avatar + tên channel | PIL composite |
| `intro_genre_mood` | Genre Mood | Hình nền thể loại + text | Stock video + overlay |
| `intro_countdown` | Countdown | 3-2-1 đếm ngược | PIL number frames |

#### 1.4 Outro Templates (4 kiểu)

| ID | Tên | Mô tả | Kỹ thuật |
|----|-----|-------|----------|
| `outro_subscribe_cta` | Subscribe CTA | "Follow + Like" animation | PIL button graphics |
| `outro_next_book` | Next Book Preview | Preview sách tiếp theo | PIL thumbnail grid |
| `outro_rating_summary` | Rating Summary | Score card tổng kết | PIL scorecard |
| `outro_social_links` | Social Links | Icons mạng xã hội | PIL icon layout |

#### 1.5 Text Overlay Templates (6 kiểu)

| ID | Tên | Mô tả | Kỹ thuật |
|----|-----|-------|----------|
| `text_lower_third` | Lower Third | Text bar dưới màn hình | PIL bar + text |
| `text_full_screen` | Full Screen Quote | Quote chiếm full màn hình | PIL centered text |
| `text_bullet_points` | Bullet Points | Danh sách điểm nổi bật | PIL list render |
| `text_comparison` | Pros vs Cons | Bảng so sánh | PIL 2-column |
| `text_chapter_marker` | Chapter Marker | Đánh dấu chương | PIL chapter tag |
| `text_highlight_box` | Highlight Box | Text trong box màu | PIL rounded rect + text |

### Phase 2: Text Animation Effects

#### 2.1 Hiệu ứng xuất hiện (Entrance)

| Effect | Mô tả | Implementation |
|--------|-------|----------------|
| `fade_in` | Text mờ → rõ | FFmpeg `fade` filter |
| `slide_up` | Text trượt từ dưới lên | FFmpeg `overlay` + y animation |
| `slide_left` | Text trượt từ phải sang | FFmpeg `overlay` + x animation |
| `zoom_in` | Text nhỏ → lớn | FFmpeg `scale` animation |
| `typewriter` | Gõ từng chữ | PIL frame-by-frame |
| `pop_bounce` | Text nảy lên | FFmpeg scale overshoot |
| `blur_reveal` | Mờ → rõ | FFmpeg `boxblur` animation |

#### 2.2 Hiệu ứng nhấn mạnh (Emphasis)

| Effect | Mô tả | Implementation |
|--------|-------|----------------|
| `word_highlight` | Highlight từng từ theo audio | PIL recolor per word |
| `pulse` | Text phóng to/nhỏ nhịp nhàng | FFmpeg scale oscillation |
| `color_change` | Đổi màu từ khóa | PIL keyword coloring |
| `underline_sweep` | Gạch chân chạy ngang | PIL line animation |
| `glow_pulse` | Phát sáng nhấp nháy | PIL glow layers |

#### 2.3 Hiệu ứng thoát (Exit)

| Effect | Mô tả | Implementation |
|--------|-------|----------------|
| `fade_out` | Text rõ → mờ | FFmpeg `fade` filter |
| `slide_out` | Text trượt ra ngoài | FFmpeg overlay animation |
| `shrink` | Text nhỏ dần | FFmpeg scale down |
| `dissolve` | Text tan biến | FFmpeg pixel dissolve |

### Phase 3: Caption/Subtitle Enhancement

Mở rộng module `subtitle_templates.py` hiện có (9 templates) thêm:

| Template | Mô tả | Nguồn tham khảo |
|----------|-------|------------------|
| `word_by_word_highlight` | Từng từ sáng lên sync audio | CapCut 958K uses |
| `chat_bubble` | Giả tin nhắn | CapCut 148K uses |
| `the_classic` | Roboto trắng/đen | CapCut Style Guide |
| `most_readable` | Open Sans vàng/đen | CapCut Style Guide |
| `the_fancy` | Lato Italic, gradient | CapCut Style Guide |
| `the_eccentric` | Lora blue, radial | CapCut Style Guide |
| `gen_z_bold` | Rose-violet, dynamic | CapCut Checksub |
| `poetry_script` | Font script, nghệ thuật | CapCut Gallery |

### Phase 4: Video Structure Presets (Book Content Types)

Kết hợp với `CONTENT_TEMPLATES_PLAN.md`:

| Preset | Sections | Duration | Platform |
|--------|----------|----------|----------|
| `booktok_review` | Hook → Title → Premise → Reaction → Rating → CTA | 30-60s | TikTok 9:16 |
| `youtube_review` | Intro → Cover → Summary → Analysis → Rating → Outro | 3-5min | YouTube 16:9 |
| `book_trailer` | Mystery hook → Quotes → Mood clips → Release info | 30-60s | All |
| `quote_compilation` | Quote 1 → Quote 2 → ... → Book info | 15-30s | Reels/TikTok |
| `recommendation_list` | "Top 5 sách..." → Book 1-5 → CTA | 60-90s | All |
| `book_promo` | Cover reveal → Benefits → Testimonials → Buy CTA | 15-30s | Ads |

---

## 🏗️ V. KIẾN TRÚC KỸ THUẬT

### Cấu trúc module mới:

```
src/bookai/
├── video_sections.py          # 🆕 Hook, Title, Intro, Outro generators
│   ├── class SectionConfig    # Cấu hình section (type, duration, text, style)
│   ├── generate_hook()        # Tạo hook video clip
│   ├── generate_title_card()  # Tạo title card
│   ├── generate_intro()       # Tạo intro
│   ├── generate_outro()       # Tạo outro
│   └── generate_text_overlay()# Tạo text overlay
│
├── text_animations.py         # 🆕 Text animation effects engine
│   ├── class AnimationConfig  # Cấu hình animation
│   ├── apply_entrance()       # Fade, slide, zoom, typewriter, pop
│   ├── apply_emphasis()       # Highlight, pulse, color change
│   ├── apply_exit()           # Fade out, slide out, shrink
│   └── render_animated_text() # Render text frames → video
│
├── video_presets.py           # 🆕 Pre-built video structure presets
│   ├── class VideoPreset      # Preset configuration
│   ├── BOOKTOK_REVIEW         # 30-60s TikTok review
│   ├── YOUTUBE_REVIEW         # 3-5min YouTube review
│   ├── BOOK_TRAILER           # 30-60s trailer
│   ├── QUOTE_COMPILATION      # 15-30s quotes
│   └── build_from_preset()    # Tự động tạo sections từ preset
│
├── subtitle_templates.py      # ✅ Existing (9 templates) + 8 new
├── video_pipeline.py          # ✅ Existing (955 LOC) - updated to use sections
└── stock_video.py             # ✅ Existing (Pexels/Pixabay/Coverr)
```

### Luồng xử lý mới:

```
Book PDF/EPUB
    ↓
AI Analysis (chunks, quotes, summary)
    ↓
Select Preset (booktok_review, youtube_review, etc.)
    ↓
Generate Sections:
    ├── Hook (text_animations + PIL render)
    ├── Title Card (book cover + text)
    ├── Content Sections (stock video + subtitle)
    ├── Text Overlays (quotes, bullet points)
    └── Outro (CTA + social links)
    ↓
Assemble Video (FFmpeg concat + transitions)
    ↓
Burn Subtitles (template-based)
    ↓
Add Audio (TTS + BGM mixing)
    ↓
Final Output (.mp4)
```

### Implementation bằng PIL + FFmpeg (không cần After Effects):

**PIL (Pillow)** - Render static frames:
- Text rendering với font tùy chỉnh
- Rounded rectangles, shadows, gradients
- Book cover compositing
- Star ratings, icons
- Multi-layer compositing

**FFmpeg** - Animation & video processing:
- `fade` filter: fade in/out
- `overlay` với expression: slide animations
- `scale` với expression: zoom effects  
- `boxblur` với expression: blur reveal
- `drawtext` với timeline: typewriter effect
- `concat` filter: ghép sections
- Frame sequence → video: complex animations

**Kỹ thuật Frame-by-Frame cho animation phức tạp:**
```python
# PIL render N frames → FFmpeg concat thành video clip
for i in range(num_frames):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Animate text position/size/color per frame
    progress = i / num_frames
    x = int(start_x + (end_x - start_x) * ease(progress))
    draw.text((x, y), text, font=font, fill=color)
    img.save(f"frame_{i:04d}.png")

# FFmpeg: frames → video
ffmpeg -r 30 -i frame_%04d.png -c:v libx264 section.mp4
```

---

## 📋 VI. ƯU TIÊN TRIỂN KHAI

### 🔴 Ưu tiên cao (Phase 1 — ngay):
1. `video_sections.py` — Hook + Title Card + Outro generators
2. `text_animations.py` — fade_in, slide_up, typewriter, zoom_in
3. Thêm 3 subtitle templates mới: word_by_word_highlight, the_classic, chat_bubble

### 🟡 Ưu tiên trung (Phase 2):
4. `video_presets.py` — booktok_review + youtube_review presets
5. Text overlays: lower_third, bullet_points, highlight_box
6. Thêm 5 subtitle templates còn lại

### 🟢 Ưu tiên thấp (Phase 3):
7. Intro templates: logo_reveal, countdown
8. Advanced animations: pop_bounce, glow_pulse, dissolve
9. Full preset library: book_trailer, quote_compilation, book_promo

---

## 📏 VII. METRICS & KPI

| Metric | Mục tiêu |
|--------|----------|
| Templates có sẵn | 25+ section templates |
| Animation effects | 15+ text effects |
| Video presets | 6 presets |
| Subtitle templates | 17 total (9 existing + 8 new) |
| Thời gian render 30s video | < 60s |
| Hỗ trợ aspect ratios | 9:16, 16:9, 1:1 |
| Font hỗ trợ tiếng Việt | 5+ fonts |
