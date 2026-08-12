/* Says which renderer is really answering: creates a real D3D11 device and
 * prints the adapter DXGI reports. D3DMetal, DXMT and DXVK describe the GPU
 * differently, so this tells them apart where a dll listing cannot.
 * build: x86_64-w64-mingw32-gcc -static -O1 -o d3dinfo.exe d3dinfo.c */

#include <windows.h>
#include <stdio.h>

typedef struct { UINT p1, p2, p3, p4; } GUID_T;

typedef HRESULT (WINAPI *pCreateDXGIFactory)(const void *riid, void **ppFactory);
typedef HRESULT (WINAPI *pD3D11CreateDevice)(void *adapter, int driverType, HMODULE soft,
        UINT flags, const UINT *levels, UINT nlevels, UINT sdk,
        void **dev, UINT *level, void **ctx);

/* IID_IDXGIFactory */
static const GUID IID_Factory = {0x7b7166ec,0x21c7,0x44ae,{0xb2,0x1a,0xc9,0xae,0x32,0x1a,0xe3,0x69}};

typedef struct DXGI_ADAPTER_DESC_ {
    WCHAR Description[128];
    UINT VendorId, DeviceId, SubSysId, Revision;
    SIZE_T DedicatedVideoMemory, DedicatedSystemMemory, SharedSystemMemory;
    LUID AdapterLuid;
} DXGI_ADAPTER_DESC_;

int main(void)
{
    HMODULE dxgi, d3d11;
    pCreateDXGIFactory mkFactory;
    pD3D11CreateDevice mkDevice;
    void *factory = NULL, *adapter = NULL, *dev = NULL, *ctx = NULL;
    UINT level = 0;
    HRESULT hr;

    setvbuf(stdout, NULL, _IONBF, 0);

    dxgi = LoadLibraryA("dxgi.dll");
    d3d11 = LoadLibraryA("d3d11.dll");
    if (!dxgi || !d3d11) { printf("load failed dxgi=%p d3d11=%p\n", dxgi, d3d11); return 1; }

    mkFactory = (pCreateDXGIFactory)GetProcAddress(dxgi, "CreateDXGIFactory");
    mkDevice = (pD3D11CreateDevice)GetProcAddress(d3d11, "D3D11CreateDevice");
    if (!mkFactory || !mkDevice) { printf("missing entry points\n"); return 1; }

    hr = mkFactory(&IID_Factory, &factory);
    printf("CreateDXGIFactory: 0x%08lx\n", (unsigned long)hr);
    if (SUCCEEDED(hr) && factory) {
        void **vt = *(void ***)factory;
        HRESULT (WINAPI *EnumAdapters)(void *, UINT, void **) = vt[7];
        if (EnumAdapters(factory, 0, &adapter) == 0 && adapter) {
            void **avt = *(void ***)adapter;
            HRESULT (WINAPI *GetDesc)(void *, DXGI_ADAPTER_DESC_ *) = avt[8];
            DXGI_ADAPTER_DESC_ d;
            memset(&d, 0, sizeof(d));
            if (GetDesc(adapter, &d) == 0)
                printf("adapter:  %ls\n  vendor 0x%04x device 0x%04x vram %lu MB\n",
                       d.Description, d.VendorId, d.DeviceId,
                       (unsigned long)(d.DedicatedVideoMemory >> 20));
        }
    }

    hr = mkDevice(NULL, 1 /*HARDWARE*/, NULL, 0, NULL, 0, 7 /*SDK*/, &dev, &level, &ctx);
    printf("D3D11CreateDevice: 0x%08lx  featurelevel 0x%04x  %s\n",
           (unsigned long)hr, level, SUCCEEDED(hr) ? "OK" : "FAILED");
    return SUCCEEDED(hr) ? 0 : 2;
}
