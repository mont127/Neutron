#!/bin/bash
# build Neutron.app - the window you use to install windows games. steam still
# owns Play; this owns everything before it.
#   build-ui.sh [output-dir] [wine-bundle.zip]
# with a zip the app is self-contained: it unpacks the engine on first install
# and can be deleted afterwards. without one the app expects a wine already on
# the machine (a macndcheese install, or a dev tree).
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$SELF/dist}"
WINE_ZIP="${2:-}"
APP="$OUT/Neutron.app"

command -v swiftc >/dev/null || { echo "need swiftc (xcode command line tools)" >&2; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/installer/src"

swiftc -O -parse-as-library -o "$APP/Contents/MacOS/Neutron" "$SELF/ui/NeutronApp.swift"

cp "$SELF/neutron" "$SELF/neutron-run" "$APP/Contents/Resources/installer/"
# everything under src/ ships: the launch shim, the watcher, the LaunchAgent
# plist and the js all get installed from there at some point
rsync -a --exclude='__pycache__' "$SELF/src/" "$APP/Contents/Resources/installer/src/"
chmod +x "$APP/Contents/Resources/installer/neutron" \
         "$APP/Contents/Resources/installer/neutron-run" \
         "$APP/Contents/Resources/installer/src/neutron-launch" \
         "$APP/Contents/Resources/installer/src/neutron-play" \
         "$APP/Contents/Resources/installer/src/neutron-watch" \
         "$APP/Contents/Resources/installer/src/compat-entry" 2>/dev/null || true

# prebuild the steam stub so the target machine needs no compiler
if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    mkdir -p "$APP/Contents/Resources/installer/prebuilt"
    x86_64-w64-mingw32-gcc -static -O2 \
        -o "$APP/Contents/Resources/installer/prebuilt/steam.exe" \
        "$SELF/src/steam_stub.c" -ladvapi32
    command -v i686-w64-mingw32-gcc >/dev/null && \
        i686-w64-mingw32-gcc -static -O2 \
            -o "$APP/Contents/Resources/installer/prebuilt/steam32.exe" \
            "$SELF/src/steam_stub.c" -ladvapi32
    echo "  prebuilt steam stub"
fi

if [ -n "$WINE_ZIP" ]; then
    [ -f "$WINE_ZIP" ] || { echo "no such wine bundle: $WINE_ZIP" >&2; exit 1; }
    echo "  adding engine ($(du -h "$WINE_ZIP" | cut -f1)), this takes a minute"
    cp "$WINE_ZIP" "$APP/Contents/Resources/wine-unified-bundle.zip"
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Neutron</string>
    <key>CFBundleDisplayName</key><string>Neutron</string>
    <key>CFBundleIdentifier</key><string>com.mont127.neutron</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>Neutron</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict>
PLIST
echo "</plist>" >> "$APP/Contents/Info.plist"

# sign last, after every resource is in place - anything written into the
# bundle afterwards invalidates the seal
find "$APP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (unsigned, fine for local use)"
codesign --verify --deep "$APP" 2>&1 && echo "  signature ok"
echo "built: $APP"
