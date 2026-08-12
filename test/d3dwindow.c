/* presents magenta, then reads the pixels back out of the WINDOW with GDI.
 * the readback probe proves the gpu drew into the backbuffer; this asks the
 * separate question of whether that surface ever reached the window. compare
 * backends: a backend that draws but shows black fails here and passes there.
 * build: x86_64-w64-mingw32-gcc -O1 -o d3dwindow.exe d3dwindow.c \
 *        -ld3d11 -ldxgi -luser32 -lgdi32 -luuid */

#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <stdio.h>

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(h, m, w, l);
}

int main(void)
{
    WNDCLASSA wc;
    HWND win;
    DXGI_SWAP_CHAIN_DESC sd;
    IDXGISwapChain *swap = NULL;
    ID3D11Device *dev = NULL;
    ID3D11DeviceContext *ctx = NULL;
    ID3D11Texture2D *back = NULL;
    ID3D11RenderTargetView *rtv = NULL;
    D3D_FEATURE_LEVEL got = 0;
    const float magenta[4] = { 1.0f, 0.0f, 1.0f, 1.0f };
    HRESULT hr;
    int frame;
    HDC dc;
    COLORREF c;

    setvbuf(stdout, NULL, _IONBF, 0);

    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "neutronwin";
    RegisterClassA(&wc);
    win = CreateWindowExA(0, "neutronwin", "neutron window probe", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                          100, 100, 320, 240, NULL, NULL, wc.hInstance, NULL);
    if (!win) { printf("CreateWindow FAILED\n"); return 2; }

    memset(&sd, 0, sizeof(sd));
    sd.BufferDesc.Width = 320;
    sd.BufferDesc.Height = 240;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.OutputWindow = win;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
                                       D3D11_SDK_VERSION, &sd, &swap, &dev, &got, &ctx);
    if (FAILED(hr)) { printf("CreateDeviceAndSwapChain 0x%08lx FAILED\n", (unsigned long)hr); return 2; }

    hr = IDXGISwapChain_GetBuffer(swap, 0, &IID_ID3D11Texture2D, (void **)&back);
    if (FAILED(hr)) { printf("GetBuffer FAILED\n"); return 2; }
    hr = ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &rtv);
    if (FAILED(hr)) { printf("CreateRenderTargetView FAILED\n"); return 2; }

    for (frame = 0; frame < 120; frame++) {
        MSG msg;
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageA(&msg);
        }
        ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &rtv, NULL);
        ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, magenta);
        IDXGISwapChain_Present(swap, 1, 0);
        Sleep(8);
    }

    dc = GetDC(win);
    c = GetPixel(dc, 160, 120);
    printf("window centre pixel: R=%u G=%u B=%u  %s\n",
           GetRValue(c), GetGValue(c), GetBValue(c),
           (GetRValue(c) > 200 && GetGValue(c) < 70 && GetBValue(c) > 200)
               ? "MAGENTA, the surface reached the window"
               : "NOT magenta, nothing reached the window");
    ReleaseDC(win, dc);
    return 0;
}
