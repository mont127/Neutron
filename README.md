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

## the policy: macOS first, Neutron for the rest

macOS Steam already downloads and runs a game's macOS build whenever it has one,
so Neutron never touches those — it leaves them to Steam. It only handles
Windows-only titles. It never forces Steam's platform to Windows globally, which
would drag native Mac games onto their Windows depots.

    neutron scan     classify installed games: native mac (Steam) vs neutron

`add` refuses a game that has a macOS build unless you pass `--force`, and
`install --all` wires only the Windows-only ones.

## install

The normal way is the `.app`: double-click it, click Install. It deploys the
bundled wine and wires up the runtime.

From a checkout (you supply your own wine build):

    NEUTRON_DEV_WINE=/path/to/wine/build64 ./neutron install
    ./neutron scan              # see what is native vs windows-only
    ./neutron get <appid>       # get a game the right way (see below)
    ./neutron status
    ./neutron uninstall

## getting a game

`neutron get <appid>` does one thing, the right way for the game:

- if the app has a macOS build, it tells Steam to install the native version and
  stops. macOS is always preferred.
- if it is Windows-only, it tells Steam to download the Windows version, then
  wires it to a Play button that runs through Neutron.

The Windows path needs Steam's platform pointed at Windows while it downloads.
That setting is global, so before flipping it `get` pauses auto-updates on every
other installed game (and restores them after) — otherwise Steam would pull their
Windows depots too. It runs in two steps, both with Steam quit:

    ./neutron get <appid>       # quit Steam; starts the windows download
    # confirm the install in Steam, let it finish, quit Steam again
    ./neutron get <appid>       # finishes: restores everything, wires the shortcut

Then restart Steam and launch "`<name> (Neutron)`" from your library. The wire
step finds the exe, drops a `steam_appid.txt` next to it so the game reports to
the right app, and writes a non-Steam shortcut that runs it through `neutron-run`.

For a Windows game whose files are already on disk, skip the download:

    ./neutron add <appid>                       # it is in your Steam library
    ./neutron add-exe "<name>" /path/to/game.exe [appid]   # anywhere else

All of these edit Steam config, so quit Steam first; originals are backed up
under `~/Library/Application Support/Neutron/steam-backup`.

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
    src/classify.py    per-app verdict + action over the installed library
    src/gameexe.py     resolves an installed app to its windows exe
    src/shortcuts.py   adds/removes non-steam shortcuts in shortcuts.vdf
    test/              standalone bringup checks (dev)

## the bridge

`lsteamclient` is a wine dll (Proton sources plus a macOS port: dylib loading,
wine 11 path helpers, minimal C++ support in the build). It lives in the wine
tree, not here, and ships inside the unified wine. Build it with
`make dlls/lsteamclient/all` in the wine `build64`.

## limits

- 64-bit games. The 32-bit side builds but has no wow64 thunks yet.
- A Windows-only game must be downloaded first, which needs Steam's platform
  briefly set to Windows (see `download` above). Don't let native Mac games
  update while that override is on, or Steam pulls their Windows depots too.
