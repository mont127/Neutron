// ask steam to plan and run a normal install for an appid, with the client
// briefly told to compute the plan as windows. steam still owns the download,
// the appmanifest, verification and updates.
(async () => {
    const APPID = __APPID__;
    const out = [];
    const info = () => SteamClient.Installs.GetInstallManagerInfo();

    const before = await info();
    if (before.currentAppID !== 0) {
        return "busy: another install is active (appid " + before.currentAppID + ")";
    }

    await SteamClient.Console.ExecCommand("@sSteamCmdForcePlatformType windows");
    out.push("platform=windows");

    try {
        await SteamClient.Installs.OpenInstallWizard([APPID]);
        out.push("wizard opened");

        // wait for steam to produce a plan (or refuse)
        let plan = null;
        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 500));
            plan = await info();
            if (plan.eAppError !== 0) break;
            if (plan.currentAppID === APPID && plan.nDiskSpaceRequired > 0) break;
        }
        out.push("appError=" + plan.eAppError +
                 " errorDetail=" + (plan.errorDetail || "-") +
                 " currentAppID=" + plan.currentAppID +
                 " bytesRequired=" + plan.nDiskSpaceRequired +
                 " installState=" + plan.eInstallState);

        if (plan.eAppError === 0 && plan.nDiskSpaceRequired > 0) {
            await SteamClient.Installs.ContinueInstall();
            out.push("ContinueInstall sent");
        }
    } catch (e) {
        out.push("threw: " + e);
    } finally {
        await SteamClient.Console.ExecCommand("@sSteamCmdForcePlatformType macos");
        out.push("platform=macos restored");
    }
    return out.join(" | ");
})()
