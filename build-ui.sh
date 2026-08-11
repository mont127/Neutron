#!/bin/bash
# build Neutron.app - the window you use to install windows games. steam still
# owns Play; this owns everything before it.
#   build-ui.sh [output-dir]
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$SELF/dist}"
APP="$OUT/Neutron.app"

command -v swiftc >/dev/null || { echo "need swiftc (xcode command line tools)" >&2; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/installer/src"

swiftc -O -parse-as-library -o "$APP/Contents/MacOS/Neutron" "$SELF/ui/NeutronApp.swift"

cp "$SELF/neutron" "$SELF/neutron-run" "$APP/Contents/Resources/installer/"
cp "$SELF/src"/*.py "$SELF/src/neutron-launch" "$APP/Contents/Resources/installer/src/"
mkdir -p "$APP/Contents/Resources/installer/src/js"
cp "$SELF/src/js"/*.js "$APP/Contents/Resources/installer/src/js/" 2>/dev/null || true
chmod +x "$APP/Contents/Resources/installer/neutron" "$APP/Contents/Resources/installer/neutron-run"

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

codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (unsigned, fine for local use)"
echo "built: $APP"
