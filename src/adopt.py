#!/usr/bin/env python3
# make steam treat an already-downloaded windows game as a real install, so its
# library page shows Play instead of a greyed Install: an appmanifest steam
# accepts, plus a launch target replaced by a shell script that hands the .exe
# to neutron-run.
#
#   adopt.py plan   <steam_dir> <appid>
#   adopt.py apply  <steam_dir> <appid> <game_dir> <neutron_run>
#   adopt.py revert <steam_dir> <appid>

import os
import shutil
import sys

import appinfo

SHIM = """#!/bin/bash
# neutron launcher. steam runs this, it hands the windows exe to wine.
exec {run} {exe} "$@"
"""


def meta(steam, appid):
    app = appinfo.load_appinfo(only_appids={appid}).get(appid)
    if not app:
        raise SystemExit("appid %d not in appinfo cache" % appid)
    common = app.get("common", {})
    config = app.get("config", {})
    depots = app.get("depots", {})
    branches = depots.get("branches", {})
    public = branches.get("public", {}) if isinstance(branches, dict) else {}

    launch = None
    for _, e in sorted((config.get("launch") or {}).items()):
        if not isinstance(e, dict):
            continue
        exe = e.get("executable")
        if not exe:
            continue
        osl = str((e.get("config") or {}).get("oslist", ""))
        # prefer an entry with no oslist (runs anywhere) else a windows one
        if launch is None or not osl:
            launch = e
        if not osl:
            break

    installed = {}
    for k, d in depots.items():
        if not k.isdigit() or not isinstance(d, dict):
            continue
        cfg = d.get("config") or {}
        if "windows" not in str(cfg.get("oslist", "")) and cfg.get("oslist"):
            continue
        pub = (d.get("manifests") or {}).get("public") or {}
        gid = pub.get("gid") if isinstance(pub, dict) else None
        if gid:
            installed[k] = (gid, int(pub.get("size") or 0))

    return {
        "name": common.get("name", str(appid)),
        "installdir": config.get("installdir") or common.get("name", str(appid)),
        "buildid": public.get("buildid", "0"),
        "exe": (launch or {}).get("executable", ""),
        "workingdir": (launch or {}).get("workingdir", ""),
        "depots": installed,
    }


def manifest_text(appid, m, size_on_disk, owner):
    depots = ""
    for depot, (gid, size) in sorted(m["depots"].items()):
        depots += ('\t\t"%s"\n\t\t{\n\t\t\t"manifest"\t\t"%s"\n\t\t\t"size"\t\t"%d"\n\t\t}\n'
                   % (depot, gid, size))
    return (
        '"AppState"\n{\n'
        '\t"appid"\t\t"%d"\n'
        '\t"universe"\t\t"1"\n'
        '\t"name"\t\t"%s"\n'
        '\t"StateFlags"\t\t"4"\n'
        '\t"installdir"\t\t"%s"\n'
        '\t"LastUpdated"\t\t"0"\n'
        '\t"SizeOnDisk"\t\t"%d"\n'
        '\t"StagingSize"\t\t"0"\n'
        '\t"buildid"\t\t"%s"\n'
        '\t"LastOwner"\t\t"%s"\n'
        '\t"UpdateResult"\t\t"0"\n'
        '\t"BytesToDownload"\t\t"0"\n'
        '\t"BytesDownloaded"\t\t"0"\n'
        '\t"BytesToStage"\t\t"0"\n'
        '\t"BytesStaged"\t\t"0"\n'
        '\t"TargetBuildID"\t\t"%s"\n'
        # 1 = only update when launched, so steam never tries to "repair" our
        # install behind our back
        '\t"AutoUpdateBehavior"\t\t"1"\n'
        '\t"AllowOtherDownloadsWhileRunning"\t\t"0"\n'
        '\t"ScheduledAutoUpdate"\t\t"0"\n'
        '\t"InstalledDepots"\n\t{\n%s\t}\n'
        '\t"UserConfig"\n\t{\n\t\t"language"\t\t"english"\n\t}\n'
        '}\n'
        % (appid, m["name"], m["installdir"], size_on_disk, m["buildid"], owner,
           m["buildid"], depots)
    )


def owner_id(steam):
    base = os.path.join(steam, "userdata")
    if os.path.isdir(base):
        for u in os.listdir(base):
            if u.isdigit() and u != "0":
                # steamID64 = accountid + 76561197960265728
                return str(int(u) + 76561197960265728)
    return "0"


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def main(argv):
    action, steam, appid = argv[1], argv[2], int(argv[3])
    m = meta(steam, appid)

    if action == "plan":
        print("name:        %s" % m["name"])
        print("installdir:  %s" % m["installdir"])
        print("buildid:     %s" % m["buildid"])
        print("launch exe:  %s" % m["exe"])
        print("depots:      %s" % ", ".join(m["depots"]))
        return 0

    common = os.path.join(steam, "steamapps", "common")
    target = os.path.join(common, m["installdir"])
    acf = os.path.join(steam, "steamapps", "appmanifest_%d.acf" % appid)

    if action == "revert":
        if os.path.exists(acf):
            os.remove(acf)
            print("removed %s" % acf)
        real = os.path.join(target, m["exe"] + ".neutron")
        shim = os.path.join(target, m["exe"])
        if os.path.exists(real):
            os.replace(real, shim)
            print("restored the real %s" % m["exe"])
        return 0

    game_dir, neutron_run = argv[4], argv[5]
    if not m["exe"]:
        raise SystemExit("no launch executable in appinfo for %d" % appid)

    os.makedirs(common, exist_ok=True)
    if os.path.abspath(game_dir) != os.path.abspath(target):
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.move(game_dir, target)
        print("moved game -> %s" % target)

    shim_path = os.path.join(target, m["exe"].replace("\\", "/"))
    os.makedirs(os.path.dirname(shim_path), exist_ok=True)
    real_path = shim_path + ".neutron"
    if not os.path.exists(real_path):
        if not os.path.exists(shim_path):
            raise SystemExit("launch exe %s not found under %s" % (m["exe"], target))
        os.replace(shim_path, real_path)

    with open(shim_path, "w") as f:
        f.write(SHIM.format(run=quote(neutron_run), exe=quote(real_path)))
    os.chmod(shim_path, 0o755)
    print("shim: %s -> %s" % (shim_path, real_path))

    with open(acf, "w") as f:
        f.write(manifest_text(appid, m, dir_size(target), owner_id(steam)))
    print("wrote %s" % acf)
    return 0


def quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    sys.exit(main(sys.argv))
