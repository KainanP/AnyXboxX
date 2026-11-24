# AnyXboxX — Xbox-Series-X-Emulator (Prototyp)

[![Discord](https://img.shields.io/badge/Discord-AnyXboxX-5865F2?logo=discord&logoColor=white)](https://discord.gg/TcX42vRyPU)

[English](../../README.md) · [Français](README.fr.md) · [Español](README.es.md) · **Deutsch** · [Italiano](README.it.md) · [Português](README.pt-BR.md) · [日本語](README.ja.md) · [中文](README.zh-CN.md) · [Русский](README.ru.md)

> [!NOTE]
> **Wo wir stehen (24.11.2026)**
>
> Gemessen auf einem i7-13700KF + RTX 4070 SUPER, Windows 11, mit dem VIctory-Fork `fxceless/victory-gta6` im Commit `7b0f736` (Submodul `third_party/victory`), gestartet mit `tools/lancer_victory.ps1 -GameDir <Spielordner>`:
>
> - ✅ Der Xbox-Series-Build 1.0.2.1 von GTA VI **startet** auf dem PC: Boot, Profilbildschirm, Einstellungen beim ersten Start, rechtliche Bildschirme, Ladevorgang, Pausenmenü. Die Menüs laufen mit 30 fps.
> - ✅ Er erreicht **die Spielwelt und zeigt sie an**: Die Figur bewegt sich unter Kontrolle des Spielers und das 3D-Bild wird dargestellt, mit etwa 4 Bildern pro Sekunde (vom Maintainer beobachtet, Windows 11, RTX 4070 Super).
> - ⛔ Aktuelle Grenze: Das Host-Gerät geht nach einigen Minuten bis etwa 13 Minuten in der Spielwelt verloren, es ist also nicht stabil. Die frühere Integration blieb bei etwa 2,4 Bildern pro Sekunde ohne 3D-Bild; mit dem festgelegten Fork wird die Welt angezeigt und ist mit etwa 4 Bildern pro Sekunde spielbar.
> - 👁 Vom Maintainer beobachtet (Windows 11, RTX 4070 Super), mit dem Fork `fxceless/victory-gta6` im Commit `d279e69` und den Einstellungen des Launchers: Das Spiel wurde etwa 13 Minuten lang mit rund 4 fps im Startbereich (dem Gefängnis) gespielt. Die Figur bewegt sich unter Kontrolle des Spielers und interagiert mit den ersten NPCs, dann geht das Host-Gerät verloren (bekannte Grenze).
> - 🆕 Festgelegt seit dem Commit `7b0f736` (enthält `e9765a7`, "Fix the device loss introduced by the wave64 update"). Vom Maintainer beobachtet (Windows 11, RTX 4070 Super), laut VIctory-Log des Laufs, mit `VICTORY_RELAY=2` und den Einstellungen des Launchers, Pipeline-Cache bereits gefüllt: Die Welt wird nach etwa 1 min 25 s erreicht, 3,5 fps im ersten Bild, nach 2 min 4,5 fps (etwa 4.975 Draws pro Bild, 346 mangels Host-Pipeline verloren), kein Geräteverlust während etwa 2 min 40 s in der Welt (das Fenster wurde danach geschlossen). Ohne `VICTORY_RELAY`: 5,4 fps nach etwa 3 min, kein Verlust. Der Maintainer findet ihn etwas besser als `d279e69`. Von uns noch nicht gemessen: Stabilität über 13 Minuten hinaus; Issue 26 des Forks berichtet von 21,5 stabilen Minuten auf einer RTX 4060 Ti mit `VICTORY_RELAY=2` (Bericht Dritter).
> - Voraussetzungen: eine eigene Kopie des Spiels, eine NVIDIA- oder AMD-GPU mit SM 6.6 und Mesh Shaders, Rust. Keine Spieldateien in diesem Repository.
> - So startest du es: [docs/running-gta6.md](../running-gta6.md).

AnyXboxX lädt Xbox-GDK-Programmdateien (Format PE32+ x86-64) und führt deren Code mit Unicorn aus. Die Systemfunktionen der Konsole werden im nativen Modus durch eine C++-Runtime und in der isolierten Maschine durch Python-Code ersetzt (High-Level-Emulation, wie bei WinDurango oder Wine). Das Programm gibt sich als Xbox Series X aus: `XSystemGetDeviceType` liefert `XboxScarlettAnaconda` zurück.

## Ziel und Stand

AnyXboxX ist auf einen einzigen Build spezialisiert: **Grand Theft Auto VI für Xbox Series, Version 1.0.2.1**. Übersetzt wird nur, was dieses Spiel braucht (die importierten Systemfunktionen, die verwendeten Shader und Direct3D-12.x-Methoden). Andere Spiele werden erprobt, sobald diese Übersetzung vollständig ist. Das Projekt baut auf [VIctory](https://github.com/Marvisak/VIctory) (Marvisak, GPL-3.0 oder neuer) auf, das denselben Build anvisiert: das Submodul `third_party/victory` ist auf den Fork `fxceless/victory-gta6` (GPL-3.0) im Commit `7b0f736` festgelegt. Dank an Marvisak und an die Autoren dieser Pull Requests, einzeln aufgeführt in [THIRD_PARTY.md](../../THIRD_PARTY.md).

> [!IMPORTANT]
> **Das Spiel ist nicht spielbar.** Den aktuellen Stand zeigt der Kasten oben auf dieser Seite. Dieses Repository enthält keine Spieldateien, Schlüssel oder ausführbaren Dateien und erklärt nicht, wie man sie erhält.

Statusseite online, mit dem benötigten Speicherplatz: **[loopersalty.github.io/AnyXboxX](https://loopersalty.github.io/AnyXboxX/)**.

## Fortschritt der Übersetzung

![Fortschrittskarte: ein Feld pro Funktion, grün, wenn übersetzt](../images/carte-avancee.svg)

Neu erzeugen: `scarlett.py --carte <Paketordner> docs/images/carte-avancee.svg`.

![Fortschritt der Übersetzung der Xbox Series X](../images/traduction.svg)

- **Prozessorbefehle: 100 %.** Die Series X nutzt einen AMD Zen 2 in x86-64, denselben Befehlssatz wie ein PC: Im nativen Modus läuft der Code des Spiels unverändert, ohne Übersetzung.
- **GPU-Befehle: 69 %.** Die Shader eines Konsolenspiels sind für die RDNA-2-GPU der Series X kompiliert. 1.032 der 1.490 RDNA-2-Kodierungen laufen im Referenzinterpreter, und der Rekompilierer RDNA 2 → DXIL zeichnet bereits einen ersten Vertex- und Pixel-Shader mit D3D12.
- **Systemfunktionen: 66 %** der 1 337 Funktionen, die von den DLLs des Testpakets importiert werden, sind im isolierten Modus aufgelöst.
- **Konsolenspezifische DLLs**: `xmem.dll` (4/4) und `d3d12_xs.dll` (2/2) sind für die vom Paket genutzten Funktionen übersetzt. D3D12.X (Gerät und `ID3D12*`-Schnittstellen) wird von TomBox' `d3d12_xs.dll` bereitgestellt, noch nicht mit einem Spiel getestet.
- **GDK-Runtime: 210 der 396 Funktionen** sind in AnyXboxX in C++ geschrieben: die Aufgabenwarteschlange (`XTaskQueue`, `XAsync`, `XThread`), der Benutzer (`XUser`, ein lokales Offline-Profil), die Identität der Xbox Series X (`XSystem`, Title ID, Analytics, Funktionen der Runtime), die Speicherstände (`XGameSave`, `XGameSaveFiles`, `XPersistentLocalStorage`) das Spielpaket (`XPackage`), der Offline-Store (`XStore`) sowie Einladungen, Aktivierungen und Fehlerberichte offline (`XGameInvite`, `XGameActivation`, `XGameProtocol`, `XError`) sowie der echte HDR-Zustand und die Netzwerkverbindung des PCs (`XDisplayTryEnableHdrMode`, `XNetworkingGetConnectivityHint`). Sie kommen zum Einsatz, wenn AnyXboxX die Runtime allein verwaltet: ohne Gaming Services oder mit `ANYXBOXX_SYSTEM_RUNTIME=0`. Ist die GDK-Runtime von Windows vorhanden, bedient sie alle Schnittstellen, auch die Aufgabenwarteschlange, da ihre APIs nur ihre eigenen Warteschlangen akzeptieren. Die Ablaufverfolgung (`ANYXBOXX_TRACE=1`) nennt jede angeforderte Schnittstelle.

Die Grafik wird mit `scarlett.py --traduction <Paketordner> docs/images/traduction.svg` neu erzeugt.

## Leistung (Ziel: konstant 60 Bilder pro Sekunde)

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc-perf <jeu.exe> [secondes] [courbe.svg]
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <jeu.exe> --fps
```

Die C++-Runtime misst die Dauer jedes `Present` der DXGI-Swap-Chain des Spiels, auch wenn DXGI von einer DLL des Spiels dynamisch geladen wird (SDL3). Daraus ergeben sich die Bilder pro Sekunde, die durchschnittliche Bildzeit und der „1-%-Tiefstwert“ (die Rate der langsamsten 1 % der Bilder, der Ruckler sichtbar macht). `--fps` zeigt diese Werte im Fenstertitel an. `--banc-perf` misst N Sekunden lang, ohne die erste (Laden), und gibt das Urteil „konstant 60 Bilder/s“ aus (Rückgabecode 2, wenn das Ziel verfehlt wird). Ohne diese Optionen wird nichts abgefangen.

![SimpleTriangle: Bilder pro Sekunde](../images/fps-simpletriangle.svg)

![testgdk: Bilder pro Sekunde](../images/fps-testgdk.svg)

Beide Testspiele laufen ohne vertikale Synchronisation: etwa 11.700 Bilder/s für SimpleTriangle und 12.600 Bilder/s für testgdk, im nativen Modus.

## Projektfortschritt

| Schritt | Status |
|---|---|
| `MicrosoftGame.Config` einlesen (TitleId, Identität, Scarlett-Programmdatei) | ✅ erledigt |
| PE32+-Laden: Sektionen und Schutzattribute, Relokationen, Importe, Exporte | ✅ erledigt |
| TLS: Kopie der Vorlage, Index, Callbacks | ✅ erledigt |
| TEB und PEB über das GS-Register erreichbar | ✅ erledigt |
| HLE-Seite: 158 emulierte Funktionsnamen aus GDK, Kernel, CRT und Mathematik | ✅ erledigt |
| Unbekannte Funktionen: `E_NOTIMPL` und Protokolleintrag statt Ablehnung | ✅ erledigt |
| Globale C++-Konstruktoren (`_initterm`) als Gast-Code | ✅ erledigt |
| Kompatibilitätsbericht (`--rapport`) und Prüfstand (`--banc`) | ✅ erledigt |
| Mehrere verknüpfte Module in derselben Maschine: DLLs des Pakets, Ordinale, Weiterleitungen, Relokation bei Konflikten | ✅ erledigt |
| `GetModuleHandle`, `GetProcAddress`, `LoadLibrary`, `RtlPcToFileHeader` | ✅ erledigt |
| 16/16 DLLs eines Scarlett-Pakets samt Abhängigkeiten initialisiert, 0 nicht emulierte Aufrufe | ✅ erledigt |
| Freies Testspiel `SimpleTriangle` kompiliert: C-Start und GDK-Initialisierung laufen in AnyXboxX | ✅ erledigt |
| Native Ausführung nach Wine-Art (`--natif`): **SimpleTriangle wird angezeigt**, GDK-Runtime von AnyXboxX bereitgestellt | ✅ erledigt |
| Zweites freies Testspiel, `testgdk` aus SDL3: **läuft im nativen Modus** (Fenster, Sprites, Ton) | ✅ erledigt |
| Isolierter Start eines Pakets oder einer exe (`--lancer`) mit der Liste der zu emulierenden Aufrufe | ✅ erledigt |
| C++-Runtime (`runtime/`): `xgameruntime.dll`, `xmem.dll`, `d3d12_xs.dll` im nativen Modus vorgeladen und allen DLLs des Spiels bereitgestellt | ✅ erledigt |
| `xmem.dll`: `XMemAlloc`, `XMemFree` mit dekodierten `XALLOC_ATTRIBUTES` (ERA-Layout: Heap- und Grafikspeicher, Ausrichtung), Hooks, `XMemVirtualQuery` (Grafikspeicher-Flag) | ✅ erledigt |
| `d3d12_xs.dll`: Serialisierung der Root-Signaturen, umgeleitet auf das D3D12 des PCs | ✅ erledigt |
| Tabelle der 396 GDK-Funktionen: Schnittstelle und Methodennummer, aus `xgameruntime.lib` extrahiert (`tools/gdk_interfaces.py`) | ✅ erledigt |
| `XTaskQueue`, `XAsync`, `XThread` von AnyXboxX bereitgestellt: testgdk läuft ohne die Runtime von Windows | ✅ erledigt |
| Übrige GDK-Schnittstellen: an die GDK-Runtime von Windows delegiert, von der Ablaufverfolgung benannt | 🟡 in Arbeit |
| 956 automatisierte Tests | ✅ erledigt |
| D3D12.X: `D3D12XboxCreateDevice`, `ID3D12*`-Schnittstellen der Konsole und `DXGIXPresentArray`, bereitgestellt von TomBox' Rust-`d3d12_xs.dll` (MIT, 48 implementierte Exporte, gebaut mit `tools/build_tombox.py d3d12_xs`, geladen mit `ANYXBOXX_D3D12_XS=<Pfad>`); ohne Konsolen-Executable hier nicht testbar | 🟡 in Arbeit |
| Konsolenbibliotheken von TomBox (Rust, GPL-3.0) für das, was AnyXboxX fehlt: `xg_xs` (Texturlayouts, 23 Exporte) und vollständiges `xmem` (38 Exporte), mit `ANYXBOXX_TOMBOX_DIR=<Ordner>`; gebaut mit `tools/build_tombox.py xg_xs xmem` | 🟡 in Arbeit |
| `XUser` offline: immer angemeldetes lokales Profil, einstellbarer Gamertag (`ANYXBOXX_GAMERTAG`), Anmeldung von testgdk erfolgreich | ✅ erledigt |
| Identität der Xbox Series X: Konsolentyp (simulierter Registrierungswert `ConsoleMode`, auch in den DLLs des Spiels), `XSystem`, Title ID aus `MicrosoftGame.config`, Analytics „Xbox Series X“ | ✅ erledigt |
| Fortschrittskarte: ein Feld pro Funktion (`--carte`) | ✅ erledigt |
| Controller (`GameInput`) und Audio (`XAudio2`): dieselbe API auf Konsole und PC, im nativen Modus an die Windows-DLLs gebunden | ✅ erledigt |
| Markdown-Bericht der fehlenden Importe pro DLL und der nicht emulierten Aufrufe (`--lancer … --md rapport.md`) | ✅ erledigt |
| Erststart-Werkzeug für eine Konsolen-Executable: Inventar, Anbieter jedes Imports (Paket, AnyXboxX, TomBox, Windows, fehlend), isolierte Läufe, optionaler nativer Lauf; Bericht außerhalb des Repositorys: `python tools/jour_j.py <Paket> [--natif]` ([Anleitung](../day-one.md), auf Französisch) | ✅ erledigt |
| Bildzähler (`--fps`) und Leistungs-Benchmark mit dem Urteil „konstant 60 Bilder/s“ und einer Kurve (`--banc-perf`) | ✅ erledigt |
| Speicherstände `XGameSave` (Container, Blobs, Kontingent, asynchrones Lesen) und lokaler dauerhafter Speicher, auf der Festplatte des PCs (`%LOCALAPPDATA%\AnyXboxX\<TitleId>` oder `ANYXBOXX_SAVE_DIR`) | ✅ erledigt |
| `XPackage`: lokal installiertes Paket (Kennung, Sprache, fertige Blöcke, Einbindung in den Spielordner) | ✅ erledigt |
| `kernelx.dll` (Konsolenkernel): 2.661 Funktionen an `kernel32`/`kernelbase` von Windows weitergeleitet | ✅ erledigt |
| Implizites TLS (`thread_local`) für Spiele im nativen Modus: Träger-DLL `anyxboxx_tls.dll`, jeder Thread erhält seine Kopie (bis 256 KiB) | ✅ erledigt |
| Nativer C++-Launcher ohne Python (`runtime/build/bin/anyxboxx.exe <spiel.exe \| ordner> [--fps]`): SimpleTriangle und testgdk mit ~12.000 B/s | ✅ erledigt |
| RDNA-2-GPU-Disassembler: 1.490 Mnemonics und Operanden in LLVM-Syntax (skalar, VOP1/VOP2/VOPC/VOP3/VOP3P/SDWA/DPP/SMEM/DS/EXP/MUBUF/MTBUF/MIMG/FLAT mit Modifikatoren), geprüft an 38.999 öffentlichen LLVM-Kodierungen: `scarlett.py --rdna2 <shader.bin> [--liste]` | 🟡 in Arbeit |
| Operanden des RDNA-2-Disassemblers identisch mit dem Text von LLVM: skalar und VOP1/VOPC 100 %, DS 100 %, EXP 100 %, SMEM 96,5 % (das Maximum: LLVM schreibt die übrigen Kodierungen auf zwei Arten) | ✅ erledigt |
| Erste RDNA-2-Vertex- und Pixel-Shader mit D3D12 gezeichnet (`anyxboxx_gpu_run.exe --draw`): jeder Vertex und jedes Pixel identisch mit dem Referenzinterpreter, auf der GPU und mit WARP | ✅ erledigt |
| Texturen in rekompilierten RDNA-2-Shadern: T#/S#-Deskriptoren und `image_sample` (2D, nächstes Texel, Wrap oder Clamp-to-Edge, 8_8_8_8_UNORM und 32_32_32_32_FLOAT), identisch mit dem Referenzinterpreter auf der GPU und mit WARP, einschließlich eines texturierten Pixel-Shaders; Deskriptor-Layout von Leonida und Mesa | ✅ erledigt |
| Zweiter Übersetzer RDNA 2 → SPIR-V (Vulkan): der von Leonida (GPL-3.0), unverändert in `third_party/leonida/` kopiert und vom eigenen Disassembler von AnyXboxX gespeist, ohne `llvm-mc`; Vertex-, Pixel- und Compute-Shader; 51 der 52 Konsolen-Shader aus `XboxBvhBuilder.dll` des Pakets werden übersetzt, lokal gemessen mit `tools/fssm_mesure.py` (`scarlett.py --rdna2 <shader.bin> --spirv ps`) | 🟡 in Arbeit |
| TomBox auf den neuesten Stand gebracht (D3D12.X: nach ihrer Zählung 194 von 200 Methoden) und 4 weitere Konsolenbibliotheken gebaut und aus `ANYXBOXX_TOMBOX_DIR` bereitgestellt: `d3d12_x` (ESRAM), `XAudio2_9` (XMA-Stimmen), `xapu`, `xgs12`; `tools/build_tombox.py d3d12_xs xg_xs xmem d3d12_x xaudio2_9 xapu xgs12` | 🟡 in Arbeit |
| Umwandlung von Konsolen-DXIL in PC-DXIL (`dxil-ms-xb2` → `dxil-ms-dx`, ohne Umweg über HLSL): das Werkzeug von Xbox2Windows (MIT), unverändert mit seinem Test in `third_party/xbox2windows/` kopiert; `python third_party/xbox2windows/tools/dxil_retarget.py <ein> <aus>` oder `--pe <spiel.exe>` | ✅ erledigt |
| Prüfungen bei Pull Requests: Lint und Abgleich der 9 READMEs (Zeilen, Bilder, Testanzahl) bei jedem Pull Request | ✅ erledigt |
| Konsolentexturen in Rust: BC7-Dekodierung und GFX10-`SW_4K_S`-Entkachelung aus Xbox2Windows portiert (MIT), Referenz-Prüfsummen reproduziert; `anyxboxx_texture bc7 <blocks.bin> <b> <h> <out.png> [--4k-s]` | 🟡 in Arbeit |
| Übrige von AnyXboxX geschriebene GDK-Schnittstellen (`XGameUi`, `XNetworking`…) | ⏳ offen |
| Shader-Rekompilierer RDNA 2 → DXIL: erste Programme nach HLSL übersetzt, zu DXIL kompiliert und mit D3D12 auf der GPU des PCs ausgeführt (`--hlsl`, `anyxboxx_gpu_run.exe`, WARP ohne GPU), Speicher identisch mit einem wave32-Referenzinterpreter, der 1.032 von 1.490 Kodierungen ausführt (skalar, VOP1/VOP2/VOPC/VOP3, Speicher: SMEM, LDS, GLOBAL, MUBUF/MTBUF mit V#-Grenzen und typisierten Formaten, Atomics, Sprünge, `exec`-Divergenz); ein erster Vertex- und Pixel-Shader (EXP-Exporte, VINTRP-Interpolation) mit D3D12 gezeichnet, Vertex für Vertex und Pixel für Pixel identisch: `scarlett.py --rdna2 <shader.bin> --executer` | 🟡 in Arbeit |
| Wave64-Compute-Programme auf GPUs mit 32-Lane-Waves (#70): jede 64-Lane-Wave läuft als eine Gruppe von 64 Threads (Lane-Masken und Lane-Lesezugriffe über groupshared-Speicher, ohne `WaveSize`), Speicher identisch mit dem Referenzinterpreter in wave64 auf einer RTX (32-Lane-Waves) und mit WARP; DPP und SDWA-Vergleiche werden weiterhin mit Namen abgelehnt | 🟡 in Arbeit |
| Shader-Cache: übersetzte Shader einmal zu DXIL kompiliert, danach von der Festplatte (1,4 ms) oder aus dem Speicher (0,8 ms) statt mit dxc (22 ms); `%LOCALAPPDATA%\AnyXboxX\shader-cache` oder `ANYXBOXX_SHADER_CACHE`, Größe begrenzt | 🟡 in Arbeit |
| GTA VI Xbox Series 1.0.2.1 über VIctory (`third_party/victory`, Fork `fxceless/victory-gta6` im Commit `7b0f736`): Die Spielwelt wird angezeigt und ist mit etwa 4 fps spielbar (vom Maintainer beobachtet, Windows 11, RTX 4070 Super); das Host-Gerät geht nach einigen Minuten bis etwa 13 Minuten verloren | 🟡 in Arbeit |
| x64-SEH-Ausnahmen (`.pdata`), mehrere Threads | ⏳ offen |
| Dynamisches Laden einer DLL zur Laufzeit (`LoadLibrary` + `DllMain`) | ⏳ offen |
| D3D12.X-Grafik nach Direct3D 12 / Vulkan | ⏳ offen |
| XMA2-Konsolenaudio: von TomBox' Rust-Portierung des FFmpeg-Decoders in WAV dekodiert (LGPL, 1 LSB Abstand zu FFmpeg beim öffentlichen FATE-Beispiel); `anyxboxx_xma <ein.xma> <aus.wav>`, Dateien mit einem Stream | 🟡 in Arbeit |

<table>
<tr>
<td><img src="../images/demo-virage.png" alt="Das Auto biegt nach rechts ab" width="380"></td>
<td><img src="../images/rapport-compatibilite.png" alt="Kompatibilitätsbericht der Demo" width="380"></td>
</tr>
<tr>
<td align="center">Die Demo reagiert auf die Pfeiltasten der Tastatur.</td>
<td align="center">Das Protokoll zeigt den Kompatibilitätsbericht an.</td>
</tr>
</table>

## Die Demo ausprobieren

Installiere unter Windows 64-Bit-Python 3.12 mit Tcl/Tk und öffne dann PowerShell im Stammverzeichnis des Repositorys.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --demo
```

Der native Modus braucht die C++-Runtime. Sie wird mit Visual Studio 2022 oder 2026 (C++-Workload) und CMake kompiliert:

```powershell
cmake -S runtime -B runtime/build -A x64
cmake --build runtime/build --config Release
```

Die Aufgabenwarteschlange übernimmt das Modul `Task` von [libHttpClient](https://github.com/microsoft/libHttpClient) (MIT-Lizenz, `runtime/third_party/libhttpclient-task`). Die DLLs landen in `runtime/build/bin` oder in dem Ordner, den `ANYXBOXX_RUNTIME` angibt. `ANYXBOXX_SYSTEM_RUNTIME=0` schaltet die Delegation an die GDK-Runtime von Windows ab.

Das kompilierte Demoprogramm ist `PrototypeScarlett/demo.pe`; sein Quellcode ist `PrototypeScarlett/demo.c`.

## Ein Spiel im nativen Modus starten

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <dossier ou fichier .exe> [dossiers de DLL…]
```

![SimpleTriangle, von AnyXboxX im nativen Modus gestartet](../images/simpletriangle-anyxboxx.png)

AnyXboxX lädt die Programmdatei selbst und führt sie direkt auf dem Prozessor aus, wie Wine. Die Xbox-Runtime (`xgameruntime.dll`) wird von AnyXboxX bereitgestellt; das Fenster und DirectX 12 stammen vom PC. **Achtung: Im nativen Modus ist das Programm nicht isoliert.** Verwende diesen Modus nur für vertrauenswürdige Programme; `--rapport` und `--banc` bleiben in Unicorn isoliert. `ANYXBOXX_TRACE=1` zeigt die abgefangenen Aufrufe an. Details: [docs/test-game.md](../test-game.md).

## Ein Paket im isolierten Modus starten

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --lancer <dossier du paquet ou fichier .exe> [dossiers de DLL…]
```

Bei einem Ordner liest AnyXboxX `MicrosoftGame.Config`, nimmt die für `Scarlett` deklarierte ausführbare Datei und startet sie in der isolierten Maschine (Unicorn): Das Programm berührt den PC nicht. Der Bericht nennt zuerst die nicht aufgelösten Importe, dann die nicht emulierten Aufrufe, vom häufigsten zum seltensten: Das ist die Arbeitsliste zur Vervollständigung des Emulators. Fehlt die ausführbare Datei, nennt die Meldung sie beim Namen. Mit `--md rapport.md` wird derselbe Bericht als Markdown geschrieben, die fehlenden Importe nach DLL gruppiert.

## Ein Programm analysieren

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --rapport <dossier ou fichier .exe>
```

Der Prüfstand lädt alle PE-Module eines Ordners und führt deren Initialisierung aus:

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc <dossier>
```

![Prüfstand für die DLLs eines Scarlett-Pakets](../images/banc-dll.svg)

Detaillierte Ergebnisse: [docs/progress.md](../progress.md). Freies Testspiel im Vergleich zu seiner nativen Ausführung: [docs/test-game.md](../test-game.md). Ein zusätzlicher DLL-Ordner (zum Beispiel die Visual-C++-DLLs) kann auf das Ziel folgen: `--rapport <cible> <dossier>`.

Der Bericht listet die importierten Funktionen, den bereits emulierten Anteil in Prozent und die fehlenden Funktionen auf. In der Oberfläche liest die Schaltfläche **Open an Xbox folder…** (Xbox-Ordner öffnen) die Datei `MicrosoftGame.Config`, zeigt diesen Bericht an und startet dann das Programm; jeder nicht emulierte Aufruf erscheint im Protokoll.

## Architektur

![Schema der Module von AnyXboxX](../images/architecture.svg)

| Modul | Aufgabe |
|---|---|
| `emu/config.py` | liest das Manifest des GDK-Pakets |
| `emu/loader.py` | lädt das PE-Image und bereitet Importe, Exporte und TLS vor |
| `emu/machine.py` | Unicorn-Prozessor, Stack, Heap, TEB/PEB, Verteilung der Aufrufe |
| `emu/hle/` | emulierte Funktionen: `gdk.py`, `kernel.py`, `crt.py`, `libm.py`, `guest.py` |
| `emu/report.py` | Kompatibilitätsbericht |
| `emu/modules.py` | lädt die DLLs des Pakets, bindet die Importe und ordnet die Initialisierungen |
| `emu/bench.py` | Prüfstand für einen Ordner mit Modulen |
| `emu/native/` | native Ausführung nach Wine-Art: Loader, echte Importe, GDK-Runtime von AnyXboxX |
| `scarlett.py` | Tkinter-Oberfläche und Kommandozeile |

Um eine Funktion hinzuzufügen, dekoriere einen Handler in `emu/hle/`:

```python
@hle("gdk")
def XSystemGetDeviceType(c):
    return XBOX_SERIES_X
```

## Recherche

- [Hardware-Architektur der Xbox Series X](../research/xbox-series-x-architecture.md): Zen-2-CPU, RDNA-2-GPU, Speicher, Velocity Architecture, Sicherheit.
- [Bestehende Emulatoren und Kompatibilitätsschichten](../research/state-of-the-art.md): WinDurango, XWine1, Xenia, XVD-Werkzeuge.
- [Reverse-Engineering-Notizen zum untersuchten Scarlett-Paket](../research/package/README.md) (von Codex verfasst): RDS5/ETPF-Tabellen, RPF-Header, Paketaufbau.
- [TomBox und seine Fortsetzung](../research/tombox.md): Konsolen-DLLs in Rust, Direct3D 12.x, RDNA-2-Shader-Übersetzer, was AnyXboxX übernimmt (MIT, zitiert).
- [Xbox2Windows](../research/xbox2windows.md): Forschung zur statischen Rekompilierung; BC7 und GFX10-Kachelung von AnyXboxX übernommen (MIT, zitiert).
- [Erster Start der Ausführungsdatei 1.0.2.1](../research/first-boot-1021.md): unter `gta6rt` von Leonida gemessene Haltepunkte der Reihe nach, die Pull Requests von Leonida dazu, Arbeitsliste für AnyXboxX.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

## Mitwirken

Der Branch `main` ist geschützt: Jeder Beitrag läuft über einen geprüften Pull Request, und die Tests müssen bestehen. Fehler und zu emulierende Funktionen werden in den Issues gemeldet. Die vollständigen Regeln stehen in [CONTRIBUTING.md](../../CONTRIBUTING.md) (auf Französisch).

Diskussion, Hilfe und Testberichte: [Discord](https://discord.gg/TcX42vRyPU)

## Lizenz

AnyXboxX steht unter der [GNU GPL 3.0 oder neuer](../../LICENSE). Fremdbestandteile behalten ihre eigene Lizenz: das `Task`-Modul von libHttpClient (MIT, `runtime/third_party/libhttpclient-task`) und die aus den öffentlichen Kodierungstests von LLVM erzeugten RDNA-2-Tabellen (Apache 2.0 mit LLVM-Ausnahme, `PrototypeScarlett/emu/rdna2_ops.py` und `rdna2_shapes.py`).

Fremdkomponenten und Danksagungen: [THIRD_PARTY.md](../../THIRD_PARTY.md).
