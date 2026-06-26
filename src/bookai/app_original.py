"""BookAI Streamlit Dashboard.

Run locally:
    streamlit run src/bookai/app.py

Deploy free on HuggingFace Spaces or Streamlit Cloud.

Features:
    📖 Upload book → convert → chunk → analyze (mock or real API)
    📊 Browse chunks with viral scores + labels
    ✅ Approve / reject content pieces
    🎙️  Generate radio scripts, quote cards, listicles, captions
    📅 Generate 30-day posting calendar
    🔊 TTS synthesis (Edge-TTS, Vietnamese)
    🖼️  Render quote card PNG images
    📦 Download full content pack as ZIP
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Make sure the package is importable when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from bookai.analyzer import analyze_chunks
from bookai.chunker import chunk_markdown
from bookai.content_studio import generate_all, generate_all_with_ai
from bookai.converter import convert_file
from bookai.library import BookLibrary, PromptManager
from bookai.models import BookResult, ChunkLabel

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BookAI — Sách → Content",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
.metric-card {
    background: #1e1e2e;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 4px 0;
    border-left: 4px solid #7c3aed;
}
.score-high { color: #22c55e; font-weight: bold; }
.score-mid  { color: #f59e0b; font-weight: bold; }
.score-low  { color: #ef4444; font-weight: bold; }
.label-pill {
    display: inline-block;
    background: #312e81;
    color: #a5b4fc;
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 0.75em;
    margin: 2px;
}
.stProgress > div > div { background-color: #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------


def _init_state() -> None:
    defaults = {
        "book_result": None,
        "content_pack": None,
        "approved_scripts": set(),
        "approved_quotes": set(),
        "approved_listicles": set(),
        "approved_captions": set(),
        "affiliate_config": {},
        "calendar_entries": [],
        "tts_results": {},
        "processing": False,
        "_library": None,
        "_prompt_mgr": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def _get_library() -> BookLibrary:
    if st.session_state._library is None:
        st.session_state._library = BookLibrary()
    return st.session_state._library


def _get_prompt_mgr() -> PromptManager:
    if st.session_state._prompt_mgr is None:
        st.session_state._prompt_mgr = PromptManager()
    return st.session_state._prompt_mgr


# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📚 BookAI")
    st.caption("Sách → Content Affiliate tự động")
    st.divider()

    st.subheader("⚙️ AI Provider")
    provider = st.selectbox(
        "Provider",
        ["mock (offline)", "custom API", "openai", "anthropic"],
        index=0,
    )
    provider_key = provider.split(" ")[0]

    api_key = ""
    base_url = ""
    model = "gpt-4o-mini"

    if provider_key == "custom":
        base_url = st.text_input(
            "Base URL",
            value="https://rh486zc.abc-tunnel.us/v1",
            help="OpenAI-compatible API endpoint",
        )
        model = st.text_input("Model", value="WindsurfAPI/gemini-2.5-flash")
        api_key = st.text_input("API Key", type="password",
                                value=os.environ.get("key_api", ""))
    elif provider_key in ("openai", "anthropic"):
        api_key = st.text_input("API Key", type="password",
                                value=os.environ.get("OPENAI_API_KEY", ""))
        model = st.text_input("Model", value="gpt-4o-mini")

    st.divider()
    st.subheader("🎛️ Processing")
    max_chunks = st.slider("Max chunks to analyze", 10, 200, 50)
    max_tokens = st.slider("Tokens per chunk", 200, 1500, 500)
    batch_mode = st.checkbox("Batch mode (faster)", value=True)
    min_viral_score = st.slider("Min viral score to show", 0.0, 10.0, 4.0)

    st.divider()
    st.subheader("🎨 Content Settings")
    ai_rewrite = st.checkbox("AI rewrite scripts", value=False,
                             help="Uses LLM to rewrite — needs API key")
    duration_min = st.slider("Script duration (min)", 1, 5, 3,
                             disabled=not ai_rewrite)
    image_theme = st.selectbox("Quote card theme",
                               ["dark", "light", "gradient_blue", "warm"])
    tts_voice = st.selectbox(
        "TTS Voice",
        ["vi-VN-HoaiMyNeural (Female)", "vi-VN-NamMinhNeural (Male)"],
    )
    tts_voice_id = tts_voice.split(" ")[0]

    st.divider()
    st.caption("💡 Tip: dùng `mock` để test offline, không cần API key.")


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------

tab_upload, tab_analyze, tab_content, tab_calendar, tab_library, tab_prompts, tab_export = st.tabs([
    "📖 Upload & Process",
    "📊 Phân tích",
    "🎬 Content Studio",
    "📅 Lịch đăng",
    "📚 Thư viện sách",
    "🔧 Prompt",
    "📦 Export",
])

# ===========================================================================
# TAB 1 — Upload & Process
# ===========================================================================

with tab_upload:
    st.header("📖 Upload Sách")
    st.caption("Hỗ trợ: PDF, EPUB, TXT, MD, PNG/JPG (OCR), MP3/WAV (Whisper)")

    uploaded = st.file_uploader(
        "Chọn file sách",
        type=["pdf", "epub", "txt", "md", "png", "jpg", "jpeg", "mp3", "wav", "m4a"],
        help="Upload file để bắt đầu pipeline",
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        if uploaded:
            st.success(f"✅ Đã tải: **{uploaded.name}** ({uploaded.size / 1024:.0f} KB)")

    with col2:
        process_btn = st.button(
            "🚀 Phân tích sách",
            type="primary",
            disabled=uploaded is None,
            use_container_width=True,
        )

    if process_btn and uploaded:
        with tempfile.NamedTemporaryFile(
            suffix=Path(uploaded.name).suffix, delete=False
        ) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        # ── Progress UI ──────────────────────────────────────
        st.markdown("---")
        st.markdown("### ⚙️ Đang xử lý...")
        col_prog, col_time = st.columns([4, 1])
        progress = col_prog.progress(0)
        timer_txt = col_time.empty()

        step_box   = st.empty()   # current step description
        detail_box = st.empty()   # detail / chunk counter
        log_box    = st.expander("📋 Chi tiết log", expanded=False)
        logs: list[str] = []

        import time as _time
        t_start = _time.time()

        def _tick():
            elapsed = _time.time() - t_start
            timer_txt.caption(f"⏱ {elapsed:.0f}s")

        def _log(msg: str):
            logs.append(msg)
            with log_box:
                st.text("\n".join(logs[-20:]))

        try:
            # ── Step 1: Convert ──────────────────────────────
            step_box.info("**Bước 1/3** — 📖 Đang đọc và convert file...")
            detail_box.caption(f"File: `{uploaded.name}` ({uploaded.size/1024:.0f} KB)")
            progress.progress(5)
            _log(f"[Convert] {uploaded.name}")

            metadata, markdown = convert_file(tmp_path)
            progress.progress(20)
            _tick()
            _log(f"[Convert OK] title={metadata.title} chapters={metadata.chapters} chars={len(markdown)}")
            detail_box.caption(
                f"📚 **{metadata.title}** — {metadata.author} | "
                f"{metadata.chapters} chương | {len(markdown):,} ký tự"
            )

            # ── Step 2: Chunk ─────────────────────────────────
            step_box.info("**Bước 2/3** — ✂️ Đang tách thành chunks...")
            progress.progress(25)
            _log(f"[Chunk] max_tokens={max_tokens}")

            chunk_list = chunk_markdown(
                markdown, book_title=metadata.title, max_tokens=max_tokens
            )
            to_analyze = chunk_list[:max_chunks]
            progress.progress(35)
            _tick()
            _log(f"[Chunk OK] total={len(chunk_list)} → analyzing={len(to_analyze)}")
            detail_box.caption(
                f"✂️ {len(chunk_list)} chunks tổng | "
                f"Sẽ phân tích **{len(to_analyze)}** chunks đầu tiên"
            )

            # ── Step 3: Analyze chunk-by-chunk ───────────────
            step_box.info(
                f"**Bước 3/3** — 🤖 Đang phân tích AI "
                f"(**{len(to_analyze)}** chunks, provider: `{provider_key}`)..."
            )
            _log(f"[Analyze] provider={provider_key} model={model} chunks={len(to_analyze)}")

            analyzed: list = []
            chunk_counter = st.empty()
            prog_start = 35
            prog_end   = 90

            if provider_key == "mock":
                # Mock: fast, show per-chunk progress
                from bookai.analyzer import _mock_analyze
                for i, chunk in enumerate(to_analyze):
                    result_chunk = _mock_analyze(chunk)
                    analyzed.append(result_chunk)
                    pct = prog_start + int((i + 1) / len(to_analyze) * (prog_end - prog_start))
                    progress.progress(pct)
                    _tick()
                    chunk_counter.markdown(
                        f"🔍 Chunk **{i+1}/{len(to_analyze)}** | "
                        f"Score: `{result_chunk.viral_score:.1f}` | "
                        f"Labels: `{'  '.join(l.value for l in result_chunk.labels)}`"
                    )
                    if (i + 1) % 5 == 0 or i == len(to_analyze) - 1:
                        _log(f"  [{i+1}/{len(to_analyze)}] score={result_chunk.viral_score:.1f}")
            else:
                # Real API: analyze all then update
                chunk_counter.markdown(
                    f"⏳ Đang gửi **{len(to_analyze)}** chunks tới `{provider_key}` API..."
                )
                analyzed = analyze_chunks(
                    to_analyze,
                    provider=provider_key,
                    api_key=api_key or None,
                    model=model,
                    base_url=base_url or None,
                )
                progress.progress(prog_end)
                _tick()
                avg = sum(a.viral_score for a in analyzed) / len(analyzed) if analyzed else 0
                chunk_counter.markdown(
                    f"✅ Đã nhận **{len(analyzed)}** kết quả | "
                    f"Avg score: `{avg:.1f}/10`"
                )
                _log(f"[Analyze OK] {len(analyzed)} results avg_score={avg:.1f}")

            # ── Build result ──────────────────────────────────
            progress.progress(95)
            result = BookResult(
                metadata=metadata,
                markdown=markdown,
                chunks=chunk_list,
                analyzed=analyzed,
                top_quotes=[a for a in analyzed if ChunkLabel.QUOTE in a.labels],
                top_hooks=[a for a in analyzed if ChunkLabel.HOOK in a.labels],
            )
            st.session_state.book_result = result
            st.session_state.content_pack = None

            # ── Auto-save to library ──────────────────────────
            try:
                lib = _get_library()
                lib.save_book(result)
            except Exception:
                pass  # library save failure should not break main flow

            progress.progress(100)
            _tick()

            # ── Summary card ──────────────────────────────────
            elapsed = _time.time() - t_start
            avg_score = sum(a.viral_score for a in analyzed) / len(analyzed) if analyzed else 0
            high = sum(1 for a in analyzed if a.viral_score >= 7)
            step_box.empty()
            detail_box.empty()
            chunk_counter.empty()

            st.success(f"✅ Hoàn thành trong **{elapsed:.0f}s** — `{metadata.title}`")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("📄 Chunks", len(analyzed))
            mc2.metric("⚡ Avg Score", f"{avg_score:.1f}/10")
            mc3.metric("🔥 High (≥7)", high)
            mc4.metric("⏱ Thời gian", f"{elapsed:.0f}s")
            st.caption("👉 Chuyển sang tab **Phân tích** để xem chi tiết")
            _log(f"[Done] elapsed={elapsed:.0f}s avg={avg_score:.1f} high={high}")

        except Exception as e:
            progress.empty()
            step_box.error(f"❌ Lỗi: {e}")
            _log(f"[ERROR] {e}")
            import traceback
            _log(traceback.format_exc()[-500:])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # Load from JSON
    st.divider()
    st.subheader("📂 Hoặc load results.json")
    json_file = st.file_uploader("Upload results.json", type=["json"], key="load_json")
    if json_file:
        try:
            data = json.loads(json_file.getvalue().decode("utf-8"))
            st.session_state.book_result = BookResult(**data)
            st.session_state.content_pack = None
            st.success(
                f"✅ Loaded: **{st.session_state.book_result.metadata.title}** "
                f"— {len(st.session_state.book_result.analyzed)} chunks"
            )
        except Exception as e:
            st.error(f"❌ {e}")

    # Quick status
    if st.session_state.book_result:
        r = st.session_state.book_result
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📄 Chunks", len(r.analyzed))
        avg = sum(a.viral_score for a in r.analyzed) / len(r.analyzed) if r.analyzed else 0
        c2.metric("⚡ Avg Score", f"{avg:.1f}/10")
        c3.metric("💬 Quotes", len(r.top_quotes))
        c4.metric("🔥 Hooks", len(r.top_hooks))


# ===========================================================================
# TAB 2 — Phân tích
# ===========================================================================

with tab_analyze:
    if not st.session_state.book_result:
        st.info("👆 Upload và phân tích sách ở tab **Upload & Process** trước.")
    else:
        r: BookResult = st.session_state.book_result
        st.header(f"📊 {r.metadata.title}")
        st.caption(f"Tác giả: {r.metadata.author} | {len(r.analyzed)} chunks đã phân tích")

        # Stats row
        total = len(r.analyzed)
        high = sum(1 for a in r.analyzed if a.viral_score >= 7)
        mid = sum(1 for a in r.analyzed if 4 <= a.viral_score < 7)
        low = sum(1 for a in r.analyzed if a.viral_score < 4)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", total)
        c2.metric("🔥 High (≥7)", high)
        c3.metric("⚠️ Mid (4-7)", mid)
        c4.metric("❄️ Low (<4)", low)

        # Label distribution
        st.subheader("Label distribution")
        label_counts: dict[str, int] = {}
        for a in r.analyzed:
            for lbl in a.labels:
                label_counts[lbl.value] = label_counts.get(lbl.value, 0) + 1

        if label_counts:
            import pandas as pd
            df_labels = pd.DataFrame(
                list(label_counts.items()), columns=["Label", "Count"]
            ).sort_values("Count", ascending=False)
            st.bar_chart(df_labels.set_index("Label"))

        # Chunk browser
        st.subheader("🔍 Duyệt Chunks")
        filter_label = st.selectbox(
            "Filter by label",
            ["Tất cả"] + [l.value for l in ChunkLabel],
            key="filter_label",
        )
        filter_min_score = st.slider(
            "Viral score ≥", 0.0, 10.0, min_viral_score, key="filter_score"
        )

        filtered = [
            a for a in r.analyzed
            if a.viral_score >= filter_min_score
            and (
                filter_label == "Tất cả"
                or any(l.value == filter_label for l in a.labels)
            )
        ]
        filtered.sort(key=lambda x: x.viral_score, reverse=True)

        st.caption(f"Hiển thị {len(filtered)}/{total} chunks")

        for i, chunk_data in enumerate(filtered[:50]):
            score = chunk_data.viral_score
            score_class = (
                "score-high" if score >= 7
                else "score-mid" if score >= 4
                else "score-low"
            )
            labels_html = "".join(
                f'<span class="label-pill">{l.value}</span>'
                for l in chunk_data.labels
            )
            with st.expander(
                f"#{i+1} | Score: {score:.1f} | {chunk_data.chunk.chapter_title[:40]} | "
                f"{'  '.join(l.value for l in chunk_data.labels)}",
                expanded=False,
            ):
                st.markdown(
                    f'<span class="{score_class}">Viral Score: {score:.1f}/10</span> '
                    f'{labels_html}',
                    unsafe_allow_html=True,
                )
                st.write(chunk_data.chunk.text)
                if chunk_data.summary:
                    st.caption(f"📝 Summary: {chunk_data.summary}")
                if chunk_data.reason:
                    st.caption(f"💡 Reason: {chunk_data.reason}")


# ===========================================================================
# TAB 3 — Content Studio
# ===========================================================================

with tab_content:
    if not st.session_state.book_result:
        st.info("👆 Upload sách trước ở tab **Upload & Process**.")
    else:
        r = st.session_state.book_result
        st.header("🎬 Content Studio")

        col_gen, col_status = st.columns([1, 2])
        with col_gen:
            gen_btn = st.button(
                "⚡ Generate Content",
                type="primary",
                use_container_width=True,
                help="Tạo radio scripts, quote cards, listicles, captions",
            )

        if gen_btn:
            with st.spinner("Đang generate content..."):
                try:
                    if ai_rewrite and (api_key or provider_key == "mock"):
                        pack = generate_all_with_ai(
                            r.analyzed,
                            r.metadata,
                            api_key=api_key or None,
                            model=model,
                            base_url=base_url or None,
                            duration_minutes=duration_min,
                        )
                    else:
                        pack = generate_all(r.analyzed, r.metadata)

                    st.session_state.content_pack = pack
                    # Default all approved
                    st.session_state.approved_scripts = set(
                        range(len(pack.radio_scripts))
                    )
                    st.session_state.approved_quotes = set(
                        range(len(pack.quote_cards))
                    )
                    st.session_state.approved_listicles = set(
                        range(len(pack.listicles))
                    )
                    st.session_state.approved_captions = set(
                        range(len(pack.captions))
                    )
                    st.success(
                        f"✅ {pack.total_pieces} content pieces generated!"
                    )
                except Exception as e:
                    st.error(f"❌ {e}")

        if st.session_state.content_pack:
            pack = st.session_state.content_pack
            total = pack.total_pieces
            approved_count = (
                len(st.session_state.approved_scripts)
                + len(st.session_state.approved_quotes)
                + len(st.session_state.approved_listicles)
                + len(st.session_state.approved_captions)
            )

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total", total)
            c2.metric("🎙️ Scripts", len(pack.radio_scripts))
            c3.metric("📸 Quotes", len(pack.quote_cards))
            c4.metric("📋 Listicles", len(pack.listicles))
            c5.metric("✅ Approved", approved_count)

            # --- Radio Scripts ---
            st.subheader(f"🎙️ Radio Scripts ({len(pack.radio_scripts)})")
            for i, script in enumerate(pack.radio_scripts):
                with st.container():
                    checked = st.checkbox(
                        f"Script #{i+1}: {script.title}",
                        value=(i in st.session_state.approved_scripts),
                        key=f"script_{i}",
                    )
                    if checked:
                        st.session_state.approved_scripts.add(i)
                    else:
                        st.session_state.approved_scripts.discard(i)

                    with st.expander("Xem nội dung"):
                        st.markdown(f"**🔥 HOOK:**\n{script.hook}")
                        st.markdown(f"**📄 BODY:**\n{script.body[:500]}...")
                        st.markdown(f"**📢 CTA:**\n{script.cta}")
                        st.caption(
                            f"~{script.estimated_seconds}s | "
                            + " ".join(f"#{t}" for t in script.hashtags)
                        )

                        # TTS button
                        tts_col1, tts_col2 = st.columns([1, 3])
                        with tts_col1:
                            if st.button("🔊 TTS", key=f"tts_{i}"):
                                from bookai.tts import synthesize_script

                                class _Proxy:
                                    pass

                                proxy = _Proxy()
                                proxy.hook = script.hook
                                proxy.body = script.body
                                proxy.cta = script.cta
                                proxy.title = script.title

                                with tempfile.NamedTemporaryFile(
                                    suffix=".mp3", delete=False
                                ) as tf:
                                    result = synthesize_script(
                                        proxy, tf.name, voice=tts_voice_id
                                    )
                                    if result.ok:
                                        audio_bytes = Path(tf.name).read_bytes()
                                        st.session_state.tts_results[i] = audio_bytes
                                    else:
                                        st.error(result.error)

                        if i in st.session_state.tts_results:
                            st.audio(
                                st.session_state.tts_results[i], format="audio/mp3"
                            )

                st.divider()

            # --- Quote Cards ---
            st.subheader(f"📸 Quote Cards ({len(pack.quote_cards)})")
            quote_cols = st.columns(2)
            for i, card in enumerate(pack.quote_cards):
                with quote_cols[i % 2]:
                    checked = st.checkbox(
                        f"Quote #{i+1}",
                        value=(i in st.session_state.approved_quotes),
                        key=f"quote_{i}",
                    )
                    if checked:
                        st.session_state.approved_quotes.add(i)
                    else:
                        st.session_state.approved_quotes.discard(i)

                    st.markdown(
                        f'> *"{card.quote_text[:200]}"*\n\n'
                        f"— {card.author}, *{card.book_title}*"
                    )
                    st.caption(
                        card.caption[:100] + "..."
                        if len(card.caption) > 100
                        else card.caption
                    )
                    st.caption(" ".join(f"#{h}" for h in card.hashtags[:5]))

            # --- Listicles ---
            if pack.listicles:
                st.subheader(f"📋 Listicles ({len(pack.listicles)})")
                for i, ls in enumerate(pack.listicles):
                    checked = st.checkbox(
                        ls.title,
                        value=(i in st.session_state.approved_listicles),
                        key=f"listicle_{i}",
                    )
                    if checked:
                        st.session_state.approved_listicles.add(i)
                    else:
                        st.session_state.approved_listicles.discard(i)

                    with st.expander("Xem nội dung"):
                        st.write(ls.intro)
                        for item in ls.items:
                            st.write(f"• {item}")
                        st.caption(f"CTA: {ls.cta}")

            # --- Captions ---
            if pack.captions:
                st.subheader(f"💬 Captions ({len(pack.captions)})")
                for i, cap in enumerate(pack.captions):
                    checked = st.checkbox(
                        f"Caption #{i+1} ({cap.platform})",
                        value=(i in st.session_state.approved_captions),
                        key=f"caption_{i}",
                    )
                    if checked:
                        st.session_state.approved_captions.add(i)
                    else:
                        st.session_state.approved_captions.discard(i)
                    st.text_area(
                        "",
                        cap.text,
                        height=80,
                        key=f"cap_text_{i}",
                        label_visibility="collapsed",
                    )

            # --- Render Quote Card Images ---
            st.divider()
            st.subheader("🖼️ Render Quote Card Images")
            render_col1, render_col2 = st.columns([1, 3])
            with render_col1:
                render_btn = st.button(
                    "🖼️ Render PNG",
                    use_container_width=True,
                    key="render_png",
                )
            with render_col2:
                st.caption(
                    f"Theme: {image_theme} | "
                    f"{len(st.session_state.approved_quotes)} quotes selected"
                )

            if render_btn:
                from bookai.quote_renderer import render_quote_card

                approved_cards = [
                    pack.quote_cards[i]
                    for i in sorted(st.session_state.approved_quotes)
                    if i < len(pack.quote_cards)
                ]
                if not approved_cards:
                    st.warning("Chưa có quote nào được chọn.")
                else:
                    with tempfile.TemporaryDirectory() as tmp:
                        img_cols = st.columns(min(3, len(approved_cards)))
                        for j, card in enumerate(approved_cards[:6]):
                            out = Path(tmp) / f"quote_{j}.png"
                            render_quote_card(
                                quote_text=card.quote_text,
                                book_title=card.book_title,
                                author=card.author,
                                output_path=out,
                                theme=image_theme,
                            )
                            with img_cols[j % 3]:
                                st.image(str(out), use_container_width=True)


# ===========================================================================
# TAB 4 — Lịch đăng
# ===========================================================================

with tab_calendar:
    if not st.session_state.content_pack:
        st.info("👆 Generate content ở tab **Content Studio** trước.")
    else:
        pack = st.session_state.content_pack
        st.header("📅 Content Calendar")

        c1, c2, c3 = st.columns(3)
        with c1:
            start_date_input = st.date_input("Ngày bắt đầu")
        with c2:
            days_input = st.slider("Số ngày", 7, 60, 30)
        with c3:
            platforms_input = st.multiselect(
                "Platforms",
                ["tiktok", "instagram", "youtube", "facebook", "blog"],
                default=["tiktok", "instagram"],
            )

        sub_id_prefix = st.text_input(
            "Sub-ID prefix (tracking)",
            value="book_" + (pack.book_title or "")[:10].lower().replace(" ", "_"),
            help="Dùng để track conversion theo từng post",
        )

        gen_cal_btn = st.button("📅 Tạo lịch", type="primary")

        if gen_cal_btn:
            from bookai.calendar import calendar_summary, generate_calendar

            with st.spinner("Đang tạo lịch..."):
                entries = generate_calendar(
                    pack,
                    start_date=start_date_input.isoformat(),
                    days=days_input,
                    platforms=platforms_input or ["tiktok"],
                    sub_id_prefix=sub_id_prefix,
                    posts_per_day=2,
                )
                st.session_state.calendar_entries = entries

            summary = calendar_summary(entries)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total posts", summary["total"])
            c2.metric("Date range", summary.get("date_range", "—"))
            c3.metric("Platforms", len(summary.get("by_platform", {})))

        if st.session_state.calendar_entries:
            entries = st.session_state.calendar_entries

            # Week filter
            week_filter = st.selectbox(
                "Xem theo tuần",
                ["Tất cả"] + [f"Tuần {i}" for i in range(1, 5)],
            )
            themes = {
                "Tuần 1": "Hook & Tease",
                "Tuần 2": "Deep Content",
                "Tuần 3": "Engagement",
                "Tuần 4": "Conversion Push",
            }
            if week_filter != "Tất cả":
                wn = int(week_filter.split()[-1])
                display_entries = [e for e in entries if e.week_number == wn]
                st.caption(
                    f"🎯 {week_filter}: **{themes.get(week_filter, '')}** "
                    f"— {len(display_entries)} posts"
                )
            else:
                display_entries = entries

            # Table view
            import pandas as pd

            df = pd.DataFrame([
                {
                    "📅 Ngày": e.date,
                    "⏰ Giờ": e.post_time,
                    "📱 Platform": e.platform,
                    "📝 Type": e.content_type.replace("_", " ").title(),
                    "📌 Title": e.content_title[:40],
                    "💬 Caption (50c)": e.caption[:50] + "..." if len(e.caption) > 50 else e.caption,
                    "🔗 Link": "✓" if e.affiliate_link else "—",
                    "🎯 Sub-ID": e.entry_id,
                }
                for e in display_entries
            ])
            st.dataframe(df, use_container_width=True, height=400)


# ===========================================================================
# TAB 5 — Export
# ===========================================================================

with tab_export:
    st.header("📦 Export")

    has_result = st.session_state.book_result is not None
    has_pack = st.session_state.content_pack is not None
    has_calendar = len(st.session_state.calendar_entries) > 0

    # --- Export results.json ---
    st.subheader("📄 Analysis Results (results.json)")
    if has_result:
        result_json = json.dumps(
            st.session_state.book_result.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            "⬇️ Download results.json",
            data=result_json.encode("utf-8"),
            file_name="results.json",
            mime="application/json",
        )
    else:
        st.caption("Chưa có dữ liệu — upload sách trước.")

    st.divider()

    # --- Export content.json ---
    st.subheader("🎬 Content Pack (content.json)")
    if has_pack:
        pack_json = json.dumps(
            st.session_state.content_pack.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            "⬇️ Download content.json",
            data=pack_json.encode("utf-8"),
            file_name="content.json",
            mime="application/json",
        )

        # Export approved only
        st.caption("Hoặc export chỉ approved:")
        pack = st.session_state.content_pack
        approved_data = {
            "book_title": pack.book_title,
            "radio_scripts": [
                pack.radio_scripts[i].model_dump()
                for i in sorted(st.session_state.approved_scripts)
                if i < len(pack.radio_scripts)
            ],
            "quote_cards": [
                pack.quote_cards[i].model_dump()
                for i in sorted(st.session_state.approved_quotes)
                if i < len(pack.quote_cards)
            ],
            "listicles": [
                pack.listicles[i].model_dump()
                for i in sorted(st.session_state.approved_listicles)
                if i < len(pack.listicles)
            ],
            "captions": [
                pack.captions[i].model_dump()
                for i in sorted(st.session_state.approved_captions)
                if i < len(pack.captions)
            ],
        }
        st.download_button(
            "⬇️ Download content_approved.json",
            data=json.dumps(approved_data, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="content_approved.json",
            mime="application/json",
        )
    else:
        st.caption("Chưa có content — generate ở tab Content Studio trước.")

    st.divider()

    # --- Export calendar.csv ---
    st.subheader("📅 Content Calendar (calendar.csv)")
    if has_calendar:
        from bookai.calendar import save_calendar_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            save_calendar_csv(st.session_state.calendar_entries, tf.name)
            csv_bytes = Path(tf.name).read_bytes()
        st.download_button(
            "⬇️ Download calendar.csv",
            data=csv_bytes,
            file_name="calendar.csv",
            mime="text/csv",
        )
    else:
        st.caption("Chưa có lịch — tạo ở tab Lịch đăng trước.")

    st.divider()

    # --- Full ZIP export ---
    st.subheader("📦 Full Content Pack (ZIP)")
    if has_pack:
        if st.button("🔄 Build ZIP", type="primary"):
            with st.spinner("Đang đóng gói..."):
                try:
                    pack = st.session_state.content_pack

                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        # results.json
                        if has_result:
                            zf.writestr(
                                "results.json",
                                json.dumps(
                                    st.session_state.book_result.model_dump(),
                                    ensure_ascii=False, indent=2
                                ),
                            )

                        # content.json (approved)
                        zf.writestr(
                            "content_approved.json",
                            json.dumps(approved_data, ensure_ascii=False, indent=2),
                        )

                        # calendar.csv
                        if has_calendar:
                            with tempfile.NamedTemporaryFile(
                                suffix=".csv", delete=False
                            ) as tf:
                                from bookai.calendar import save_calendar_csv
                                save_calendar_csv(
                                    st.session_state.calendar_entries, tf.name
                                )
                                zf.write(tf.name, "calendar.csv")
                                Path(tf.name).unlink(missing_ok=True)

                        # Quote card PNGs
                        from bookai.quote_renderer import render_quote_card
                        approved_cards = [
                            pack.quote_cards[i]
                            for i in sorted(st.session_state.approved_quotes)
                            if i < len(pack.quote_cards)
                        ]
                        with tempfile.TemporaryDirectory() as tmp:
                            for j, card in enumerate(approved_cards):
                                out = Path(tmp) / f"quote_{j:02d}.png"
                                render_quote_card(
                                    quote_text=card.quote_text,
                                    book_title=card.book_title,
                                    author=card.author,
                                    output_path=out,
                                    theme=image_theme,
                                )
                                zf.write(str(out), f"quote_cards/quote_{j:02d}.png")

                        # Radio scripts as TXT
                        for i in sorted(st.session_state.approved_scripts):
                            if i < len(pack.radio_scripts):
                                s = pack.radio_scripts[i]
                                txt = f"# {s.title}\n\n## HOOK\n{s.hook}\n\n## BODY\n{s.body}\n\n## CTA\n{s.cta}\n"
                                zf.writestr(f"scripts/script_{i+1:02d}.txt", txt)

                    buf.seek(0)
                    book_slug = (
                        (pack.book_title or "bookai")
                        .lower().replace(" ", "_")[:20]
                    )
                    st.download_button(
                        "⬇️ Download ZIP",
                        data=buf.getvalue(),
                        file_name=f"{book_slug}_content_pack.zip",
                        mime="application/zip",
                    )
                    st.success("✅ ZIP sẵn sàng!")
                except Exception as e:
                    st.error(f"❌ {e}")
    else:
        st.caption("Chưa có content — generate ở tab Content Studio trước.")

    # --- HuggingFace deploy hint ---
    st.divider()
    with st.expander("🚀 Deploy lên HuggingFace Spaces (miễn phí)"):
        st.markdown("""
        **Bước 1:** Tạo Space tại https://huggingface.co/new-space
        - SDK: **Streamlit**
        - Visibility: Private hoặc Public

        **Bước 2:** Upload các files:
        ```
        app.py  (← file này, rename từ src/bookai/app.py)
        requirements.txt
        ```

        **Bước 3:** requirements.txt nội dung:
        ```
        bookai @ git+https://github.com/bilonglo9x-code/bookai.git@initial-setup
        streamlit
        edge-tts
        ```

        **Bước 4:** Thêm API key vào Secrets của Space (Settings → Secrets):
        ```
        key_api = your_api_key_here
        ```
        """)


# ===========================================================================
# TAB 5 — Thư viện sách
# ===========================================================================

with tab_library:
    lib = _get_library()
    st.header("📚 Thư viện sách")

    stats = lib.stats()
    if stats["total"] == 0:
        st.info("Chưa có sách nào. Upload và phân tích sách ở tab **Upload & Process** — sẽ tự động lưu vào thư viện.")
    else:
        # ── Stats bar ──────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📚 Tổng sách", stats["total"])
        c2.metric("🔬 Tổng chunks", stats["total_chunks"])
        c3.metric("⚡ Avg score", f"{stats['avg_score']:.1f}/10")
        c4.metric("🎬 Có content", stats["with_content"])

        st.divider()

        # ── Search ─────────────────────────────────────────────
        search_q = st.text_input("🔍 Tìm kiếm", placeholder="Tên sách hoặc tác giả...")
        sort_col = st.selectbox(
            "Sắp xếp theo",
            ["analyzed_at", "avg_viral_score", "top_score", "chunks_analyzed", "title"],
            format_func=lambda x: {
                "analyzed_at": "📅 Ngày phân tích",
                "avg_viral_score": "⚡ Avg score",
                "top_score": "🔥 Top score",
                "chunks_analyzed": "📄 Số chunks",
                "title": "🔤 Tên sách",
            }.get(x, x),
        )

        entries = lib.search(search_q) if search_q else lib.list_books(sort_by=sort_col)

        st.caption(f"Hiển thị {len(entries)} sách")

        # ── Book cards ─────────────────────────────────────────
        for entry in entries:
            with st.container():
                col_info, col_score, col_actions = st.columns([4, 2, 2])

                with col_info:
                    st.markdown(f"**{entry.title}**")
                    st.caption(
                        f"👤 {entry.author or '—'} | "
                        f"📄 {entry.source_format} | "
                        f"🕐 {entry.analyzed_at_display}"
                    )
                    if entry.label_counts:
                        top_labels = sorted(
                            entry.label_counts.items(), key=lambda x: -x[1]
                        )[:4]
                        st.caption("  ".join(f"`{k}×{v}`" for k, v in top_labels))
                    if entry.notes:
                        st.caption(f"📝 {entry.notes}")

                with col_score:
                    score_color = (
                        "🟢" if entry.avg_viral_score >= 7
                        else "🟡" if entry.avg_viral_score >= 4
                        else "🔴"
                    )
                    st.metric(
                        "Avg Score",
                        f"{score_color} {entry.avg_viral_score:.1f}",
                        f"Top: {entry.top_score:.1f}",
                    )
                    st.caption(
                        f"{entry.chunks_analyzed} chunks | "
                        f"{'🎬 Content' if entry.has_content else '—'}"
                    )

                with col_actions:
                    if st.button("📂 Load", key=f"load_{entry.slug}", use_container_width=True):
                        result = lib.load_result(entry.slug)
                        if result:
                            st.session_state.book_result = result
                            st.session_state.content_pack = None
                            st.success(f"✅ Đã load: **{entry.title}**")
                            st.rerun()
                        else:
                            st.error("Không tìm thấy file results.json")

                    if entry.has_content:
                        if st.button("🎬 Load Content", key=f"loadc_{entry.slug}", use_container_width=True):
                            content_data = lib.load_content(entry.slug)
                            if content_data:
                                st.session_state._pending_content = content_data
                                st.info("Content loaded — chuyển sang tab Content Studio")

                    if st.button("🗑️ Xóa", key=f"del_{entry.slug}", use_container_width=True, type="secondary"):
                        lib.delete_book(entry.slug)
                        st.success(f"Đã xóa: {entry.title}")
                        st.rerun()

                st.divider()


# ===========================================================================
# TAB 6 — Prompt Manager
# ===========================================================================

with tab_prompts:
    pm = _get_prompt_mgr()
    st.header("🔧 Quản lý Prompt")
    st.caption(
        "Tùy chỉnh các prompt AI dùng cho phân tích và tạo content. "
        "Thay đổi sẽ áp dụng ngay lần chạy tiếp theo."
    )

    prompts = pm.list_prompts()

    for p in prompts:
        key = p["key"]
        is_custom = p["is_custom"]
        label = f"{'🟠 Đã tùy chỉnh' if is_custom else '⚪ Mặc định'} — {p['name']}"

        with st.expander(label, expanded=False):
            st.caption(p["description"])

            edited = st.text_area(
                "Template",
                value=p["template"],
                height=300,
                key=f"prompt_{key}",
                help="Dùng {variable} cho các biến động. Xem mô tả để biết biến nào có sẵn.",
            )

            col_save, col_reset, col_test = st.columns([1, 1, 2])
            with col_save:
                if st.button("💾 Lưu", key=f"save_{key}", use_container_width=True):
                    pm.set(key, edited)
                    st.success("✅ Đã lưu")

            with col_reset:
                if is_custom:
                    if st.button("↩️ Reset", key=f"reset_{key}", use_container_width=True):
                        pm.reset(key)
                        st.success("Reset về mặc định")
                        st.rerun()

            with col_test:
                if key == "analysis" and st.session_state.book_result:
                    if st.button(
                        "🧪 Test trên chunk đầu tiên",
                        key=f"test_{key}",
                        use_container_width=True,
                    ):
                        r = st.session_state.book_result
                        if r.chunks:
                            sample = r.chunks[0].text[:300]
                            rendered = edited.replace("{text}", sample)
                            st.code(rendered, language=None)

    st.divider()
    st.subheader("⚙️ Cài đặt nâng cao")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("↩️ Reset tất cả về mặc định", type="secondary", use_container_width=True):
            pm.reset_all()
            st.success("Đã reset tất cả prompts về mặc định")
            st.rerun()
    with col_b:
        # Export prompts
        prompts_export = {p["key"]: p["template"] for p in pm.list_prompts()}
        st.download_button(
            "⬇️ Export prompts.json",
            data=json.dumps(prompts_export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="bookai_prompts.json",
            mime="application/json",
            use_container_width=True,
        )

    # Import prompts
    st.subheader("📥 Import prompts")
    prompt_file = st.file_uploader("Upload prompts.json", type=["json"], key="import_prompts")
    if prompt_file:
        try:
            imported = json.loads(prompt_file.getvalue().decode("utf-8"))
            for k, v in imported.items():
                if isinstance(v, str):
                    pm.set(k, v)
            st.success(f"✅ Imported {len(imported)} prompts")
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
