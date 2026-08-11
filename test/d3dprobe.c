/* checks the graphics dlls actually load in the prefix. before the mnc-d3d pack
 * was staged these all failed with 126 (module not found) and no dx game could
 * start. build: x86_64-w64-mingw32-gcc -static -O1 -o d3dprobe.exe d3dprobe.c */

#include <windows.h>
#include <stdio.h>

int main(void)
{
    const char *dlls[] = { "lsteamclient.dll", "dxgi.dll", "d3d11.dll",
                           "d3d10core.dll", "d3d12.dll", "d3d9.dll" };
    int i, ok = 0;

    setvbuf(stdout, NULL, _IONBF, 0);
    for (i = 0; i < (int)(sizeof(dlls) / sizeof(dlls[0])); i++)
    {
        HMODULE m = LoadLibraryA(dlls[i]);
        if (m) { printf("  %-18s loaded\n", dlls[i]); ok++; }
        else   { printf("  %-18s FAILED (gle %lu)\n", dlls[i], GetLastError()); }
    }
    printf("%d/%d loaded\n", ok, i);
    return ok == i ? 0 : 1;
}
