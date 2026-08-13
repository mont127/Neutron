# vendor

`dxvk-1.10.3/x86_64/dxgi.dll` is DXVK v1.10.3-20230507-async (macOS), which the
installer stages into a prefix as `dxgi_dxvk.dll`.

It is here because the graphics pack in the unified wine ships wine's own
wined3d dxgi under that name (0 dxvk strings, 2672 wined3d ones), and DXVK's
d3d11 needs `IDXGIVkAdapter` from a real DXVK dxgi to report the right adapter.

DXVK is distributed under the zlib licence, which is not the Apache 2.0 licence
covering the rest of this repo. See https://github.com/doitsujin/dxvk

## what is deliberately NOT here

D3DMetal, `libd3dshared.dylib` and the D3D dlls built on them come from Apple's
Game Porting Toolkit, whose licence does not permit redistribution. Neutron does
not ship them. Download the toolkit yourself ("Evaluation environment for
Windows games", developer.apple.com) and install it into the engine with:

    neutron d3dmetal /path/to/Evaluation_environment_for_Windows_games_3.0.dmg

The DXVK and DXMT backends work without it.
