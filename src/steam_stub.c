/* stand-in for the windows steam.exe. games and steam_api64.dll check the
 * registry for a live steam process before they will init; this writes that
 * state and stays resident so the pid keeps resolving while a game runs.
 * it does not draw anything. */

#include <windows.h>
#include <stdio.h>

#define FWD64 "C:\\Program Files (x86)\\Steam\\bin64\\steamclient.dll"

static void set_str(HKEY k, const char *name, const char *val)
{
    RegSetValueExA(k, name, 0, REG_SZ, (const BYTE *)val, (DWORD)strlen(val) + 1);
}

static void set_dword(HKEY k, const char *name, DWORD val)
{
    RegSetValueExA(k, name, 0, REG_DWORD, (const BYTE *)&val, sizeof(val));
}

static void win_dir_of_self(char *out, DWORD n)
{
    char path[MAX_PATH], *slash;
    GetModuleFileNameA(NULL, path, MAX_PATH);
    slash = strrchr(path, '\\');
    if (slash) *slash = 0;
    lstrcpynA(out, path, n);
}

int main(int argc, char **argv)
{
    HKEY steam, active;
    char dir[MAX_PATH], exe[MAX_PATH + 16];
    DWORD pid = GetCurrentProcessId();
    int stay = 1, i;

    for (i = 1; i < argc; i++)
    {
        if (!strcmp(argv[i], "--once")) stay = 0;
        /* steam:// urls just get swallowed, we have no ui to route them to */
        else if (!strncmp(argv[i], "steam://", 8)) return 0;
    }

    win_dir_of_self(dir, sizeof(dir));
    snprintf(exe, sizeof(exe), "%s\\steam.exe", dir);

    if (RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Valve\\Steam", 0, NULL, 0,
                        KEY_SET_VALUE, NULL, &steam, NULL) == ERROR_SUCCESS)
    {
        set_str(steam, "SteamPath", dir);
        set_str(steam, "SteamExe", exe);
        set_dword(steam, "BigPictureInForeground", 0);
        RegCloseKey(steam);
    }

    if (RegCreateKeyExA(HKEY_CURRENT_USER, "Software\\Valve\\Steam\\ActiveProcess", 0, NULL, 0,
                        KEY_SET_VALUE, NULL, &active, NULL) == ERROR_SUCCESS)
    {
        set_dword(active, "pid", pid);
        set_dword(active, "ActiveUser", 1);
        /* proton presents the bridge under steam's own name and path rather than
         * as lsteamclient.dll in system32. keep the same layout: a game (and
         * anything inspecting the process) then sees the module it expects. */
        /* a steam DRM game loads the path named here and then looks the module
         * back up as the literal "steamclient.dll" to reach
         * Steam_ReleaseThreadLocalMemory. GetModuleHandle only finds modules
         * that are already loaded, so the file this names has to itself be
         * called steamclient.dll, and it has to be the export forwarder rather
         * than the bridge: the bridge allocates its interface objects into the
         * .data of whatever module carries that name, so naming the bridge kills
         * its own globals. bin64 holds the 64-bit forwarder because the 32-bit
         * build already owns steamclient.dll in the Steam directory.
         * neutron stages a forwarder only when it could write one that matches
         * the bridge, so read the disk rather than assume: pointing this at a
         * file that is not there would take the 64-bit path down with it. */
        set_str(active, "SteamClientDll", "C:\\Program Files (x86)\\Steam\\steamclient.dll");
        set_str(active, "SteamClientDll64",
                GetFileAttributesA(FWD64) != INVALID_FILE_ATTRIBUTES
                    ? FWD64 : "C:\\Program Files (x86)\\Steam\\steamclient64.dll");
        set_str(active, "Universe", "Public");
        RegCloseKey(active);
    }

    printf("neutron steam stub, pid %lu, %s\n", pid, dir);
    fflush(stdout);

    if (!stay) return 0;
    for (;;) Sleep(3600 * 1000);
    return 0;
}
