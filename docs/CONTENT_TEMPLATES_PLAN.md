# BookAI — Kế hoạch Bổ sung Mẫu Nội dung Video
*Tham khảo từ FlexClip, Canva, CapCut, MoneyPrinterTurbo*

## Phân tích hiện trạng BookAI

### Nội dung hiện có:
| # | Loại nội dung | Module | Mô tả |
|---|---|---|---|
| 1 | Radio Script | `content_studio.py` | Script tường thuật TikTok/Reels (90-150s) |
| 2 | Quote Card | `quote_renderer.py` | Ảnh trích dẫn sách đẹp |
| 3 | Listicle | `content_studio.py` | Bài dạng danh sách (Top 5, 10 bài học...) |
| 4 | Caption | `content_studio.py` | Caption social media ngắn |
| 5 | Blog Post | `blog.py` | Bài SEO blog dài |
| 6 | Storyboard | `content_studio.py` | Kịch bản phân cảnh cho AI video |
| 7 | Quote Video | `video_render.py` | Video quote ngắn 15-30s (Ken Burns) |
| 8 | Slideshow Video | `video_render.py` | Video trình chiếu hình ảnh |
| 9 | Radio Video | `video_render.py` | Video tường thuật có stock footage |
| 10 | Pipeline Video | `video_pipeline.py` | Video đầy đủ MPT-style (stock + TTS + subtitle) |

### Thiếu sót (so với FlexClip/Canva):
- ❌ Không có **Book Trailer** — video cinematic giới thiệu sách
- ❌ Không có **Book Review** — video đánh giá chi tiết có rating
- ❌ Không có **Book Recommendation** — video gợi ý sách hàng tháng
- ❌ Không có **Book Report** — tóm tắt học thuật
- ❌ Không có **Rating/Ranking** — xếp hạng sách kiểu TikTok
- ❌ Không có **Character Profile** — giới thiệu nhân vật
- ❌ Không có **Book Promo** — quảng cáo sách có CTA mua hàng
- ❌ Không có **Text Animation** — hiệu ứng chữ động (typewriter, fade, slide)
- ❌ Không có **Book Cover Mockup** — 3D book cover xoay/lật

---

## Đề xuất 8 Mẫu Nội dung Mới

### 1. 📖 Book Review Video (Đánh giá sách)
**Tham khảo:** FlexClip "Modern Creative Romance Book Review", Canva "Beige Minimalist Book Review"
**Cấu trúc 5 phần:**
```
[Intro 3s] → Bìa sách + tên + tác giả
[Tóm tắt 20s] → Nội dung chính, highlight bằng stock footage
[Phân tích 25s] → Điểm mạnh/yếu, trích dẫn hay
[Rating 5s] → Hiển thị ⭐ rating (1-5 sao) + animation
[CTA 5s] → "Đọc ngay!" + link mua + hashtags
```
**Tổng thời lượng:** 50-60s (TikTok/Reels)
**Đặc điểm:** Rating animation (sao lần lượt sáng), quote highlight, book cover overlay

### 2. 🎬 Book Trailer (Trailer sách cinematic)
**Tham khảo:** FlexClip "Galaxy Style Book Promo", "Best Seller Book Trailer"
**Cấu trúc 4 phần:**
```
[Hook 3s] → Câu hỏi/thống kê gây tò mò (text lớn, nền tối)
[Teaser 15s] → 3-4 cảnh cinematic + narration bí ẩn
[Reveal 5s] → Hiện bìa sách + "Available Now" / "Sắp ra mắt"
[CTA 3s] → Logo + link + hashtag
```
**Tổng thời lượng:** 25-30s
**Đặc điểm:** Tối giản, cinematic, nhạc epic, text animation chậm

### 3. 📚 Book Recommendation List (Gợi ý sách)
**Tham khảo:** FlexClip "Monthly Book Recommendation", Canva "Book Recommendation Mobile Video"
**Cấu trúc:**
```
[Title 3s] → "📚 Top 5 sách hay tháng 7/2026"
[Book 1-5] → Mỗi cuốn 8-10s: bìa + tóm tắt 1 dòng + rating
[Outro 3s] → "Follow để cập nhật hàng tháng!"
```
**Tổng thời lượng:** 45-60s
**Đặc điểm:** Swipe animation, numbering (1/5, 2/5...), multiple book covers

### 4. 💬 Quote Compilation (Tuyển tập trích dẫn)
**Tham khảo:** Canva "Pink White Aesthetic Watercolor Book Review", CapCut quote templates
**Cấu trúc:**
```
[Intro 2s] → "10 câu nói hay nhất từ [Tên sách]"
[Quote 1-10] → Mỗi quote 4-6s: text đẹp + background thay đổi
[Outro 3s] → Bìa sách + "Đọc sách đầy đủ tại..."
```
**Tổng thời lượng:** 45-65s
**Đặc điểm:** Quote typography đẹp, smooth transition, nhạc nhẹ nhàng

### 5. 🏆 Book Rating/Ranking (Xếp hạng sách)
**Tham khảo:** FlexClip "Rating Popular Books TikTok Video", Canva "Rate My 2 Favorite Books"
**Cấu trúc:**
```
[Title 3s] → "Xếp hạng 5 sách self-help hay nhất 2026"
[Book N] → Mỗi cuốn 6-8s: bìa + tên + rating bars/score animation
[Winner 5s] → "🏆 Top 1: [Tên sách]!" + confetti effect
```
**Tổng thời lượng:** 40-50s (TikTok)
**Đặc điểm:** Progress bar animation, score counter, ranking reveal

### 6. 👤 Character Profile (Hồ sơ nhân vật)
**Tham khảo:** FlexClip "Best Selling Story Character Biography"
**Cấu trúc:**
```
[Intro 3s] → "Nhân vật: [Tên]" + silhouette/ảnh
[Profile 15s] → Thông tin: tuổi, nghề, tính cách, mục tiêu
[Journey 20s] → Hành trình nhân vật qua các chương
[Quote 5s] → Câu nói đặc trưng của nhân vật
[CTA 3s] → "Khám phá thêm trong [Tên sách]"
```
**Tổng thời lượng:** 45s
**Đặc điểm:** Character card UI, info panels, timeline animation

### 7. 📊 Book Report / Summary (Báo cáo / Tóm tắt sách)
**Tham khảo:** FlexClip "Book Report Sample", Canva "Book Review Worksheet"
**Cấu trúc:**
```
[Title 3s] → Tên sách + tác giả
[Overview 15s] → Bối cảnh, thể loại, năm xuất bản
[Key Points 25s] → 3-5 điểm chính (bullet list animation)
[Takeaway 10s] → Bài học rút ra + ý nghĩa
[Rating 5s] → Đánh giá tổng quan
```
**Tổng thời lượng:** 55-60s
**Đặc điểm:** Educational style, clean layout, bullet animations, infographic feel

### 8. 🛒 Book Promo / Launch (Quảng cáo sách)
**Tham khảo:** FlexClip "Book Promotion Trailer", "Book Promo Simple Trailer Post"
**Cấu trúc:**
```
[Teaser 3s] → Problem statement / câu hỏi
[Solution 10s] → Sách giải quyết vấn đề gì
[Social Proof 5s] → Rating, reviews, bestseller badge
[Offer 5s] → Giá, giảm giá, free chapter
[CTA 5s] → "Mua ngay!" + QR code / link + countdown
```
**Tổng thời lượng:** 25-30s
**Đặc điểm:** 3D book mockup, CTA button animation, urgency timer, affiliate link

---

## Ưu tiên triển khai

| Ưu tiên | Template | Lý do | Độ phức tạp |
|---------|----------|-------|-------------|
| ⭐ P1 | Book Review | Phổ biến nhất, core use case | Trung bình |
| ⭐ P1 | Book Trailer | Viral potential cao, cinematic | Trung bình |
| P2 | Quote Compilation | Tái sử dụng quote_renderer | Thấp |
| P2 | Book Recommendation | Multi-book, monthly series | Trung bình |
| P3 | Rating/Ranking | TikTok trend, gamification | Trung bình |
| P3 | Book Promo | Monetization (affiliate) | Cao |
| P4 | Character Profile | Niche (fiction books only) | Cao |
| P4 | Book Report | Education niche | Thấp |

---

## Kỹ thuật cần bổ sung

### 1. Text Animation Engine (`text_effects.py`)
```python
# Cần xây dựng các hiệu ứng text:
- typewriter: Chữ gõ từng ký tự
- fade_word: Fade in từng từ
- slide_up: Chữ trượt từ dưới lên
- scale_pop: Chữ zoom từ nhỏ → lớn
- highlight_scan: Quét highlight ngang
- counter: Đếm số (rating, ranking)
- star_rating: Hiệu ứng sao sáng lần lượt
```

### 2. Book Cover Mockup Renderer (`book_mockup.py`)
```python
# Tạo 3D book cover từ ảnh bìa phẳng:
- perspective_3d: Xoay 3D perspective
- rotate_reveal: Xoay sách mở ra
- float_shadow: Sách lơ lửng + đổ bóng
- stack_books: Xếp chồng nhiều sách
```

### 3. Scene Transition Effects Mở rộng (`video_effects.py`)
```python
# Bổ sung transitions:
- page_flip: Lật trang sách
- dissolve: Hòa tan chuyển cảnh
- wipe_circle: Wipe hình tròn
- glitch: Hiệu ứng glitch ngắn
- zoom_blur: Zoom + blur chuyển cảnh
```

### 4. Layout Templates (`layout_templates.py`)
```python
# Layout sẵn cho từng loại video:
- info_card: Card thông tin (tên, tác giả, rating)
- split_screen: Chia đôi màn hình (bìa + text)
- lower_third: Banner thông tin phía dưới
- full_quote: Quote toàn màn hình
- ranking_bar: Progress bar xếp hạng
```

---

## Kế hoạch triển khai chi tiết

### Phase 1: Foundation (Text Animations + Book Review)
**~1,500 LOC | 1 sprint**
1. `text_effects.py` — 6 hiệu ứng text animation cơ bản
2. `layout_templates.py` — 4 layout templates (info_card, split_screen, lower_third, full_quote)
3. `content_templates.py` — Content Template Engine:
   - `BookReviewTemplate` — tạo script review 5 phần từ BookResult
   - `generate_review_video()` — pipeline tạo video review hoàn chỉnh
4. WebUI: Tab "Content Templates" với dropdown chọn loại

### Phase 2: Cinematic (Book Trailer + Quote Compilation)
**~1,200 LOC | 1 sprint**
1. `book_mockup.py` — 3D book cover rendering (PIL perspective transform)
2. `BookTrailerTemplate` — script + storyboard trailer cinematic
3. `QuoteCompilationTemplate` — tuyển tập quote đẹp
4. Mở rộng transitions: page_flip, dissolve, zoom_blur

### Phase 3: Social Content (Recommendation + Rating)
**~1,000 LOC | 1 sprint**
1. `BookRecommendationTemplate` — multi-book monthly list
2. `BookRatingTemplate` — ranking/rating animation
3. `star_rating` + `counter` + `ranking_bar` effects
4. Multi-book support trong video_pipeline

### Phase 4: Advanced (Promo + Character)
**~1,200 LOC | 1 sprint**
1. `BookPromoTemplate` — quảng cáo + affiliate CTA
2. `CharacterProfileTemplate` — hồ sơ nhân vật (fiction)
3. QR code generator cho affiliate links
4. `BookReportTemplate` — tóm tắt học thuật

---

## Tổng kết

| Metric | Giá trị |
|--------|---------|
| Templates mới | 8 loại |
| Modules mới | ~5 files |
| LOC ước tính | ~4,900 |
| Phases | 4 |
| Ưu tiên cao nhất | Book Review + Book Trailer |

BookAI sẽ từ một công cụ "tạo video từ sách" đơn thuần → trở thành *nền tảng tạo nội dung sách đa dạng* tương đương FlexClip/Canva nhưng *tự động hoàn toàn* nhờ AI.
