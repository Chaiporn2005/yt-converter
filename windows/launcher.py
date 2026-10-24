"""Windows entry point: start the converter, open it in the browser, and run until this window closes."""
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import server


def already_running(url):
    try:
        with socket.create_connection((server.HOST, server.PORT), timeout=1):
            pass
    except OSError:
        return False
    webbrowser.open(url)
    return True


def update_ytdlp():
    # YouTube changes often; keep the installed copy of yt-dlp current. The portable
    # exe unpacks a fresh copy on every launch, so there is nothing to update there.
    if server.YTDLP and Path(server.YTDLP).parent == Path(sys.executable).parent / "bin":
        subprocess.run([server.YTDLP, "-U"], capture_output=True, check=False)


def main():
    url = f"http://{server.HOST}:{server.PORT}"
    if already_running(url):
        return
    print("Local Converter is running. Close this window to quit.\n")
    threading.Thread(target=update_ytdlp, daemon=True).start()
    threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    try:
        server.main()
    except (SystemExit, OSError) as exc:
        print(exc)
        input("\nPress Enter to close.")


if __name__ == "__main__":
    main()
