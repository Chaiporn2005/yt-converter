#!/usr/bin/env python3
"""Local YouTube -> MP3/MP4 converter. Stdlib only; shells out to yt-dlp and ffmpeg."""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8765"))
WINDOWS = os.name == "nt"
# A PyInstaller build unpacks index.html (and, for the portable exe, the tools) into _MEIPASS.
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
OUT_DIR = Path(os.environ.get("OUT_DIR", Path.home() / "Downloads" / "YT Converter"))
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

AUDIO_KBPS = (128, 192, 256, 320)
VIDEO_HEIGHTS = (360, 480, 720, 1080, 1440, 2160)
DEFAULT_SETTINGS = {"format": "mp3", "audio_kbps": 192, "video_height": 1080}
APP_DATA = (Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) if WINDOWS
            else Path.home() / "Library" / "Application Support")
SETTINGS_PATH = Path(os.environ.get("SETTINGS_PATH", APP_DATA / "Local Converter" / "settings.json"))

VOCAL_ENGINE_PATH = SETTINGS_PATH.parent / "vocal-engine.json"

JOBS = {}
JOBS_LOCK = threading.Lock()
SETTINGS_LOCK = threading.Lock()


def clean_settings(data):
    """Return a valid settings dict, falling back to defaults for anything unrecognised."""
    out = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        if data.get("format") in ("mp3", "mp4", "karaoke"):
            out["format"] = data["format"]
        if type(data.get("audio_kbps")) is int and data["audio_kbps"] in AUDIO_KBPS:
            out["audio_kbps"] = data["audio_kbps"]
        if type(data.get("video_height")) is int and data["video_height"] in VIDEO_HEIGHTS:
            out["video_height"] = data["video_height"]
    return out


def load_settings():
    try:
        return clean_settings(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(data):
    settings = clean_settings(data)
    with SETTINGS_LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(settings), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
    return settings


def find_tool(name):
    # Windows builds ship yt-dlp and ffmpeg in a bin folder beside the exe or inside the bundle.
    if getattr(sys, "frozen", False):
        for folder in (Path(sys.executable).parent / "bin", ROOT / "bin"):
            bundled = folder / (name + ".exe" if WINDOWS else name)
            if bundled.is_file():
                return str(bundled)
    path = shutil.which(name)
    if not path:
        for candidate in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
            if os.access(candidate, os.X_OK):
                return candidate
    return path


YTDLP = find_tool("yt-dlp")
FFMPEG = find_tool("ffmpeg")


def is_youtube_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() in YOUTUBE_HOSTS


def build_command(url, fmt, quality):
    # The quality is part of the name so a different setting never reuses an earlier file.
    suffix = f"{quality}kbps" if fmt == "mp3" else f"{quality}p"
    cmd = [
        YTDLP, "--no-playlist", "--no-simulate", "--no-quiet", "--progress", "--newline",
        "--windows-filenames", "--ffmpeg-location", str(Path(FFMPEG).parent),
        "-P", str(OUT_DIR), "-o", f"%(title).150B [%(id)s] {suffix}.%(ext)s",
        "--progress-template", "download:PROG|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s",
        "--print", "after_move:FILE|%(filepath)s",
    ]
    if fmt == "mp3":
        cmd += ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", f"{quality}K"]
    elif quality <= 1080:
        # Up to 1080p prefers H.264/AAC so the file plays in QuickTime; falls back if unavailable.
        cmd += ["-f", "bv*+ba/b", "-S", f"vcodec:h264,res:{quality},acodec:aac", "--merge-output-format", "mp4"]
    else:
        # 1440p/4K only exist as VP9/AV1; prefer VP9 for wider player support.
        cmd += ["-f", "bv*+ba/b", "-S", f"res:{quality},vcodec:vp9,acodec:aac", "--merge-output-format", "mp4"]
    return cmd + ["--", url]


def vocal_command():
    """Find a ready engine from setup, even when the Mac app is installed elsewhere."""
    candidates = [Path(os.environ["VOCAL_PYTHON"])] if os.environ.get("VOCAL_PYTHON") else []
    try:
        registered = json.loads(VOCAL_ENGINE_PATH.read_text(encoding="utf-8"))
        python = registered.get("python") if isinstance(registered, dict) else None
        if isinstance(python, str) and Path(python).is_absolute():
            candidates.append(Path(python))
    except (OSError, ValueError):
        pass
    candidates.append(ROOT / ".venv-vocals" / ("Scripts/python.exe" if WINDOWS else "bin/python"))
    if ROOT.name == "Resources" and len(ROOT.parents) > 3:
        candidates.append(ROOT.parents[3] / ".venv-vocals" / "bin" / "python")
    for python in candidates:
        if python.is_file() and os.access(python, os.X_OK) and (python.parent.parent / ".ready").is_file():
            return [str(python), "-m", "demucs"]
    executable = find_tool("demucs")
    return [executable] if executable else None


VOCAL_SETUP_HINT = (
    "Cut vocal needs the vocal remover. Follow the Cut vocal steps in README-Windows.md "
    "(github.com/Chaiporn2005/yt-converter), then restart Local Converter."
    if WINDOWS else
    "Vocal remover needs setup. Double-click setup-vocals.command in the yt-converter folder, then try again.")


def run_stage(job, cmd, on_line=None):
    """Launch and cancel every processing stage through the same job lock."""
    with JOBS_LOCK:
        if job.get("cancelled"):
            raise InterruptedError("Cancelled")
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                env={**os.environ, **({"TORCH_HOME": job["torch_home"]} if job.get("torch_home") else {})})
        job["proc"] = proc
    tail = []
    for raw in proc.stdout:
        line = raw.strip()
        if line:
            tail = (tail + [line])[-8:]
            if on_line:
                on_line(line)
    code = proc.wait()
    if job.get("cancelled"):
        raise InterruptedError("Cancelled")
    if code:
        raise RuntimeError("\n".join(tail) or "Audio processing failed")


def run_karaoke(job_id, url, quality):
    job = JOBS[job_id]
    try:
        engine = vocal_command()
        if not engine:
            raise RuntimeError(VOCAL_SETUP_HINT)
        if len(engine) > 1:
            job["torch_home"] = str(Path(engine[0]).parent.parent / "models")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".karaoke-", dir=OUT_DIR) as temp:
            work = Path(temp)
            cmd = build_command(url, "mp3", quality)
            # Download lossless PCM for separation rather than encoding MP3 twice.
            cmd[cmd.index("-P") + 1] = str(work)
            cmd[cmd.index("--audio-format") + 1] = "wav"
            source = None
            job.update(state="downloading", percent=0)

            def downloaded(line):
                nonlocal source
                if line.startswith("FILE|"):
                    source = Path(line[5:])
                elif line.startswith("PROG|"):
                    _, done, total, estimate = line.split("|")[:4]
                    size = total if total.isdigit() else estimate
                    if done.isdigit() and size.isdigit() and int(size) > 0:
                        job["percent"] = round(min(int(done) / int(size), 1) * 35, 1)

            run_stage(job, cmd, downloaded)
            if not source or not source.is_file():
                raise RuntimeError("Downloaded audio was not found")
            job.update(state="separating", percent=35)
            run_stage(job, engine + ["-n", "htdemucs", "--two-stems", "vocals", "-d", "cpu",
                                    "-o", str(work / "stems"), str(source)])
            instrumental = work / "stems" / "htdemucs" / source.stem / "no_vocals.wav"
            if not instrumental.is_file():
                raise RuntimeError("Vocal remover did not produce a backing track")
            job.update(state="converting", percent=95)
            filename = source.stem + " (Instrumental).mp3"
            encoded = work / filename
            run_stage(job, [FFMPEG, "-nostdin", "-y", "-i", str(instrumental),
                            "-vn", "-codec:a", "libmp3lame", "-b:a", f"{quality}k", str(encoded)])
            with JOBS_LOCK:
                if job.get("cancelled"):
                    raise InterruptedError("Cancelled")
                encoded.replace(OUT_DIR / filename)
                job.update(state="done", percent=100, filename=filename, filepath=str(OUT_DIR / filename))
    except InterruptedError:
        job["state"] = "cancelled"
    except Exception as exc:
        job.update(state="cancelled" if job.get("cancelled") else "error", error=str(exc))


def run_job(job_id, url, fmt, quality):
    job = JOBS[job_id]
    streams_expected = 1 if fmt == "mp3" else 2
    stream_index = 0
    last_lines = []
    try:
        proc = subprocess.Popen(
            build_command(url, fmt, quality), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        job["proc"] = proc
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            last_lines = (last_lines + [line])[-8:]
            if line.startswith("[download] Destination:"):
                stream_index += 1
                job["state"] = "downloading"
            elif line.startswith("PROG|"):
                _, done, total, estimate = line.split("|")[:4]
                size = total if total.isdigit() else estimate
                if done.isdigit() and size.isdigit() and int(size) > 0:
                    fraction = min(int(done) / int(size), 1.0)
                    base = max(stream_index - 1, 0)
                    job["percent"] = round(min(base + fraction, streams_expected) / streams_expected * 90, 1)
            elif line.startswith(("[ExtractAudio]", "[Merger]", "[VideoConvertor]")):
                job["state"] = "converting"
                job["percent"] = 95
            elif line.startswith("FILE|"):
                job["filepath"] = line[5:]
        code = proc.wait()
        if job.get("cancelled"):
            job["state"] = "cancelled"
        elif code == 0 and job.get("filepath") and Path(job["filepath"]).exists():
            job["state"] = "done"
            job["percent"] = 100
            job["filename"] = Path(job["filepath"]).name
        else:
            job["state"] = "error"
            errors = [l for l in last_lines if l.startswith("ERROR")]
            job["error"] = (errors or last_lines or ["yt-dlp failed"])[-1]
    except Exception as exc:  # surface any launch failure to the UI
        job["state"] = "error"
        job["error"] = str(exc)


def video_id(url):
    """Return the 11-character video ID from a YouTube URL, or None."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.match(r"^/(?:shorts|embed|live)/([\w-]{11})", parsed.path)
        candidate = match.group(1) if match else ""
    return candidate if re.fullmatch(r"[\w-]{11}", candidate or "") else None


def video_info(url):
    """Title/channel via YouTube's public oEmbed endpoint; the ID alone is enough if that fails."""
    vid = video_id(url)
    if not vid:
        return None
    canonical = f"https://www.youtube.com/watch?v={vid}"
    info = {"id": vid, "url": canonical, "title": None, "channel": None}
    try:
        request = Request(
            "https://www.youtube.com/oembed?format=json&url=" + quote(canonical, safe=""),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urlopen(request, timeout=8) as response:
            data = json.load(response)
        info["title"], info["channel"] = data.get("title"), data.get("author_name")
    except Exception:
        pass
    return info


LIBRARY_NAME = re.compile(r"^(?P<title>.*?) \[[\w-]{11}\](?: (?P<q>\d+)(?P<unit>kbps|p))?(?P<instrumental> \(Instrumental\))?\.(?P<ext>mp3|mp4)$")


def list_library():
    items = []
    if OUT_DIR.is_dir():
        for entry in OUT_DIR.iterdir():
            if entry.suffix.lower() not in (".mp3", ".mp4") or not entry.is_file():
                continue
            match = LIBRARY_NAME.match(entry.name)
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "title": (match["title"] + (" (Instrumental)" if match["instrumental"] else "")) if match else entry.stem,
                "kind": entry.suffix.lower().lstrip("."),
                "quality": (match["q"] + ("k" if match["unit"] == "kbps" else "p")) if match and match["q"] else "",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items[:100]


def reveal_in_finder(target=None):
    """Select a file in Finder or Explorer, or open the output folder when no file is given."""
    if WINDOWS:
        subprocess.run(["explorer", f"/select,{target}" if target else str(OUT_DIR)], check=False)
    else:
        subprocess.run(["open", "-R", str(target)] if target else ["open", str(OUT_DIR)], check=False)


def search_youtube(query):
    result = subprocess.run(
        [YTDLP, "--flat-playlist", "--dump-single-json", "--", f"ytsearch6:{query}"],
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip().splitlines()[-1] if result.stderr else "search failed")
    entries = json.loads(result.stdout).get("entries", [])
    return [
        {
            "id": e["id"], "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
            "duration": e.get("duration"), "url": f"https://www.youtube.com/watch?v={e['id']}",
            "thumbnail": f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg",
        }
        for e in entries if e.get("id")
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalConverter/1.0"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_allowed(self):
        # Guard against DNS rebinding: only answer for loopback host names.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self.host_allowed():
            return self.send_json({"error": "forbidden"}, 403)
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self.serve_file(ROOT / "index.html", "text/html; charset=utf-8")
        if path == "/api/settings":
            return self.send_json(load_settings())
        if path == "/api/library":
            return self.send_json({"items": list_library()})
        if path == "/api/info":
            url = parse_qs(parsed.query).get("url", [""])[0].strip()
            info = video_info(url) if is_youtube_url(url) else None
            return self.send_json(info, 200) if info else self.send_json({"error": "Not a single-video link."}, 400)
        if path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            if not query:
                return self.send_json({"error": "empty query"}, 400)
            try:
                return self.send_json({"results": search_youtube(query)})
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 502)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})", path)
        if match:
            job = JOBS.get(match.group(1))
            if not job:
                return self.send_json({"error": "unknown job"}, 404)
            return self.send_json({k: job.get(k) for k in ("state", "percent", "filename", "error")})
        if path.startswith("/files/"):
            name = Path(unquote(path[len("/files/"):])).name
            target = OUT_DIR / name
            if not name or not target.is_file():
                return self.send_json({"error": "not found"}, 404)
            return self.serve_file(target, "application/octet-stream", download_name=name)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.host_allowed():
            return self.send_json({"error": "forbidden"}, 403)
        if self.headers.get("Origin") and urlparse(self.headers["Origin"]).hostname not in ("127.0.0.1", "localhost"):
            return self.send_json({"error": "forbidden origin"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(min(length, 4096)) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "bad json"}, 400)
        if self.path == "/api/settings":
            return self.send_json(save_settings(data))
        if self.path == "/api/reveal":
            name = Path(str(data.get("name", ""))).name
            target = OUT_DIR / name if name else None
            if target and not target.is_file():
                return self.send_json({"error": "File not found."}, 404)
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            reveal_in_finder(target)
            return self.send_json({"ok": True})
        if self.path == "/api/jobs":
            url, fmt = str(data.get("url", "")).strip(), data.get("format")
            if fmt not in ("mp3", "mp4", "karaoke"):
                return self.send_json({"error": "format must be mp3, mp4 or karaoke"}, 400)
            if not is_youtube_url(url):
                return self.send_json({"error": "That is not a YouTube link."}, 400)
            allowed = VIDEO_HEIGHTS if fmt == "mp4" else AUDIO_KBPS
            quality = data.get("quality", DEFAULT_SETTINGS["video_height" if fmt == "mp4" else "audio_kbps"])
            if type(quality) is not int or quality not in allowed:
                return self.send_json({"error": f"quality must be one of {list(allowed)}"}, 400)
            if fmt == "karaoke" and not vocal_command():
                return self.send_json({"error": VOCAL_SETUP_HINT}, 503)
            job_id = uuid.uuid4().hex
            with JOBS_LOCK:
                JOBS[job_id] = {"state": "starting", "percent": 0}
            target = run_karaoke if fmt == "karaoke" else run_job
            args = (job_id, url, quality) if fmt == "karaoke" else (job_id, url, fmt, quality)
            threading.Thread(target=target, args=args, daemon=True).start()
            return self.send_json({"id": job_id}, 201)
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/cancel", self.path)
        if match and match.group(1) in JOBS:
            job = JOBS[match.group(1)]
            with JOBS_LOCK:
                if job["state"] not in ("done", "error", "cancelled"):
                    job["cancelled"] = True
                    if job.get("proc") and job["proc"].poll() is None:
                        job["proc"].terminate()
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def serve_file(self, path, content_type, download_name=None):
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        if download_name:
            ascii_name = download_name.encode("ascii", "ignore").decode() or "download"
            from urllib.parse import quote
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(download_name)}",
            )
        self.end_headers()
        with open(path, "rb") as handle:
            shutil.copyfileobj(handle, self.wfile)


def stop_all_jobs(*_):
    for job in list(JOBS.values()):
        proc = job.get("proc")
        if proc and proc.poll() is None:
            proc.terminate()
    os._exit(0)


def watch_parent():
    # When embedded in the Mac app, exit if the app disappears without stopping us.
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            stop_all_jobs()


def main():
    missing = [n for n, p in (("yt-dlp", YTDLP), ("ffmpeg", FFMPEG)) if not p]
    if missing:
        hint = "winget install yt-dlp.yt-dlp Gyan.FFmpeg" if WINDOWS else f"brew install {' '.join(missing)}"
        raise SystemExit(f"Missing: {', '.join(missing)}.\nInstall with: {hint}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)  # PORT=0 picks a free port
    signal.signal(signal.SIGTERM, stop_all_jobs)
    if os.environ.get("WATCH_PARENT"):
        threading.Thread(target=watch_parent, daemon=True).start()
    print(f"READY http://{HOST}:{httpd.server_address[1]}  (files saved to {OUT_DIR})", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
