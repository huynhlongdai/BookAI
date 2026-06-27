"""CLI interface for BookAI."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .analyzer import analyze_chunks, analyze_chunks_batch
from .chunker import chunk_markdown
from .content_studio import (
    generate_all,
    generate_all_with_ai,
    generate_quote_images,
)
from .converter import convert_audio, convert_file, convert_image, convert_images_dir
from .models import BookResult, ChunkLabel

app = typer.Typer(
    name="bookai",
    help="Convert books to affiliate marketing content using AI.",
)
console = Console()


@app.command()
def process(
    file_path: str = typer.Argument(
        help="Path to book file (.epub, .pdf, .txt, .md, .png, .jpg, .mp3, .wav, ...)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output JSON file path"),
    max_chunks: int = typer.Option(100, "--max-chunks", help="Max chunks to analyze"),
    max_tokens: int = typer.Option(500, "--max-tokens", help="Max tokens per chunk"),
    provider: str = typer.Option(
        "mock", "--provider", help="AI provider: openai, anthropic, custom, mock"
    ),
    model: str = typer.Option("gpt-4o-mini", "--model", help="Model name for AI provider"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key (or use env var)"),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Custom API base URL (OpenAI-compatible)"
    ),
    top_n: int = typer.Option(10, "--top", help="Show top N results"),
    batch: bool = typer.Option(False, "--batch", help="Use batch analysis (faster, less accurate)"),
) -> None:
    """Process a book file: convert → chunk → analyze.

    Examples:
        bookai process book.epub
        bookai process book.pdf --provider openai --top 20
        bookai process book.epub -o results.json --provider mock
    """
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    # Step 1: Convert
    console.print(f"\n[bold blue]📖 Converting:[/bold blue] {path.name}")
    try:
        metadata, markdown = convert_file(file_path)
    except Exception as e:
        console.print(f"[red]Error converting file: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"  Title: [green]{metadata.title}[/green]")
    console.print(f"  Author: {metadata.author}")
    console.print(f"  Chapters: {metadata.chapters}")
    console.print(f"  Format: {metadata.source_format.value}")

    # Step 2: Chunk
    console.print(f"\n[bold blue]✂️  Chunking:[/bold blue] max {max_tokens} tokens/chunk")
    chunks = chunk_markdown(markdown, book_title=metadata.title, max_tokens=max_tokens)
    console.print(f"  Total chunks: [green]{len(chunks)}[/green]")

    # Step 3: Analyze
    chunks_to_analyze = chunks[:max_chunks]
    console.print(
        f"\n[bold blue]🤖 Analyzing:[/bold blue] {len(chunks_to_analyze)} chunks "
        f"(provider: {provider})"
    )

    try:
        if batch and provider != "mock":
            analyzed = analyze_chunks_batch(
                chunks_to_analyze,
                api_key=api_key,
                model=model,
                provider=provider,
                base_url=base_url,
            )
        else:
            analyzed = analyze_chunks(
                chunks_to_analyze,
                api_key=api_key,
                model=model,
                provider=provider,
                base_url=base_url,
            )
    except Exception as e:
        console.print(f"[red]Error during analysis: {e}[/red]")
        raise typer.Exit(1)

    # Build result
    result = BookResult(
        metadata=metadata,
        markdown=markdown[:1000] + "..." if len(markdown) > 1000 else markdown,
        chunks=chunks,
        analyzed=analyzed,
        top_quotes=[a for a in analyzed if ChunkLabel.QUOTE in a.labels],
        top_hooks=[a for a in analyzed if ChunkLabel.HOOK in a.labels],
    )

    # Display results
    _display_results(result, top_n=top_n)

    # Save output
    if output:
        output_path = Path(output)
        output_data = result.model_dump()
        output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
        console.print(f"\n[green]Results saved to: {output_path}[/green]")


@app.command()
def convert(
    file_path: str = typer.Argument(help="Path to book file"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output markdown file"),
) -> None:
    """Convert a book file to Markdown (without analysis)."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    metadata, markdown = convert_file(file_path)

    console.print(f"Title: [green]{metadata.title}[/green]")
    console.print(f"Author: {metadata.author}")
    console.print(f"Chapters: {metadata.chapters}")
    console.print(f"Markdown length: {len(markdown)} chars")

    if output:
        Path(output).write_text(markdown, encoding="utf-8")
        console.print(f"\n[green]Saved to: {output}[/green]")
    else:
        console.print("\n" + markdown[:2000])
        if len(markdown) > 2000:
            console.print(f"\n[dim]... ({len(markdown) - 2000} more characters)[/dim]")


@app.command()
def chunks(
    file_path: str = typer.Argument(help="Path to book file"),
    max_tokens: int = typer.Option(500, "--max-tokens", help="Max tokens per chunk"),
    show: int = typer.Option(10, "--show", help="Number of chunks to display"),
) -> None:
    """Convert and chunk a book (without analysis)."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    metadata, markdown = convert_file(file_path)
    chunk_list = chunk_markdown(markdown, book_title=metadata.title, max_tokens=max_tokens)

    console.print(f"Book: [green]{metadata.title}[/green]")
    console.print(f"Total chunks: [green]{len(chunk_list)}[/green]\n")

    table = Table(title=f"First {show} chunks")
    table.add_column("#", width=4)
    table.add_column("Chapter", width=20)
    table.add_column("Tokens", width=8)
    table.add_column("Preview", max_width=60)

    for i, chunk in enumerate(chunk_list[:show], 1):
        preview = chunk.text[:80].replace("\n", " ")
        table.add_row(
            str(i),
            chunk.chapter_title[:20],
            str(chunk.token_count),
            preview + "..." if len(chunk.text) > 80 else preview,
        )

    console.print(table)


@app.command()
def generate(
    input_json: str = typer.Argument(help="Path to analysis result JSON (from `process -o`)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output JSON file path"),
    format: str = typer.Option(
        "all", "--format", help="Content type: all, radio, quote, listicle, caption"
    ),
) -> None:
    """Generate ready-to-post content from analysis results.

    Takes the JSON output of `bookai process -o results.json` and generates
    radio scripts, quote cards, listicles, and captions.

    Examples:
        bookai generate results.json -o content.json
        bookai generate results.json --format radio
    """
    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    result = BookResult(**data)

    if not result.analyzed:
        console.print("[red]No analyzed chunks found in input. Run `process` first.[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]🎬 Generating content:[/bold blue] "
        f"{result.metadata.title} ({len(result.analyzed)} chunks)"
    )

    pack = generate_all(result.analyzed, result.metadata)

    # Display summary
    console.print(f"\n[bold green]Total content pieces: {pack.total_pieces}[/bold green]\n")

    # Radio scripts
    if pack.radio_scripts and format in ("all", "radio"):
        console.print(f"[bold]🎙️ Radio Scripts ({len(pack.radio_scripts)}):[/bold]\n")
        for i, script in enumerate(pack.radio_scripts, 1):
            console.print(Panel(
                f"[bold cyan]HOOK:[/bold cyan] {script.hook}\n\n"
                f"[bold]BODY:[/bold] {script.body[:300]}"
                f"{'...' if len(script.body) > 300 else ''}\n\n"
                f"[bold yellow]CTA:[/bold yellow] {script.cta}\n\n"
                f"[dim]~{script.estimated_seconds}s | "
                f"{'  '.join('#' + t for t in script.hashtags)}[/dim]",
                title=f"Script #{i}",
                border_style="cyan",
            ))

    # Quote cards
    if pack.quote_cards and format in ("all", "quote"):
        console.print(f"\n[bold]📸 Quote Cards ({len(pack.quote_cards)}):[/bold]\n")
        table = Table()
        table.add_column("#", width=3)
        table.add_column("Quote", max_width=60)
        table.add_column("Caption preview", max_width=40)
        for i, card in enumerate(pack.quote_cards[:10], 1):
            table.add_row(
                str(i),
                card.quote_text[:80] + "..." if len(card.quote_text) > 80 else card.quote_text,
                card.caption[:50] + "...",
            )
        console.print(table)

    # Listicles
    if pack.listicles and format in ("all", "listicle"):
        console.print(f"\n[bold]📋 Listicles ({len(pack.listicles)}):[/bold]\n")
        for ls in pack.listicles:
            console.print(Panel(
                f"[bold]{ls.intro}[/bold]\n\n"
                + "\n".join(ls.items)
                + f"\n\n[yellow]{ls.cta}[/yellow]",
                title=ls.title,
                border_style="green",
            ))

    # Captions
    if pack.captions and format in ("all", "caption"):
        console.print(f"\n[bold]💬 Captions ({len(pack.captions)}):[/bold]\n")
        for i, cap in enumerate(pack.captions[:5], 1):
            console.print(Panel(
                cap.text,
                title=f"Caption #{i} ({cap.platform})",
                border_style="magenta",
            ))

    # Save output
    if output:
        output_path = Path(output)
        output_path.write_text(
            json.dumps(pack.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"\n[green]Content saved to: {output_path}[/green]")


@app.command("generate-ai")
def generate_ai(
    input_json: str = typer.Argument(help="Path to analysis result JSON (from `process -o`)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output JSON file path"),
    images_dir: str | None = typer.Option(
        None, "--images", help="Directory to save quote card images"
    ),
    image_theme: str = typer.Option(
        "dark", "--theme", help="Image theme: dark, light, gradient_blue, warm"
    ),
    model: str = typer.Option("gpt-4o-mini", "--model", help="Model for AI rewriting"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Custom API base URL (OpenAI-compatible)"
    ),
    format: str = typer.Option(
        "all", "--format", help="Content type: all, radio, quote, listicle, caption"
    ),
    duration: int = typer.Option(
        3, "--duration", help="Target video duration in minutes (1-5)"
    ),
    storyboard: bool = typer.Option(
        False, "--storyboard", help="Generate scene prompts for AI video"
    ),
) -> None:
    """Generate premium content using AI rewriting + quote card images.

    Unlike `generate` (template-based), this command uses an LLM to
    rewrite and EXPAND book content into natural radio scripts (1-5 min).
    Also renders PNG quote card images ready for Instagram/Pinterest.

    Use --storyboard to generate visual scene prompts for each script,
    ready for AI video tools (Runway, Pika, Kling, Midjourney).

    Examples:
        bookai generate-ai results.json --base-url ... --duration 3
        bookai generate-ai results.json --storyboard --duration 3
        bookai generate-ai results.json -o content.json --images ./cards
    """
    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    result = BookResult(**data)

    if not result.analyzed:
        console.print("[red]No analyzed chunks found in input. Run `process` first.[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]🎬 AI Content Generation:[/bold blue] "
        f"{result.metadata.title} ({len(result.analyzed)} chunks)"
    )

    # Generate with AI rewriting
    pack = generate_all_with_ai(
        result.analyzed,
        result.metadata,
        api_key=api_key,
        model=model,
        base_url=base_url,
        output_dir=images_dir,
        image_theme=image_theme,
        duration_minutes=duration,
    )

    # Display summary
    console.print(f"\n[bold green]Total content pieces: {pack.total_pieces}[/bold green]\n")

    # Radio scripts
    if pack.radio_scripts and format in ("all", "radio"):
        console.print(f"[bold]🎙️ AI Radio Scripts ({len(pack.radio_scripts)}):[/bold]\n")
        for i, script in enumerate(pack.radio_scripts, 1):
            console.print(Panel(
                f"[bold cyan]HOOK:[/bold cyan] {script.hook}\n\n"
                f"[bold]BODY:[/bold] {script.body[:400]}"
                f"{'...' if len(script.body) > 400 else ''}\n\n"
                f"[bold yellow]CTA:[/bold yellow] {script.cta}\n\n"
                f"[dim]~{script.estimated_seconds}s | "
                f"{'  '.join('#' + t for t in script.hashtags)}[/dim]",
                title=f"Script #{i}: {script.title}",
                border_style="cyan",
            ))

    # Storyboard generation (optional)
    storyboards_data: list[dict] = []
    if storyboard and pack.radio_scripts:
        from .content_studio import generate_storyboards_batch
        console.print(
            f"\n[bold]🎬 Generating storyboards for "
            f"{len(pack.radio_scripts)} scripts...[/bold]\n"
        )
        sbs = generate_storyboards_batch(
            pack.radio_scripts,
            result.metadata,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
        for i, sb in enumerate(sbs, 1):
            scene_lines = []
            for s in sb.scenes:
                narr_short = s.narration[:80]
                scene_lines.append(
                    f"[cyan]Scene {s.scene_number}[/cyan] "
                    f"({s.duration_seconds}s)\n"
                    f"  [dim]Narration:[/dim] {narr_short}...\n"
                    f"  [green]Visual:[/green] {s.visual_prompt}\n"
                    f"  [dim]Camera: {s.camera_note}[/dim]"
                )
            console.print(Panel(
                "\n\n".join(scene_lines),
                title=(
                    f"Storyboard #{i}: {sb.script_title} "
                    f"({sb.total_scenes} scenes)"
                ),
                border_style="yellow",
            ))
            storyboards_data.append(sb.model_dump())

    # Quote cards
    if pack.quote_cards and format in ("all", "quote"):
        console.print(f"\n[bold]📸 Quote Cards ({len(pack.quote_cards)}):[/bold]\n")
        table = Table()
        table.add_column("#", width=3)
        table.add_column("Quote", max_width=60)
        table.add_column("Caption preview", max_width=40)
        for i, card in enumerate(pack.quote_cards[:10], 1):
            table.add_row(
                str(i),
                card.quote_text[:80] + ("..." if len(card.quote_text) > 80 else ""),
                card.caption[:50] + "...",
            )
        console.print(table)

    # Images generated?
    if images_dir:
        img_path = Path(images_dir)
        if img_path.exists():
            png_count = len(list(img_path.glob("*.png")))
            console.print(
                f"\n[bold green]🖼️ Generated {png_count} quote card images "
                f"in: {images_dir}[/bold green]"
            )

    # Listicles
    if pack.listicles and format in ("all", "listicle"):
        console.print(f"\n[bold]📋 Listicles ({len(pack.listicles)}):[/bold]\n")
        for ls in pack.listicles:
            console.print(Panel(
                f"[bold]{ls.intro}[/bold]\n\n"
                + "\n".join(ls.items)
                + f"\n\n[yellow]{ls.cta}[/yellow]",
                title=ls.title,
                border_style="green",
            ))

    # Captions
    if pack.captions and format in ("all", "caption"):
        console.print(f"\n[bold]💬 AI Captions ({len(pack.captions)}):[/bold]\n")
        for i, cap in enumerate(pack.captions[:5], 1):
            console.print(Panel(
                cap.text,
                title=f"Caption #{i} ({cap.platform})",
                border_style="magenta",
            ))

    # Save output (include storyboards if generated)
    if output:
        output_path = Path(output)
        out_data = pack.model_dump()
        if storyboards_data:
            out_data["storyboards"] = storyboards_data
        output_path.write_text(
            json.dumps(out_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"\n[green]Content saved to: {output_path}[/green]")


@app.command("render-quotes")
def render_quotes(
    input_json: str = typer.Argument(help="Path to analysis result JSON"),
    output_dir: str = typer.Option("./quote_cards", "-o", "--output", help="Output directory"),
    theme: str = typer.Option("dark", "--theme", help="Theme: dark, light, gradient_blue, warm"),
    max_cards: int = typer.Option(10, "--max", help="Maximum number of cards"),
    min_score: float = typer.Option(5.0, "--min-score", help="Minimum viral score"),
) -> None:
    """Render quote cards as PNG images.

    Generates beautiful 1080x1080 quote card images ready for
    Instagram, Pinterest, or any visual platform.

    Examples:
        bookai render-quotes results.json -o ./cards --theme warm
        bookai render-quotes results.json --max 20 --theme gradient_blue
    """
    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    result = BookResult(**data)

    if not result.analyzed:
        console.print("[red]No analyzed chunks found. Run `process` first.[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]🖼️ Rendering quote cards:[/bold blue] "
        f"{result.metadata.title} (theme: {theme})"
    )

    paths = generate_quote_images(
        result.analyzed,
        result.metadata,
        output_dir=output_dir,
        max_cards=max_cards,
        min_score=min_score,
        theme=theme,
    )

    console.print(f"\n[bold green]Generated {len(paths)} quote card images:[/bold green]")
    for p in paths:
        console.print(f"  {p}")


def _display_results(result: BookResult, top_n: int = 10) -> None:
    """Display analysis results in a formatted table."""
    console.print(f"\n[bold]{'=' * 60}[/bold]")
    console.print(f"[bold green]📊 Analysis Results: {result.metadata.title}[/bold green]")
    console.print(f"[bold]{'=' * 60}[/bold]\n")

    # Stats
    total = len(result.analyzed)
    avg_score = sum(a.viral_score for a in result.analyzed) / total if total else 0
    console.print(f"  Total analyzed: {total}")
    console.print(f"  Average viral score: {avg_score:.1f}/10")
    console.print(f"  Quotes found: {len(result.top_quotes)}")
    console.print(f"  Hooks found: {len(result.top_hooks)}")

    # Label distribution
    label_counts: dict[str, int] = {}
    for a in result.analyzed:
        for label in a.labels:
            label_counts[label.value] = label_counts.get(label.value, 0) + 1

    if label_counts:
        console.print("\n  [bold]Label distribution:[/bold]")
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            bar = "█" * (count * 2)
            console.print(f"    {label:14s} {bar} ({count})")

    # Top content by viral score
    top = result.get_top_content(top_n)
    if top:
        console.print(f"\n[bold]🔥 Top {top_n} by Viral Score:[/bold]\n")
        table = Table()
        table.add_column("#", width=3)
        table.add_column("Score", width=6)
        table.add_column("Labels", width=24)
        table.add_column("Content Preview", max_width=50)

        for i, item in enumerate(top, 1):
            labels_str = ", ".join(lbl.value for lbl in item.labels)
            preview = item.chunk.text[:60].replace("\n", " ")
            score_color = (
                "green" if item.viral_score >= 7
                else "yellow" if item.viral_score >= 5
                else "white"
            )
            table.add_row(
                str(i),
                f"[{score_color}]{item.viral_score:.1f}[/{score_color}]",
                labels_str,
                preview + "...",
            )

        console.print(table)

    # Top quotes
    if result.top_quotes:
        console.print("\n[bold]💬 Best Quotes:[/bold]\n")
        for i, q in enumerate(sorted(result.top_quotes, key=lambda x: -x.viral_score)[:5], 1):
            console.print(
                Panel(
                    q.chunk.text[:200],
                    title=f"Quote #{i} (score: {q.viral_score})",
                    border_style="cyan",
                )
            )


@app.command("ocr")
def ocr_command(
    file_path: str = typer.Argument(help="Path to image file or directory of images"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output markdown file"),
    lang: str = typer.Option("vie+eng", "--lang", help="OCR language (tesseract code)"),
) -> None:
    """Extract text from images or scanned documents using OCR.

    Supports single image files (.png, .jpg, .tiff, .bmp) or
    a directory of images (processed in sorted order as book pages).

    Examples:
        bookai ocr page.png -o output.md
        bookai ocr ./book_pages/ -o book.md
        bookai ocr scan.jpg --lang vie+eng
    """
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error: Path not found: {file_path}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]🔍 OCR Processing:[/bold blue] {path.name}")

    try:
        if path.is_dir():
            metadata, markdown = convert_images_dir(file_path, lang=lang)
        else:
            metadata, markdown = convert_image(file_path, lang=lang)
    except Exception as e:
        console.print(f"[red]Error during OCR: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"  Title: [green]{metadata.title}[/green]")
    console.print(f"  Pages/images: {metadata.chapters}")
    console.print(f"  Text length: {len(markdown)} chars")

    if output:
        Path(output).write_text(markdown, encoding="utf-8")
        console.print(f"\n[green]Saved to: {output}[/green]")
    else:
        console.print("\n" + markdown[:2000])
        if len(markdown) > 2000:
            console.print(f"\n[dim]... ({len(markdown) - 2000} more characters)[/dim]")


@app.command("transcribe")
def transcribe_command(
    file_path: str = typer.Argument(help="Path to audio file (.mp3, .wav, .m4a, .flac, ...)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output markdown file"),
    model_size: str = typer.Option(
        "base", "--model-size", help="Whisper model: tiny, base, small, medium, large"
    ),
    language: str = typer.Option("vi", "--language", help="Language code (vi, en, etc.)"),
    timestamps: bool = typer.Option(
        False, "--timestamps", help="Include timestamp JSON in output"
    ),
) -> None:
    """Transcribe audio/audiobook to Markdown using Whisper.

    Converts audio files to text with timestamps, suitable for
    further processing with `process` or direct use.

    Examples:
        bookai transcribe audiobook.mp3 -o transcript.md
        bookai transcribe chapter1.m4a --model-size small --language vi
        bookai transcribe podcast.wav --timestamps -o output.md
    """
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(1)

    from .audio import is_supported_audio

    if not is_supported_audio(file_path):
        console.print(
            f"[red]Error: Unsupported audio format: {path.suffix}[/red]\n"
            "Supported: .mp3, .wav, .m4a, .flac, .ogg, .wma, .aac, .opus"
        )
        raise typer.Exit(1)

    console.print(f"\n[bold blue]🎙️ Transcribing:[/bold blue] {path.name}")
    console.print(f"  Model: whisper-{model_size}, Language: {language}")

    try:
        if timestamps:
            from .audio import transcribe_audio_with_timestamps

            metadata, markdown, ts_data = transcribe_audio_with_timestamps(
                file_path, model_size=model_size, language=language
            )
            console.print(f"  Segments: {len(ts_data)}")
        else:
            metadata, markdown = convert_audio(file_path, model_size=model_size, language=language)
    except Exception as e:
        console.print(f"[red]Error during transcription: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"  Title: [green]{metadata.title}[/green]")
    console.print(f"  Chapters detected: {metadata.chapters}")
    console.print(f"  Text length: {len(markdown)} chars")

    if output:
        out_path = Path(output)
        out_path.write_text(markdown, encoding="utf-8")
        console.print(f"\n[green]Transcript saved to: {out_path}[/green]")

        # Save timestamps JSON alongside if requested
        if timestamps:
            ts_path = out_path.with_suffix(".timestamps.json")
            ts_path.write_text(
                json.dumps(ts_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            console.print(f"[green]Timestamps saved to: {ts_path}[/green]")
    else:
        console.print("\n" + markdown[:2000])
        if len(markdown) > 2000:
            console.print(f"\n[dim]... ({len(markdown) - 2000} more characters)[/dim]")


# ---------------------------------------------------------------------------
# New MVP-4 commands
# ---------------------------------------------------------------------------


@app.command("affiliate")
def affiliate_command(
    action: str = typer.Argument(help="Action: list, add, remove"),
    config_file: str = typer.Option(
        "affiliate_links.json", "-c", "--config", help="Path to affiliate config JSON"
    ),
    title: str = typer.Option("", "--title", help="Book title (for add/remove)"),
    shopee: str = typer.Option("", "--shopee", help="Shopee affiliate URL"),
    tiktok: str = typer.Option("", "--tiktok", help="TikTok Shop affiliate URL"),
    tiki: str = typer.Option("", "--tiki", help="Tiki affiliate URL"),
    isbn: str = typer.Option("", "--isbn", help="Book ISBN"),
) -> None:
    """Manage affiliate links for books.

    Examples:
        bookai affiliate list
        bookai affiliate add --title "Đắc Nhân Tâm" --shopee https://shope.ee/xxx --tiktok https://vt.tiktok.com/xxx
        bookai affiliate remove --title "Đắc Nhân Tâm"
    """
    from .affiliate import AffiliateManager, BookLinks

    mgr = AffiliateManager.from_file(config_file)

    if action == "list":
        books = mgr.list_books()
        if not books:
            console.print("[yellow]No affiliate links configured.[/yellow]")
            return
        table = Table(title=f"Affiliate Links ({config_file})")
        table.add_column("Title", max_width=40)
        table.add_column("ISBN", width=14)
        table.add_column("Platforms", width=30)
        for b in books:
            table.add_row(b["title"], b["isbn"], ", ".join(b["platforms"]) or "—")
        console.print(table)

    elif action == "add":
        if not title:
            console.print("[red]--title required for add[/red]")
            raise typer.Exit(1)
        book = BookLinks(book_title=title, isbn=isbn, shopee=shopee, tiktok=tiktok, tiki=tiki)
        mgr.add_book(book)
        mgr.save(config_file)
        platforms = [p for p in ("shopee", "tiktok", "tiki") if getattr(book, p)]
        console.print(f"[green]Added: {title} ({', '.join(platforms) or 'no links yet'})[/green]")
        console.print(f"Saved to: {config_file}")

    elif action == "remove":
        if not title:
            console.print("[red]--title required for remove[/red]")
            raise typer.Exit(1)
        if mgr.remove_book(title):
            mgr.save(config_file)
            console.print(f"[green]Removed: {title}[/green]")
        else:
            console.print(f"[yellow]Not found: {title}[/yellow]")

    else:
        console.print(f"[red]Unknown action: {action}. Use: list, add, remove[/red]")
        raise typer.Exit(1)


@app.command("tts")
def tts_command(
    input_json: str = typer.Argument(help="Path to content JSON (from generate/generate-ai)"),
    output_dir: str = typer.Option("./audio", "-o", "--output", help="Output directory for MP3s"),
    voice: str = typer.Option(
        "vi-VN-HoaiMyNeural", "--voice",
        help="TTS voice: vi-VN-HoaiMyNeural (female) or vi-VN-NamMinhNeural (male)"
    ),
    rate: str = typer.Option("+0%", "--rate", help="Speaking rate: +10%, -5%, etc."),
    max_scripts: int = typer.Option(5, "--max", help="Max scripts to synthesize"),
) -> None:
    """Convert radio scripts to Vietnamese voiceover MP3s using Edge TTS.

    Reads content JSON and synthesizes each radio script to audio.
    Free, no API key required.

    Examples:
        bookai tts content.json -o ./audio
        bookai tts content.json --voice vi-VN-NamMinhNeural --rate +10%
    """
    from .tts import synthesize_script

    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    scripts_data = data.get("radio_scripts", [])
    if not scripts_data:
        console.print("[red]No radio_scripts found in input JSON.[/red]")
        raise typer.Exit(1)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"\n[bold blue]🔊 TTS Synthesis:[/bold blue] "
        f"{len(scripts_data[:max_scripts])} scripts → {output_dir}"
    )
    console.print(f"  Voice: {voice}")
    console.print(f"  Rate:  {rate}\n")

    # Create simple script-like objects from dicts
    class _Script:
        def __init__(self, d: dict) -> None:
            self.hook = d.get("hook", "")
            self.body = d.get("body", "")
            self.cta = d.get("cta", "")
            self.title = d.get("title", "script")

    results = []
    for i, sd in enumerate(scripts_data[:max_scripts]):
        script = _Script(sd)
        slug = script.title[:30].replace(" ", "_").lower() if script.title else f"script_{i:03d}"
        out_path = out_dir / f"{i + 1:02d}_{slug}.mp3"
        console.print(f"  [{i + 1}/{min(len(scripts_data), max_scripts)}] {out_path.name}... ", end="")
        result = synthesize_script(script, out_path, voice=voice, rate=rate)
        if result.ok:
            console.print(f"[green]✓[/green] ({result.duration_seconds:.0f}s)")
        else:
            console.print(f"[red]✗ {result.error}[/red]")
        results.append(result)

    ok = sum(1 for r in results if r.ok)
    console.print(f"\n[bold green]{ok}/{len(results)} audio files generated in {output_dir}[/bold green]")


@app.command("render-video")
def render_video_command(
    input_json: str = typer.Argument(help="Path to content JSON (from generate/generate-ai)"),
    audio_dir: str = typer.Argument(help="Directory containing MP3 voiceovers (from tts command)"),
    output_dir: str = typer.Option("./videos", "-o", "--output", help="Output directory for MP4s"),
    cover: str | None = typer.Option(None, "--cover", help="Book cover image path"),
    resolution: str = typer.Option("1080x1920", "--resolution", help="Video resolution WxH"),
    max_videos: int = typer.Option(5, "--max", help="Max videos to render"),
    no_blur: bool = typer.Option(False, "--no-blur", help="Disable background blur"),
) -> None:
    """Render TikTok/Reels videos from scripts + voiceovers.

    Combines MP3 audio (from `tts` command) + book cover + text overlays
    into 1080×1920 MP4 files ready to upload.

    Examples:
        bookai render-video content.json ./audio -o ./videos --cover cover.jpg
        bookai render-video content.json ./audio --max 3
    """
    from .video_render import VideoConfig, check_ffmpeg, render_radio_video

    if not check_ffmpeg():
        console.print("[red]FFmpeg not found. Install: sudo apt install ffmpeg[/red]")
        raise typer.Exit(1)

    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    audio_path = Path(audio_dir)
    if not audio_path.exists():
        console.print(f"[red]Audio directory not found: {audio_dir}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    scripts_data = data.get("radio_scripts", [])
    audio_files = sorted(audio_path.glob("*.mp3"))

    if not scripts_data:
        console.print("[red]No radio_scripts found in input JSON.[/red]")
        raise typer.Exit(1)
    if not audio_files:
        console.print(f"[red]No MP3 files found in {audio_dir}[/red]")
        raise typer.Exit(1)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = VideoConfig(resolution=resolution, cover_blur=not no_blur)

    class _Script:
        def __init__(self, d: dict) -> None:
            self.hook = d.get("hook", "")
            self.body = d.get("body", "")
            self.cta = d.get("cta", "")
            self.title = d.get("title", "video")

    pairs = list(zip(scripts_data[:max_videos], audio_files[:max_videos]))
    console.print(
        f"\n[bold blue]🎬 Rendering {len(pairs)} videos:[/bold blue] → {output_dir}\n"
    )

    for i, (sd, audio_file) in enumerate(pairs):
        script = _Script(sd)
        out_path = out_dir / f"{i + 1:02d}_video.mp4"
        console.print(f"  [{i + 1}/{len(pairs)}] {out_path.name} + {audio_file.name}... ", end="")
        result = render_radio_video(script, audio_file, out_path, cover_image=cover, config=cfg)
        if result.ok:
            console.print(
                f"[green]✓[/green] ({result.duration_seconds:.0f}s, {result.file_size_mb:.1f}MB)"
            )
        else:
            console.print(f"[red]✗ {result.error[:80]}[/red]")

    console.print(f"\n[bold green]Videos saved to: {output_dir}[/bold green]")


@app.command("calendar")
def calendar_command(
    input_json: str = typer.Argument(help="Path to content JSON (from generate/generate-ai)"),
    output: str = typer.Option("calendar.csv", "-o", "--output", help="Output CSV file"),
    start_date: str = typer.Option("", "--start", help="Start date (YYYY-MM-DD). Default: today"),
    days: int = typer.Option(30, "--days", help="Number of days to schedule"),
    platforms: str = typer.Option(
        "tiktok,instagram", "--platforms",
        help="Comma-separated platforms: tiktok,instagram,youtube,blog"
    ),
    sub_id_prefix: str = typer.Option("", "--sub-id", help="Sub-ID prefix for affiliate tracking"),
    posts_per_day: int = typer.Option(2, "--posts-per-day", help="Max posts per day"),
    json_output: bool = typer.Option(False, "--json", help="Also save JSON alongside CSV"),
) -> None:
    """Generate a 30-day content posting calendar.

    Turns a ContentPack into a structured posting schedule with:
    Week 1: Hook & Tease (quotes) → Week 2: Deep Content (radio) →
    Week 3: Engagement (listicles) → Week 4: Conversion Push (captions)

    Examples:
        bookai calendar content.json -o calendar.csv --start 2025-08-01
        bookai calendar content.json --days 14 --platforms tiktok,instagram,youtube
        bookai calendar content.json --sub-id eckhart_aug --json
    """
    from datetime import date as date_type

    from .calendar import calendar_summary, generate_calendar, save_calendar_csv, save_calendar_json

    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))

    # Re-build a minimal pack-like object from the JSON
    class _Pack:
        def __init__(self, d: dict) -> None:

            self.book_title = d.get("book_title", "")

            def _from_list(cls, items, **kw):
                result = []
                for item in items:
                    try:
                        result.append(cls(**{k: v for k, v in item.items() if k != "type"}))
                    except Exception:
                        pass
                return result

            self.radio_scripts = [
                type("RS", (), {"hook": s.get("hook", ""), "body": s.get("body", ""),
                                "cta": s.get("cta", ""), "title": s.get("title", ""),
                                "hashtags": s.get("hashtags", [])})()
                for s in d.get("radio_scripts", [])
            ]
            self.quote_cards = [
                type("QC", (), {"quote_text": s.get("quote_text", ""),
                                "caption": s.get("caption", ""),
                                "book_title": s.get("book_title", ""),
                                "author": s.get("author", ""),
                                "hashtags": s.get("hashtags", []),
                                "image_path": s.get("image_path", "")})()
                for s in d.get("quote_cards", [])
            ]
            self.listicles = [
                type("LS", (), {"title": s.get("title", ""), "items": s.get("items", []),
                                "intro": s.get("intro", ""), "cta": s.get("cta", ""),
                                "hashtags": s.get("hashtags", [])})()
                for s in d.get("listicles", [])
            ]
            self.captions = [
                type("CA", (), {"text": s.get("text", ""), "hashtags": s.get("hashtags", []),
                                "platform": s.get("platform", "tiktok")})()
                for s in d.get("captions", [])
            ]

    pack = _Pack(data)
    total_content = (
        len(pack.radio_scripts) + len(pack.quote_cards)
        + len(pack.listicles) + len(pack.captions)
    )

    if total_content == 0:
        console.print("[red]No content found in input JSON. Run `generate` first.[/red]")
        raise typer.Exit(1)

    start = start_date if start_date else date_type.today().isoformat()
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    console.print(
        f"\n[bold blue]📅 Generating {days}-day calendar:[/bold blue] "
        f"{pack.book_title or 'Unknown book'}"
    )
    console.print(f"  Start: {start} | Platforms: {', '.join(platform_list)}")
    console.print(
        f"  Content pool: {len(pack.radio_scripts)} radio, {len(pack.quote_cards)} quotes, "
        f"{len(pack.listicles)} listicles, {len(pack.captions)} captions"
    )

    entries = generate_calendar(
        pack,
        start_date=start,
        days=days,
        platforms=platform_list,
        sub_id_prefix=sub_id_prefix,
        posts_per_day=posts_per_day,
    )

    # Save CSV
    csv_path = save_calendar_csv(entries, output)
    console.print(f"\n[green]Calendar saved: {csv_path}[/green]")

    # Optionally save JSON
    if json_output:
        json_path = Path(output).with_suffix(".json")
        save_calendar_json(entries, json_path)
        console.print(f"[green]JSON saved: {json_path}[/green]")

    # Summary table
    summary = calendar_summary(entries)
    console.print("\n[bold green]📊 Calendar Summary:[/bold green]")
    console.print(f"  Total posts: {summary['total']}")
    console.print(f"  Date range: {summary.get('date_range', '—')}")

    if summary.get("by_platform"):
        console.print("\n  [bold]By platform:[/bold]")
        for p, n in summary["by_platform"].items():
            console.print(f"    {p:12s} {n} posts")

    if summary.get("by_week"):
        console.print("\n  [bold]By week:[/bold]")
        week_themes = {
            "week_1": "Hook & Tease",
            "week_2": "Deep Content",
            "week_3": "Engagement",
            "week_4": "Conversion Push",
        }
        for w, n in summary["by_week"].items():
            theme = week_themes.get(w, "")
            console.print(f"    {w}: {n} posts  [{theme}]")


@app.command("blog")
def blog_command(
    input_json: str = typer.Argument(help="Path to analysis result JSON (from `process -o`)"),
    output: str = typer.Option("review.html", "-o", "--output", help="Output file (.html or .md)"),
    affiliate_link: str = typer.Option("", "--affiliate", help="Primary affiliate URL"),
    shopee_link: str = typer.Option("", "--shopee", help="Shopee affiliate URL"),
    tiki_link: str = typer.Option("", "--tiki", help="Tiki affiliate URL"),
    use_ai: bool = typer.Option(False, "--ai", help="Use LLM to write (needs API key)"),
    model: str = typer.Option("gpt-4o-mini", "--model", help="Model for AI writing"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    base_url: str | None = typer.Option(None, "--base-url", help="Custom API base URL"),
) -> None:
    """Generate an SEO-optimized blog review post from analysis results.

    Creates a 1500-2000 word Vietnamese blog article with:
    H1/H2 structure, affiliate links, quote sections, schema markup.

    Examples:
        bookai blog results.json -o review.html --affiliate https://shope.ee/xxx
        bookai blog results.json --ai --base-url ... --model ... -o review.html
        bookai blog results.json -o review.md  (Markdown output)
    """
    from .blog import generate_blog_post

    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    result = BookResult(**data)

    if not result.analyzed:
        console.print("[red]No analyzed chunks. Run `process` first.[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]✍️ Generating blog post:[/bold blue] {result.metadata.title} "
        f"({'AI' if use_ai else 'template'})"
    )

    post = generate_blog_post(
        result,
        affiliate_link=affiliate_link,
        shopee_link=shopee_link,
        tiki_link=tiki_link,
        api_key=api_key,
        base_url=base_url,
        model=model,
        use_ai=use_ai,
    )

    out_path = Path(output)
    fmt = "md" if out_path.suffix == ".md" else "html"
    post.save(out_path, fmt=fmt)

    console.print(f"\n[bold green]✅ Blog post saved: {out_path}[/bold green]")
    console.print(f"  Title: {post.title}")
    console.print(f"  Words: ~{post.word_count}")
    console.print(f"  Sections: {', '.join(post.sections)}")
    console.print(f"  Meta: {post.meta_description[:80]}...")


@app.command("split-series")
def split_series_command(
    input_json: str = typer.Argument(help="Path to content JSON (from generate/generate-ai)"),
    output: str = typer.Option("series.json", "-o", "--output", help="Output JSON file"),
    parts: int = typer.Option(5, "--parts", help="Number of parts per script (3-7)"),
    target_seconds: int = typer.Option(75, "--seconds", help="Target seconds per video"),
) -> None:
    """Split long radio scripts into a cliffhanger series (5-7 short videos).

    Each video ends with a cliffhanger to drive follow + watch time.
    Uses the 'Phần tiếp theo còn hay hơn...' formula popularized by @sachhayexpress.

    Examples:
        bookai split-series content.json -o series.json --parts 5
        bookai split-series content.json --parts 7 --seconds 60
    """
    from .content_studio import split_pack_to_series

    path = Path(input_json)
    if not path.exists():
        console.print(f"[red]Error: File not found: {input_json}[/red]")
        raise typer.Exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))

    # Build minimal pack
    class _Pack:
        def __init__(self, d: dict) -> None:
            from .content_studio import RadioScript
            self.book_title = d.get("book_title", "")
            self.radio_scripts = []
            for s in d.get("radio_scripts", []):
                try:
                    self.radio_scripts.append(RadioScript(**{
                        k: v for k, v in s.items()
                        if k in ("title", "hook", "body", "cta", "hashtags",
                                 "estimated_seconds", "source_chunks")
                    }))
                except Exception:
                    pass

    pack = _Pack(data)
    if not pack.radio_scripts:
        console.print("[red]No radio_scripts found. Run `generate` first.[/red]")
        raise typer.Exit(1)

    all_videos = split_pack_to_series(pack, parts=parts, target_seconds=target_seconds)

    console.print(
        f"\n[bold blue]✂️ Split {len(pack.radio_scripts)} scripts → "
        f"{len(all_videos)} videos ({parts} parts each)[/bold blue]\n"
    )

    for v in all_videos:
        console.print(
            f"  [{v.series_title[:30]}] Part {v.part_number}/{v.total_parts} "
            f"~{v.estimated_seconds}s"
        )

    out_path = Path(output)
    out_data = {
        "book_title": pack.book_title,
        "total_videos": len(all_videos),
        "parts_per_script": parts,
        "videos": [v.model_dump() for v in all_videos],
    }
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"\n[green]Series saved to: {out_path}[/green]")
