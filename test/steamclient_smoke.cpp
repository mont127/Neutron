// dlopens the native steamclient.dylib and talks to the running arm64 steam
// over IPC, no wine involved. proves an x86_64 rosetta process can drive the
// arm64 client. we hand-declare only the vtable slots we call.
//   clang++ -arch x86_64 -std=c++17 -O1 -o smoke_x86_64 steamclient_smoke.cpp
//   clang++ -arch arm64  -std=c++17 -O1 -o smoke_arm64  steamclient_smoke.cpp

#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <unistd.h>
#include <signal.h>
#include <sys/sysctl.h>

typedef uint32_t HSteamPipe;
typedef uint32_t HSteamUser;
typedef uint32_t AppId_t;

struct SteamIPAddress_t { uint8_t pad[20]; };

class ISteamClient {
public:
    virtual HSteamPipe CreateSteamPipe() = 0;                                            // 0
    virtual bool BReleaseSteamPipe(HSteamPipe pipe) = 0;                                 // 1
    virtual HSteamUser ConnectToGlobalUser(HSteamPipe pipe) = 0;                         // 2
    virtual HSteamUser CreateLocalUser(HSteamPipe *pipe, int account_type) = 0;          // 3
    virtual void ReleaseUser(HSteamPipe pipe, HSteamUser user) = 0;                      // 4
    virtual void *GetISteamUser(HSteamUser, HSteamPipe, const char *) = 0;               // 5
    virtual void *GetISteamGameServer(HSteamUser, HSteamPipe, const char *) = 0;         // 6
    virtual void SetLocalIPBinding(const SteamIPAddress_t &, uint16_t) = 0;              // 7
    virtual void *GetISteamFriends(HSteamUser, HSteamPipe, const char *) = 0;            // 8
    virtual void *GetISteamUtils(HSteamPipe, const char *) = 0;                          // 9
    virtual void *GetISteamMatchmaking(HSteamUser, HSteamPipe, const char *) = 0;        // 10
    virtual void *GetISteamMatchmakingServers(HSteamUser, HSteamPipe, const char *) = 0; // 11
    virtual void *GetISteamGenericInterface(HSteamUser, HSteamPipe, const char *) = 0;   // 12
};

class ISteamUser {
public:
    virtual HSteamUser GetHSteamUser() = 0;   // 0
    virtual bool BLoggedOn() = 0;             // 1
    // CSteamID is one packed uint64 with only trivial members, so clang on both
    // sides returns it in rax -- declaring it as uint64_t here matches the ABI
    virtual uint64_t GetSteamID() = 0;        // 2
};

class ISteamFriends {
public:
    virtual const char *GetPersonaName() = 0; // 0
};

class ISteamApps {
public:
    virtual bool BIsSubscribed() = 0;                     // 0
    virtual bool BIsLowViolence() = 0;                    // 1
    virtual bool BIsCybercafe() = 0;                      // 2
    virtual bool BVACBanned() = 0;                        // 3
    virtual const char *GetCurrentGameLanguage() = 0;     // 4
    virtual const char *GetAvailableGameLanguages() = 0;  // 5
    virtual bool BIsSubscribedApp(AppId_t appid) = 0;     // 6
};

static const char *k_default_suffix =
    "/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/steamclient.dylib";

// a hung IPC handshake is a real failure mode here, so bound every run
static void on_alarm(int)
{
    const char msg[] = "\nRESULT: TIMEOUT - a steamclient call hung for 45s\n";
    write(2, msg, sizeof(msg) - 1);
    _exit(3);
}

static void *get_iface(ISteamClient *client, HSteamUser user, HSteamPipe pipe,
                       const char *const *vers, size_t n, const char **picked)
{
    for (size_t i = 0; i < n; i++) {
        void *p = client->GetISteamGenericInterface(user, pipe, vers[i]);
        if (p) { if (picked) *picked = vers[i]; return p; }
    }
    if (picked) *picked = NULL;
    return NULL;
}

int main()
{
    setbuf(stdout, NULL);
    signal(SIGALRM, on_alarm);
    alarm(45);

#if defined(__x86_64__)
    const char *arch = "x86_64";
#elif defined(__arm64__) || defined(__aarch64__)
    const char *arch = "arm64";
#else
    const char *arch = "unknown";
#endif
    int translated = 0;
    size_t sz = sizeof(translated);
    if (sysctlbyname("sysctl.proc_translated", &translated, &sz, NULL, 0) != 0)
        translated = -1;
    printf("probe: arch=%s rosetta=%d pid=%d\n", arch, translated, (int)getpid());

    char default_path[1024];
    const char *path = getenv("STEAMCLIENT_DYLIB");
    if (!path) {
        const char *home = getenv("HOME");
        snprintf(default_path, sizeof(default_path), "%s%s", home ? home : "", k_default_suffix);
        path = default_path;
    }
    printf("dlopen %s ...\n", path);
    void *h = dlopen(path, RTLD_NOW);
    if (!h) { printf("RESULT: FAIL dlopen: %s\n", dlerror()); return 1; }
    printf("dlopen: OK\n");

    typedef void *(*CreateInterfaceFn)(const char *, int *);
    CreateInterfaceFn create_interface = (CreateInterfaceFn)dlsym(h, "CreateInterface");
    if (!create_interface) { printf("RESULT: FAIL dlsym CreateInterface: %s\n", dlerror()); return 1; }
    printf("dlsym CreateInterface: OK\n");

    const char *client_vers[] = { "SteamClient020", "SteamClient021" };
    ISteamClient *client = NULL;
    const char *client_ver = NULL;
    for (const char *v : client_vers) {
        client = (ISteamClient *)create_interface(v, NULL);
        if (client) { client_ver = v; break; }
    }
    if (!client) { printf("RESULT: FAIL CreateInterface returned null for SteamClient020/021\n"); return 1; }
    printf("CreateInterface(%s): OK (%p)\n", client_ver, (void *)client);

    printf("CreateSteamPipe ...\n");
    HSteamPipe pipe = client->CreateSteamPipe();
    printf("CreateSteamPipe: %u %s\n", pipe, pipe ? "OK" : "FAIL");
    if (!pipe) { printf("RESULT: FAIL no pipe (is native Steam running?)\n"); return 1; }

    printf("ConnectToGlobalUser ...\n");
    HSteamUser user = client->ConnectToGlobalUser(pipe);
    printf("ConnectToGlobalUser: %u %s\n", user, user ? "OK" : "FAIL");
    if (!user) {
        client->BReleaseSteamPipe(pipe);
        printf("RESULT: FAIL no global user (Steam not logged in yet?)\n");
        return 1;
    }

    const char *picked = NULL;
    const char *user_vers[] = { "SteamUser023", "SteamUser022", "SteamUser021" };
    ISteamUser *iuser = (ISteamUser *)get_iface(client, user, pipe, user_vers, 3, &picked);
    if (!iuser) { printf("RESULT: FAIL no ISteamUser (tried 023/022/021)\n"); return 1; }
    printf("ISteamUser (%s): OK\n", picked);

    bool logged = iuser->BLoggedOn();
    uint64_t sid = iuser->GetSteamID();
    printf("BLoggedOn:   %s\n", logged ? "true" : "false");
    printf("SteamID:     %llu\n", (unsigned long long)sid);

    const char *friends_vers[] = { "SteamFriends017", "SteamFriends016", "SteamFriends015" };
    ISteamFriends *ifriends = (ISteamFriends *)get_iface(client, user, pipe, friends_vers, 3, &picked);
    if (ifriends) {
        const char *name = ifriends->GetPersonaName();
        printf("PersonaName: %s  (via %s)\n", name ? name : "(null)", picked);
    } else {
        printf("ISteamFriends: not available (non-fatal)\n");
    }

    const char *apps_vers[] = { "STEAMAPPS_INTERFACE_VERSION008", "STEAMAPPS_INTERFACE_VERSION007" };
    ISteamApps *iapps = (ISteamApps *)get_iface(client, user, pipe, apps_vers, 2, &picked);
    if (iapps) {
        printf("BIsSubscribedApp(730 CS2):     %s\n", iapps->BIsSubscribedApp(730) ? "true" : "false");
        printf("BIsSubscribedApp(1174180 RDR2): %s\n", iapps->BIsSubscribedApp(1174180) ? "true" : "false");
    } else {
        printf("ISteamApps: not available (non-fatal)\n");
    }

    client->ReleaseUser(pipe, user);
    client->BReleaseSteamPipe(pipe);

    if (logged && sid) {
        printf("\nRESULT: PASS - %s probe talked to native Steam over steamclient IPC\n", arch);
        return 0;
    }
    printf("\nRESULT: PARTIAL - IPC works but user not logged on\n");
    return 2;
}
