/* two windows side by side, identical except for the swap effect.
 *   left  = DXGI_SWAP_EFFECT_DISCARD (0)      filled MAGENTA
 *   right = DXGI_SWAP_EFFECT_FLIP_DISCARD (3) filled GREEN
 * unity asks for 3, and dxmt logs "unsupported swap effect 3" for it. if the
 * left window shows and the right stays black, the flip-model path is the bug.
 * build: x86_64-w64-mingw32-gcc -O1 -o d3dswapeffect.exe d3dswapeffect.c \
 *        -ld3d11 -ldxgi -luser32 -lgdi32 -luuid */

#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <stdio.h>

struct chain {
    IDXGISwapChain *swap;
    ID3D11RenderTargetView *rtv;
    const float *colour;
    const char *name;
};

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(h, m, w, l);
}

static int make(ID3D11Device *dev, HWND win, UINT effect, struct chain *out,
                const float *colour, const char *name)
{
    DXGI_SWAP_CHAIN_DESC sd;
    IDXGIDevice *dxdev = NULL;
    IDXGIAdapter *ad = NULL;
    IDXGIFactory *fac = NULL;
    ID3D11Texture2D *back = NULL;
    HRESULT hr;

    memset(&sd, 0, sizeof(sd));
    sd.BufferDesc.Width = 400;
    sd.BufferDesc.Height = 300;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.OutputWindow = win;
    sd.Windowed = TRUE;
    sd.SwapEffect = effect;

    ID3D11Device_QueryInterface(dev, &IID_IDXGIDevice, (void **)&dxdev);
    IDXGIDevice_GetAdapter(dxdev, &ad);
    IDXGIAdapter_GetParent(ad, &IID_IDXGIFactory, (void **)&fac);
    hr = IDXGIFactory_CreateSwapChain(fac, (IUnknown *)dev, &sd, &out->swap);
    printf("%-14s swap effect %u  CreateSwapChain 0x%08lx %s\n",
           name, effect, (unsigned long)hr, SUCCEEDED(hr) ? "ok" : "FAILED");
    if (FAILED(hr)) return 0;

    IDXGISwapChain_GetBuffer(out->swap, 0, &IID_ID3D11Texture2D, (void **)&back);
    ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &out->rtv);
    out->colour = colour;
    out->name = name;
    return 1;
}

int main(void)
{
    WNDCLASSA wc;
    HWND w1, w2;
    ID3D11Device *dev = NULL;
    ID3D11DeviceContext *ctx = NULL;
    struct chain a = {0}, b = {0};
    static const float magenta[4] = { 1.0f, 0.0f, 1.0f, 1.0f };
    static const float green[4]   = { 0.0f, 1.0f, 0.0f, 1.0f };
    D3D_FEATURE_LEVEL got = 0;
    int frame;

    setvbuf(stdout, NULL, _IONBF, 0);

    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "neutronswap";
    RegisterClassA(&wc);
    w1 = CreateWindowExA(0, "neutronswap", "LEFT  discard  = MAGENTA",
                         WS_OVERLAPPEDWINDOW | WS_VISIBLE, 80, 120, 400, 300, NULL, NULL, wc.hInstance, NULL);
    w2 = CreateWindowExA(0, "neutronswap", "RIGHT flip_discard = GREEN",
                         WS_OVERLAPPEDWINDOW | WS_VISIBLE, 520, 120, 400, 300, NULL, NULL, wc.hInstance, NULL);

    if (FAILED(D3D11CreateDevice(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
                                 D3D11_SDK_VERSION, &dev, &got, &ctx))) {
        printf("device FAILED\n"); return 2;
    }

    make(dev, w1, DXGI_SWAP_EFFECT_DISCARD, &a, magenta, "left/discard");
    make(dev, w2, DXGI_SWAP_EFFECT_FLIP_DISCARD, &b, green, "right/flip");

    printf("\nlook at the two windows for ~25 seconds\n");
    for (frame = 0; frame < 1500; frame++) {
        MSG msg;
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageA(&msg);
        }
        if (a.rtv) {
            ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &a.rtv, NULL);
            ID3D11DeviceContext_ClearRenderTargetView(ctx, a.rtv, a.colour);
            IDXGISwapChain_Present(a.swap, 0, 0);
        }
        if (b.rtv) {
            ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &b.rtv, NULL);
            ID3D11DeviceContext_ClearRenderTargetView(ctx, b.rtv, b.colour);
            IDXGISwapChain_Present(b.swap, 0, 0);
        }
        Sleep(16);
    }
    return 0;
}
