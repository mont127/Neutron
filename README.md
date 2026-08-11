# Neutron

The proton mac never had.

Neutron runs Windows Steam games on macOS through the native Steam client and a
custom unified wine, so there is no Windows Steam client in the loop. A game's
own `steam_api64.dll` talks to the real (arm64) Steam over a wine dll ported
from Proton that loads the x86_64 slice of `steamclient.dylib`; a small stub
`steam.exe` provides the running process the api checks for; Steam's Play button
runs a shim that launches the game under wine.

This repo is the installer only. The unified wine engine is shipped separately
inside a `.app` bundle and is not part of this source tree.

## install

The normal way is the `.app`: double-click it, click Install. It deploys the
bundled wine and wires up the runtime.

From a checkout (you supply your own wine build):

    NEUTRON_DEV_WINE=/path/to/wine/build64 ./neutron install
    ./neutron add <appid>       # quit Steam first
    ./neutron status
    ./neutron uninstall

`add`/`remove` edit Steam's `localconfig.vdf`, so quit Steam before running them
— it rewrites that file on exit. Originals are backed up under
`~/Library/Application Support/Neutron/steam-backup`.

## building the .app

    ./build-app.sh /path/to/unified-wine [output-dir]

The wine build dir must have `loader/wine` and, built into it,
`dlls/lsteamclient`. It is copied into `Neutron Installer.app` and never touches
this repo. The steam stub is prebuilt into the app so the target machine needs
no compiler.

## layout

    neutron            the installer
    neutron-run        the launch shim Steam calls per game
    build-app.sh       wraps the installer + a private wine into a .app
    src/steam_stub.c   the stub steam.exe
    src/appinfo.py     reads appinfo.vdf: native-mac vs windows-only
    src/vdf_launchopt.py   sets/clears LaunchOptions in localconfig.vdf
    test/              standalone bringup checks (dev)

## the bridge

`lsteamclient` is a wine dll (Proton sources plus a macOS port: dylib loading,
wine 11 path helpers, minimal C++ support in the build). It lives in the wine
tree, not here, and ships inside the unified wine. Build it with
`make dlls/lsteamclient/all` in the wine `build64`.

## limits

- 64-bit games. The 32-bit side builds but has no wow64 thunks yet.
- Steam shows a Play button for a Windows-only title only once it has a macOS
  launch entry. Games already present for macOS, or installed via the
  platform-override trick, launch cleanly; injecting that entry for a pure
  Windows-only app is not automated here yet.
