# Local Converter

Double-click `start.command` for the browser interface, or open
`dist/Local Converter.app` for the Mac app.

## Download

Get the latest build from the [Releases page](../../releases/latest). Windows install steps (in Thai) are in
[README-Windows.md](README-Windows.md).

- **LocalConverter-Setup.exe**: Windows installer. It needs no admin rights and installs to your user profile.
- **LocalConverter-Portable.exe**: a single Windows exe you can run without installing.
- **LocalConverter-mac.zip**: the Mac app. It needs `python3`, `yt-dlp` and `ffmpeg` from Homebrew.

The Windows builds bundle `yt-dlp` and `ffmpeg`. They open the converter in your browser and
keep a console window open while running; close that window to quit. Files save to
`Downloads\YT Converter`. Windows SmartScreen may warn about an unsigned app: choose
**More info → Run anyway**.

To publish a new release, push a version tag (`git tag v1.0.1 && git push --tags`). GitHub Actions
builds the Windows and Mac files and attaches them to the release. To build the Windows files by hand,
run `windows\build.ps1` on Windows.

## Cut vocal

Select **Cut vocal**, paste a YouTube link (or search for a song), choose an MP3
bitrate, and click Convert. The app saves `… (Instrumental).mp3` in
`~/Downloads/YT Converter` and lists it under Audio. It downloads the original
into a temporary folder, separates the singing, and keeps only the backing
track. Cancel stops processing and removes the temporary files.

The optional engine uses [Demucs](https://github.com/facebookresearch/demucs)
with the `htdemucs` model. Run `setup-vocals.command` once to install it. It needs
Python 3.12, 3.11, or 3.10; `brew install python@3.12` supplies a supported Python.
The model downloads on first use and is cached inside `.venv-vocals/models`.
Separation runs locally on the CPU and can take several minutes per song.
Some vocals, reverb, or audio artifacts may remain; results vary by recording.

Setup registers the engine in `~/Library/Application Support/Local Converter/vocal-engine.json`,
so the Mac app can also run from `~/Applications`. Keep the project's `.venv-vocals`
folder in place; if you move the project, run setup again to update its location.
You can also set `VOCAL_PYTHON` to the environment's `bin/python` path when launching
the server. MP3 and MP4 conversion use the
existing `yt-dlp` and `ffmpeg` installations and do not require the vocal engine.

Run offline pipeline checks with:

```sh
python3 -m unittest discover -s app/yt-converter -v
```
