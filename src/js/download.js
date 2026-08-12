// run download_depot on the already-running steam client, so a game can install
// itself while steam is up. returns immediately, the caller polls the console log.
(async () => {
    if (!window.SteamClient || !SteamClient.Console) return "no SteamClient.Console";
    await SteamClient.Console.ExecCommand("download_depot __APPID__ __DEPOT__ __MANIFEST__");
    return "download_depot sent";
})()
