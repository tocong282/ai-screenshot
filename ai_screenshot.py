"""Screenshot -> OCR -> LLM answer -> clipboard. Linux, macOS, Windows.

Usage: ai-screenshot [--settings | --selftest | --version | --help]

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

SETTINGS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ai-screenshot settings</title><style>
:root{color-scheme:light dark}
body{font:14px/1.55 system-ui,sans-serif;max-width:660px;margin:40px auto;padding:0 16px}
h1{font-size:18px;margin-bottom:2px}
label{display:block;margin:14px 0 4px;font-weight:600}
input,textarea{width:100%;padding:8px;box-sizing:border-box;font:inherit;
 border:1px solid rgba(128,128,128,.45);border-radius:6px;background:transparent;color:inherit}
textarea{min-height:150px;resize:vertical}
.row{display:flex;gap:12px}.row>div{flex:1}
button{padding:8px 14px;font:inherit;border:1px solid rgba(128,128,128,.45);
 border-radius:6px;background:rgba(128,128,128,.1);cursor:pointer}
button.primary{background:#2f6feb;border-color:#2f6feb;color:#fff}
button:disabled{opacity:.5;cursor:default}
#bar{margin-top:22px;display:flex;gap:10px;flex-wrap:wrap}
#out{white-space:pre-wrap;font-size:13px;border:1px solid rgba(128,128,128,.3);
 border-radius:6px;padding:10px;margin-top:14px;display:none;max-height:260px;overflow:auto}
#status{margin-top:14px;white-space:pre-wrap;font:12px ui-monospace,monospace;
 border-top:1px solid rgba(128,128,128,.3);padding-top:12px;opacity:.85}
small{opacity:.65;font-weight:400}
</style></head><body>
<h1>ai-screenshot</h1><small id="cfgpath"></small>
<label>API base URL</label><input id="base_url" placeholder="http://localhost:20128/v1">
<div class="row">
 <div><label>Model</label><input id="model"></div>
 <div><label>OCR language</label><input id="lang" placeholder="eng"></div>
</div>
<label>API key</label><input id="api_key" type="password" autocomplete="off" spellcheck="false">
<div><small id="keyset"></small></div>
<label>Tessdata dir <small>optional, when system Tesseract lacks lang data</small></label>
<input id="tessdata_dir" placeholder="">
<div class="row">
 <div><label>max_tokens</label><input id="max_tokens" type="number" min="1" max="4096"></div>
 <div><label>temperature</label><input id="temperature" type="number" step="0.1" min="0" max="2"></div>
</div>
<label>Prompt <small>extracted text is appended</small></label><textarea id="prompt"></textarea>
<div id="bar">
 <button class="primary" id="bsave">Save</button>
 <button id="btest">Test API</button>
 <button id="bgrab">Capture + OCR</button>
</div>
<div id="out"></div>
<div id="status">ready</div>
<script>
const CFG=__CONFIG__, API="__API__";
const $=id=>document.getElementById(id);
const fields=["base_url","model","lang","api_key","tessdata_dir","max_tokens","temperature","prompt"];
for(const k of fields) if(k in CFG) $(k).value = CFG[k];
$("cfgpath").textContent = CFG.path;
$("keyset").textContent = CFG.api_key_set ? "key stored — leave blank to keep it" : "no key stored yet";
function status(m){ $("status").textContent = new Date().toLocaleTimeString()+"  "+m; }
function out(m){ $("out").style.display="block"; $("out").textContent=m; }
function payload(){ const o={}; for(const k of fields) o[k]=$(k).value; return o; }
function busy(on){ for(const id of ["bsave","btest","bgrab"]) $(id).disabled=on; }
async function call(route){
  busy(true);
  try{
    const r=await fetch(API+"/"+route,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload())});
    return [r.ok, await r.json().catch(()=>({error:"unreadable response"}))];
  }catch(e){ return [false,{error:String(e)}]; }
  finally{ busy(false); }
}
$("bsave").onclick=async()=>{ status("saving..."); const [ok,d]=await call("save");
  status(ok ? "saved: "+d.path : "error: "+d.error); if(ok){ $("api_key").value=""; } };
$("btest").onclick=async()=>{ status("calling model..."); const [ok,d]=await call("test-api");
  out(ok ? "model says: "+d.answer : "error: "+d.error); status(ok?"api ok":"api failed"); };
$("bgrab").onclick=async()=>{ status("capturing screen..."); const [ok,d]=await call("capture");
  out(ok ? (d.text||"(no text found)") : "error: "+d.error);
  status(ok ? "ocr: "+d.chars+" chars" : "capture failed"); };
</script></body></html>"""


def config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP


def save_config(cfg):
    """Write config.json next to the OS config dir, 0600 on POSIX."""
    path = config_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    if os.name != "nt":
        tmp.chmod(0o600)
    os.replace(tmp, path)
    return path


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


# -------------------------------------------------------------- settings UI
def clean_form(data, current):
    """Validate form values, return a full config dict. Raises ValueError."""

    def number(key, cast, lo, hi):
        try:
            value = cast(data.get(key, current[key]))
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
        return value

    base_url = str(data.get("base_url", current["base_url"])).strip()
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    model = str(data.get("model", current["model"])).strip()
    if not model:
        raise ValueError("model is required")
    cfg = dict(current)
    cfg.update(
        base_url=base_url,
        model=model,
        lang=str(data.get("lang") or current["lang"]).strip(),
        tessdata_dir=str(data.get("tessdata_dir") or "").strip(),
        prompt=str(data.get("prompt") or "").strip() or DEFAULT_PROMPT,
        max_tokens=number("max_tokens", int, 1, 4096),
        temperature=number("temperature", float, 0.0, 2.0),
    )
    api_key = str(data.get("api_key") or "").strip()
    if api_key:  # blank field keeps the stored key
        cfg["api_key"] = api_key
    return cfg


def build_settings_server(current=None):
    """Build the settings HTTP server. Returns (server, prefix, state)."""
    import secrets
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if current is None:
        load_config()  # creates the template + sets CONFIG_PATH
        current = load_config(create=False)
    state = {"cfg": current}
    token = secrets.token_urlsafe(18)
    prefix = f"/{token}"

    class Handler(BaseHTTPRequestHandler):
        server_version = "ai-screenshot"

        def log_message(self, *args):
            pass

        def _send(self, code, payload, ctype="application/json"):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _host_ok(self):
            # Host check blocks DNS rebinding; path token blocks other local apps.
            host = (self.headers.get("Host") or "").lower()
            port = self.server.server_port
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self._host_ok() or self.path.rstrip("/") != prefix:
                return self._send(404, {"error": "not found"})
            cfg = state["cfg"]
            public = {k: v for k, v in cfg.items() if k != "api_key"}
            public["api_key_set"] = bool(cfg.get("api_key"))
            public["path"] = str(CONFIG_PATH) if CONFIG_PATH else "(not saved yet)"
            page = SETTINGS_HTML.replace("__CONFIG__", json.dumps(public)).replace("__API__", prefix)
            self._send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            if not self._host_ok() or not self.path.startswith(prefix + "/"):
                return self._send(404, {"error": "not found"})
            route = self.path.rstrip("/").rsplit("/", 1)[-1]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(length) or b"{}")
                if route == "save":
                    state["cfg"] = clean_form(data, state["cfg"])
                    path = save_config(state["cfg"])
                    return self._send(200, {"ok": True, "path": str(path)})
                if route == "test-api":
                    answer = ask("Reply with the single word OK.", clean_form(data, state["cfg"]))
                    return self._send(200, {"ok": True, "answer": answer})
                if route == "capture":
                    cfg = clean_form(data, state["cfg"])
                    fd, shot = tempfile.mkstemp(prefix="ai-screenshot-", suffix=".png")
                    os.close(fd)
                    try:
                        if not capture(shot):
                            raise RuntimeError("no working capture backend")
                        text = ocr(shot, cfg)
                    finally:
                        Path(shot).unlink(missing_ok=True)
                    return self._send(200, {"ok": True, "chars": len(text), "text": text[:4000]})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # network, tesseract, permissions
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
            self._send(404, {"error": "unknown route"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server, prefix, state


def serve_settings():
    """Serve the settings form on a random localhost port, open the browser."""
    import webbrowser

    server, prefix, _ = build_settings_server()
    url = f"http://127.0.0.1:{server.server_port}{prefix}/"
    print(f"Settings: {url}\nCtrl-C to stop.", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ---------------------------------------------------------------- pipeline
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

    import urllib.error
    import urllib.request

    server, prefix, state = build_settings_server(current=dict(cfg, api_key="__SELFTEST_SECRET__"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(origin + prefix + "/", timeout=15) as resp:
            page = resp.read().decode()
        assert resp.status == 200 and "ai-screenshot settings" in page, "settings page missing"
        assert "__SELFTEST_SECRET__" not in page, "API key value leaked into settings page"
        assert '"api_key":' not in page, "API key field sent to browser"
        assert '"api_key_set": true' in page, "api_key_set flag missing"
        print("PASS settings: form served, key not exposed")

        try:
            urllib.request.urlopen(origin + "/", timeout=10)
            raise AssertionError("token-less request was served")
        except urllib.error.HTTPError as err:
            assert err.code == 404, err.code
        print("PASS settings: path token enforced")

        body = json.dumps({"base_url": "ftp://nope", "model": "m", "max_tokens": 1, "temperature": 0}).encode()
        req = urllib.request.Request(origin + prefix + "/save", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("invalid base_url accepted")
        except urllib.error.HTTPError as err:
            assert err.code == 400, err.code
        print("PASS settings: validation rejects bad input")
    finally:
        server.shutdown()

    print("SELFTEST PASSED")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--selftest" in argv:
            selftest()
        elif "--settings" in argv or "--gui" in argv:
            serve_settings()
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
