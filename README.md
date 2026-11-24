# AnyXboxX — Xbox Series X emulator (prototype)

[![Discord](https://img.shields.io/badge/Discord-AnyXboxX-5865F2?logo=discord&logoColor=white)](https://discord.gg/TcX42vRyPU)

**English** · [Français](docs/i18n/README.fr.md) · [Español](docs/i18n/README.es.md) · [Deutsch](docs/i18n/README.de.md) · [Italiano](docs/i18n/README.it.md) · [Português](docs/i18n/README.pt-BR.md) · [日本語](docs/i18n/README.ja.md) · [中文](docs/i18n/README.zh-CN.md) · [Русский](docs/i18n/README.ru.md)

> [!NOTE]
> **Where we are (2026-11-24)**
>
> Measured on an i7-13700KF + RTX 4070 SUPER, Windows 11, with the VIctory fork `fxceless/victory-gta6` at commit `7b0f736` (submodule `third_party/victory`) started by `tools/lancer_victory.ps1 -GameDir <game folder>`:
>
> - ✅ The Xbox Series 1.0.2.1 build of GTA VI **launches** on PC: boot, profile screen, first-run settings, legal screens, loading, pause menu. Menus run at 30 fps.
> - ✅ It reaches **the world and displays it**: the character moves under the player's control and the 3D image is shown, at about 4 frames per second (observed by the maintainer, Windows 11, RTX 4070 Super).
> - ⛔ Current limit: the host device is lost after a few minutes to about 13 minutes in the world, so it is not stable. The former integration stayed at about 2.4 frames per second with no 3D image; with the pinned fork the world is displayed and playable at about 4 frames per second.
> - 👁 Observed by the maintainer (Windows 11, RTX 4070 Super), with the `fxceless/victory-gta6` fork at commit `d279e69` and the launcher settings: the game was played at about 4 fps for about 13 minutes in the starting area (the prison). The character moves under the player's control and interacts with the first NPCs, then the host device is lost (known limit).
> - 🆕 Pinned since the commit `7b0f736` (includes `e9765a7`, "Fix the device loss introduced by the wave64 update"). Observed by the maintainer (Windows 11, RTX 4070 Super), from the VIctory log of the run, with `VICTORY_RELAY=2` and the launcher settings, pipeline cache already filled: the world is reached in about 1 min 25 s, 3.5 fps on the first frame, then 4.5 fps after 2 min (about 4,975 draws per frame, 346 lost without a host pipeline), no device loss during about 2 min 40 s in the world (the window was then closed). Without `VICTORY_RELAY`: 5.4 fps at about 3 min, no loss. The maintainer finds it slightly better than `d279e69`. Not yet measured by us: stability beyond 13 minutes; the fork's issue #26 reports 21.5 minutes stable on an RTX 4060 Ti with `VICTORY_RELAY=2` (third-party report).
> - Requirements: your own copy of the game, an NVIDIA or AMD GPU with SM 6.6 and mesh shaders, Rust. No game files in this repository.
> - How to run it: [docs/running-gta6.md](docs/running-gta6.md).

AnyXboxX loads Xbox GDK executables (PE32+ x86-64 format) and runs their code with Unicorn. The console's system functions are replaced by a C++ runtime in native mode, and by Python code in the isolated machine (high-level emulation, like WinDurango or Wine). The program presents itself as an Xbox Series X: `XSystemGetDeviceType` returns `XboxScarlettAnaconda`.

## Focus and status

AnyXboxX is specialised on one build: **Grand Theft Auto VI for Xbox Series, version 1.0.2.1**. Only what this game needs is translated (the system functions it imports, the shaders and the Direct3D 12.x methods it uses). Other games will be tried once that translation is complete. The project builds on [VIctory](https://github.com/Marvisak/VIctory) (Marvisak, GPL-3.0 or later), which targets the same build: the `third_party/victory` submodule is pinned to the fork `fxceless/victory-gta6` (GPL-3.0) at commit `7b0f736`. Thanks to Marvisak and to the authors of those pull requests, credited one by one in [THIRD_PARTY.md](THIRD_PARTY.md).

> [!IMPORTANT]
> **The game is not playable.** See the box at the top of this page for where we are. This repository contains no game files, keys or executable, and does not explain how to get them.

Live status page, with the disk space to plan for: **[loopersalty.github.io/AnyXboxX](https://loopersalty.github.io/AnyXboxX/)**.

## Translation progress

![Progress map: one cell per function, green if translated](docs/images/carte-avancee.svg)

Regenerate: `scarlett.py --carte <package folder> docs/images/carte-avancee.svg`.

![Xbox Series X translation progress](docs/images/traduction.svg)

- **CPU instructions: 100%.** The Series X uses an AMD Zen 2 in x86-64, the same instruction set as a PC: in native mode, the game's code runs as is, without translation.
- **GPU instructions: 70%.** A console game's shaders are compiled for the Series X's RDNA 2 GPU. 1,046 of the 1,490 RDNA 2 encodings run in the reference interpreter, and the RDNA 2 → DXIL recompiler already draws a first vertex shader and pixel shader with D3D12.
- **System functions: 66%** of the 1,337 functions imported by the DLLs of the test package are resolved in isolated mode.
- **Console-specific DLLs**: `xmem.dll` (4/4) and `d3d12_xs.dll` (2/2) are translated for the functions the package uses. D3D12.X (device and `ID3D12*` interfaces) is served by TomBox's `d3d12_xs.dll`, not yet tried with a game.
- **GDK runtime: 210 of the 396 functions** are written in AnyXboxX, in C++: the task queue (`XTaskQueue`, `XAsync`, `XThread`), the user (`XUser`, an offline local profile), the Xbox Series X identity (`XSystem`, Title ID, analytics, runtime features), saves (`XGameSave`, `XGameSaveFiles`, `XPersistentLocalStorage`) the game package (`XPackage`), the offline Store (`XStore`: local game license, empty product queries) and offline invitations, activations and error reports (`XGameInvite`, `XGameActivation`, `XGameProtocol`, `XError`), plus the PC's real HDR state and network connectivity (`XDisplayTryEnableHdrMode`, `XNetworkingGetConnectivityHint`). They are used when AnyXboxX manages the runtime on its own: without Gaming Services, or with `ANYXBOXX_SYSTEM_RUNTIME=0`. If the Windows GDK runtime is present, it serves all the interfaces, task queue included, because its APIs only accept its own queues. The trace (`ANYXBOXX_TRACE=1`) names each interface requested.

The chart is regenerated by `scarlett.py --traduction <package folder> docs/images/traduction.svg`.

## Performance (goal: a constant 60 frames per second)

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc-perf <jeu.exe> [secondes] [courbe.svg]
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <jeu.exe> --fps
```

The C++ runtime times every `Present` of the game's DXGI swap chain, including when DXGI is loaded dynamically by one of the game's DLLs (SDL3). From this it derives the frames per second, the average frame time and the "1% low" (the rate of the slowest 1% of frames, which reveals stutter). `--fps` shows these values in the window title. `--banc-perf` measures for N seconds, leaving out the first one (loading), and gives a "constant 60 fps" verdict (exit code 2 if the target is missed). Without these options, nothing is intercepted.

![SimpleTriangle: frames per second](docs/images/fps-simpletriangle.svg)

![testgdk: frames per second](docs/images/fps-testgdk.svg)

Both test games run without vertical sync: about 11,700 fps for SimpleTriangle and 12,600 fps for testgdk, in native mode.

## Project progress

| Step | Status |
|---|---|
| Reading `MicrosoftGame.Config` (TitleId, identity, Scarlett executable) | ✅ done |
| PE32+ loading: sections and protections, relocations, imports, exports | ✅ done |
| TLS: template copy, index, callbacks | ✅ done |
| TEB and PEB reachable through the GS register | ✅ done |
| HLE page: 158 emulated GDK, kernel, CRT and math function names | ✅ done |
| Unknown functions: `E_NOTIMPL` and a log entry instead of a refusal | ✅ done |
| Global C++ constructors (`_initterm`) run as guest code | ✅ done |
| Compatibility report (`--rapport`) and test bench (`--banc`) | ✅ done |
| Several linked modules in a single machine: package DLLs, ordinals, forwarders, relocation on conflict | ✅ done |
| `GetModuleHandle`, `GetProcAddress`, `LoadLibrary`, `RtlPcToFileHeader` | ✅ done |
| 16/16 DLLs of a Scarlett package initialized with their dependencies, 0 non-emulated calls | ✅ done |
| Free `SimpleTriangle` test game compiled: C startup and GDK initialization run in AnyXboxX | ✅ done |
| Wine-style native execution (`--natif`): **SimpleTriangle is displayed**, GDK runtime served by AnyXboxX | ✅ done |
| Second free test game, SDL3's `testgdk`: **runs in native mode** (window, sprites, sound) | ✅ done |
| Isolated launch of a package or an exe (`--lancer`) with the list of calls to emulate | ✅ done |
| C++ runtime (`runtime/`): `xgameruntime.dll`, `xmem.dll`, `d3d12_xs.dll` preloaded in native mode, served to all of the game's DLLs | ✅ done |
| `xmem.dll`: `XMemAlloc`, `XMemFree` with `XALLOC_ATTRIBUTES` decoded (ERA layout: heap and graphics memory, alignment), hooks, `XMemVirtualQuery` (graphics memory flag) | ✅ done |
| `d3d12_xs.dll`: root signature serialization, redirected to the PC's D3D12 | ✅ done |
| Table of the 396 GDK functions: interface and method number, extracted from `xgameruntime.lib` (`tools/gdk_interfaces.py`) | ✅ done |
| `XTaskQueue`, `XAsync`, `XThread` served by AnyXboxX: testgdk runs without the Windows runtime | ✅ done |
| Other GDK interfaces: delegated to the Windows GDK runtime, named by the trace | 🟡 in progress |
| 1008 automated tests | ✅ done |
| D3D12.X: `D3D12XboxCreateDevice`, console `ID3D12*` interfaces and `DXGIXPresentArray`, served by TomBox's Rust `d3d12_xs.dll` (MIT, 48 implemented exports, built by `tools/build_tombox.py d3d12_xs`, loaded with `ANYXBOXX_D3D12_XS=<path>`); untestable here without a console executable | 🟡 in progress |
| Console libraries from TomBox (Rust, GPL-3.0) for what AnyXboxX lacks: `xg_xs` (texture layouts, 23 exports) and full `xmem` (38 exports), with `ANYXBOXX_TOMBOX_DIR=<folder>`; built by `tools/build_tombox.py xg_xs xmem` | 🟡 in progress |
| Offline `XUser`: always-signed-in local profile, configurable gamertag (`ANYXBOXX_GAMERTAG`), testgdk sign-in succeeds | ✅ done |
| Xbox Series X identity: console type (simulated `ConsoleMode` registry value, including inside the game's DLLs), `XSystem`, Title ID read from `MicrosoftGame.config`, "Xbox Series X" analytics | ✅ done |
| Progress map: one cell per function (`--carte`) | ✅ done |
| Controller (`GameInput`) and audio (`XAudio2`): same API on console and PC, bound to the Windows DLLs in native mode | ✅ done |
| Markdown report of the missing imports per DLL and of the unemulated calls (`--lancer … --md rapport.md`) | ✅ done |
| First-launch tool for a console executable: inventory, who provides each import (package, AnyXboxX, TomBox, Windows, missing), isolated runs, optional native run; report kept outside the repository: `python tools/jour_j.py <package> [--natif]` ([guide](docs/day-one.md), in French) | ✅ done |
| Frame counter (`--fps`) and performance bench with a "constant 60 fps" verdict and a curve (`--banc-perf`) | ✅ done |
| `XGameSave` saves (containers, blobs, quota, asynchronous reads) and persistent local storage, on the PC's disk (`%LOCALAPPDATA%\AnyXboxX\<TitleId>`, or `ANYXBOXX_SAVE_DIR`) | ✅ done |
| `XPackage`: locally installed package (identifier, language, ready chunks, mounting on the game folder) | ✅ done |
| `kernelx.dll` (console kernel): 2,661 functions forwarded to Windows `kernel32`/`kernelbase` | ✅ done |
| Implicit TLS (`thread_local`) for games in native mode: carrier DLL `anyxboxx_tls.dll`, every thread gets its own copy (up to 256 KiB) | ✅ done |
| Native C++ launcher without Python (`runtime/build/bin/anyxboxx.exe <game.exe \| folder> [--fps]`): SimpleTriangle and testgdk at ~12,000 fps | ✅ done |
| RDNA 2 GPU disassembler: 1,490 mnemonics and LLVM-syntax operands (scalar, VOP1/VOP2/VOPC/VOP3/VOP3P/SDWA/DPP/SMEM/DS/EXP/MUBUF/MTBUF/MIMG/FLAT with modifiers), checked against 38,999 public LLVM encodings: `scarlett.py --rdna2 <shader.bin> [--liste]` | 🟡 in progress |
| RDNA 2 disassembler operands identical to LLVM's text: scalar and VOP1/VOPC 100%, DS 100%, EXP 100%, SMEM 96.5% (the maximum: LLVM writes the other encodings two ways) | ✅ done |
| First RDNA 2 vertex and pixel shaders drawn with D3D12 (`anyxboxx_gpu_run.exe --draw`): every vertex and every pixel identical to the reference interpreter, on the GPU and on WARP | ✅ done |
| Textures in recompiled RDNA 2 shaders: T#/S# descriptors and `image_sample` (2D, nearest texel, wrap or clamp-to-edge, 8_8_8_8_UNORM and 32_32_32_32_FLOAT), identical to the reference interpreter on the GPU and on WARP, including a textured pixel shader; descriptor layout from Leonida and Mesa | ✅ done |
| Second RDNA 2 → SPIR-V (Vulkan) translator: Leonida's (GPL-3.0), copied unchanged in `third_party/leonida/` and fed by AnyXboxX's own disassembler, without `llvm-mc`; vertex, pixel and compute shaders; 51 of the 52 console shaders shipped in the package's `XboxBvhBuilder.dll` translate, measured locally with `tools/fssm_mesure.py` (`scarlett.py --rdna2 <shader.bin> --spirv ps`) | 🟡 in progress |
| TomBox updated to its latest version (D3D12.X: 194 of 200 methods by their count) and 4 more of its console libraries built and served from `ANYXBOXX_TOMBOX_DIR`: `d3d12_x` (ESRAM), `XAudio2_9` (XMA voices), `xapu`, `xgs12`; `tools/build_tombox.py d3d12_xs xg_xs xmem d3d12_x xaudio2_9 xapu xgs12` | 🟡 in progress |
| Console DXIL → PC DXIL retarget (`dxil-ms-xb2` → `dxil-ms-dx`, without going through HLSL): Xbox2Windows' tool (MIT), copied unchanged in `third_party/xbox2windows/` with its test; `python third_party/xbox2windows/tools/dxil_retarget.py <in> <out>` or `--pe <game.exe>` | ✅ done |
| Pull request checks: lint and the 9 READMEs kept in sync (rows, images, test count) on every pull request | ✅ done |
| Console textures in Rust: BC7 decoding and GFX10 `SW_4K_S` detiling ported from Xbox2Windows (MIT), reproducing their reference digests; `anyxboxx_texture bc7 <blocks.bin> <w> <h> <out.png> [--4k-s]` | 🟡 in progress |
| Other GDK interfaces written by AnyXboxX (`XGameUi`, `XNetworking`…) | ⏳ to do |
| RDNA 2 → DXIL shader recompiler: first programs translated to HLSL, compiled to DXIL and run on the PC's GPU with D3D12 (`--hlsl`, `anyxboxx_gpu_run.exe`, WARP without a GPU), memory identical to a wave32 reference interpreter running 1,046 of 1,490 encodings (scalar, VOP1/VOP2/VOPC/VOP3/VOP3P, memory: SMEM, LDS, GLOBAL, MUBUF/MTBUF with V# bounds and typed formats, atomics, branches, `exec` divergence); a first vertex shader and pixel shader (EXP exports, VINTRP interpolation) drawn with D3D12, identical vertex by vertex and pixel by pixel: `scarlett.py --rdna2 <shader.bin> --executer` | 🟡 in progress |
| Wave64 compute programs on GPUs whose waves have 32 lanes (#70): each 64-lane wave runs as one group of 64 threads (lane masks and lane reads through groupshared memory, no `WaveSize`), memory identical to the reference interpreter in wave64 on an RTX (32-lane waves) and with WARP; DPP and SDWA compares are still refused by name | 🟡 in progress |
| Shader cache: translated shaders compiled to DXIL once, then reused from disk (1.4 ms) or memory (0.8 ms) instead of dxc (22 ms); `%LOCALAPPDATA%\AnyXboxX\shader-cache` or `ANYXBOXX_SHADER_CACHE`, size-capped | 🟡 in progress |
| GTA VI Xbox Series 1.0.2.1 via VIctory (`third_party/victory`, fork `fxceless/victory-gta6` at `7b0f736`): the world is displayed and playable at about 4 fps (observed by the maintainer, Windows 11, RTX 4070 Super); the host device is lost after a few minutes to about 13 minutes | 🟡 in progress |
| x64 SEH exceptions (`.pdata`), multiple threads | ⏳ to do |
| Dynamic loading of a DLL at run time (`LoadLibrary` + `DllMain`) | ⏳ to do |
| D3D12.X graphics to Direct3D 12 / Vulkan | ⏳ to do |
| Console XMA2 audio: decoded to WAV by TomBox's Rust port of FFmpeg's decoder (LGPL, 1 LSB from FFmpeg on the public FATE sample); `anyxboxx_xma <in.xma> <out.wav>`, single-stream files | 🟡 in progress |

<table>
<tr>
<td><img src="docs/images/demo-virage.png" alt="The car turns to the right" width="380"></td>
<td><img src="docs/images/rapport-compatibilite.png" alt="Compatibility report of the demo" width="380"></td>
</tr>
<tr>
<td align="center">The demo responds to the keyboard arrow keys.</td>
<td align="center">The log shows the compatibility report.</td>
</tr>
</table>

## Try the demo

On Windows, install 64-bit Python 3.12 with Tcl/Tk, then open PowerShell at the root of the repository.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --demo
```

Native mode needs the C++ runtime. It is built with Visual Studio 2022 or 2026 (C++ workload) and CMake:

```powershell
cmake -S runtime -B runtime/build -A x64
cmake --build runtime/build --config Release
```

The task queue reuses the `Task` module from [libHttpClient](https://github.com/microsoft/libHttpClient) (MIT license, `runtime/third_party/libhttpclient-task`). The DLLs end up in `runtime/build/bin`, or in the folder given by `ANYXBOXX_RUNTIME`. `ANYXBOXX_SYSTEM_RUNTIME=0` turns off delegation to the Windows GDK runtime.

The compiled demo program is `PrototypeScarlett/demo.pe`; its source code is `PrototypeScarlett/demo.c`.

## Run a game in native mode

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <dossier ou fichier .exe> [dossiers de DLL…]
```

![SimpleTriangle launched by AnyXboxX in native mode](docs/images/simpletriangle-anyxboxx.png)

AnyXboxX loads the executable itself and runs it directly on the processor, like Wine. The Xbox runtime (`xgameruntime.dll`) is provided by AnyXboxX; the window and DirectX 12 are the PC's. **Warning: in native mode, the program is not isolated.** Reserve this mode for trusted programs; `--rapport` and `--banc` remain isolated inside Unicorn. `ANYXBOXX_TRACE=1` displays the intercepted calls. Details: [docs/test-game.md](docs/test-game.md).

## Run a package in isolated mode

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --lancer <dossier du paquet ou fichier .exe> [dossiers de DLL…]
```

With a folder, AnyXboxX reads `MicrosoftGame.Config`, takes the executable declared for `Scarlett` and runs it in the isolated machine (Unicorn): the program does not touch the PC. The report lists the unresolved imports, then the unemulated calls, from most to least frequent: this is the to-do list for completing the emulator. If the executable is missing, the message names it. With `--md rapport.md`, the same report is written in Markdown, with the missing imports grouped by DLL.

## Analyze a program

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --rapport <dossier ou fichier .exe>
```

The test bench loads every PE module in a folder and runs their initialization:

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc <dossier>
```

![Test bench on the DLLs of a Scarlett package](docs/images/banc-dll.svg)

Detailed results: [docs/progress.md](docs/progress.md). Free test game compared with its native execution: [docs/test-game.md](docs/test-game.md). An additional DLL folder (for example the Visual C++ DLLs) can follow the target: `--rapport <cible> <dossier>`.

The report lists the imported functions, the percentage already emulated and the missing functions. In the interface, the **Open an Xbox folder…** button reads `MicrosoftGame.Config`, displays this report, then launches the program; every non-emulated call appears in the log.

## Architecture

![Module diagram of AnyXboxX](docs/images/architecture.svg)

| Module | Role |
|---|---|
| `emu/config.py` | reads the GDK package manifest |
| `emu/loader.py` | loads the PE image and prepares imports, exports and TLS |
| `emu/machine.py` | Unicorn processor, stack, heap, TEB/PEB, call dispatch |
| `emu/hle/` | emulated functions: `gdk.py`, `kernel.py`, `crt.py`, `libm.py`, `guest.py` |
| `emu/report.py` | compatibility report |
| `emu/modules.py` | loads the package DLLs, links the imports, orders the initializations |
| `emu/bench.py` | test bench on a folder of modules |
| `emu/native/` | Wine-style native execution: loader, real imports, AnyXboxX's GDK runtime |
| `scarlett.py` | Tkinter interface and command line |

To add a function, decorate a handler in `emu/hle/`:

```python
@hle("gdk")
def XSystemGetDeviceType(c):
    return XBOX_SERIES_X
```

## Research

- [Xbox Series X hardware architecture](docs/research/xbox-series-x-architecture.md): Zen 2 CPU, RDNA 2 GPU, memory, Velocity Architecture, security.
- [Existing emulators and compatibility layers](docs/research/state-of-the-art.md): WinDurango, XWine1, Xenia, XVD tools.
- [Reverse-engineering notes on the studied Scarlett package](docs/research/package/README.md) (written by Codex): RDS5/ETPF tables, RPF headers, package layout.
- [TomBox and its continuation](docs/research/tombox.md): Rust console DLLs, Direct3D 12.x, RDNA 2 shader translator, what AnyXboxX reuses (MIT, credited).
- [Xbox2Windows](docs/research/xbox2windows.md): static recompilation research; BC7 and GFX10 tiling reused by AnyXboxX (MIT, credited).
- [First boot of the 1.0.2.1 executable](docs/research/first-boot-1021.md): stops measured under Leonida's `gta6rt` in order, the Leonida pull requests that treat them, work list for AnyXboxX.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

## Contributing

The `main` branch is protected: every contribution goes through a reviewed pull request, and the tests must pass. Bugs and functions to emulate are reported in the issues. The full rules are in [CONTRIBUTING.md](CONTRIBUTING.md) (in French).

Discussion, help and test reports: [Discord](https://discord.gg/TcX42vRyPU)

## License

AnyXboxX is distributed under the [GNU GPL 3.0 or later](LICENSE). Third-party parts keep their own license: the `Task` module of libHttpClient (MIT, `runtime/third_party/libhttpclient-task`) and the RDNA 2 tables generated from LLVM's public encoding tests (Apache 2.0 with LLVM exception, `PrototypeScarlett/emu/rdna2_ops.py` and `rdna2_shapes.py`).

Third-party components and credits: [THIRD_PARTY.md](THIRD_PARTY.md).
