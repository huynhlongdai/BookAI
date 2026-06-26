"""REST API for BookAI — Phase 2.

Full CRUD API for video generation tasks, BGM management, material upload,
streaming, and download.

Inspired by MoneyPrinterTurbo's /api/v1/ controller.

Run::

    uvicorn bookai.api:app --host 0.0.0.0 --port 8080 --reload

Endpoints:
    POST   /api/v1/videos          — Create video generation task
    POST   /api/v1/audio           — Create TTS-only task
    POST   /api/v1/subtitle        — Create subtitle-only task
    POST   /api/v1/batch           — Create batch video generation
    GET    /api/v1/tasks           — List all tasks (paginated)
    GET    /api/v1/tasks/{id}      — Get task status
    DELETE /api/v1/tasks/{id}      — Cancel/delete task
    GET    /api/v1/bgm             — List BGM tracks
    POST   /api/v1/bgm/upload      — Upload BGM file
    GET    /api/v1/voices          — List available TTS voices
    GET    /api/v1/download/{path} — Download output file
    GET    /api/v1/stream/{path}   — Stream video file
    GET    /api/v1/health          — Health check
"""

from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import (
        FastAPI, File, HTTPException, Path as PathParam,
        Query, Request, UploadFile,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from pydantic import BaseModel, Field

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    # -----------------------------------------------------------------------
    # App setup
    # -----------------------------------------------------------------------

    app = FastAPI(
        title="BookAI API",
        description="AI-powered book → video content pipeline",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Request / Response models
    # -----------------------------------------------------------------------

    class VideoRequest(BaseModel):
        """Request to create a video generation task."""
        text: str = Field("", description="Script text (or provide script_hook/body/cta)")
        script_hook: str = Field("", description="Hook section of the script")
        script_body: str = Field("", description="Body section")
        script_cta: str = Field("", description="CTA section")
        audio_path: str = Field("", description="Pre-existing audio file path (skips TTS)")
        cover_image: str = Field("", description="Cover image path")
        output_dir: str = Field("output", description="Output directory")

        # Video options
        aspect: str = Field("9:16", description="Aspect ratio: 9:16, 16:9, 1:1")
        transition: str = Field("fade_in", description="Transition effect")
        bgm_mode: str = Field("none", description="BGM mode: none, random, specific")
        bgm_file: str = Field("", description="Specific BGM filename")
        subtitle_enabled: bool = Field(True, description="Enable subtitles")

        # TTS options
        tts_provider: str = Field("edge_tts", description="TTS provider")
        tts_voice: str = Field("vi-VN-HoaiMyNeural", description="TTS voice name")
        tts_rate: str = Field("+0%", description="TTS speed rate")

        # Stock video
        stock_search_terms: list[str] = Field(default_factory=list)
        pexels_api_key: str = Field("", description="Pexels API key for stock video")

        # Pipeline control
        stop_at: str = Field("all", description="Stop at stage: script, tts, subtitle, materials, video, all")

        # Metadata
        book_title: str = ""
        author: str = ""

    class BatchRequest(BaseModel):
        """Request for batch video generation."""
        text: str = ""
        audio_path: str = ""
        cover_image: str = ""
        output_dir: str = "output"
        video_count: int = Field(3, ge=1, le=20)
        shuffle_stock: bool = True
        vary_transitions: bool = True
        vary_bgm: bool = True
        vary_aspect: bool = False
        aspect: str = "9:16"
        transition: str = "fade_in"
        bgm_mode: str = "random"
        subtitle_enabled: bool = True
        tts_provider: str = "edge_tts"
        tts_voice: str = "vi-VN-HoaiMyNeural"
        stock_search_terms: list[str] = Field(default_factory=list)

    class TaskResponse(BaseModel):
        """Response for task creation."""
        task_id: str
        message: str = "Task created"

    class TaskStatusResponse(BaseModel):
        """Response for task status query."""
        task_id: str
        state: int
        state_label: str
        progress: int
        created_at: float
        updated_at: float
        error: str = ""
        result_files: list[str] = Field(default_factory=list)
        params: dict[str, Any] = Field(default_factory=dict)

    class TaskListResponse(BaseModel):
        """Response for task list query."""
        tasks: list[TaskStatusResponse]
        total: int
        page: int
        page_size: int

    class BgmItem(BaseModel):
        """BGM track info."""
        name: str
        size_mb: float
        path: str

    class VoiceItem(BaseModel):
        """TTS voice info."""
        name: str
        provider: str
        gender: str
        description: str

    class HealthResponse(BaseModel):
        """Health check response."""
        status: str = "ok"
        version: str = "0.2.0"
        moviepy_available: bool = False
        ffmpeg_available: bool = False
        active_tasks: int = 0
        queued_tasks: int = 0

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _build_script_from_request(req: VideoRequest):
        """Build a script-like object from API request."""
        if req.text:
            # Create a simple script object
            class SimpleScript:
                def __init__(self, text):
                    self.hook = ""
                    self.body = text
                    self.cta = ""
            return SimpleScript(req.text)

        if req.script_hook or req.script_body or req.script_cta:
            class SimpleScript:
                def __init__(self, hook, body, cta):
                    self.hook = hook
                    self.body = body
                    self.cta = cta
            return SimpleScript(req.script_hook, req.script_body, req.script_cta)

        return None

    def _task_info_to_response(info) -> TaskStatusResponse:
        d = info.to_dict()
        return TaskStatusResponse(
            task_id=d["task_id"],
            state=d["state"],
            state_label=d["state_label"],
            progress=d["progress"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            error=d.get("error", ""),
            result_files=d.get("result_files", []),
            params=d.get("params", {}),
        )

    def _resolve_safe_path(base_dir: str, file_path: str) -> Path:
        """Resolve file path safely within base directory."""
        base = Path(base_dir).resolve()
        target = (base / file_path).resolve()
        if not str(target).startswith(str(base)):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return target

    # -----------------------------------------------------------------------
    # Video endpoints
    # -----------------------------------------------------------------------

    @app.post("/api/v1/videos", response_model=TaskResponse, tags=["Video"])
    def create_video(req: VideoRequest):
        """Create a video generation task."""
        from bookai.task_manager import TaskParams, get_task_manager

        script = _build_script_from_request(req)
        text = req.text or ""
        if not text and script:
            text = "\n".join(filter(None, [
                getattr(script, "hook", ""),
                getattr(script, "body", ""),
                getattr(script, "cta", ""),
            ]))

        if not text and not req.audio_path:
            raise HTTPException(status_code=400, detail="Provide text or audio_path")

        params = TaskParams(
            task_type="video",
            script=script,
            text=text,
            audio_path=req.audio_path,
            cover_image=req.cover_image,
            output_dir=req.output_dir,
            aspect=req.aspect,
            transition=req.transition,
            bgm_mode=req.bgm_mode,
            bgm_file=req.bgm_file,
            subtitle_enabled=req.subtitle_enabled,
            tts_provider=req.tts_provider,
            tts_voice=req.tts_voice,
            tts_rate=req.tts_rate,
            stock_search_terms=req.stock_search_terms,
            pexels_api_key=req.pexels_api_key,
            stop_at=req.stop_at,
            book_title=req.book_title,
            author=req.author,
        )

        manager = get_task_manager()
        task_id = manager.submit(params)
        return TaskResponse(task_id=task_id, message="Video task created")

    @app.post("/api/v1/audio", response_model=TaskResponse, tags=["Audio"])
    def create_audio(req: VideoRequest):
        """Create a TTS-only task (stop at audio stage)."""
        req.stop_at = "tts"
        return create_video(req)

    @app.post("/api/v1/subtitle", response_model=TaskResponse, tags=["Subtitle"])
    def create_subtitle(req: VideoRequest):
        """Create a subtitle-only task."""
        req.stop_at = "subtitle"
        return create_video(req)

    @app.post("/api/v1/batch", response_model=TaskResponse, tags=["Batch"])
    def create_batch(req: BatchRequest):
        """Create a batch video generation task."""
        from bookai.task_manager import TaskParams, get_task_manager

        if not req.text and not req.audio_path:
            raise HTTPException(status_code=400, detail="Provide text or audio_path")

        params = TaskParams(
            task_type="batch",
            text=req.text,
            audio_path=req.audio_path,
            output_dir=req.output_dir,
            aspect=req.aspect,
            transition=req.transition,
            bgm_mode=req.bgm_mode,
            subtitle_enabled=req.subtitle_enabled,
            tts_provider=req.tts_provider,
            tts_voice=req.tts_voice,
            video_count=req.video_count,
            stock_search_terms=req.stock_search_terms,
        )

        manager = get_task_manager()
        task_id = manager.submit(params)
        return TaskResponse(task_id=task_id, message=f"Batch task created ({req.video_count} variants)")

    # -----------------------------------------------------------------------
    # Task management endpoints
    # -----------------------------------------------------------------------

    @app.get("/api/v1/tasks", response_model=TaskListResponse, tags=["Tasks"])
    def list_tasks(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        """List all tasks with pagination."""
        from bookai.task_manager import get_task_manager

        manager = get_task_manager()
        tasks, total = manager.list_tasks(page=page, page_size=page_size)
        return TaskListResponse(
            tasks=[_task_info_to_response(t) for t in tasks],
            total=total,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse, tags=["Tasks"])
    def get_task(task_id: str):
        """Get task status by ID."""
        from bookai.task_manager import get_task_manager

        manager = get_task_manager()
        info = manager.get_status(task_id)
        if info is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_info_to_response(info)

    @app.delete("/api/v1/tasks/{task_id}", tags=["Tasks"])
    def delete_task(task_id: str, cancel: bool = Query(True)):
        """Cancel and/or delete a task."""
        from bookai.task_manager import get_task_manager

        manager = get_task_manager()
        if cancel:
            manager.cancel(task_id)
        deleted = manager.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": f"Task {task_id} deleted", "task_id": task_id}

    # -----------------------------------------------------------------------
    # BGM endpoints
    # -----------------------------------------------------------------------

    @app.get("/api/v1/bgm", response_model=list[BgmItem], tags=["BGM"])
    def list_bgm():
        """List available BGM tracks."""
        from bookai.bgm import list_bgm as _list_bgm

        tracks = _list_bgm()
        return [BgmItem(
            name=t["name"],
            size_mb=t.get("size_mb", 0),
            path=t.get("path", ""),
        ) for t in tracks]

    @app.post("/api/v1/bgm/upload", tags=["BGM"])
    async def upload_bgm(file: UploadFile = File(...)):
        """Upload a new BGM track."""
        from bookai.bgm import get_songs_dir

        if not file.filename or not file.filename.endswith((".mp3", ".wav", ".ogg", ".m4a")):
            raise HTTPException(status_code=400, detail="Only audio files allowed")

        songs_dir = get_songs_dir()
        dest = songs_dir / file.filename
        content = await file.read()
        dest.write_bytes(content)
        return {"message": f"Uploaded {file.filename}", "path": str(dest)}

    # -----------------------------------------------------------------------
    # Voice listing endpoint
    # -----------------------------------------------------------------------

    @app.get("/api/v1/voices", response_model=list[VoiceItem], tags=["TTS"])
    def list_voices(include_multilingual: bool = Query(False)):
        """List available TTS voices."""
        from bookai.tts_providers import list_all_voices

        voices = list_all_voices(include_multilingual=include_multilingual)
        return [VoiceItem(
            name=name,
            provider=info["provider"],
            gender=info["gender"],
            description=info["desc"],
        ) for name, info in voices.items()]

    # -----------------------------------------------------------------------
    # File download / stream
    # -----------------------------------------------------------------------

    @app.get("/api/v1/download/{file_path:path}", tags=["Files"])
    async def download_file(file_path: str):
        """Download an output file."""
        target = _resolve_safe_path("output", file_path)
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(
            path=str(target),
            media_type=media_type,
            filename=target.name,
        )

    @app.get("/api/v1/stream/{file_path:path}", tags=["Files"])
    async def stream_file(file_path: str, request: Request):
        """Stream a video file with range support."""
        target = _resolve_safe_path("output", file_path)
        file_size = target.stat().st_size
        media_type = mimetypes.guess_type(str(target))[0] or "video/mp4"

        # Handle range requests
        range_header = request.headers.get("range")
        if range_header:
            range_str = range_header.replace("bytes=", "")
            start_str, end_str = range_str.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
            content_length = end - start + 1

            def iter_range():
                with open(target, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(65536, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            return StreamingResponse(
                iter_range(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                },
            )

        return FileResponse(path=str(target), media_type=media_type)

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
    def health_check():
        """API health check."""
        from bookai.video_render import check_ffmpeg, check_moviepy

        try:
            from bookai.task_manager import get_task_manager
            manager = get_task_manager()
            active = manager.get_active_count()
            queued = manager.get_queue_count()
        except Exception:
            active = 0
            queued = 0

        return HealthResponse(
            status="ok",
            version="0.2.0",
            moviepy_available=check_moviepy(),
            ffmpeg_available=check_ffmpeg(),
            active_tasks=active,
            queued_tasks=queued,
        )

    # -----------------------------------------------------------------------
    # Startup / shutdown
    # -----------------------------------------------------------------------

    @app.on_event("startup")
    async def startup():
        """Initialize task manager on startup."""
        from bookai.task_manager import get_task_manager
        get_task_manager()

    @app.on_event("shutdown")
    async def shutdown():
        """Shut down task manager gracefully."""
        try:
            from bookai.task_manager import get_task_manager
            get_task_manager().shutdown(wait=False)
        except Exception:
            pass

else:
    # Fallback when FastAPI is not installed
    app = None

    def create_app():
        raise ImportError(
            "FastAPI not installed. Run: pip install 'fastapi[standard]' uvicorn"
        )
