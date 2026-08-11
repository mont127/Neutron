/* drives ISteamClient directly through lsteamclient.dll, no steam_api, no
 * windows steam. the early bringup check before the proton wrappers were in.
 * build: x86_64-w64-mingw32-gcc -static -O1 -o steam_test.exe steam_test.c
 * run:   wine steam_test.exe [c:\steamclient64.dll]   (native steam up) */

#include <windows.h>
#include <stdio.h>
#include <stdint.h>

typedef void *(__cdecl *CreateInterface_t)( const char *name, int *return_code );

#define VT(obj) (*(void ***)(obj))

typedef uint32_t (*client_CreateSteamPipe_t)( void *self );
typedef unsigned char (*client_BReleaseSteamPipe_t)( void *self, uint32_t pipe );
typedef uint32_t (*client_ConnectToGlobalUser_t)( void *self, uint32_t pipe );
typedef void (*client_ReleaseUser_t)( void *self, uint32_t pipe, uint32_t user );
typedef void * (*client_GetISteamGenericInterface_t)( void *self, uint32_t user, uint32_t pipe, const char *version );
typedef unsigned char (*user_BLoggedOn_t)( void *self );
/* msvc x64 returns CSteamID through a hidden pointer param (it has ctors) */
typedef uint64_t * (*user_GetSteamID_t)( void *self, uint64_t *ret );
typedef const char * (*friends_GetPersonaName_t)( void *self );
typedef unsigned char (*apps_BIsSubscribedApp_t)( void *self, uint32_t appid );

int main( int argc, char **argv )
{
    const char *dll = argc > 1 ? argv[1] : "lsteamclient.dll";
    HMODULE mod;
    CreateInterface_t create_interface;
    void *client, *iuser, *ifriends, *iapps;
    uint32_t pipe, user;
    uint64_t sid = 0;
    unsigned char logged;

    setvbuf( stdout, NULL, _IONBF, 0 );
    printf( "steam_test: loading %s\n", dll );

    mod = LoadLibraryA( dll );
    if (!mod) { printf( "RESULT: FAIL LoadLibrary (gle %lu)\n", GetLastError() ); return 1; }

    create_interface = (CreateInterface_t)GetProcAddress( mod, "CreateInterface" );
    if (!create_interface) { printf( "RESULT: FAIL no CreateInterface export\n" ); return 1; }

    client = create_interface( "SteamClient020", NULL );
    if (!client) { printf( "RESULT: FAIL CreateInterface(SteamClient020)\n" ); return 1; }
    printf( "CreateInterface(SteamClient020): OK\n" );

    pipe = ((client_CreateSteamPipe_t)VT(client)[0])( client );
    printf( "CreateSteamPipe: %u %s\n", pipe, pipe ? "OK" : "FAIL" );
    if (!pipe) { printf( "RESULT: FAIL no pipe (native Steam not running?)\n" ); return 1; }

    user = ((client_ConnectToGlobalUser_t)VT(client)[2])( client, pipe );
    printf( "ConnectToGlobalUser: %u %s\n", user, user ? "OK" : "FAIL" );
    if (!user) { printf( "RESULT: FAIL no global user (not logged in?)\n" ); return 1; }

    iuser = ((client_GetISteamGenericInterface_t)VT(client)[12])( client, user, pipe, "SteamUser023" );
    if (!iuser) { printf( "RESULT: FAIL no ISteamUser\n" ); return 1; }

    logged = ((user_BLoggedOn_t)VT(iuser)[1])( iuser );
    printf( "BLoggedOn:     %s\n", logged ? "true" : "false" );

    ((user_GetSteamID_t)VT(iuser)[2])( iuser, &sid );
    printf( "SteamID:       %llu\n", (unsigned long long)sid );

    ifriends = ((client_GetISteamGenericInterface_t)VT(client)[12])( client, user, pipe, "SteamFriends017" );
    if (ifriends)
        printf( "PersonaName:   %s\n", ((friends_GetPersonaName_t)VT(ifriends)[0])( ifriends ) );
    else
        printf( "PersonaName:   (no ISteamFriends)\n" );

    iapps = ((client_GetISteamGenericInterface_t)VT(client)[12])( client, user, pipe, "STEAMAPPS_INTERFACE_VERSION008" );
    if (iapps)
    {
        printf( "BIsSubscribedApp(730):     %s\n",
                ((apps_BIsSubscribedApp_t)VT(iapps)[6])( iapps, 730 ) ? "true" : "false" );
        printf( "BIsSubscribedApp(1174180): %s\n",
                ((apps_BIsSubscribedApp_t)VT(iapps)[6])( iapps, 1174180 ) ? "true" : "false" );
    }
    else printf( "ISteamApps:    (not available)\n" );

    ((client_ReleaseUser_t)VT(client)[4])( client, pipe, user );
    ((client_BReleaseSteamPipe_t)VT(client)[1])( client, pipe );

    if (logged && sid)
    {
        printf( "\nRESULT: PASS - wine PE code reached native Steam through the Neutron bridge\n" );
        return 0;
    }
    printf( "\nRESULT: PARTIAL - bridge works but user not logged on\n" );
    return 2;
}
