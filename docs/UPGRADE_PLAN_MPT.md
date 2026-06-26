# BookAI — Upgrade Plan (tham khảo MoneyPrinterTurbo)

> Plan nâng cấp BookAI lấy cảm hứng từ MoneyPrinterTurbo.
> Chia 3 phase theo độ ưu tiên.

---

## Tổng quan

BookAI hiện tại là pipeline AI chuyển sách → nội dung affiliate marketing.
MoneyPrinterTurbo (MPT) là video factory: topic → video hoàn chỉnh.

**Mục tiêu:** Kết hợp thế mạnh BookAI (phân tích sách sâu, content chất lượng)
với khả năng sản xuất video chuyên nghiệp của MPT.

---

## PHASE 1 — Video Engine Upgrade (Ưu tiên CAO, 2-3 tuần)

### 1. MoviePy thay FFmpeg subprocess
- Hiện tại: `subprocess.run(["ffmpeg", ...])` — khó control
- Mục tiêu: MoviePy engine + hardware codec fallback
- Tham khảo: `MPT/app/services/video.py` (1236 dòng)
- Hỗ trợ 3 aspect: 9:16, 16:9, 1:1
- Class `SubClippedVideoClip` quản lý clip segment

### 2. Video Transition Effects
- Tham khảo: `MPT/app/services/utils/video_effects.py`
- FadeIn/FadeOut, SlideIn/SlideOut, Shuffle
- Thêm ZoomKenBurns riêng cho BookAI

### 3. Subtitle Overlay chuyên nghiệp
- Hiện tại BookAI: KHÔNG CÓ subtitle trên video
- Tham khảo: `MPT/app/services/video.py` (generate_video function)
- Font (BeVietnamPro), màu, kích thước, viền, vị trí
- Subtitle background (hộp nền mờ)
- Sinh SRT từ Edge-TTS, fallback Whisper
- Auto-correct bằng Levenshtein distance

### 4. Background Music (BGM)
- Hiện tại BookAI: KHÔNG CÓ nhạc nền
- Tham khảo: `MPT/app/services/video.py` (get_bgm_file)
- 25+ tracks sẵn có (có thể copy từ MPT resource/songs/)
- Random, chọn cụ thể, hoặc không nhạc
- Volume control riêng voice + BGM

### 5. Stock Video Materials
- Hiện tại BookAI: chỉ dùng hình tĩnh (quote card)
- Tham khảo: `MPT/app/services/material.py` (476 dòng)
- Pexels + Pixabay + Coverr API
- Search terms từ storyboard BookAI (đã có visual prompt EN)
- match_materials_to_script: ghép video theo thứ tự script
- Cache + local materials support

---

## PHASE 2 — TTS + Task System (Ưu tiên TRUNG BÌNH, 2 tuần)

### 6. TTS Multi-Provider
- Tham khảo: `MPT/app/services/voice.py` (1635 dòng)
- Thêm: Azure Speech, SiliconFlow CosyVoice2, ElevenLabs, MiMo TTS
- Chế độ no-voice, voice rate control, real-time preview

### 7. Task Queue + State Management
- Tham khảo: `MPT/app/services/state.py` + `MPT/app/controllers/manager/`
- TaskManager concurrent + queue + progress tracking
- Memory (dev) / Redis (production) state
- stop_at parameter, max concurrent/queued tasks

### 8. Batch Video Generation
- Tham khảo: `MPT/app/services/task.py` (video_count parameter)
- N video variants/script, random stock footage shuffle
- Hữu ích cho A/B testing hooks

### 9. REST API nâng cấp
- Tham khảo: `MPT/app/controllers/v1/video.py`
- Full CRUD cho tasks, streaming, download, BGM/material upload
- External integration (Zapier, n8n)

---

## PHASE 3 — Distribution + DevOps (Ưu tiên SAU, 2 tuần)

### 10. Cross-Platform Auto-Post
- Tham khảo: `MPT/app/services/upload_post.py`
- Upload-Post API (TikTok/IG/YouTube Shorts)
- Auto-sinh metadata per platform
- YouTube AI-generated content flag

### 11. LLM Multi-Provider
- Tham khảo: `MPT/app/services/llm.py` (1132 dòng)
- Native Gemini, DeepSeek, Qwen, Ollama, MiniMax, LiteLLM
- Strip <think> block, sanitize errors, auto-retry

### 12. Docker + Docker Compose
- Tham khảo: `MPT/Dockerfile`, `MPT/docker-compose.yml`
- CPU + GPU Dockerfile
- Redis service, one-command deploy

### 13. Config JSON → TOML
- Tham khảo: `MPT/config.example.toml`
- Sections: [app], [llm], [tts], [video], [affiliate], [proxy]

### 14. WebUI nâng cấp (i18n + UX)
- Tham khảo: `MPT/webui/Main.py` + `MPT/webui/i18n/`
- i18n JSON lang files
- Real-time voice preview, progress bar, video preview

### 15. Social Metadata Generator
- Tham khảo: `MPT/app/services/llm.py` (generate_social_metadata)
- AI sinh title + caption + hashtags per platform

### 16. File Security
- Tham khảo: `MPT/app/utils/file_security.py`
- resolve_path_within_directory(), sanitize filename

---

## So sánh trước/sau

| Feature | BookAI Hiện tại | BookAI Nâng cấp |
|---------|----------------|-----------------|
| Video Engine | FFmpeg subprocess | MoviePy + codec fallback |
| Transitions | Không có | Fade/Slide/ZoomKenBurns |
| Phụ đề | Không có | Full (font/màu/viền/nền) |
| Nhạc nền | Không có | 25+ tracks + volume ctrl |
| Video stock | Không có | Pexels/Pixabay/Coverr |
| TTS | 2 giọng Edge-TTS | 5 providers (10+ giọng VN) |
| Task queue | Đồng bộ 1 task | Async + Redis + progress |
| Batch gen | 1 video/script | N variants/script |
| API | Admin only | Full video gen API |
| Auto-post | Không có | TikTok/IG/YouTube |
| LLM | 1 provider | 20+ providers |
| Docker | Không có | CPU + GPU Docker |
| Config | JSON | TOML + sections |
| Video formats | 9:16 only | 9:16 + 16:9 + 1:1 |
| Security | Cơ bản | Path traversal protect |
