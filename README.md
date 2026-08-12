# Neutron

The proton mac never had.

<img width="220" height="217" alt="Logo" src="https://github.com/user-attachments/assets/099ab753-e42d-47a1-add6-0fc4549039b2" />


Neutron runs Windows Steam games on macOS through the native Steam client and a
custom unified wine, so there is no Windows Steam client in the loop. A game's
own `steam_api64.dll` talks to the real (arm64) Steam over a wine dll ported
from Proton that loads the x86_64 slice of `steamclient.dylib`; a small stub
`steam.exe` provides the running process the api checks for; Steam's Play button
runs a shim that launches the game under wine.

This repo is the installer only. The unified wine engine is shipped separately
inside a `.app` bundle and is not part of this source tree.

## why there is no native Install button (yet)

Proton is not a trick: Valve built compatibility-tool support into the Steam
client. A tool declares itself in `compatibilitytools.d/`, the client maps
app to tool in `CompatToolMapping`, and from then on the client itself offers
Install for Windows-only titles and launches them through the tool.

The macOS client ships that entire machinery — `CCompatManager`,
`CompatToolMapping`, `compatibilitytools.d`, the toolmanifest v2 loader, even the
string "Enable Steam Play for supported titles" — and its `compat_log.txt` has
real entries from older builds. On the current client it is dormant: register a
tool and map it correctly and the client round-trips the registry key but never
runs the compat manager, never writes `compat_log.txt`, and never renders the
Steam Play toggle (no JS in the macOS UI bundle references it). The
`-compat-disable-filtering` flag does not wake it either.

Neutron still registers itself as a proper compat tool, so if Valve ever turns
this on it works with no changes. Until then the Play button comes from a
non-Steam shortcut, which is what `add` sets up.

## the policy: macOS first, Neutron for the rest

macOS Steam already downloads and runs a game's macOS build whenever it has one,
so Neutron never touches those — it leaves them to Steam. It only handles
Windows-only titles. It never forces Steam's platform to Windows globally, which
would drag native Mac games onto their Windows depots.

    neutron scan     classify installed games: native mac (Steam) vs neutron

`add` refuses a game that has a macOS build unless you pass `--force`, and
`install --all` wires only the Windows-only ones.

## install

The normal way is the `.app` from the releases page: drag it to Applications,
right-click it and choose Open (it is not notarised, so a plain double-click
gets refused the first time), then click Install. It unpacks the bundled engine
once and wires up the runtime; after that the app is optional and only holds the
settings.

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

Three steps, because the engine is packed once and reused:

    ./build-wine-bundle.sh /path/to/unified-wine dist/wine-unified-bundle.zip
    ./build-ui.sh dist dist/wine-unified-bundle.zip
    ./build-dmg.sh 0.2

The wine build dir must have `loader/wine` and, built into it,
`dlls/lsteamclient`. `build-wine-bundle.sh` drops object files, static libs and
wine's per-dll test suites (about half the tree, none of it needed to run a
game) and copies `nls/` and `fonts/` for real rather than shipping the symlinks,
which would dangle on someone else's machine. The zip lands in the app's
Resources; the installer unpacks it on first run. Nothing here is committed to
this repo.

`build-app.sh` is the older variant that copies an unpacked wine into the
bundle instead of a zip; it still works but produces a much larger app.

The steam stub is prebuilt into the app so the target machine needs no compiler.
Sign last: anything written into the bundle after `codesign` breaks its seal,
which is why the installer sets `PYTHONDONTWRITEBYTECODE`.

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
