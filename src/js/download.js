// run download_depot on the ALREADY-RUNNING steam client, so a game can install
// itself while steam is up (e.g. when launched from a shortcut). no restart, no
// platform override. returns immediately; the caller polls the console log.
(async () => {
    if (!window.SteamClient || !SteamClient.Console) return "no SteamClient.Console";
    await SteamClient.Console.ExecCommand("download_depot __APPID__ __DEPOT__ __MANIFEST__");
    return "download_depot sent";
})()
