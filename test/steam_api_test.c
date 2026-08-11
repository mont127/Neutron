/* drives a game-shipped steam_api64.dll against native Steam through the
 * bridge. run it after the steam stub is up so ActiveProcess resolves.
 * build: x86_64-w64-mingw32-gcc -static -O1 -o steam_api_test.exe steam_api_test.c */

#include <windows.h>
#include <stdio.h>
#include <stdint.h>

typedef int (__cdecl *init_t)(void);
typedef void (__cdecl *shutdown_t)(void);
typedef uint32_t (__cdecl *hsteam_t)(void);
typedef void (__cdecl *run_callbacks_t)(void);
typedef void *(__cdecl *internal_create_t)(const char *version);
typedef void *(__cdecl *get_iface_t)(void *client, uint32_t user, uint32_t pipe, const char *version);
typedef unsigned char (__cdecl *bool_t)(void *iface);
typedef uint64_t (__cdecl *u64_t)(void *iface);
typedef const char *(__cdecl *str_t)(void *iface);
typedef unsigned char (__cdecl *bool_u32_t)(void *iface, uint32_t appid);

#define SYM(t, n) ((t)GetProcAddress(mod, n))

int main(void)
{
    HMODULE mod;
    void *client, *iuser, *ifriends, *iapps;
    uint32_t user, pipe;
    uint64_t sid;
    unsigned char logged;
    int i;

    setvbuf(stdout, NULL, _IONBF, 0);

    mod = LoadLibraryA("steam_api64.dll");
    if (!mod) { printf("FAIL: LoadLibrary steam_api64.dll (%lu)\n", GetLastError()); return 1; }

    if (!SYM(init_t, "SteamAPI_Init")()) { printf("FAIL: SteamAPI_Init\n"); return 1; }
    printf("SteamAPI_Init: ok\n");

    user = SYM(hsteam_t, "SteamAPI_GetHSteamUser")();
    pipe = SYM(hsteam_t, "SteamAPI_GetHSteamPipe")();

    client = SYM(internal_create_t, "SteamInternal_CreateInterface")("SteamClient017");
    if (!client) { printf("FAIL: no ISteamClient\n"); return 1; }

    iuser = SYM(get_iface_t, "SteamAPI_ISteamClient_GetISteamUser")(client, user, pipe, "SteamUser019");
    ifriends = SYM(get_iface_t, "SteamAPI_ISteamClient_GetISteamFriends")(client, user, pipe, "SteamFriends017");
    iapps = SYM(get_iface_t, "SteamAPI_ISteamClient_GetISteamApps")(client, user, pipe, "STEAMAPPS_INTERFACE_VERSION008");
    if (!iuser) { printf("FAIL: no ISteamUser\n"); return 1; }

    logged = SYM(bool_t, "SteamAPI_ISteamUser_BLoggedOn")(iuser);
    sid = SYM(u64_t, "SteamAPI_ISteamUser_GetSteamID")(iuser);
    printf("BLoggedOn: %s\n", logged ? "true" : "false");
    printf("SteamID:   %llu\n", (unsigned long long)sid);
    if (ifriends)
        printf("Persona:   %s\n", SYM(str_t, "SteamAPI_ISteamFriends_GetPersonaName")(ifriends));
    if (iapps)
    {
        bool_u32_t sub = SYM(bool_u32_t, "SteamAPI_ISteamApps_BIsSubscribedApp");
        printf("owns 480:  %s\n", sub(iapps, 480) ? "true" : "false");
        printf("owns 730:  %s\n", sub(iapps, 730) ? "true" : "false");
    }

    for (i = 0; i < 10; i++) { SYM(run_callbacks_t, "SteamAPI_RunCallbacks")(); Sleep(50); }
    SYM(shutdown_t, "SteamAPI_Shutdown")();

    if (logged && sid) { printf("PASS\n"); return 0; }
    printf("PARTIAL: init ok but not logged on\n");
    return 2;
}
