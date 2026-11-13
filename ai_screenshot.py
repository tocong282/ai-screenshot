"""Screenshot -> OCR -> LLM answer -> clipboard. Linux, macOS, Windows.

Config: ~/.config/ai-screenshot/config.json (Linux),
        ~/Library/Application Support/ai-screenshot/config.json (macOS),
        %APPDATA%\\ai-screenshot\\config.json (Windows).
Env overrides: AI_SCREENSHOT_BASE_URL, AI_SCREENSHOT_API_KEY,
               AI_SCREENSHOT_MODEL, AI_SCREENSHOT_LANG.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = "ai-screenshot"
CONFIG_PATH = None  # set by load_config()
DEFAULT_PROMPT = (
    "You are a test-taking assistant. Look at the following extracted text "
    "from a screen. Identify the question and provide ONLY the correct "
    "answer as briefly as possible. Do not include any formatting, "
    "explanations, or conversational text. \n\nExtracted Text: "
)

DEFAULTS = {
    "base_url": "http://localhost:20128/v1",
    "api_key": "",
    "model": "cx/gpt-5.3-codex",
    "lang": "eng",
    "tessdata_dir": "",
    "prompt": DEFAULT_PROMPT,
    "max_tokens": 50,
    "temperature": 0.1,
}
ENV = {
    "base_url": "AI_SCREENSHOT_BASE_URL",
    "api_key": "AI_SCREENSHOT_API_KEY",
    "model": "AI_SCREENSHOT_MODEL",
    "lang": "AI_SCREENSHOT_LANG",
}


def config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP


def load_config(create=True):
    """Merged config: defaults <- file <- env. Creates template if missing."""
    global CONFIG_PATH
    CONFIG_PATH = config_dir() / "config.json"
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    elif create:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
        sys.exit(f"Created config template: {CONFIG_PATH}\nFill in api_key, then rerun.")
    for key, env in ENV.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


# ---------------------------------------------------------------- capture
def capture(path):
    """Save a full-screen grab to path. Returns True on success."""
    system = platform_key()
    if system == "darwin":
        cmds = [["screencapture", "-x", "-o", path]]
    elif system == "windows":
        cmds = [["powershell", "-NoProfile", "-Command", _PS_CAPTURE % path]]
    else:
        cmds = [
            ["spectacle", "-b", "-n", "-o", path],
            ["grim", path],
            ["gnome-screenshot", "-f", path],
            ["scrot", "-o", path],
            ["import", "-window", "root", path],
        ]
    for cmd in cmds:
        if not _have(cmd[0]):
            continue
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        p = Path(path)
        if p.exists() and p.stat().st_size > 0:
            return True
    return False


_PS_CAPTURE = (
    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
    "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
    "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
    "$g=[System.Drawing.Graphics]::FromImage($bmp);"
    "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
    "$bmp.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png);"
    "$g.Dispose();$bmp.Dispose()"
)


def platform_key():
    if os.name == "nt":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _have(binary):
    return shutil.which(binary) is not None


# ------------------------------------------------------------------ OCR
def ocr(path, cfg):
    import pytesseract
    from PIL import Image

    kwargs = {"lang": cfg["lang"]}
    if cfg.get("tessdata_dir"):
        kwargs["config"] = f'--tessdata-dir "{cfg["tessdata_dir"]}"'
    with Image.open(path) as img:
        return " ".join(pytesseract.image_to_string(img, **kwargs).split())


# ------------------------------------------------------------- clipboard
def copy_text(text):
    """Put text on the clipboard. Returns True on success."""
    system = platform_key()
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    try:
        if system == "macos":
            return subprocess.run(["pbcopy"], input=text.encode(), timeout=15, **quiet).returncode == 0
        if system == "windows":
            ps = "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                input=text.encode("utf-8"), timeout=20, **quiet,
            ).returncode == 0
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard", "-i"], ["xsel", "-b", "-i"]):
            if _have(cmd[0]):
                r = subprocess.run(cmd, input=text.encode("utf-8"), timeout=15, **quiet)
                if r.returncode == 0:
                    return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


# ------------------------------------------------------------------ LLM
def ask(text, cfg, client=None):
    if client is None:
        from openai import OpenAI

        client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "unset", timeout=60)
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "user", "content": cfg["prompt"] + text}],
        max_tokens=cfg["max_tokens"],
        temperature=cfg["temperature"],
    )
    return (response.choices[0].message.content or "").strip()


# ------------------------------------------------------------------ main
def run(cfg):
    start = time.time()
    fd, shot = tempfile.mkstemp(prefix="ai-screenshot-", suffix=".png")
    os.close(fd)
    try:
        if not capture(shot):
            sys.exit("Screenshot failed: no working capture backend found.")
        print(f"  capture {time.time() - start:.2f}s", file=sys.stderr)

        t = time.time()
        text = ocr(shot, cfg)
        print(f"  ocr     {time.time() - t:.2f}s ({len(text)} chars)", file=sys.stderr)
        if not text:
            sys.exit("No text found on screen.")
    finally:
        Path(shot).unlink(missing_ok=True)

    t = time.time()
    answer = ask(text, cfg)
    print(f"  llm     {time.time() - t:.2f}s", file=sys.stderr)
    if not answer:
        sys.exit("Model returned an empty answer.")

    print(answer)
    if copy_text(answer):
        print("Copied to clipboard.", file=sys.stderr)
    else:
        print("Clipboard copy failed (answer printed above).", file=sys.stderr)


def selftest():
    """OCR, API and clipboard paths against real libs + a stub server."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from PIL import Image, ImageDraw

    cfg = dict(DEFAULTS)
    cfg["lang"] = os.environ.get("AI_SCREENSHOT_LANG", "eng")
    if os.environ.get("AI_SCREENSHOT_TESSDATA"):
        cfg["tessdata_dir"] = os.environ["AI_SCREENSHOT_TESSDATA"]

    tmp = Path(tempfile.mkdtemp(prefix="ai-screenshot-test-"))
    img_path = tmp / "sample.png"
    image = Image.new("RGB", (520, 90), "white")
    ImageDraw.Draw(image).text((12, 30), "HELLO 42 SCREENSHOT", fill="black")
    image.save(img_path)

    text = ocr(str(img_path), cfg).upper()
    assert "HELLO" in text and "42" in text, f"OCR mismatch: {text!r}"
    print("PASS ocr:", text)

    payload = {"choices": [{"message": {"content": "42"}, "index": 0, "finish_reason": "stop"}]}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cfg["base_url"] = f"http://127.0.0.1:{server.server_port}/v1"
        cfg["api_key"] = "test"
        assert ask("question numbers", cfg) == "42"
        print("PASS api: stub chat completion round-trip")
    finally:
        server.shutdown()

    ok = copy_text("ai-screenshot selftest")
    print(f"{'PASS' if ok else 'SKIP'} clipboard:", "copied" if ok else "no clipboard backend (headless)")
    print("SELFTEST PASSED")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--selftest" in argv:
            selftest()
        elif "--version" in argv:
            from importlib.metadata import version

            try:
                print("ai-screenshot", version("ai-screenshot"))
            except Exception:
                print("ai-screenshot unknown (source checkout)")
        elif "-h" in argv or "--help" in argv:
            print(__doc__)
        else:
            run(load_config())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
