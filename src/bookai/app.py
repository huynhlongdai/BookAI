"""BookAI Streamlit Dashboard — v0.2.0.

Run locally:
    streamlit run src/bookai/app.py

Features (original):
    📖 Upload book → convert → chunk → analyze (mock or real API)
    📊 Browse chunks with viral scores + labels
    ✅ Approve / reject content pieces
    🎙️  Generate radio scripts, quote cards, listicles, captions
    📅 Generate 30-day posting calendar
    🔊 TTS synthesis (Edge-TTS, Vietnamese)
    🖼️  Render quote card PNG images
    📦 Download full content pack as ZIP

New in v0.2.0 (Phase 1-3 upgrade):
    🎬 Video Studio — MoviePy video render + transitions + stock video
    🔊 Multi-TTS — 5 providers, 10+ Vietnamese voices
    📡 Batch Generation — multiple videos from one script
    ⚙️ Settings — TOML config, LLM/TTS provider, i18n
    📤 Social Post — cross-platform auto-upload
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
from bookai.config import get_config, get_section, load_config, set_value
from bookai.content_studio import generate_all, generate_all_with_ai
from bookai.converter import convert_file

# Phase 1-3 imports (safe — all tested)
from bookai.i18n import available_languages, set_language, t
from bookai.library import BookLibrary, PromptManager
from bookai.models import BookResult, ChunkLabel

# ---------------------------------------------------------------------------
# Load config & i18n
# ---------------------------------------------------------------------------

_cfg = load_config(os.environ.get("BOOKAI_CONFIG", "config.toml"))
_ui_lang = get_section("ui").get("language", "vi")
set_language(_ui_lang)

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
.video-card {
    border: 1px solid #333;
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
}
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
        "video_tasks": {},
        "batch_results": [],
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
    st.title("📚 BookAI v0.2")
    st.caption("Sách → Video + Content Affiliate tự động")
    st.divider()

    # Language selector
    langs = available_languages()
    lang_options = {l["code"]: l["name"] for l in langs}
    selected_lang = st.selectbox(
        "🌐 " + t("Language"),
        options=list(lang_options.keys()),
        format_func=lambda x: lang_options[x],
        index=list(lang_options.keys()).index(_ui_lang) if _ui_lang in lang_options else 0,
    )
    if selected_lang != _ui_lang:
        set_language(selected_lang)
        set_value("ui", "language", selected_lang)

    st.divider()

    st.subheader("⚙️ AI Provider")
    provider = st.selectbox(
        "Provider",
        ["mock (offline)", "custom API", "openai", "anthropic", "deepseek", "gemini", "ollama"],
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
    elif provider_key == "deepseek":
        api_key = st.text_input("API Key", type="password",
                                value=os.environ.get("DEEPSEEK_API_KEY", ""))
        model = st.text_input("Model", value="deepseek-chat")
    elif provider_key == "gemini":
        api_key = st.text_input("API Key", type="password",
                                value=os.environ.get("GEMINI_API_KEY", ""))
        model = st.text_input("Model", value="gemini-2.0-flash")
    elif provider_key == "ollama":
        base_url = st.text_input("Ollama URL", value="http://localhost:11434/v1")
        model = st.text_input("Model", value="llama3.1")
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

    # TTS provider selection (Phase 2)
    st.divider()
    st.subheader("🔊 TTS")
    tts_provider = st.selectbox(
        t("TTS Provider"),
        ["edge_tts", "azure", "siliconflow", "elevenlabs", "no_voice"],
        index=0,
    )

    if tts_provider == "edge_tts":
        tts_voice = st.selectbox(
            t("Voice"),
            [
                "vi-VN-HoaiMyNeural (Nữ, miền Bắc)",
                "vi-VN-NamMinhNeural (Nam, miền Bắc)",
            ],
        )
        tts_voice_id = tts_voice.split(" ")[0]
    elif tts_provider == "azure":
        azure_key = st.text_input("Azure Speech Key", type="password",
                                  value=os.environ.get("AZURE_SPEECH_KEY", ""))
        azure_region = st.text_input("Azure Region", value="southeastasia")
        tts_voice = st.selectbox(
            t("Voice"),
            [
                "vi-VN-HoaiMyNeural (Nữ)",
                "vi-VN-NamMinhNeural (Nam)",
            ],
        )
        tts_voice_id = tts_voice.split(" ")[0]
    else:
        tts_voice_id = "vi-VN-HoaiMyNeural"

    tts_rate = st.slider(t("Speech Rate") + " (%)", -50, 50, 0)
    tts_rate_str = f"+{tts_rate}%" if tts_rate >= 0 else f"{tts_rate}%"

    st.divider()
    st.caption("💡 Tip: dùng `mock` để test offline, không cần API key.")


# ---------------------------------------------------------------------------
# Main tabs (original + new Phase 1-3 tabs)
# ---------------------------------------------------------------------------

tab_upload, tab_analyze, tab_content, tab_video, tab_calendar, tab_library, tab_prompts, tab_export, tab_settings = st.tabs([
    "📖 Upload",
    "📊 " + t("Book Analysis"),
    "🎬 " + t("Content Studio"),
    "🎥 " + t("Video Render"),
    "📅 " + t("Content Calendar"),
    "📚 Thư viện",
    "🔧 Prompt",
    "📦 Export",
    "⚙️ " + t("Settings"),
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

        st.markdown("---")
        st.markdown("### ⚙️ Đang xử lý...")
        col_prog, col_time = st.columns([4, 1])
        progress = col_prog.progress(0)
        timer_txt = col_time.empty()

        step_box   = st.empty()
        detail_box = st.empty()
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

            try:
                lib = _get_library()
                lib.save_book(result)
            except Exception:
                pass

            progress.progress(100)
            _tick()

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

        total = len(r.analyzed)
        high = sum(1 for a in r.analyzed if a.viral_score >= 7)
        mid = sum(1 for a in r.analyzed if 4 <= a.viral_score < 7)
        low = sum(1 for a in r.analyzed if a.viral_score < 4)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", total)
        c2.metric("🔥 High (≥7)", high)
        c3.metric("⚠️ Mid (4-7)", mid)
        c4.metric("❄️ Low (<4)", low)

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
        st.header("🎬 " + t("Content Studio"))

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
            total_pieces = pack.total_pieces
            approved_count = (
                len(st.session_state.approved_scripts)
                + len(st.session_state.approved_quotes)
                + len(st.session_state.approved_listicles)
                + len(st.session_state.approved_captions)
            )

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total", total_pieces)
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
                            + " ".join(f"#{t_tag}" for t_tag in script.hashtags)
                        )

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
                                    tts_result = synthesize_script(
                                        proxy, tf.name, voice=tts_voice_id
                                    )
                                    if tts_result.ok:
                                        audio_bytes = Path(tf.name).read_bytes()
                                        st.session_state.tts_results[i] = audio_bytes
                                    else:
                                        st.error(tts_result.error)

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
# TAB 4 — Video Studio (NEW — Phase 1 + 2)
# ===========================================================================

with tab_video:
    st.header("🎥 " + t("Video Render"))
    st.caption("Tạo video chuyên nghiệp từ kịch bản sách — Tự thu thập stock video/ảnh, phụ đề, BGM")

    from bookai.models import BgmMode, SubtitlePosition, TransitionMode, VideoAspect

    v_col1, v_col2 = st.columns(2)

    with v_col1:
        st.subheader("📝 " + t("Script Text"))
        video_script = st.text_area(
            "Kịch bản video",
            height=200,
            placeholder=(
                "Nhập kịch bản video...\n\nVí dụ:\n"
                "Bạn có biết cuốn sách Atomic Habits đã thay đổi cuộc sống của hàng triệu người?\n\n"
                "Thói quen nhỏ tạo nên kết quả lớn. James Clear chỉ ra rằng chỉ cần cải thiện 1% mỗi ngày..."
            ),
            key="video_script",
        )

        # Pre-fill from content pack
        if st.session_state.content_pack and not video_script:
            pack = st.session_state.content_pack
            if pack.radio_scripts:
                s = pack.radio_scripts[0]
                st.caption(f"💡 Tip: Bạn có {len(pack.radio_scripts)} scripts sẵn từ Content Studio")
                if st.button("📋 Dùng Script #1"):
                    st.session_state.video_script = f"{s.hook}\n\n{s.body}\n\n{s.cta}"
                    st.rerun()

    with v_col2:
        st.subheader("⚙️ " + t("Video Settings"))

        video_aspect = st.selectbox(
            t("Video Ratio"),
            [a.value for a in VideoAspect],
            format_func=lambda x: {
                "9:16": "📱 Dọc 9:16 (TikTok/Reels)",
                "16:9": "🖥️ Ngang 16:9 (YouTube)",
                "1:1": "⬜ Vuông 1:1 (Instagram)",
            }.get(x, x),
        )

        video_transition = st.selectbox(
            t("Transition Mode"),
            [m.value for m in TransitionMode],
            format_func=lambda x: {
                "none": "Không chuyển đổi",
                "fade_in": "Fade In",
                "fade_out": "Fade Out",
                "slide_in": "Slide In (trái → phải)",
                "slide_out": "Slide Out (phải → trái)",
                "zoom_ken_burns": "Zoom Ken Burns",
                "shuffle": "🎲 Ngẫu nhiên",
            }.get(x, x),
            index=1,
        )

        # Max clip duration
        max_clip_dur = st.slider("⏱️ Thời lượng tối đa/clip (giây)", 2, 10, 5)

        # Concat mode
        concat_mode = st.selectbox(
            "Chế độ ghép clip",
            ["random", "sequential"],
            format_func=lambda x: {
                "random": "🎲 Ngẫu nhiên",
                "sequential": "📋 Theo thứ tự",
            }.get(x, x),
        )

    # Material source — 3 modes
    st.divider()
    st.subheader("📹 Nguồn hình ảnh / video")
    st.caption("Chọn nơi lấy video/ảnh nền cho video sách")

    material_source = st.radio(
        "Nguồn material",
        ["pexels", "pixabay", "coverr", "local", "ai"],
        format_func=lambda x: {
            "pexels": "🌐 Pexels — Stock video HD miễn phí",
            "pixabay": "🌐 Pixabay — Stock video HD miễn phí",
            "coverr": "🎬 Coverr — Stock video 4K miễn phí",
            "local": "📂 Thư mục local — Ảnh/video của bạn",
            "ai": "🎨 AI Background — Nền màu gradient",
        }.get(x, x),
        horizontal=True,
    )

    pexels_key = ""
    pixabay_key = ""
    coverr_key = ""
    stock_search_terms = ""
    local_mat_dir = ""
    uploaded_files = []

    if material_source in ("pexels", "pixabay", "coverr"):
        mat_col1, mat_col2 = st.columns(2)
        with mat_col1:
            if material_source == "pexels":
                pexels_key = st.text_input(
                    "🔑 Pexels API Key",
                    type="password",
                    value=os.environ.get("PEXELS_API_KEY", ""),
                    help="Đăng ký miễn phí tại pexels.com/api",
                )
            elif material_source == "pixabay":
                pixabay_key = st.text_input(
                    "🔑 Pixabay API Key",
                    type="password",
                    value=os.environ.get("PIXABAY_API_KEY", ""),
                    help="Đăng ký miễn phí tại pixabay.com/api/docs",
                )
            else:
                coverr_key = st.text_input(
                    "🔑 Coverr API Key",
                    type="password",
                    value=os.environ.get("COVERR_API_KEY", ""),
                    help="Đăng ký miễn phí tại coverr.co",
                )
        with mat_col2:
            stock_search_terms = st.text_input(
                "🔍 Từ khóa tìm kiếm",
                placeholder="reading, books, AI, motivation",
                help="Phẩy cách. Để trống = tự tạo từ kịch bản",
            )
        st.info("💡 Hệ thống sẽ tự tìm kiếm stock video phù hợp với nội dung kịch bản, tải về và cắt ghép tự động")

    elif material_source == "local":
        local_mat_dir = st.text_input(
            "📂 Đường dẫn thư mục ảnh/video",
            placeholder="/path/to/your/materials",
            help="Thư mục chứa ảnh (.jpg, .png) và video (.mp4, .mov) để ghép",
        )
        uploaded_files = st.file_uploader(
            "Hoặc upload trực tiếp",
            type=["jpg", "jpeg", "png", "gif", "mp4", "mov", "avi", "webm"],
            accept_multiple_files=True,
            help="Upload ảnh/video để dùng làm nền video",
        )
        st.info("💡 Ảnh sẽ tự chuyển thành clip video với hiệu ứng Ken Burns (zoom). Video sẽ được resize và cắt tự động")

    # ===== KEYWORD PREVIEW =====
    st.divider()
    st.subheader("🔑 Keyword tìm kiếm — LLM AI")
    st.caption("Hệ thống tự phân tích script → trích xuất English keywords cho stock video/ảnh")

    kw_col1, kw_col2 = st.columns([2, 1])
    with kw_col1:
        keyword_mode = st.radio(
            "Chế độ keyword",
            ["llm", "regex", "manual"],
            format_func=lambda x: {
                "llm": "🤖 LLM AI — Phân tích sâu bằng GPT",
                "regex": "📝 Regex — Trích xuất tự động (không cần API)",
                "manual": "✏️ Thủ công — Nhập từ khóa trực tiếp",
            }.get(x, x),
            horizontal=True,
        )
    with kw_col2:
        if keyword_mode == "llm":
            kw_llm_key = st.text_input(
                "🔑 LLM API Key",
                type="password",
                value=get_section("llm").get("openai_api_key", ""),
                help="Dùng OpenAI, TokenRouter, hoặc bất kỳ API tương thích",
                key="kw_llm_key",
            )

    if keyword_mode == "manual":
        manual_keywords = st.text_input(
            "🔍 Từ khóa (phẩy cách)",
            placeholder="reading book, self improvement, atomic habits, success",
            key="manual_keywords",
        )

    # Preview keywords
    if video_script and keyword_mode != "manual":
        if st.button("👁️ Xem trước Keywords", key="preview_kw"):
            try:
                from bookai.keyword_generator import (
                    KeywordConfig,
                    generate_keywords,
                    generate_keywords_regex,
                )
                if keyword_mode == "llm" and kw_llm_key:
                    kw_cfg = KeywordConfig(
                        llm_api_key=kw_llm_key,
                        llm_base_url=get_section("llm").get("openai_base_url", "https://api.openai.com/v1"),
                        llm_model=get_section("llm").get("openai_model_name", "gpt-4o-mini"),
                    )
                    preview_kw = generate_keywords(video_script, "", "book review", kw_cfg)
                else:
                    preview_kw = generate_keywords_regex(video_script, "", 8)
                st.success(f"🔑 Keywords ({len(preview_kw)}): " + ", ".join(f"`{k}`" for k in preview_kw))
            except Exception as e:
                st.error(f"Lỗi: {e}")

    # ===== MATERIAL MANAGEMENT — Local + Mixed =====
    st.divider()
    st.subheader("📂 Quản lý tư liệu — Local & Mixed")
    st.caption("Kết hợp thư mục local + stock API cho video phong phú hơn")

    mat_mgr_col1, mat_mgr_col2 = st.columns(2)
    with mat_mgr_col1:
        local_material_mode = st.selectbox(
            "Chế độ tư liệu local",
            ["none", "supplement", "priority", "only"],
            format_func=lambda x: {
                "none": "❌ Không dùng local",
                "supplement": "➕ Bổ sung — Stock chính, local phụ",
                "priority": "⭐ Ưu tiên — Local trước, stock bổ sung",
                "only": "📂 Chỉ local — Không dùng stock API",
            }.get(x, x),
            key="local_material_mode",
        )
    with mat_mgr_col2:
        if local_material_mode != "none":
            local_dir_path = st.text_input(
                "📂 Thư mục tư liệu",
                placeholder="/path/to/materials/",
                help="Cấu trúc: hooks/, backgrounds/, book_covers/, overlays/, intros/, outros/",
                key="local_dir_path",
            )
        else:
            local_dir_path = ""

    if local_dir_path and os.path.isdir(local_dir_path):
        try:
            from bookai.material_manager import scan_local_directory
            scanned = scan_local_directory(local_dir_path, recursive=True)
            if scanned:
                cats = {}
                for m in scanned:
                    cats.setdefault(m.category, []).append(m)
                cat_str = " | ".join(f"{k}: {len(v)} files" for k, v in cats.items())
                st.success(f"📂 Tìm thấy {len(scanned)} files — {cat_str}")
            else:
                st.warning("⚠️ Không tìm thấy file nào trong thư mục")
        except Exception:
            pass

    # Google Drive integration
    st.divider()
    st.subheader("☁️ Google Drive — Tải tư liệu từ Drive")
    st.caption("Nhập link thư mục Drive chia sẻ công khai để tải video/ảnh tư liệu")

    drive_col1, drive_col2 = st.columns([3, 1])
    with drive_col1:
        drive_folder_url = st.text_input(
            "🔗 Link thư mục Drive",
            placeholder="https://drive.google.com/drive/folders/1ABC...",
            key="drive_folder_url",
        )
    with drive_col2:
        drive_api_key = st.text_input(
            "🔑 Google API Key (optional)",
            type="password",
            key="drive_api_key",
            help="Cần cho thư mục private. Public folder không cần.",
        )

    if drive_folder_url:
        drive_col_a, drive_col_b = st.columns(2)
        with drive_col_a:
            if st.button("📋 Xem danh sách files", key="drive_list"):
                try:
                    from bookai.drive_material import DriveConfig, DriveMaterialManager
                    dcfg = DriveConfig(
                        folder_url=drive_folder_url,
                        api_key=drive_api_key,
                    )
                    dmgr = DriveMaterialManager(dcfg)
                    dfiles = dmgr.list_files()
                    st.success(f"☁️ Tìm thấy {len(dfiles)} files trên Drive")
                    for df in dfiles[:10]:
                        icon = "🎥" if df.is_video else "🖼️" if df.is_image else "📄"
                        st.caption(f"{icon} {df.name} ({df.category}) — {df.size_bytes/1024:.0f} KB")
                except Exception as e:
                    st.error(f"❌ Lỗi: {e}")

        with drive_col_b:
            drive_output = st.text_input(
                "📂 Thư mục tải về",
                value="materials/drive",
                key="drive_output_dir",
            )
            if st.button("⬇️ Tải về tất cả", key="drive_download"):
                try:
                    from bookai.drive_material import DriveConfig, DriveMaterialManager
                    dcfg = DriveConfig(
                        folder_url=drive_folder_url,
                        api_key=drive_api_key,
                        download_dir=drive_output,
                    )
                    dmgr = DriveMaterialManager(dcfg)
                    local_dir = dmgr.sync_to_local()
                    st.success(f"✅ Đã tải {len(dmgr._files)} files → {local_dir}")
                except Exception as e:
                    st.error(f"❌ Lỗi: {e}")

    # ===== HOOK / TITLE / OUTRO SECTIONS =====
    st.divider()
    st.subheader("🎬 Video Sections — Hook / Title / Outro")
    st.caption("Thêm đoạn mở đầu (Hook), thẻ tiêu đề, và đoạn kết chuyên nghiệp")

    sec_col1, sec_col2, sec_col3 = st.columns(3)
    with sec_col1:
        hook_style_choice = st.selectbox(
            "🪝 Hook Style",
            ["", "bold_question", "shocking_fact", "book_rating", "quote_reveal", "mystery"],
            format_func=lambda x: {
                "": "❌ Không dùng Hook",
                "bold_question": "❓ Câu hỏi gây tò mò",
                "shocking_fact": "⚡ Sự thật bất ngờ",
                "book_rating": "⭐ Đánh giá sách",
                "quote_reveal": "💬 Trích dẫn nổi bật",
                "mystery": "🔮 Bí ẩn / Teaser",
            }.get(x, x),
        )
        if hook_style_choice:
            hook_text_input = st.text_input(
                "📝 Nội dung Hook",
                placeholder="Cuốn sách này đã thay đổi cuộc đời tôi!",
                key="hook_text_input",
            )
        else:
            hook_text_input = ""

    with sec_col2:
        title_card_choice = st.selectbox(
            "🏷️ Title Card Style",
            ["", "book_cover", "minimalist", "gradient_card", "split_screen"],
            format_func=lambda x: {
                "": "❌ Không dùng Title Card",
                "book_cover": "📕 Bìa sách",
                "minimalist": "✨ Tối giản",
                "gradient_card": "🌈 Gradient",
                "split_screen": "📐 Chia đôi",
            }.get(x, x),
        )
        cover_img_path = ""
        if title_card_choice == "book_cover":
            cover_img_path = st.text_input(
                "🖼️ Ảnh bìa sách",
                placeholder="/path/to/cover.jpg",
                key="cover_img",
            )

    with sec_col3:
        outro_style_choice = st.selectbox(
            "🎬 Outro Style",
            ["", "subscribe_cta", "rating_summary", "next_book"],
            format_func=lambda x: {
                "": "❌ Không dùng Outro",
                "subscribe_cta": "🔔 Subscribe CTA",
                "rating_summary": "⭐ Tổng kết đánh giá",
                "next_book": "📚 Giới thiệu sách tiếp",
            }.get(x, x),
        )
        if outro_style_choice:
            outro_text_input = st.text_input(
                "📝 Nội dung Outro",
                value="Cảm ơn đã xem! Đăng ký kênh nhé!",
                key="outro_text_input",
            )
        else:
            outro_text_input = ""

    # ===== DYNAMIC TEXT EFFECTS (CapCut Phase 2) =====
    st.divider()
    st.subheader("✨ Dynamic Text Effects — CapCut Phase 2")
    st.caption("Hiệu ứng text động nâng cao: glow, overlay, counter")

    fx_col1, fx_col2 = st.columns(2)
    with fx_col1:
        glow_preset_choice = st.selectbox(
            "🔆 Glow Preset (cho subtitle)",
            ["", "neon_pulse", "neon_flicker", "soft_glow", "fire_glow", "rainbow_cycle", "gradient_sweep", "shadow_pop", "frost_shine"],
            format_func=lambda x: {
                "": "❌ Không dùng glow",
                "neon_pulse": "💚 Neon Pulse — Xanh lá nhấp nháy",
                "neon_flicker": "💜 Neon Flicker — Tím ngẫu nhiên",
                "soft_glow": "⬜ Soft Glow — Trắng dịu",
                "fire_glow": "🔥 Fire Glow — Lửa cam-đỏ",
                "rainbow_cycle": "🌈 Rainbow — Xoay cầu vồng",
                "gradient_sweep": "🔵 Gradient Sweep — Quét xanh",
                "shadow_pop": "⬛ Shadow Pop — Bóng nổi",
                "frost_shine": "❄️ Frost Shine — Lấp lánh lạnh",
            }.get(x, x),
        )
    with fx_col2:
        overlay_choice = st.selectbox(
            "📋 Text Overlay",
            ["", "lower_third", "full_screen_quote", "bullet_list", "chapter_marker", "highlight_box", "stats_counter"],
            format_func=lambda x: {
                "": "❌ Không dùng overlay",
                "lower_third": "📺 Lower Third — Thanh tên/tiêu đề",
                "full_screen_quote": "💬 Full Screen Quote — Trích dẫn lớn",
                "bullet_list": "📝 Bullet List — Danh sách điểm",
                "chapter_marker": "📖 Chapter Marker — Đánh dấu chương",
                "highlight_box": "💡 Highlight Box — Hộp insight",
                "stats_counter": "📊 Stats Counter — Đếm số",
            }.get(x, x),
        )
        if overlay_choice:
            overlay_text = st.text_input(
                "📝 Nội dung overlay",
                placeholder="Tên tác giả, insight chính, hoặc số liệu",
                key="overlay_text",
            )
        else:
            overlay_text = ""

    # Audio & Subtitle settings
    st.divider()
    audio_sub_col1, audio_sub_col2 = st.columns(2)

    with audio_sub_col1:
        st.subheader("🔊 Giọng đọc (TTS)")
        tts_voice_choice = st.selectbox(
            "Giọng đọc",
            ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
            format_func=lambda x: {
                "vi-VN-HoaiMyNeural": "👩 Hoài My (Nữ, miền Nam)",
                "vi-VN-NamMinhNeural": "👨 Nam Minh (Nam, miền Bắc)",
            }.get(x, x),
        )

        # BGM settings
        bgm_mode = st.selectbox(
            t("Background Music"),
            [m.value for m in BgmMode],
            format_func=lambda x: {
                "none": "🔇 " + t("No Background Music"),
                "random": "🎲 " + t("Random Background Music"),
                "specific": "🎵 Chọn bài cụ thể",
            }.get(x, x),
            index=1,
        )
        bgm_volume = st.slider(t("BGM Volume"), 0.0, 1.0, 0.15, step=0.05)

    with audio_sub_col2:
        st.subheader("📝 Phụ đề (Subtitles)")
        enable_subtitle = st.checkbox(t("Enable Subtitles"), value=True)
        if enable_subtitle:
            # Template selector (CapCut-style)
            try:
                from bookai.subtitle_templates import TEMPLATES, list_templates
                template_options = ["(Tùy chỉnh)"] + [
                    f"{t_info['name']} — {t_info['description']}"
                    for t_info in list_templates()
                ]
                template_ids = [""] + list(TEMPLATES.keys())
                selected_template_idx = st.selectbox(
                    "🎨 Kiểu phụ đề (Template)",
                    range(len(template_options)),
                    format_func=lambda i: template_options[i],
                    index=1,  # Default to capcut_white_box (first template after custom)
                    help="Chọn mẫu phụ đề kiểu CapCut hoặc tùy chỉnh",
                )
                selected_template = template_ids[selected_template_idx]
            except ImportError:
                selected_template = ""

            # Show custom settings only when no template selected
            if not selected_template:
                sub_position = st.selectbox(
                    t("Subtitle Position"),
                    [p.value for p in SubtitlePosition],
                    format_func=lambda x: {
                        "top": "⬆️ " + t("Top"),
                        "center": "⏺️ " + t("Center"),
                        "bottom": "⬇️ " + t("Bottom"),
                    }.get(x, x),
                    index=2,
                )
                sub_font_size = st.slider(t("Font Size"), 12, 48, 24)
                sub_col_a, sub_col_b = st.columns(2)
                with sub_col_a:
                    sub_font_color = st.color_picker(t("Font Color"), value="#FFFFFF")
                with sub_col_b:
                    sub_stroke_color = st.color_picker(t("Stroke Color"), value="#000000")
                sub_bg_enabled = st.checkbox("Nền phụ đề bán trong suốt", value=False)
            else:
                # Defaults when using template (template handles everything)
                sub_position = "bottom"
                sub_font_size = 24
                sub_font_color = "#FFFFFF"
                sub_stroke_color = "#000000"
                sub_bg_enabled = False
        else:
            selected_template = ""

    # ===== RENDER BUTTON =====
    st.divider()
    render_video_btn = st.button(
        "🎬 " + t("Generate Video"),
        type="primary",
        use_container_width=True,
        disabled=not video_script,
    )

    if render_video_btn and video_script:
        progress_bar = st.progress(0, text="Bắt đầu pipeline...")

        try:
            from bookai.video_pipeline import PipelineConfig, create_book_video

            # Handle uploaded files
            local_mats = None
            temp_upload_dir = None
            if material_source == "local" and uploaded_files:
                temp_upload_dir = tempfile.mkdtemp(prefix="bookai_uploads_")
                local_mats = []
                for uf in uploaded_files:
                    save_path = os.path.join(temp_upload_dir, uf.name)
                    with open(save_path, "wb") as f:
                        f.write(uf.getbuffer())
                    local_mats.append(save_path)

            # Parse search terms
            terms = None
            if stock_search_terms:
                terms = [t.strip() for t in stock_search_terms.split(",") if t.strip()]

            # Build config
            pipe_cfg = PipelineConfig(
                material_source=material_source,
                pexels_api_key=pexels_key,
                pixabay_api_key=pixabay_key,
                coverr_api_key=coverr_key,
                local_material_dir=local_mat_dir,
                aspect=video_aspect,
                max_clip_duration=max_clip_dur,
                transition=video_transition,
                concat_mode=concat_mode,
                tts_voice=tts_voice_choice,
                subtitle_enabled=enable_subtitle,
                subtitle_position=sub_position if enable_subtitle else "bottom",
                subtitle_font_size=sub_font_size if enable_subtitle else 24,
                subtitle_color=sub_font_color if enable_subtitle else "#FFFFFF",
                subtitle_stroke_color=sub_stroke_color if enable_subtitle else "#000000",
                subtitle_bg_color="#00000090" if (enable_subtitle and sub_bg_enabled) else "",
                subtitle_template=selected_template if enable_subtitle else "",
                bgm_mode=bgm_mode,
                bgm_volume=bgm_volume,
                # New: keyword settings
                keyword_mode=keyword_mode if keyword_mode != "manual" else "regex",
                llm_api_key=kw_llm_key if keyword_mode == "llm" else "",
                llm_base_url=get_section("llm").get("openai_base_url", "https://api.openai.com/v1"),
                llm_model=get_section("llm").get("openai_model_name", "gpt-4o-mini"),
                # New: local material mode
                local_mode=local_material_mode if local_material_mode != "none" else "supplement",
                # New: video sections (hook/title/outro)
                hook_style=hook_style_choice,
                hook_text=hook_text_input,
                title_card_style=title_card_choice,
                cover_image_path=cover_img_path,
                outro_style=outro_style_choice,
                outro_text=outro_text_input,
            )

            # Output path
            output_dir = Path("output/videos")
            output_dir.mkdir(parents=True, exist_ok=True)
            import time as _time2
            final_path = str(output_dir / f"bookai_{int(_time2.time())}.mp4")

            progress_bar.progress(10, text="📝 Đang tạo giọng đọc (TTS)...")

            result = create_book_video(
                script_text=video_script,
                book_title=st.session_state.get("book_metadata", {}).get("title", "BookAI"),
                config=pipe_cfg,
                output_path=final_path,
                search_terms=terms,
                local_materials=local_mats,
            )

            # Cleanup uploads
            if temp_upload_dir:
                import shutil
                shutil.rmtree(temp_upload_dir, ignore_errors=True)

            if result.ok:
                progress_bar.progress(100, text="✅ Hoàn thành!")

                st.success(
                    f"✅ Video hoàn thành! "
                    f"({result.duration_seconds:.1f}s, {result.file_size_mb:.1f}MB)"
                )

                # Show pipeline steps
                steps_display = {
                    "tts": "🔊 TTS", "subtitle": "📝 SRT",
                    "materials": "📹 Materials", "clips": "✂️ Clips",
                    "concat": "🔗 Concat", "subtitle_burn": "📝 Subtitle burn",
                    "audio_bgm": "🎵 Audio+BGM", "complete": "✅ Done",
                }
                steps_str = " → ".join(
                    steps_display.get(s, s) for s in result.steps_completed
                )
                st.caption(f"Pipeline: {steps_str}")

                if result.search_terms_used:
                    st.caption(f"🔍 Stock search terms: {', '.join(result.search_terms_used)}")
                if result.material_paths:
                    st.caption(f"📹 {len(result.material_paths)} material clips sử dụng")

                st.video(final_path)

                with open(final_path, "rb") as f:
                    st.download_button(
                        "⬇️ " + t("Download") + " Video",
                        data=f.read(),
                        file_name=os.path.basename(final_path),
                        mime="video/mp4",
                    )
            else:
                progress_bar.progress(100, text="❌ Thất bại")
                st.error(f"❌ Pipeline thất bại: {result.error}")
                if result.steps_completed:
                    st.caption(f"Steps completed: {', '.join(result.steps_completed)}")

        except ImportError as e:
            st.error(f"❌ Thiếu thư viện: {e}\n\nChạy: `pip install edge-tts`")
        except Exception as e:
            st.error(f"❌ Lỗi: {e}")
            import traceback
            st.code(traceback.format_exc()[-500:])

    # Batch generation section
    st.divider()
    st.subheader("📦 " + t("Batch Generate"))
    st.caption("Tạo nhiều video variants từ một kịch bản — tự động thay đổi transition, aspect, stock footage")

    batch_col1, batch_col2 = st.columns(2)
    with batch_col1:
        batch_count = st.number_input(t("Number of Videos"), min_value=1, max_value=10, value=3)
    with batch_col2:
        batch_vary = st.multiselect(
            "Thay đổi tự động",
            ["transition", "aspect", "stock_footage"],
            default=["transition"],
        )

    if st.button("🔄 " + t("Batch Generate"), disabled=not video_script):
        st.info(f"Sẽ tạo {batch_count} video variants — cần API keys")
        st.caption("💡 Batch generation sử dụng module `bookai.batch` với ThreadPoolExecutor")
        st.caption("💡 Trong production, dùng REST API: `POST /api/v1/batch`")


# ===========================================================================
# TAB 5 — Lịch đăng
# ===========================================================================

with tab_calendar:
    if not st.session_state.content_pack:
        st.info("👆 Generate content ở tab **Content Studio** trước.")
    else:
        pack = st.session_state.content_pack
        st.header("📅 " + t("Content Calendar"))

        c1, c2, c3 = st.columns(3)
        with c1:
            start_date_input = st.date_input("Ngày bắt đầu")
        with c2:
            days_input = st.slider("Số ngày", 7, 60, 30)
        with c3:
            platforms_input = st.multiselect(
                t("Platforms"),
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

    # Social post section
    st.divider()
    st.subheader("📤 " + t("Cross Post"))
    st.caption("Đăng video lên TikTok, Instagram, YouTube, Facebook tự động")

    sp_col1, sp_col2 = st.columns(2)
    with sp_col1:
        social_platforms = st.multiselect(
            t("Platforms"),
            ["tiktok", "instagram", "youtube", "facebook"],
            default=["tiktok", "instagram"],
            key="social_platforms",
        )
    with sp_col2:
        upload_post_key = st.text_input(
            "Upload-Post API Key",
            type="password",
            value=os.environ.get("UPLOAD_POST_API_KEY", ""),
        )
        auto_upload = st.checkbox(t("Auto Upload"), value=False)

    st.caption(
        "💡 Cần Upload-Post API key (upload-post.com) — "
        "hoặc cấu hình webhook cho Zapier/n8n"
    )


# ===========================================================================
# TAB 6 — Thư viện sách
# ===========================================================================

with tab_library:
    lib = _get_library()
    st.header("📚 Thư viện sách")

    stats = lib.stats()
    if stats["total"] == 0:
        st.info("Chưa có sách nào. Upload và phân tích sách ở tab **Upload & Process** — sẽ tự động lưu vào thư viện.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📚 Tổng sách", stats["total"])
        c2.metric("🔬 Tổng chunks", stats["total_chunks"])
        c3.metric("⚡ Avg score", f"{stats['avg_score']:.1f}/10")
        c4.metric("🎬 Có content", stats["with_content"])

        st.divider()

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
# TAB 7 — Prompt Manager
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
                help="Dùng {variable} cho các biến động.",
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
        prompts_export = {p["key"]: p["template"] for p in pm.list_prompts()}
        st.download_button(
            "⬇️ Export prompts.json",
            data=json.dumps(prompts_export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="bookai_prompts.json",
            mime="application/json",
            use_container_width=True,
        )

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


# ===========================================================================
# TAB 8 — Export
# ===========================================================================

with tab_export:
    st.header("📦 Export")

    has_result = st.session_state.book_result is not None
    has_pack = st.session_state.content_pack is not None
    has_calendar = len(st.session_state.calendar_entries) > 0

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

    st.subheader("📦 Full Content Pack (ZIP)")
    if has_pack:
        if st.button("🔄 Build ZIP", type="primary"):
            with st.spinner("Đang đóng gói..."):
                try:
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
                    }

                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        if has_result:
                            zf.writestr(
                                "results.json",
                                json.dumps(
                                    st.session_state.book_result.model_dump(),
                                    ensure_ascii=False, indent=2
                                ),
                            )

                        zf.writestr(
                            "content_approved.json",
                            json.dumps(approved_data, ensure_ascii=False, indent=2),
                        )

                        if has_calendar:
                            with tempfile.NamedTemporaryFile(
                                suffix=".csv", delete=False
                            ) as tf_cal:
                                from bookai.calendar import save_calendar_csv
                                save_calendar_csv(
                                    st.session_state.calendar_entries, tf_cal.name
                                )
                                zf.write(tf_cal.name, "calendar.csv")
                                Path(tf_cal.name).unlink(missing_ok=True)

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
        moviepy>=2.0
        ```

        **Bước 4:** Thêm API key vào Secrets của Space (Settings → Secrets):
        ```
        key_api = your_api_key_here
        ```
        """)


# ===========================================================================
# TAB 9 — Settings (NEW — Phase 3)
# ===========================================================================

with tab_settings:
    st.header("⚙️ " + t("Settings"))

    st.subheader("📋 Config hiện tại")
    st.caption("File: `config.toml` — cấu hình TOML với các sections")

    cfg = get_config()

    # Display current config sections
    config_tabs = st.tabs(["[app]", "[llm]", "[tts]", "[video]", "[material]", "[social]", "[affiliate]"])

    with config_tabs[0]:
        st.subheader("🏠 App Settings")
        app_cfg = get_section("app")
        for k, v in app_cfg.items():
            st.text(f"{k} = {v}")

    with config_tabs[1]:
        st.subheader("🤖 LLM Settings")
        llm_cfg = get_section("llm")

        from bookai.llm_providers import list_providers
        all_providers_data = list_providers()
        all_providers = list(all_providers_data.keys()) if isinstance(all_providers_data, dict) else list(all_providers_data)

        new_llm_provider = st.selectbox(
            "LLM Provider",
            all_providers,
            index=all_providers.index(llm_cfg.get("provider", "openai")) if llm_cfg.get("provider", "openai") in all_providers else 0,
            key="settings_llm_provider",
        )
        new_llm_key = st.text_input(
            "API Key",
            value=llm_cfg.get("api_key", ""),
            type="password",
            key="settings_llm_key",
        )
        new_llm_model = st.text_input(
            "Model",
            value=llm_cfg.get("model_name", "gpt-4o-mini"),
            key="settings_llm_model",
        )
        new_llm_temp = st.slider(
            "Temperature",
            0.0, 2.0,
            float(llm_cfg.get("temperature", 0.7)),
            key="settings_llm_temp",
        )

        if st.button("💾 " + t("Save Settings"), key="save_llm"):
            set_value("llm", "provider", new_llm_provider)
            set_value("llm", "api_key", new_llm_key)
            set_value("llm", "model_name", new_llm_model)
            set_value("llm", "temperature", new_llm_temp)
            st.success("✅ " + t("Settings Saved"))

    with config_tabs[2]:
        st.subheader("🔊 TTS Settings")
        tts_cfg = get_section("tts")
        for k, v in tts_cfg.items():
            if k != "api_key":
                st.text(f"{k} = {v}")

    with config_tabs[3]:
        st.subheader("🎥 Video Settings")
        video_cfg = get_section("video")
        for k, v in video_cfg.items():
            if "key" not in k.lower():
                st.text(f"{k} = {v}")

        st.divider()
        st.subheader("🔑 Stock Video API Keys")
        new_pexels = st.text_input(
            "Pexels API Key",
            value=video_cfg.get("pexels_api_key", os.environ.get("PEXELS_API_KEY", "")),
            type="password",
            key="settings_pexels_key",
            help="https://www.pexels.com/api → Free signup",
        )
        new_pixabay = st.text_input(
            "Pixabay API Key",
            value=video_cfg.get("pixabay_api_key", os.environ.get("PIXABAY_API_KEY", "")),
            type="password",
            key="settings_pixabay_key",
            help="https://pixabay.com/api/docs → Free signup",
        )

        if st.button("💾 Save Video API Keys", key="save_video_keys"):
            set_value("video", "pexels_api_key", new_pexels)
            set_value("video", "pixabay_api_key", new_pixabay)
            st.success("✅ API Keys saved!")

    with config_tabs[4]:
        st.subheader("📂 Material Settings")
        st.caption("Cấu hình keyword generation và local material directories")

        mat_cfg = get_section("material")

        new_kw_mode = st.selectbox(
            "Keyword Mode",
            ["llm", "regex"],
            index=0 if mat_cfg.get("keyword_mode", "llm") == "llm" else 1,
            format_func=lambda x: {
                "llm": "🤖 LLM AI — Keyword từ GPT",
                "regex": "📝 Regex — Không cần API",
            }.get(x, x),
            key="settings_kw_mode",
        )
        new_match_order = st.checkbox(
            "Match script order (keywords theo thứ tự kịch bản)",
            value=mat_cfg.get("match_script_order", True),
            key="settings_match_order",
        )
        new_local_dir = st.text_input(
            "📂 Default local material directory",
            value=mat_cfg.get("local_dir", ""),
            key="settings_local_dir",
        )
        new_local_mode = st.selectbox(
            "Local mode",
            ["supplement", "priority", "only"],
            index=["supplement", "priority", "only"].index(mat_cfg.get("local_mode", "supplement")),
            format_func=lambda x: {
                "supplement": "➕ Supplement (stock + local)",
                "priority": "⭐ Priority (local first)",
                "only": "📂 Only (no stock API)",
            }.get(x, x),
            key="settings_local_mode",
        )

        if st.button("💾 Save Material Settings", key="save_material"):
            set_value("material", "keyword_mode", new_kw_mode)
            set_value("material", "match_script_order", new_match_order)
            set_value("material", "local_dir", new_local_dir)
            set_value("material", "local_mode", new_local_mode)
            st.success("✅ Material settings saved!")

    with config_tabs[5]:
        st.subheader("📤 Social Settings")
        social_cfg = get_section("social")
        for k, v in social_cfg.items():
            if "key" not in k.lower():
                st.text(f"{k} = {v}")

    with config_tabs[6]:
        st.subheader("💰 Affiliate Settings")
        aff_cfg = get_section("affiliate")
        for k, v in aff_cfg.items():
            st.text(f"{k} = {v}")

    # System info
    st.divider()
    st.subheader("📊 System Info")
    sys_col1, sys_col2, sys_col3 = st.columns(3)
    with sys_col1:
        st.metric("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        try:
            import moviepy
            st.metric("MoviePy", moviepy.__version__)
        except ImportError:
            st.metric("MoviePy", "❌ Not installed")
    with sys_col2:
        try:
            import edge_tts  # noqa: F401
            st.metric("Edge-TTS", "✅ Available")
        except ImportError:
            st.metric("Edge-TTS", "❌ Not installed")
        try:
            import fastapi
            st.metric("FastAPI", fastapi.__version__)
        except ImportError:
            st.metric("FastAPI", "❌ Not installed")
    with sys_col3:
        import bookai
        st.metric("BookAI", bookai.__version__)

        # i18n info
        langs = available_languages()
        st.metric("Languages", f"{len(langs)} ({', '.join(l['code'] for l in langs)})")

    # Generate config file
    st.divider()
    st.subheader("📥 Export / Import Config")
    col_ex, col_im = st.columns(2)
    with col_ex:
        from bookai.config import generate_example_config
        example_toml = generate_example_config()
        st.download_button(
            "⬇️ Download config.example.toml",
            data=example_toml.encode("utf-8"),
            file_name="config.example.toml",
            mime="text/plain",
        )
    with col_im:
        config_upload = st.file_uploader("Upload config.toml", type=["toml"], key="config_upload")
        if config_upload:
            try:
                import toml as _toml
                uploaded_cfg = _toml.loads(config_upload.getvalue().decode("utf-8"))
                st.json(uploaded_cfg)
                st.success("✅ Config parsed successfully")
            except Exception as e:
                st.error(f"❌ {e}")
