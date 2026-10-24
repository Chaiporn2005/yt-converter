#!/bin/bash
# Builds dist/Local Converter.app. Needs the Xcode command line tools (swiftc, iconutil).
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
APP="$ROOT/dist/Local Converter.app"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

swiftc -O -swift-version 5 -o "$APP/Contents/MacOS/LocalConverter" main.swift
cp Info.plist "$APP/Contents/Info.plist"
cp "$ROOT/server.py" "$ROOT/index.html" "$APP/Contents/Resources/"

swift make_icon.swift "$WORK/AppIcon.iconset"
iconutil -c icns "$WORK/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"

codesign --force --sign - "$APP"
echo "Built: $APP"
