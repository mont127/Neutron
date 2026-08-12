#!/bin/bash
# wrap the installer and a private unified wine into "Neutron Installer.app".
# the app is what you hand out; this repo stays wine-free.
#   build-app.sh <path-to-unified-wine> [output-dir]
# <path-to-unified-wine> is a wine build dir (has loader/wine and, built in,
# dlls/lsteamclient). it goes inside the app and is never committed here.
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
WINE_SRC="${1:-}"
OUT="${2:-$SELF/dist}"
[ -n "$WINE_SRC" ] || { echo "usage: build-app.sh <unified-wine-dir> [out]" >&2; exit 2; }
[ -x "$WINE_SRC/loader/wine" ] || { echo "not a wine build dir: $WINE_SRC" >&2; exit 1; }
[ -f "$WINE_SRC/dlls/lsteamclient/lsteamclient.so" ] || \
    echo "warning: no lsteamclient in that wine, bridge will be missing" >&2

APP="$OUT/Neutron Installer.app"
RES="$APP/Contents/Resources"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/installer/src" "$RES/installer/prebuilt" "$RES/wine-unified"

# installer sources
cp "$SELF/neutron" "$SELF/neutron-run" "$RES/installer/"
cp "$SELF/src/steam_stub.c" "$SELF/src/appinfo.py" "$SELF/src/vdf_launchopt.py" "$RES/installer/src/"
chmod +x "$RES/installer/neutron" "$RES/installer/neutron-run"

# prebuild the stub so the target needs no compiler
if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    x86_64-w64-mingw32-gcc -static -O2 -o "$RES/installer/prebuilt/steam.exe" "$SELF/src/steam_stub.c" -ladvapi32
    command -v i686-w64-mingw32-gcc >/dev/null && \
        i686-w64-mingw32-gcc -static -O2 -o "$RES/installer/prebuilt/steam32.exe" "$SELF/src/steam_stub.c" -ladvapi32
    echo "prebuilt steam stub"
else
    echo "warning: no mingw, app will need it on the target to build the stub" >&2
    rmdir "$RES/installer/prebuilt" 2>/dev/null || true
fi

# the private wine
echo "copying wine (this is the big part)..."
rsync -a "$WINE_SRC/" "$RES/wine-unified/"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Neutron Installer</string>
    <key>CFBundleDisplayName</key><string>Neutron Installer</string>
    <key>CFBundleIdentifier</key><string>com.mont127.neutron.installer</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>neutron-installer</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/neutron-installer" <<'LAUNCH'
#!/bin/bash
here="$(cd "$(dirname "$0")/../Resources" && pwd)"
export NEUTRON_BUNDLED_WINE="$here/wine-unified"
export NEUTRON_WINE_ZIP="$here/wine-unified-bundle.zip"
log="$HOME/Library/Logs/neutron-install.log"
mkdir -p "$(dirname "$log")"

osascript -e 'display dialog "Install Neutron? This sets up Windows-game support in your Steam library using the bundled wine engine." with title "Neutron" buttons {"Cancel","Install"} default button "Install"' >/dev/null 2>&1 || exit 0

if "$here/installer/neutron" install >"$log" 2>&1; then
    osascript -e 'display dialog "Neutron is installed. Quit Steam, then run: neutron add <appid> for each Windows game, or launch one that already has a Play button." with title "Neutron" buttons {"OK"} default button "OK"' >/dev/null 2>&1
else
    osascript -e 'display dialog "Install failed. See ~/Library/Logs/neutron-install.log" with title "Neutron" buttons {"OK"} default button "OK"' >/dev/null 2>&1
fi
LAUNCH
chmod +x "$APP/Contents/MacOS/neutron-installer"

echo "built: $APP"
