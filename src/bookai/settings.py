"""BookAI Settings Module — quản lý API key, model, và prompts.

Lưu cấu hình vào ~/.bookai/config.json (hoặc .bookai/config.json trong project).

CLI Usage::

    # Xem toàn bộ config hiện tại
    python -m bookai.settings show

    # Cài API
    python -m bookai.settings set api.key sk-xxxx
    python -m bookai.settings set api.base_url http://152.42.217.33:20128/v1
    python -m bookai.settings set api.model gh/gpt-4o-mini

    # Xem / sửa prompt
    python -m bookai.settings prompt list
    python -m bookai.settings prompt show radio
    python -m bookai.settings prompt edit radio

    # Reset về mặc định
    python -m bookai.settings reset

    # Test kết nối API
    python -m bookai.settings test
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Default prompts (persona)
# ---------------------------------------------------------------------------

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "radio": {
        "name": "Radio / TikTok Script",
        "description": "Kịch bản sách nói, podcast, TikTok video",
        "system": (
            "Bạn là nhà văn và content creator chuyên nghiệp 10 năm viết kịch bản sách nói, "
            "podcast và TikTok viral tại Việt Nam.\n\n"
            "PHONG CÁCH VIẾT:\n"
            "- Mỗi câu đều HOÀN CHỈNH, rõ nghĩa khi đọc riêng lẻ\n"
            "- Viết như đang NÓI CHUYỆN với bạn bè thông minh\n"
            "- Câu ngắn (8-15 từ) xen câu dài (20-30 từ) tạo nhịp điệu tự nhiên\n"
            "- Hook BẮT BUỘC là câu hỏi tu từ mà người nghe chắc chắn đã từng nghĩ đến\n"
            "- Body: Khẳng định → Bằng chứng cụ thể → Ví dụ thực tế → Bài học rút ra\n"
            "- KHÔNG lặp lại hook ở body\n"
            "- Giữ nguyên tên tác giả, số liệu, thuật ngữ từ sách\n"
            "- Kết bằng CTA kêu gọi comment/share, KHÔNG kêu gọi mua hàng thẳng"
        ),
    },
    "caption": {
        "name": "Caption TikTok / Reels",
        "description": "Caption ngắn cho TikTok, Instagram Reels",
        "system": (
            "Bạn là copywriter chuyên viết caption viral, hiểu thuật toán TikTok "
            "và tâm lý người đọc 18-35 tuổi tại Việt Nam.\n\n"
            "NGUYÊN TẮC:\n"
            "- Câu đầu tiên ≤12 từ, HOÀN CHỈNH về nghĩa, gây tò mò hoặc shock nhẹ\n"
            "- Mỗi câu ĐỌC HIỂU NGAY khi lướt qua — không cần context\n"
            "- Tổng ≤5 câu (người dùng TikTok không đọc dài)\n"
            "- Kết bằng câu hỏi mở để kéo comment\n"
            "- Giữ nguyên số liệu, tên tác giả, thuật ngữ chuyên ngành\n"
            "- KHÔNG dùng emoji quá nhiều (≤2 emoji/caption)"
        ),
    },
    "blog": {
        "name": "Blog SEO",
        "description": "Bài blog dài 1500-2000 từ, chuẩn SEO",
        "system": (
            "Bạn là blogger chuyên review sách viết theo phong cách Spiderum, Ybox "
            "— thân mật, có chiều sâu, lập luận chặt chẽ.\n\n"
            "NGUYÊN TẮC:\n"
            "- KHÔNG mở bài bằng 'Cuốn sách này...' hay 'Hôm nay tôi sẽ...'\n"
            "- Mở bài bằng câu hỏi tu từ hoặc một tình huống ai cũng từng gặp\n"
            "- Mỗi bài học: Tiêu đề → Giải thích → Ví dụ thực tế → Quote ngắn từ sách\n"
            "- Giọng văn: 76% câu chủ động, dùng 'bạn/tôi' (không 'chúng ta')\n"
            "- Cấu trúc: H1 (tiêu đề SEO) → H2 (mở bài) → H2 x3-5 (bài học) → H2 (kết)\n"
            "- Giữ nguyên thuật ngữ chuyên ngành, tên tác giả, số liệu nghiên cứu\n"
            "- Dài 1500-2000 từ, đủ để rank Google"
        ),
    },
    "analyzer": {
        "name": "Phân tích chunk",
        "description": "Phân tích viral score và nhãn cho từng đoạn sách",
        "system": (
            "Bạn là chuyên gia phân tích nội dung và viral marketing tại Việt Nam, "
            "hiểu sâu tâm lý người dùng TikTok/mạng xã hội.\n\n"
            "NHIỆM VỤ:\n"
            "- Đánh giá tiềm năng viral của đoạn text trên TikTok/Facebook\n"
            "- Giữ nguyên thuật ngữ chuyên ngành, KHÔNG dịch lại hay giải thích\n"
            "- Nhận diện câu hỏi tu từ — rất mạnh cho TikTok hook\n"
            "- Nhận diện số liệu/nghiên cứu/thống kê — tăng độ tin cậy\n"
            "- Trả về JSON hợp lệ, KHÔNG thêm giải thích ngoài JSON"
        ),
    },
}

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

def _config_path() -> Path:
    """Tìm file config: ưu tiên .bookai/config.json trong project, fallback ~/.bookai/."""
    local = Path(".bookai") / "config.json"
    if local.parent.exists() or Path("src/bookai").exists():
        return local
    return Path.home() / ".bookai" / "config.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Đọc config hiện tại. Trả về dict mặc định nếu chưa có file."""
    path = _config_path()
    if not path.exists():
        return _default_config()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge prompts mặc định vào nếu thiếu key
        for key, val in DEFAULT_PROMPTS.items():
            data.setdefault("prompts", {}).setdefault(key, val)
        return data
    except json.JSONDecodeError:
        print(f"[settings] Lỗi đọc config tại {path} — dùng mặc định.")
        return _default_config()


def save_config(config: dict[str, Any]) -> None:
    """Ghi config ra file."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"✅ Đã lưu config vào {path}")


def _default_config() -> dict[str, Any]:
    return {
        "api": {
            "key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        },
        "prompts": DEFAULT_PROMPTS,
        "output": {
            "dir": "./output",
            "formats": ["md", "txt"],
        },
    }


# ---------------------------------------------------------------------------
# Getter helpers (dùng trong analyzer.py, content_studio.py, blog.py)
# ---------------------------------------------------------------------------

def get_api_key() -> str:
    cfg = load_config()
    return cfg["api"].get("key") or os.getenv("OPENAI_API_KEY", "")


def get_base_url() -> str | None:
    cfg = load_config()
    url = cfg["api"].get("base_url") or os.getenv("OPENAI_BASE_URL")
    if url and url == "https://api.openai.com/v1":
        return None  # openai SDK tự xử lý default
    return url or None


def get_model() -> str:
    cfg = load_config()
    return cfg["api"].get("model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_system_prompt(prompt_key: str) -> str:
    """Lấy system prompt theo key (radio/caption/blog/analyzer)."""
    cfg = load_config()
    prompts = cfg.get("prompts", DEFAULT_PROMPTS)
    entry = prompts.get(prompt_key, DEFAULT_PROMPTS.get(prompt_key, {}))
    return entry.get("system", "")


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _set_nested(d: dict, dotted_key: str, value: str) -> None:
    """Gán giá trị theo dotted key, vd: 'api.key' -> d['api']['key'] = value."""
    keys = dotted_key.split(".")
    node = d
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def cmd_show(cfg: dict) -> None:
    print("\n📋  BookAI Config\n" + "=" * 50)
    print(f"  Config file : {_config_path()}")
    api = cfg.get("api", {})
    key = api.get("key", "")
    masked = (key[:8] + "..." + key[-4:]) if len(key) > 12 else ("(chưa cài)" if not key else key)
    print(f"\n  [API]")
    print(f"    key      : {masked}")
    print(f"    base_url : {api.get('base_url', '(mặc định OpenAI)')}")
    print(f"    model    : {api.get('model', 'gpt-4o-mini')}")
    out = cfg.get("output", {})
    print(f"\n  [Output]")
    print(f"    dir      : {out.get('dir', './output')}")
    print(f"    formats  : {', '.join(out.get('formats', ['md']))}")
    print(f"\n  [Prompts] — {len(cfg.get('prompts', {}))} prompts đã cài")
    for k, v in cfg.get("prompts", {}).items():
        name = v.get("name", k) if isinstance(v, dict) else k
        print(f"    • {k:12s} → {name}")
    print()


def cmd_set(cfg: dict, dotted_key: str, value: str) -> None:
    _set_nested(cfg, dotted_key, value)
    save_config(cfg)
    print(f"✅ {dotted_key} = {value}")


def cmd_prompt_list(cfg: dict) -> None:
    print("\n🎭  Danh sách prompts\n" + "=" * 50)
    for k, v in cfg.get("prompts", DEFAULT_PROMPTS).items():
        name = v.get("name", k) if isinstance(v, dict) else k
        desc = v.get("description", "") if isinstance(v, dict) else ""
        print(f"  {k:12s}  {name}")
        if desc:
            print(f"              {desc}")
    print(f"\n  👉 Xem chi tiết: python -m bookai.settings prompt show <key>")
    print(f"  ✏️  Sửa prompt : python -m bookai.settings prompt edit <key>\n")


def cmd_prompt_show(cfg: dict, key: str) -> None:
    prompts = cfg.get("prompts", DEFAULT_PROMPTS)
    if key not in prompts:
        print(f"❌ Không tìm thấy prompt '{key}'. Dùng: {', '.join(prompts.keys())}")
        return
    p = prompts[key]
    print(f"\n🎭  Prompt: {key} — {p.get('name', key)}\n" + "=" * 50)
    print(f"  Mô tả: {p.get('description', '')}\n")
    print("  [System prompt]")
    for line in p.get("system", "").splitlines():
        print(f"    {line}")
    print()


def cmd_prompt_edit(cfg: dict, key: str) -> None:
    """Mở editor để sửa system prompt."""
    prompts = cfg.get("prompts", DEFAULT_PROMPTS)
    if key not in prompts:
        print(f"❌ Key '{key}' không tồn tại. Tạo mới với key này? (y/n): ", end="")
        if input().strip().lower() != "y":
            return
        prompts[key] = {"name": key, "description": "", "system": ""}

    # Ghi ra file tmp để user sửa
    import tempfile
    current = prompts[key].get("system", "")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8", prefix=f"bookai_prompt_{key}_") as f:
        f.write(current)
        tmp_path = f.name

    editor = os.getenv("EDITOR", "nano")
    try:
        subprocess.call([editor, tmp_path])
    except FileNotFoundError:
        print(f"Editor '{editor}' không tìm thấy. Sửa trực tiếp file: {tmp_path}")
        print("Rồi chạy lại: python -m bookai.settings prompt set <key> <file>")
        return

    with open(tmp_path, "r", encoding="utf-8") as f:
        new_system = f.read().strip()

    Path(tmp_path).unlink(missing_ok=True)

    if new_system == current:
        print("Không có thay đổi.")
        return

    cfg["prompts"][key]["system"] = new_system
    save_config(cfg)
    print(f"✅ Đã cập nhật prompt '{key}'")


def cmd_prompt_set_file(cfg: dict, key: str, filepath: str) -> None:
    """Load system prompt từ file text."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File không tồn tại: {filepath}")
        return
    new_system = path.read_text(encoding="utf-8").strip()
    cfg.setdefault("prompts", {})[key] = cfg.get("prompts", {}).get(key, {})
    cfg["prompts"][key]["system"] = new_system
    save_config(cfg)
    print(f"✅ Prompt '{key}' đã load từ {filepath}")


def cmd_reset(cfg: dict) -> None:
    print("⚠️  Reset sẽ xóa toàn bộ config (giữ lại API key). Tiếp tục? (y/n): ", end="")
    if input().strip().lower() != "y":
        print("Đã hủy.")
        return
    old_key = cfg.get("api", {}).get("key", "")
    new_cfg = _default_config()
    new_cfg["api"]["key"] = old_key  # giữ key
    save_config(new_cfg)
    print("✅ Reset xong — prompts đã về mặc định, API key được giữ.")


def cmd_test(cfg: dict) -> None:
    """Test kết nối API với model đã cài."""
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ Chưa cài openai: pip install openai")
        return

    api = cfg.get("api", {})
    key = api.get("key", "") or os.getenv("OPENAI_API_KEY", "")
    base_url = api.get("base_url") or None
    model = api.get("model", "gpt-4o-mini")

    if not key:
        print("❌ Chưa có API key. Chạy: python -m bookai.settings set api.key sk-xxxx")
        return

    if base_url and base_url == "https://api.openai.com/v1":
        base_url = None

    print(f"🔌 Testing: {base_url or 'api.openai.com'} | model: {model}")

    client = OpenAI(api_key=key, base_url=base_url or "https://api.openai.com/v1")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Trả lời đúng 1 từ: 'OK'"}],
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip()
        print(f"✅ Kết nối thành công! Model trả lời: '{answer}'")
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = (argv or sys.argv[1:])
    cfg = load_config()

    if not args or args[0] == "show":
        cmd_show(cfg)

    elif args[0] == "set" and len(args) >= 3:
        cmd_set(cfg, args[1], " ".join(args[2:]))

    elif args[0] == "prompt":
        sub = args[1] if len(args) > 1 else "list"
        if sub == "list":
            cmd_prompt_list(cfg)
        elif sub == "show" and len(args) >= 3:
            cmd_prompt_show(cfg, args[2])
        elif sub == "edit" and len(args) >= 3:
            cmd_prompt_edit(cfg, args[2])
        elif sub == "set" and len(args) >= 4:
            cmd_prompt_set_file(cfg, args[2], args[3])
        else:
            print("Usage: prompt list | prompt show <key> | prompt edit <key> | prompt set <key> <file>")

    elif args[0] == "reset":
        cmd_reset(cfg)

    elif args[0] == "test":
        cmd_test(cfg)

    else:
        print(textwrap.dedent("""
        BookAI Settings — Quản lý cấu hình

        Commands:
          show                        Xem toàn bộ config
          set api.key <value>         Cài API key
          set api.base_url <url>      Cài base URL (custom endpoint)
          set api.model <model>       Cài model (vd: gh/gpt-4o-mini)
          set output.dir <path>       Thư mục output
          prompt list                 Danh sách prompts
          prompt show <key>           Xem prompt (radio/caption/blog/analyzer)
          prompt edit <key>           Sửa prompt bằng text editor
          prompt set <key> <file>     Load prompt từ file .txt
          reset                       Reset về mặc định
          test                        Test kết nối API
        """))


if __name__ == "__main__":
    main()
