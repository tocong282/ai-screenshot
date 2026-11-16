# ai-screenshot

Grab the screen, OCR it, ask an OpenAI-compatible model for the answer, put the
answer on the clipboard.

Works on Linux (X11 + KDE/GNOME Wayland), macOS and Windows.

## Install (no Python needed)

Download from [Releases](https://github.com/tocong282/ai-screenshot/releases):

| OS | File | Notes |
| --- | --- | --- |
| Windows | `ai-screenshot-<version>-windows-x64-setup.exe` | installer: Start Menu + desktop shortcut, Ctrl+Alt+Q capture, Ctrl+Alt+S settings |
| Windows | `ai-screenshot-<version>-windows-x64.zip` | portable single exe |
| macOS (Apple Silicon) | `ai-screenshot-<version>-macos-arm64.dmg` | drag to Applications |
| Linux x64 | `ai-screenshot-<version>-linux-x64.tar.gz` | `tar xzf`, run `./ai-screenshot` |

Linux quick start:

```bash
mkdir -p ~/.local/bin
tar xzf ai-screenshot-0.3.0-linux-x64.tar.gz -C ~/.local/bin
chmod +x ~/.local/bin/ai-screenshot
ai-screenshot --settings      # set base_url, model, api key
ai-screenshot                  # capture -> answer on clipboard
```

Needs a graphical session (`DISPLAY` or `WAYLAND_DISPLAY`) and one capture tool:
`spectacle` (KDE), `grim` (wlroots), `gnome-screenshot`, `scrot` or ImageMagick
`import`. Clipboard: `wl-copy`, `xclip` or `xsel`. `ai-screenshot --diagnose`
tells you exactly which of those is missing.

These builds bundle the OCR engine (RapidOCR, ONNX) — Tesseract is **not**
required. Intel Macs and other Linux archs: use the source install below.

The binaries are not code-signed:

- Windows SmartScreen: *More info* -> *Run anyway*.
- macOS Gatekeeper: right-click the app -> *Open* (once), or
  `xattr -dr com.apple.quarantine /Applications/ai-screenshot.app`.
  macOS asks for Screen Recording permission on first capture.

macOS shortcut: Shortcuts.app -> *Run Shell Script* ->
`/Applications/ai-screenshot.app/Contents/MacOS/ai-screenshot`, assign a key.

## Install from source

Needs Python 3.9+ and [uv](https://docs.astral.sh/uv/), plus Tesseract:

| OS | Tesseract |
| --- | --- |
| Arch | `sudo pacman -S tesseract tesseract-data-eng` |
| Debian/Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-eng` |
| macOS | `brew install tesseract` |
| Windows | `choco install tesseract` (or the UB-Mannheim installer) |

```bash
uv tool install git+https://github.com/tocong282/ai-screenshot
```

Pinned release: `uv tool install git+https://github.com/tocong282/ai-screenshot@v0.3.0`

OCR engine is picked by `engine` in config: `auto` (default) uses the bundled
RapidOCR in frozen builds and the system Tesseract in source checkouts; force
`tesseract` or `rapidocr` to override.

## Configure

First run writes a template and exits:

| OS | Path |
| --- | --- |
| Linux | `~/.config/ai-screenshot/config.json` |
| macOS | `~/Library/Application Support/ai-screenshot/config.json` |
| Windows | `%APPDATA%\ai-screenshot\config.json` |

```json
{
  "base_url": "http://localhost:20128/v1",
  "api_key": "sk-...",
  "model": "cx/gpt-5.3-codex",
  "lang": "eng",
  "tessdata_dir": "",
  "prompt": "...",
  "max_tokens": 50,
  "temperature": 0.1
}
```

Any key can be overridden by env: `AI_SCREENSHOT_BASE_URL`,
`AI_SCREENSHOT_API_KEY`, `AI_SCREENSHOT_MODEL`, `AI_SCREENSHOT_LANG`.

`tessdata_dir` is optional — point it at a directory of `*.traineddata` when the
system Tesseract has no English data (`--tessdata-dir`).

## When it does nothing

Run the diagnostics build — it prints (and pops up, in the packaged app) a
report for config, capture backend, OCR, clipboard and API:

```bash
ai-screenshot --diagnose        # Windows: Start Menu -> Diagnostics
```

Report is also saved to `diagnose.txt` next to `config.json`, and every run
appends to `log.txt` there. Common causes:

- `capture: FAIL ...` — no graphical session (SSH/service), or missing capture
  tool on Linux.
- `api: FAIL APIConnectionError` — `base_url` unreachable. The default
  `http://localhost:20128/v1` is a **local** proxy; on another machine point it
  at the real endpoint or start the proxy there.
- `api_key: MISSING` — fill it in `--settings`.
- `api: FAIL ... finished_reason=max_tokens` / empty answer — reasoning models
  spend tokens thinking before writing. Raise `max_tokens` (512 default, 2048+
  for GPT-5-class models).

## Use

```bash
ai-screenshot            # capture -> ocr -> ask -> clipboard
ai-screenshot --settings # open the settings form in your browser
ai-screenshot --selftest # offline check of OCR, API, clipboard, settings server
```

`--settings` (alias `--gui`) starts a throwaway HTTP server on `127.0.0.1` with a
random port and a random URL token, then opens the page. It edits the same
`config.json` the CLI reads, with Save / Test API / Capture + OCR buttons. The
stored API key is never sent to the browser: the field starts blank and only
overwrites when you type a new key. The server exits on Ctrl-C.

Bind it to a key. No resident process needed:

- **KDE**: System Settings -> Shortcuts -> Add Command -> `ai-screenshot`
- **GNOME**: Settings -> Keyboard -> Custom Shortcuts
- **macOS**: Shortcuts.app -> New Shortcut -> Run Shell Script -> `ai-screenshot`,
  assign a key; or Automator Quick Action
- **Windows**: right-click `ai-screenshot.exe` shortcut -> Properties ->
  Shortcut key

## Capture backends

Picked in order, first that produces a file:

- macOS: `screencapture -x -o`
- Windows: PowerShell `System.Drawing` virtual screen (all monitors)
- Linux: `spectacle -b -n -o`, `grim`, `gnome-screenshot`, `scrot`,
  ImageMagick `import`

Clipboard: `pbcopy` / PowerShell `Set-Clipboard` / `wl-copy` / `xclip` / `xsel`.

## Release

Version lives in `pyproject.toml`. Tag to publish:

```bash
git tag v0.3.1 && git push origin v0.3.1
```

`.github/workflows/release.yml` freezes a PyInstaller binary per OS, smoke-tests
it with `--selftest` on that runner, packs Linux tarball / macOS dmg / Windows
installer + zip, then creates the GitHub Release with wheel + sdist.
`.github/workflows/ci.yml` runs `--selftest` from source on Linux, macOS and
Windows for every push.

Known limits of the packaged builds: unsigned (Gatekeeper / SmartScreen prompts),
macOS dmg is Apple Silicon only, Linux tarball built on Ubuntu 22.04.

