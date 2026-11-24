# AnyXboxX — emulador de Xbox Series X (prototipo)

[![Discord](https://img.shields.io/badge/Discord-AnyXboxX-5865F2?logo=discord&logoColor=white)](https://discord.gg/TcX42vRyPU)

[English](../../README.md) · [Français](README.fr.md) · **Español** · [Deutsch](README.de.md) · [Italiano](README.it.md) · [Português](README.pt-BR.md) · [日本語](README.ja.md) · [中文](README.zh-CN.md) · [Русский](README.ru.md)

> [!NOTE]
> **Dónde estamos (24/11/2026)**
>
> Medido en un i7-13700KF + RTX 4070 SUPER, Windows 11, con el fork de VIctory `fxceless/victory-gta6` en el commit `7b0f736` (submódulo `third_party/victory`) iniciado con `tools/lancer_victory.ps1 -GameDir <carpeta del juego>`:
>
> - ✅ La versión 1.0.2.1 de Xbox Series de GTA VI **se inicia** en PC: arranque, pantalla de perfil, ajustes del primer inicio, pantallas legales, carga, menú de pausa. Los menús van a 30 fps.
> - ✅ Llega **al mundo y lo muestra**: el personaje se mueve bajo el control del jugador y se muestra la imagen 3D, a unas 4 imágenes por segundo (observado por el mantenedor, Windows 11, RTX 4070 Super).
> - ⛔ Límite actual: el dispositivo del host se pierde tras unos minutos o hasta unos 13 minutos en el mundo, así que no es estable. La integración anterior se quedaba en unas 2,4 imágenes por segundo sin imagen 3D; con el fork fijado el mundo se muestra y se puede jugar a unas 4 imágenes por segundo.
> - 👁 Observado por el mantenedor (Windows 11, RTX 4070 Super), con el fork `fxceless/victory-gta6` en el commit `d279e69` y los ajustes del lanzador: el juego se jugó a unos 4 fps durante unos 13 minutos en la zona de inicio (la prisión). El personaje se mueve bajo el control del jugador e interactúa con los primeros PNJ; después se pierde el dispositivo del host (límite conocido).
> - 🆕 Fijado desde el commit `7b0f736` (incluye `e9765a7`, "Fix the device loss introduced by the wave64 update"). Observado por el mantenedor (Windows 11, RTX 4070 Super), según el registro de VIctory de la ejecución, con `VICTORY_RELAY=2` y los ajustes del lanzador, con la caché de pipelines ya llena: mundo alcanzado en unos 1 min 25 s, 3,5 fps en el primer fotograma y 4,5 fps tras 2 min (unos 4.975 draws por fotograma, 346 perdidos por falta de pipeline del host), sin pérdida del dispositivo durante unos 2 min 40 s en el mundo (la ventana se cerró después). Sin `VICTORY_RELAY`: 5,4 fps a los 3 min aprox., sin pérdida. El mantenedor lo considera ligeramente mejor que `d279e69`. Aún no medido por nosotros: la estabilidad más allá de 13 minutos; la issue n.º 26 del fork informa de 21,5 minutos estables en una RTX 4060 Ti con `VICTORY_RELAY=2` (informe de terceros).
> - Requisitos: tu propia copia del juego, una GPU NVIDIA o AMD con SM 6.6 y mesh shaders, Rust. Ningún archivo del juego en este repositorio.
> - Cómo ejecutarlo: [docs/running-gta6.md](../running-gta6.md).

AnyXboxX carga ejecutables de Xbox GDK (formato PE32+ x86-64) y ejecuta su código con Unicorn. Las funciones de sistema de la consola se sustituyen por un runtime C++ en modo nativo, y por código Python en la máquina aislada (emulación de alto nivel, como WinDurango o Wine). El programa se presenta como una Xbox Series X: `XSystemGetDeviceType` devuelve `XboxScarlettAnaconda`.

## Objetivo y estado

AnyXboxX está especializado en una sola versión: **Grand Theft Auto VI para Xbox Series, versión 1.0.2.1**. Solo se traduce lo que este juego necesita (las funciones del sistema que importa, los shaders y los métodos de Direct3D 12.x que usa). Otros juegos se probarán cuando esa traducción esté completa. El proyecto se apoya en [VIctory](https://github.com/Marvisak/VIctory) (Marvisak, GPL-3.0 o posterior), que apunta a la misma versión: el submódulo `third_party/victory` está fijado al fork `fxceless/victory-gta6` (GPL-3.0) en el commit `7b0f736`. Gracias a Marvisak y a los autores de esas pull requests, acreditados uno por uno en [THIRD_PARTY.md](../../THIRD_PARTY.md).

> [!IMPORTANT]
> **El juego no es jugable.** Consulta el recuadro de arriba para ver el estado actual. Este repositorio no contiene archivos del juego, claves ni ejecutables, y no explica cómo obtenerlos.

Página de estado en línea, con el espacio en disco necesario: **[loopersalty.github.io/AnyXboxX](https://loopersalty.github.io/AnyXboxX/)**.

## Avance de la traducción

![Mapa del avance: una casilla por función, verde si está traducida](../images/carte-avancee.svg)

Regenerar: `scarlett.py --carte <carpeta del paquete> docs/images/carte-avancee.svg`.

![Avance de la traducción de Xbox Series X](../images/traduction.svg)

- **Instrucciones del procesador: 100 %.** La Series X usa un AMD Zen 2 en x86-64, el mismo conjunto de instrucciones que un PC: en modo nativo, el código del juego se ejecuta tal cual, sin traducción.
- **Instrucciones de la GPU: 68 %.** Los shaders de un juego de consola se compilan para la GPU RDNA 2 de la Series X. 1.009 de las 1.487 codificaciones RDNA 2 se ejecutan en el intérprete de referencia, y el recompilador RDNA 2 → DXIL ya dibuja un primer vertex shader y pixel shader con D3D12.
- **Funciones de sistema: 66 %** de las 1 337 funciones importadas por las DLL del paquete de prueba se resuelven en modo aislado.
- **DLL propias de la consola**: `xmem.dll` (4/4) y `d3d12_xs.dll` (2/2) están traducidas para las funciones que usa el paquete. D3D12.X (dispositivo e interfaces `ID3D12*`) lo sirve la `d3d12_xs.dll` de TomBox, aún sin probar con un juego.
- **Runtime GDK: 210 de las 396 funciones** están escritas en AnyXboxX, en C++: la cola de tareas (`XTaskQueue`, `XAsync`, `XThread`), el usuario (`XUser`, un perfil local sin conexión), la identidad de la Xbox Series X (`XSystem`, Title ID, analítica, funcionalidades del runtime), las partidas guardadas (`XGameSave`, `XGameSaveFiles`, `XPersistentLocalStorage`) el paquete del juego (`XPackage`), la tienda sin conexión (`XStore`) y las invitaciones, activaciones e informes de error sin conexión (`XGameInvite`, `XGameActivation`, `XGameProtocol`, `XError`), además del estado HDR real y la conectividad de red del PC (`XDisplayTryEnableHdrMode`, `XNetworkingGetConnectivityHint`). Se usan cuando AnyXboxX gestiona el runtime por sí solo: sin Gaming Services, o con `ANYXBOXX_SYSTEM_RUNTIME=0`. Si el runtime GDK de Windows está presente, sirve todas las interfaces, incluida la cola de tareas, porque sus API solo aceptan sus propias colas. La traza (`ANYXBOXX_TRACE=1`) nombra cada interfaz solicitada.

El gráfico se regenera con `scarlett.py --traduction <carpeta del paquete> docs/images/traduction.svg`.

## Rendimiento (objetivo: 60 fotogramas por segundo constantes)

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc-perf <jeu.exe> [secondes] [courbe.svg]
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <jeu.exe> --fps
```

El runtime en C++ cronometra cada `Present` de la swap chain DXGI del juego, incluso cuando una DLL del juego carga DXGI de forma dinámica (SDL3). De ahí obtiene los fotogramas por segundo, el tiempo medio de un fotograma y el «1 % bajo» (la cadencia del 1 % de fotogramas más lentos, que revela los tirones). `--fps` muestra estos valores en el título de la ventana. `--banc-perf` mide durante N segundos, sin contar el primero (carga), y emite un veredicto «60 f/s constantes» (código de salida 2 si no se alcanza el objetivo). Sin estas opciones, no se intercepta nada.

![SimpleTriangle: fotogramas por segundo](../images/fps-simpletriangle.svg)

![testgdk: fotogramas por segundo](../images/fps-testgdk.svg)

Los dos juegos de prueba funcionan sin sincronización vertical: unos 11 700 f/s para SimpleTriangle y 12 600 f/s para testgdk, en modo nativo.

## Avance del proyecto

| Etapa | Estado |
|---|---|
| Lectura de `MicrosoftGame.Config` (TitleId, identidad, ejecutable Scarlett) | ✅ hecho |
| Carga PE32+: secciones y protecciones, reubicaciones, importaciones, exportaciones | ✅ hecho |
| TLS: copia de la plantilla, índice, callbacks | ✅ hecho |
| TEB y PEB accesibles mediante el registro GS | ✅ hecho |
| Página HLE: 158 nombres de funciones GDK, kernel, CRT y matemáticas emulados | ✅ hecho |
| Funciones desconocidas: `E_NOTIMPL` y registro en el diario en lugar de un rechazo | ✅ hecho |
| Constructores globales de C++ (`_initterm`) ejecutados como código invitado | ✅ hecho |
| Informe de compatibilidad (`--rapport`) y banco de pruebas (`--banc`) | ✅ hecho |
| Varios módulos enlazados en una misma máquina: DLL del paquete, ordinales, redirecciones, reubicación en caso de conflicto | ✅ hecho |
| `GetModuleHandle`, `GetProcAddress`, `LoadLibrary`, `RtlPcToFileHeader` | ✅ hecho |
| 16/16 DLL de un paquete Scarlett inicializadas con sus dependencias, 0 llamadas no emuladas | ✅ hecho |
| Juego de prueba libre `SimpleTriangle` compilado: el arranque en C y la inicialización de GDK funcionan en AnyXboxX | ✅ hecho |
| Ejecución nativa al estilo Wine (`--natif`): **SimpleTriangle se muestra**, runtime GDK proporcionado por AnyXboxX | ✅ hecho |
| Segundo juego de prueba libre, `testgdk` de SDL3: **funciona en modo nativo** (ventana, sprites, sonido) | ✅ hecho |
| Lanzamiento aislado de un paquete o de un exe (`--lancer`) con la lista de llamadas por emular | ✅ hecho |
| Runtime C++ (`runtime/`): `xgameruntime.dll`, `xmem.dll`, `d3d12_xs.dll` precargadas en modo nativo, servidas a todas las DLL del juego | ✅ hecho |
| `xmem.dll`: `XMemAlloc`, `XMemFree` con `XALLOC_ATTRIBUTES` decodificados (disposición ERA: memoria de montón y gráfica, alineación), ganchos, `XMemVirtualQuery` (indicador de memoria gráfica) | ✅ hecho |
| `d3d12_xs.dll`: serialización de las firmas raíz, redirigida al D3D12 del PC | ✅ hecho |
| Tabla de las 396 funciones GDK: interfaz y número de método, extraídos de `xgameruntime.lib` (`tools/gdk_interfaces.py`) | ✅ hecho |
| `XTaskQueue`, `XAsync`, `XThread` servidas por AnyXboxX: testgdk funciona sin el runtime de Windows | ✅ hecho |
| Otras interfaces GDK: delegadas al runtime GDK de Windows, nombradas por la traza | 🟡 en curso |
| 864 pruebas automatizadas | ✅ hecho |
| D3D12.X: `D3D12XboxCreateDevice`, interfaces `ID3D12*` de la consola y `DXGIXPresentArray`, servidos por la `d3d12_xs.dll` en Rust de TomBox (MIT, 48 exportaciones implementadas, compilada con `tools/build_tombox.py d3d12_xs`, cargada con `ANYXBOXX_D3D12_XS=<ruta>`); no se puede probar aquí sin un ejecutable de consola | 🟡 en curso |
| Bibliotecas de consola de TomBox (Rust, GPL-3.0) para lo que falta en AnyXboxX: `xg_xs` (disposición de texturas, 23 exportaciones) y `xmem` completo (38 exportaciones), con `ANYXBOXX_TOMBOX_DIR=<carpeta>`; compiladas con `tools/build_tombox.py xg_xs xmem` | 🟡 en curso |
| `XUser` sin conexión: perfil local siempre conectado, gamertag configurable (`ANYXBOXX_GAMERTAG`), inicio de sesión de testgdk correcto | ✅ hecho |
| Identidad de la Xbox Series X: tipo de consola (valor de registro `ConsoleMode` simulado, también dentro de las DLL del juego), `XSystem`, Title ID leído de `MicrosoftGame.config`, analítica «Xbox Series X» | ✅ hecho |
| Mapa del avance: una casilla por función (`--carte`) | ✅ hecho |
| Mando (`GameInput`) y audio (`XAudio2`): la misma API en consola y en PC, enlazados con las DLL de Windows en modo nativo | ✅ hecho |
| Informe Markdown de las importaciones que faltan por DLL y de las llamadas no emuladas (`--lancer … --md rapport.md`) | ✅ hecho |
| Herramienta de primer arranque de un ejecutable de consola: inventario, proveedor de cada importación (paquete, AnyXboxX, TomBox, Windows, ausente), ejecuciones aisladas, ejecución nativa opcional; informe fuera del repositorio: `python tools/jour_j.py <paquete> [--natif]` ([guía](../day-one.md), en francés) | ✅ hecho |
| Contador de fotogramas (`--fps`) y banco de rendimiento con veredicto «60 f/s constantes» y curva (`--banc-perf`) | ✅ hecho |
| Partidas guardadas `XGameSave` (contenedores, blobs, cuota, lectura asíncrona) y almacenamiento local persistente, en el disco del PC (`%LOCALAPPDATA%\AnyXboxX\<TitleId>`, o `ANYXBOXX_SAVE_DIR`) | ✅ hecho |
| `XPackage`: paquete instalado en local (identificador, idioma, fragmentos listos, montaje sobre la carpeta del juego) | ✅ hecho |
| `kernelx.dll` (núcleo de la consola): 2 661 funciones redirigidas a `kernel32`/`kernelbase` de Windows | ✅ hecho |
| TLS implícito (`thread_local`) de los juegos en modo nativo: DLL portadora `anyxboxx_tls.dll`, cada hilo recibe su copia (hasta 256 KiB) | ✅ hecho |
| Lanzador nativo en C++ sin Python (`runtime/build/bin/anyxboxx.exe <juego.exe \| carpeta> [--fps]`): SimpleTriangle y testgdk a ~12 000 i/s | ✅ hecho |
| Desensamblador de GPU RDNA 2: 1.487 mnemónicos y operandos con sintaxis LLVM (escalares, VOP1/VOP2/VOPC/VOP3/VOP3P/SDWA/DPP/SMEM/DS/EXP/MUBUF/MTBUF/MIMG/FLAT con modificadores), verificado con 35.088 codificaciones públicas de LLVM: `scarlett.py --rdna2 <shader.bin> [--liste]` | 🟡 en curso |
| Operandos del desensamblador RDNA 2 idénticos al texto de LLVM: escalares y VOP1/VOPC 100 %, DS 100 %, EXP 100 %, SMEM 96,5 % (el máximo: LLVM escribe las demás codificaciones de dos maneras) | ✅ hecho |
| Primeros vertex y pixel shaders RDNA 2 dibujados con D3D12 (`anyxboxx_gpu_run.exe --draw`): cada vértice y cada píxel idénticos al intérprete de referencia, en la GPU y con WARP | ✅ hecho |
| Texturas en los shaders RDNA 2 recompilados: descriptores T#/S# e `image_sample` (2D, texel más cercano, wrap o clamp-to-edge, 8_8_8_8_UNORM y 32_32_32_32_FLOAT), idénticos al intérprete de referencia en la GPU y con WARP, incluido un pixel shader texturizado; disposición de los descriptores de Leonida y Mesa | ✅ hecho |
| Segundo traductor RDNA 2 → SPIR-V (Vulkan): el de Leonida (GPL-3.0), copiado sin cambios en `third_party/leonida/` y alimentado por el desensamblador propio de AnyXboxX, sin `llvm-mc`; vertex, pixel y compute shaders; se traducen 51 de los 52 shaders de consola incluidos en `XboxBvhBuilder.dll` del paquete, medido localmente con `tools/fssm_mesure.py` (`scarlett.py --rdna2 <shader.bin> --spirv ps`) | 🟡 en curso |
| TomBox actualizado a su última versión (D3D12.X: 194 de 200 métodos según su recuento) y 4 bibliotecas de consola más compiladas y servidas desde `ANYXBOXX_TOMBOX_DIR`: `d3d12_x` (ESRAM), `XAudio2_9` (voces XMA), `xapu`, `xgs12`; `tools/build_tombox.py d3d12_xs xg_xs xmem d3d12_x xaudio2_9 xapu xgs12` | 🟡 en curso |
| Conversión del DXIL de consola en DXIL de PC (`dxil-ms-xb2` → `dxil-ms-dx`, sin pasar por HLSL): la herramienta de Xbox2Windows (MIT), copiada sin cambios con su prueba en `third_party/xbox2windows/`; `python third_party/xbox2windows/tools/dxil_retarget.py <entrada> <salida>` o `--pe <juego.exe>` | ✅ hecho |
| Comprobaciones de las pull requests: lint y los 9 README sincronizados (filas, imágenes, número de pruebas) en cada pull request | ✅ hecho |
| Texturas de consola en Rust: decodificación BC7 y desentrelazado GFX10 `SW_4K_S` portados de Xbox2Windows (MIT), resúmenes de referencia reproducidos; `anyxboxx_texture bc7 <bloques.bin> <an> <al> <salida.png> [--4k-s]` | 🟡 en curso |
| Otras interfaces GDK escritas por AnyXboxX (`XGameUi`, `XNetworking`…) | ⏳ pendiente |
| Recompilador de shaders RDNA 2 → DXIL: primeros programas traducidos a HLSL, compilados a DXIL y ejecutados en la GPU del PC con D3D12 (`--hlsl`, `anyxboxx_gpu_run.exe`, WARP sin GPU), memoria idéntica a un intérprete de referencia wave32 que ejecuta 1.009 de 1.487 codificaciones (escalares, VOP1/VOP2/VOPC/VOP3, memoria: SMEM, LDS, GLOBAL, MUBUF con límites V#, atómicas, saltos, divergencia con `exec`); un primer vertex shader y pixel shader (exportaciones EXP, interpolación VINTRP) dibujados con D3D12, idénticos vértice a vértice y píxel a píxel: `scarlett.py --rdna2 <shader.bin> --executer` | 🟡 en curso |
| Caché de shaders: los shaders traducidos se compilan una vez a DXIL y luego se reutilizan desde disco (1,4 ms) o memoria (0,8 ms) en lugar de dxc (22 ms); `%LOCALAPPDATA%\AnyXboxX\shader-cache` o `ANYXBOXX_SHADER_CACHE`, tamaño limitado | 🟡 en curso |
| GTA VI Xbox Series 1.0.2.1 con VIctory (`third_party/victory`, fork `fxceless/victory-gta6` en `7b0f736`): el mundo se muestra y se puede jugar a unos 4 fps (observado por el mantenedor, Windows 11, RTX 4070 Super); el dispositivo del host se pierde tras unos minutos o hasta unos 13 minutos | 🟡 en curso |
| Excepciones SEH x64 (`.pdata`), múltiples hilos | ⏳ pendiente |
| Carga dinámica de una DLL durante la ejecución (`LoadLibrary` + `DllMain`) | ⏳ pendiente |
| Gráficos D3D12.X hacia Direct3D 12 / Vulkan | ⏳ pendiente |
| Audio XMA2 de consola: decodificado a WAV por el port en Rust del decodificador de FFmpeg hecho por TomBox (LGPL, a 1 LSB de FFmpeg en la muestra pública de FATE); `anyxboxx_xma <entrada.xma> <salida.wav>`, archivos de un flujo | 🟡 en curso |

<table>
<tr>
<td><img src="../images/demo-virage.png" alt="El coche gira hacia la derecha" width="380"></td>
<td><img src="../images/rapport-compatibilite.png" alt="Informe de compatibilidad de la demo" width="380"></td>
</tr>
<tr>
<td align="center">La demo responde a las flechas del teclado.</td>
<td align="center">El diario muestra el informe de compatibilidad.</td>
</tr>
</table>

## Probar la demo

En Windows, instala Python 3.12 de 64 bits con Tcl/Tk y abre PowerShell en la raíz del repositorio.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --demo
```

El modo nativo necesita el runtime C++. Se compila con Visual Studio 2022 o 2026 (carga de trabajo de C++) y CMake:

```powershell
cmake -S runtime -B runtime/build -A x64
cmake --build runtime/build --config Release
```

La cola de tareas reutiliza el módulo `Task` de [libHttpClient](https://github.com/microsoft/libHttpClient) (licencia MIT, `runtime/third_party/libhttpclient-task`). Las DLL acaban en `runtime/build/bin`, o en la carpeta indicada por `ANYXBOXX_RUNTIME`. `ANYXBOXX_SYSTEM_RUNTIME=0` desactiva la delegación al runtime GDK de Windows.

El programa de demostración compilado es `PrototypeScarlett/demo.pe`; su código fuente es `PrototypeScarlett/demo.c`.

## Lanzar un juego en modo nativo

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <dossier ou fichier .exe> [dossiers de DLL…]
```

![SimpleTriangle lanzado por AnyXboxX en modo nativo](../images/simpletriangle-anyxboxx.png)

AnyXboxX carga el propio ejecutable y lo ejecuta directamente en el procesador, como Wine. El runtime de Xbox (`xgameruntime.dll`) lo proporciona AnyXboxX; la ventana y DirectX 12 son los del PC. **Atención: en modo nativo, el programa no está aislado.** Reserva este modo para programas de confianza; `--rapport` y `--banc` siguen aislados dentro de Unicorn. `ANYXBOXX_TRACE=1` muestra las llamadas interceptadas. Detalles: [docs/test-game.md](../test-game.md).

## Lanzar un paquete en modo aislado

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --lancer <dossier du paquet ou fichier .exe> [dossiers de DLL…]
```

Con una carpeta, AnyXboxX lee `MicrosoftGame.Config`, toma el ejecutable declarado para `Scarlett` y lo lanza en la máquina aislada (Unicorn): el programa no toca el PC. El informe indica las importaciones sin resolver y después las llamadas no emuladas, de la más frecuente a la más rara: es la lista de trabajo para completar el emulador. Si falta el ejecutable, el mensaje lo nombra. Con `--md rapport.md`, el mismo informe se escribe en Markdown, con las importaciones que faltan agrupadas por DLL.

## Analizar un programa

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --rapport <dossier ou fichier .exe>
```

El banco de pruebas carga todos los módulos PE de una carpeta y ejecuta su inicialización:

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc <dossier>
```

![Banco de pruebas sobre las DLL de un paquete Scarlett](../images/banc-dll.svg)

Resultados detallados: [docs/progress.md](../progress.md). Juego de prueba libre comparado con su ejecución nativa: [docs/test-game.md](../test-game.md). Una carpeta de DLL adicional (por ejemplo, las DLL de Visual C++) puede seguir al objetivo: `--rapport <cible> <dossier>`.

El informe enumera las funciones importadas, el porcentaje ya emulado y las funciones que faltan. En la interfaz, el botón **Open an Xbox folder…** (Abrir una carpeta Xbox) lee `MicrosoftGame.Config`, muestra este informe y luego lanza el programa; cada llamada no emulada aparece en el diario.

## Arquitectura

![Esquema de los módulos de AnyXboxX](../images/architecture.svg)

| Módulo | Función |
|---|---|
| `emu/config.py` | lee el manifiesto del paquete GDK |
| `emu/loader.py` | carga la imagen PE y prepara importaciones, exportaciones y TLS |
| `emu/machine.py` | procesador Unicorn, pila, heap, TEB/PEB, despacho de llamadas |
| `emu/hle/` | funciones emuladas: `gdk.py`, `kernel.py`, `crt.py`, `libm.py`, `guest.py` |
| `emu/report.py` | informe de compatibilidad |
| `emu/modules.py` | carga las DLL del paquete, enlaza las importaciones, ordena las inicializaciones |
| `emu/bench.py` | banco de pruebas sobre una carpeta de módulos |
| `emu/native/` | ejecución nativa al estilo Wine: cargador, importaciones reales, runtime GDK de AnyXboxX |
| `scarlett.py` | interfaz Tkinter y línea de comandos |

Para añadir una función, decora un manejador en `emu/hle/`:

```python
@hle("gdk")
def XSystemGetDeviceType(c):
    return XBOX_SERIES_X
```

## Investigación

- [Arquitectura de hardware de la Xbox Series X](../research/xbox-series-x-architecture.md): CPU Zen 2, GPU RDNA 2, memoria, Velocity Architecture, seguridad.
- [Emuladores y capas de compatibilidad existentes](../research/state-of-the-art.md): WinDurango, XWine1, Xenia, herramientas XVD.
- [Notas de ingeniería inversa del paquete Scarlett estudiado](../research/package/README.md) (escritas por Codex): tablas RDS5/ETPF, cabeceras RPF, organización del paquete.
- [TomBox y su continuación](../research/tombox.md): DLL de consola en Rust, Direct3D 12.x, traductor de shaders RDNA 2, lo que AnyXboxX reutiliza (MIT, citado).
- [Xbox2Windows](../research/xbox2windows.md): investigación sobre recompilación estática; BC7 y mosaico GFX10 reutilizados por AnyXboxX (MIT, citado).
- [Primer arranque del ejecutable 1.0.2.1](../research/first-boot-1021.md): paradas medidas con `gta6rt` de Leonida en orden, las pull requests de Leonida que las tratan, lista de trabajos para AnyXboxX.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

## Contribuir

La rama `main` está protegida: toda contribución pasa por una pull request revisada, y las pruebas deben pasar. Los errores y las funciones por emular se notifican en las issues. Las reglas completas están en [CONTRIBUTING.md](../../CONTRIBUTING.md) (en francés).

Debate, ayuda e informes de pruebas: [Discord](https://discord.gg/TcX42vRyPU)

## Licencia

AnyXboxX se distribuye bajo la [GNU GPL 3.0 o posterior](../../LICENSE). Las partes de terceros conservan su licencia: el módulo `Task` de libHttpClient (MIT, `runtime/third_party/libhttpclient-task`) y las tablas RDNA 2 generadas a partir de las pruebas de codificación públicas de LLVM (Apache 2.0 con excepción LLVM, `PrototypeScarlett/emu/rdna2_ops.py` y `rdna2_shapes.py`).

Componentes de terceros y créditos: [THIRD_PARTY.md](../../THIRD_PARTY.md).
