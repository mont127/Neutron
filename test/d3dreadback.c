/* clears the backbuffer, then copies it to a staging texture and reads the
 * pixels back. present returning S_OK only says the api path worked; this says
 * whether the gpu actually wrote the colour. if the readback is magenta but the
 * window is black, the problem is getting the surface onto the screen, not
 * rendering.
 * build: x86_64-w64-mingw32-gcc -O1 -o d3dreadback.exe d3dreadback.c \
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
    ID3D11Texture2D *back = NULL, *stage = NULL;
    ID3D11RenderTargetView *rtv = NULL;
    D3D11_TEXTURE2D_DESC td;
    D3D11_MAPPED_SUBRESOURCE ms;
    D3D_FEATURE_LEVEL got = 0;
    const float magenta[4] = { 1.0f, 0.0f, 1.0f, 1.0f };
    HRESULT hr;

    setvbuf(stdout, NULL, _IONBF, 0);

    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "neutronreadback";
    RegisterClassA(&wc);
    win = CreateWindowExA(0, "neutronreadback", "neutron readback", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                          CW_USEDEFAULT, CW_USEDEFAULT, 320, 240, NULL, NULL, wc.hInstance, NULL);
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
    if (FAILED(hr)) { printf("GetBuffer 0x%08lx FAILED\n", (unsigned long)hr); return 2; }

    hr = ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &rtv);
    if (FAILED(hr)) { printf("CreateRenderTargetView 0x%08lx FAILED\n", (unsigned long)hr); return 2; }

    ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &rtv, NULL);
    ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, magenta);
    ID3D11DeviceContext_Flush(ctx);

    ID3D11Texture2D_GetDesc(back, &td);
    td.Usage = D3D11_USAGE_STAGING;
    td.BindFlags = 0;
    td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    td.MiscFlags = 0;
    hr = ID3D11Device_CreateTexture2D(dev, &td, NULL, &stage);
    if (FAILED(hr)) { printf("CreateTexture2D(staging) 0x%08lx FAILED\n", (unsigned long)hr); return 2; }

    ID3D11DeviceContext_CopyResource(ctx, (ID3D11Resource *)stage, (ID3D11Resource *)back);
    hr = ID3D11DeviceContext_Map(ctx, (ID3D11Resource *)stage, 0, D3D11_MAP_READ, 0, &ms);
    if (FAILED(hr)) { printf("Map 0x%08lx FAILED\n", (unsigned long)hr); return 2; }
    {
        const unsigned char *row = (const unsigned char *)ms.pData + (td.Height / 2) * ms.RowPitch;
        const unsigned char *p = row + (td.Width / 2) * 4;
        printf("backbuffer centre pixel: R=%u G=%u B=%u A=%u  %s\n",
               p[0], p[1], p[2], p[3],
               (p[0] > 200 && p[1] < 70 && p[2] > 200) ? "MAGENTA, the gpu drew it"
                                                       : "NOT magenta, nothing was drawn");
    }
    ID3D11DeviceContext_Unmap(ctx, (ID3D11Resource *)stage, 0);

    hr = IDXGISwapChain_Present(swap, 0, 0);
    printf("Present: 0x%08lx\n", (unsigned long)hr);
    return 0;
}
