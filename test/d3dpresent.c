/* creates a real window, swapchain and render target, clears it and presents.
 * d3dinfo only makes a device, which is why it called a backend working while
 * a game using the same backend showed a black screen: presentation is a
 * separate path. this exercises it and says which step fails.
 * build: x86_64-w64-mingw32-gcc -O1 -o d3dpresent.exe d3dpresent.c \
 *        -ld3d11 -ldxgi -luser32 -lgdi32 */

#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <stdio.h>

#define STEP(hr, what) do { \
    printf("%-28s 0x%08lx %s\n", what, (unsigned long)(hr), \
           SUCCEEDED(hr) ? "ok" : "FAILED"); \
    if (FAILED(hr)) return 2; \
} while (0)

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

    setvbuf(stdout, NULL, _IONBF, 0);

    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "neutronprobe";
    RegisterClassA(&wc);
    win = CreateWindowExA(0, "neutronprobe", "neutron present probe",
                          WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                          CW_USEDEFAULT, CW_USEDEFAULT, 640, 360,
                          NULL, NULL, wc.hInstance, NULL);
    printf("%-28s %s\n", "CreateWindow", win ? "ok" : "FAILED");
    if (!win) return 2;

    memset(&sd, 0, sizeof(sd));
    sd.BufferDesc.Width = 640;
    sd.BufferDesc.Height = 360;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.OutputWindow = win;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0,
                                       NULL, 0, D3D11_SDK_VERSION,
                                       &sd, &swap, &dev, &got, &ctx);
    STEP(hr, "CreateDeviceAndSwapChain");
    printf("%-28s 0x%04x\n", "feature level", (unsigned)got);

    hr = IDXGISwapChain_GetBuffer(swap, 0, &IID_ID3D11Texture2D, (void **)&back);
    STEP(hr, "GetBuffer(backbuffer)");

    hr = ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &rtv);
    STEP(hr, "CreateRenderTargetView");

    for (frame = 0; frame < 60; frame++) {
        MSG msg;
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageA(&msg);
        }
        ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &rtv, NULL);
        ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, magenta);
        hr = IDXGISwapChain_Present(swap, 1, 0);
        if (FAILED(hr)) { STEP(hr, "Present"); }
        Sleep(16);
    }
    printf("%-28s 0x%08lx %s\n", "Present x60", (unsigned long)hr,
           SUCCEEDED(hr) ? "ok" : "FAILED");
    printf("window should have been magenta for ~1s\n");
    return 0;
}
