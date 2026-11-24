# AnyXboxX — emulador de Xbox Series X (protótipo)

[![Discord](https://img.shields.io/badge/Discord-AnyXboxX-5865F2?logo=discord&logoColor=white)](https://discord.gg/TcX42vRyPU)

[English](../../README.md) · [Français](README.fr.md) · [Español](README.es.md) · [Deutsch](README.de.md) · [Italiano](README.it.md) · **Português** · [日本語](README.ja.md) · [中文](README.zh-CN.md) · [Русский](README.ru.md)

> [!NOTE]
> **Onde estamos (24/11/2026)**
>
> Medido em um i7-13700KF + RTX 4070 SUPER, Windows 11, com o fork do VIctory `fxceless/victory-gta6` no commit `7b0f736` (submódulo `third_party/victory`) iniciado por `tools/lancer_victory.ps1 -GameDir <pasta do jogo>`:
>
> - ✅ O build 1.0.2.1 do Xbox Series de GTA VI **inicia** no PC: boot, tela de perfil, configurações da primeira execução, telas legais, carregamento, menu de pausa. Os menus rodam a 30 fps.
> - ✅ Ele chega **ao mundo e o exibe**: o personagem se move sob o controle do jogador e a imagem 3D é exibida, a cerca de 4 imagens por segundo (observado pelo mantenedor, Windows 11, RTX 4070 Super).
> - ⛔ Limite atual: o dispositivo host é perdido após alguns minutos até cerca de 13 minutos no mundo, então não é estável. A integração anterior ficava em cerca de 2,4 imagens por segundo sem imagem 3D; com o fork fixado o mundo é exibido e jogável a cerca de 4 imagens por segundo.
> - 👁 Observado pelo mantenedor (Windows 11, RTX 4070 Super), com o fork `fxceless/victory-gta6` no commit `d279e69` e as configurações do lançador: o jogo foi jogado a cerca de 4 fps por cerca de 13 minutos na área inicial (a prisão). O personagem se move sob o controle do jogador e interage com os primeiros NPCs; depois o dispositivo host é perdido (limite conhecido).
> - 🆕 Fixado desde o commit `7b0f736` (inclui `e9765a7`, "Fix the device loss introduced by the wave64 update"). Observado pelo mantenedor (Windows 11, RTX 4070 Super), a partir do log do VIctory da execução, com `VICTORY_RELAY=2` e as configurações do lançador, cache de pipelines já preenchido: mundo alcançado em cerca de 1 min 25 s, 3,5 fps no primeiro quadro e 4,5 fps após 2 min (cerca de 4.975 draws por quadro, 346 perdidos por falta de pipeline do host), sem perda do dispositivo por cerca de 2 min 40 s no mundo (a janela foi fechada depois). Sem `VICTORY_RELAY`: 5,4 fps em cerca de 3 min, sem perda. O mantenedor o considera um pouco melhor que `d279e69`. Ainda não medido por nós: a estabilidade além de 13 minutos; a issue 26 do fork relata 21,5 minutos estáveis em uma RTX 4060 Ti com `VICTORY_RELAY=2` (relato de terceiros).
> - Requisitos: a sua própria cópia do jogo, uma GPU NVIDIA ou AMD com SM 6.6 e mesh shaders, Rust. Nenhum arquivo do jogo neste repositório.
> - Como executar: [docs/running-gta6.md](../running-gta6.md).

O AnyXboxX carrega executáveis Xbox GDK (formato PE32+ x86-64) e executa o código deles com o Unicorn. As funções de sistema do console são substituídas por um runtime C++ em modo nativo e por código Python na máquina isolada (emulação de alto nível, como o WinDurango ou o Wine). O programa se apresenta como um Xbox Series X: `XSystemGetDeviceType` retorna `XboxScarlettAnaconda`.

## Foco e estado

O AnyXboxX é especializado em um único build: **Grand Theft Auto VI para Xbox Series, versão 1.0.2.1**. Só é traduzido o que este jogo precisa (as funções de sistema que ele importa, os shaders e os métodos do Direct3D 12.x que ele usa). Outros jogos serão testados quando essa tradução estiver completa. O projeto se apoia no [VIctory](https://github.com/Marvisak/VIctory) (Marvisak, GPL-3.0 ou posterior), que mira o mesmo build: o submódulo `third_party/victory` está fixado no fork `fxceless/victory-gta6` (GPL-3.0) no commit `7b0f736`. Obrigado a Marvisak e aos autores dessas pull requests, creditados um a um em [THIRD_PARTY.md](../../THIRD_PARTY.md).

> [!IMPORTANT]
> **O jogo não é jogável.** Veja o quadro no topo desta página para saber o estado atual. Este repositório não contém arquivos do jogo, chaves nem executáveis, e não explica como obtê-los.

Página de status online, com o espaço em disco necessário: **[loopersalty.github.io/AnyXboxX](https://loopersalty.github.io/AnyXboxX/)**.

## Andamento da tradução

![Mapa do andamento: uma célula por função, verde se traduzida](../images/carte-avancee.svg)

Regenerar: `scarlett.py --carte <pasta do pacote> docs/images/carte-avancee.svg`.

![Andamento da tradução do Xbox Series X](../images/traduction.svg)

- **Instruções do processador: 100%.** O Series X usa um AMD Zen 2 em x86-64, o mesmo conjunto de instruções de um PC: no modo nativo, o código do jogo é executado como está, sem tradução.
- **Instruções da GPU: 60%.** Os shaders de um jogo de console são compilados para a GPU RDNA 2 do Series X. 888 das 1.487 codificações RDNA 2 rodam no interpretador de referência, e o recompilador RDNA 2 → DXIL já desenha um primeiro vertex shader e pixel shader com D3D12.
- **Funções de sistema: 66%** das 1 337 funções importadas pelas DLLs do pacote de teste são resolvidas no modo isolado.
- **DLLs próprias do console**: `xmem.dll` (4/4) e `d3d12_xs.dll` (2/2) estão traduzidas para as funções que o pacote usa. O D3D12.X (dispositivo e interfaces `ID3D12*`) é servido pela `d3d12_xs.dll` do TomBox, ainda não testado com um jogo.
- **Runtime GDK: 210 das 396 funções** estão escritas no AnyXboxX, em C++: a fila de tarefas (`XTaskQueue`, `XAsync`, `XThread`), o usuário (`XUser`, um perfil local offline), a identidade do Xbox Series X (`XSystem`, Title ID, análise de uso, recursos do runtime), os saves (`XGameSave`, `XGameSaveFiles`, `XPersistentLocalStorage`) o pacote do jogo (`XPackage`), a loja offline (`XStore`) e, offline, convites, ativações e relatórios de erro (`XGameInvite`, `XGameActivation`, `XGameProtocol`, `XError`), além do estado HDR real e da conectividade de rede do PC (`XDisplayTryEnableHdrMode`, `XNetworkingGetConnectivityHint`). Elas são usadas quando o AnyXboxX gerencia o runtime sozinho: sem o Gaming Services, ou com `ANYXBOXX_SYSTEM_RUNTIME=0`. Se o runtime GDK do Windows estiver presente, ele fornece todas as interfaces, inclusive a fila de tarefas, pois suas APIs só aceitam as próprias filas. O rastreamento (`ANYXBOXX_TRACE=1`) nomeia cada interface solicitada.

O gráfico é regenerado por `scarlett.py --traduction <pasta do pacote> docs/images/traduction.svg`.

## Desempenho (meta: 60 quadros por segundo constantes)

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc-perf <jeu.exe> [secondes] [courbe.svg]
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <jeu.exe> --fps
```

O runtime C++ cronometra cada `Present` da swap chain DXGI do jogo, inclusive quando o DXGI é carregado dinamicamente por uma DLL do jogo (SDL3). Dele saem os quadros por segundo, o tempo médio de um quadro e o «1% baixo» (a cadência dos 1% de quadros mais lentos, que revela as travadas). `--fps` mostra esses valores no título da janela. `--banc-perf` mede durante N segundos, sem contar o primeiro (carregamento), e dá um veredito «60 q/s constantes» (código de saída 2 se a meta não for atingida). Sem essas opções, nada é interceptado.

![SimpleTriangle: quadros por segundo](../images/fps-simpletriangle.svg)

![testgdk: quadros por segundo](../images/fps-testgdk.svg)

Os dois jogos de teste rodam sem sincronização vertical: cerca de 11 700 q/s no SimpleTriangle e 12 600 q/s no testgdk, em modo nativo.

## Andamento do projeto

| Etapa | Estado |
|---|---|
| Leitura de `MicrosoftGame.Config` (TitleId, identidade, executável Scarlett) | ✅ feito |
| Carregamento PE32+: seções e proteções, realocações, importações, exportações | ✅ feito |
| TLS: cópia do modelo, índice, callbacks | ✅ feito |
| TEB e PEB acessíveis pelo registrador GS | ✅ feito |
| Página HLE: 158 nomes de funções GDK, kernel, CRT e matemáticas emulados | ✅ feito |
| Funções desconhecidas: `E_NOTIMPL` e registro no log em vez de uma recusa | ✅ feito |
| Construtores globais de C++ (`_initterm`) executados como código convidado | ✅ feito |
| Relatório de compatibilidade (`--rapport`) e bancada de testes (`--banc`) | ✅ feito |
| Vários módulos vinculados em uma mesma máquina: DLLs do pacote, ordinais, redirecionamentos, realocação em caso de conflito | ✅ feito |
| `GetModuleHandle`, `GetProcAddress`, `LoadLibrary`, `RtlPcToFileHeader` | ✅ feito |
| 16/16 DLLs de um pacote Scarlett inicializadas com suas dependências, 0 chamadas não emuladas | ✅ feito |
| Jogo de teste livre `SimpleTriangle` compilado: a inicialização em C e a inicialização do GDK funcionam no AnyXboxX | ✅ feito |
| Execução nativa no estilo Wine (`--natif`): **o SimpleTriangle é exibido**, runtime GDK fornecido pelo AnyXboxX | ✅ feito |
| Segundo jogo de teste livre, `testgdk` do SDL3: **roda em modo nativo** (janela, sprites, som) | ✅ feito |
| Execução isolada de um pacote ou de um exe (`--lancer`) com a lista das chamadas a emular | ✅ feito |
| Runtime C++ (`runtime/`): `xgameruntime.dll`, `xmem.dll`, `d3d12_xs.dll` pré-carregadas em modo nativo e fornecidas a todas as DLLs do jogo | ✅ feito |
| `xmem.dll`: `XMemAlloc`, `XMemFree` com `XALLOC_ATTRIBUTES` decodificados (layout ERA: memória de heap e gráfica, alinhamento), ganchos, `XMemVirtualQuery` (sinalizador de memória gráfica) | ✅ feito |
| `d3d12_xs.dll`: serialização das assinaturas raiz, redirecionada para o D3D12 do PC | ✅ feito |
| Tabela das 396 funções do GDK: interface e número do método, extraídos de `xgameruntime.lib` (`tools/gdk_interfaces.py`) | ✅ feito |
| `XTaskQueue`, `XAsync`, `XThread` fornecidas pelo AnyXboxX: o testgdk roda sem o runtime do Windows | ✅ feito |
| Outras interfaces do GDK: delegadas ao runtime GDK do Windows, nomeadas pelo rastreamento | 🟡 em andamento |
| 752 testes automatizados | ✅ feito |
| D3D12.X: `D3D12XboxCreateDevice`, interfaces `ID3D12*` do console e `DXGIXPresentArray`, servidos pela `d3d12_xs.dll` em Rust do TomBox (MIT, 48 exportações implementadas, compilada por `tools/build_tombox.py d3d12_xs`, carregada com `ANYXBOXX_D3D12_XS=<caminho>`); não testável aqui sem um executável de console | 🟡 em andamento |
| Bibliotecas de console do TomBox (Rust, GPL-3.0) para o que falta no AnyXboxX: `xg_xs` (layout de texturas, 23 exportações) e `xmem` completo (38 exportações), com `ANYXBOXX_TOMBOX_DIR=<pasta>`; compiladas por `tools/build_tombox.py xg_xs xmem` | 🟡 em andamento |
| `XUser` offline: perfil local sempre conectado, gamertag configurável (`ANYXBOXX_GAMERTAG`), login do testgdk bem-sucedido | ✅ feito |
| Identidade do Xbox Series X: tipo de console (valor de registro `ConsoleMode` simulado, inclusive nas DLLs do jogo), `XSystem`, Title ID lido de `MicrosoftGame.config`, análise de uso «Xbox Series X» | ✅ feito |
| Mapa do andamento: uma célula por função (`--carte`) | ✅ feito |
| Controle (`GameInput`) e áudio (`XAudio2`): a mesma API no console e no PC, ligados às DLLs do Windows em modo nativo | ✅ feito |
| Relatório Markdown das importações ausentes por DLL e das chamadas não emuladas (`--lancer … --md rapport.md`) | ✅ feito |
| Ferramenta de primeira execução de um executável de console: inventário, fornecedor de cada importação (pacote, AnyXboxX, TomBox, Windows, ausente), execuções isoladas, execução nativa opcional; relatório fora do repositório: `python tools/jour_j.py <pacote> [--natif]` ([guia](../day-one.md), em francês) | ✅ feito |
| Contador de quadros (`--fps`) e bancada de desempenho com veredito «60 q/s constantes» e curva (`--banc-perf`) | ✅ feito |
| Saves `XGameSave` (contêineres, blobs, cota, leitura assíncrona) e armazenamento local persistente, no disco do PC (`%LOCALAPPDATA%\AnyXboxX\<TitleId>`, ou `ANYXBOXX_SAVE_DIR`) | ✅ feito |
| `XPackage`: pacote instalado localmente (identificador, idioma, blocos prontos, montagem na pasta do jogo) | ✅ feito |
| `kernelx.dll` (kernel do console): 2 661 funções redirecionadas para `kernel32`/`kernelbase` do Windows | ✅ feito |
| TLS implícito (`thread_local`) dos jogos no modo nativo: DLL portadora `anyxboxx_tls.dll`, cada thread recebe sua cópia (até 256 KiB) | ✅ feito |
| Inicializador nativo em C++ sem Python (`runtime/build/bin/anyxboxx.exe <jogo.exe \| pasta> [--fps]`): SimpleTriangle e testgdk a ~12 000 qps | ✅ feito |
| Desmontador de GPU RDNA 2: 1.487 mnemônicos e operandos na sintaxe do LLVM (escalares, VOP1/VOP2/VOPC/VOP3/VOP3P/SDWA/DPP/SMEM/DS/EXP/MUBUF/MTBUF/MIMG/FLAT com modificadores), verificado em 35.088 codificações públicas do LLVM: `scarlett.py --rdna2 <shader.bin> [--liste]` | 🟡 em andamento |
| Operandos do desmontador RDNA 2 idênticos ao texto do LLVM: escalares e VOP1/VOPC 100%, DS 100%, EXP 100%, SMEM 96,5% (o máximo: o LLVM escreve as demais codificações de duas formas) | ✅ feito |
| Primeiros vertex e pixel shaders RDNA 2 desenhados com D3D12 (`anyxboxx_gpu_run.exe --draw`): cada vértice e cada pixel idênticos ao interpretador de referência, na GPU e com WARP | ✅ feito |
| Texturas nos shaders RDNA 2 recompilados: descritores T#/S# e `image_sample` (2D, texel mais próximo, wrap ou clamp-to-edge, 8_8_8_8_UNORM e 32_32_32_32_FLOAT), idênticos ao interpretador de referência na GPU e com WARP, incluindo um pixel shader com textura; layout dos descritores do Leonida e do Mesa | ✅ feito |
| Segundo tradutor RDNA 2 → SPIR-V (Vulkan): o do Leonida (GPL-3.0), copiado sem alterações em `third_party/leonida/` e alimentado pelo desmontador do próprio AnyXboxX, sem `llvm-mc`; vertex, pixel e compute shaders; 51 dos 52 shaders de console incluídos em `XboxBvhBuilder.dll` do pacote são traduzidos, medição local com `tools/fssm_mesure.py` (`scarlett.py --rdna2 <shader.bin> --spirv ps`) | 🟡 em andamento |
| TomBox atualizado para a versão mais recente (D3D12.X: 194 de 200 métodos pela contagem deles) e mais 4 bibliotecas do console compiladas e servidas a partir de `ANYXBOXX_TOMBOX_DIR`: `d3d12_x` (ESRAM), `XAudio2_9` (vozes XMA), `xapu`, `xgs12`; `tools/build_tombox.py d3d12_xs xg_xs xmem d3d12_x xaudio2_9 xapu xgs12` | 🟡 em andamento |
| Conversão do DXIL do console em DXIL do PC (`dxil-ms-xb2` → `dxil-ms-dx`, sem passar por HLSL): a ferramenta do Xbox2Windows (MIT), copiada sem alterações com seu teste em `third_party/xbox2windows/`; `python third_party/xbox2windows/tools/dxil_retarget.py <entrada> <saída>` ou `--pe <jogo.exe>` | ✅ feito |
| Verificações das pull requests: lint e os 9 README sincronizados (linhas, imagens, número de testes) em cada pull request | ✅ feito |
| Texturas de console em Rust: decodificação BC7 e destilização GFX10 `SW_4K_S` portadas do Xbox2Windows (MIT), resumos de referência reproduzidos; `anyxboxx_texture bc7 <blocos.bin> <l> <a> <saida.png> [--4k-s]` | 🟡 em andamento |
| Outras interfaces do GDK escritas pelo AnyXboxX (`XGameUi`, `XNetworking`…) | ⏳ a fazer |
| Recompilador de shaders RDNA 2 → DXIL: primeiros programas traduzidos para HLSL, compilados para DXIL e executados na GPU do PC com D3D12 (`--hlsl`, `anyxboxx_gpu_run.exe`, WARP sem GPU), memória idêntica a um interpretador de referência wave32 que executa 888 de 1.487 codificações (escalares, VOP1/VOP2/VOPC/VOP3, memória: SMEM, LDS, GLOBAL, MUBUF com limites V#, atômicas, desvios, divergência por `exec`); um primeiro vertex shader e pixel shader (exportações EXP, interpolação VINTRP) desenhados com D3D12, idênticos vértice a vértice e pixel a pixel: `scarlett.py --rdna2 <shader.bin> --executer` | 🟡 em andamento |
| Cache de shaders: shaders traduzidos compilados uma vez em DXIL e depois reaproveitados do disco (1,4 ms) ou da memória (0,8 ms) em vez do dxc (22 ms); `%LOCALAPPDATA%\AnyXboxX\shader-cache` ou `ANYXBOXX_SHADER_CACHE`, tamanho limitado | 🟡 em andamento |
| GTA VI Xbox Series 1.0.2.1 via VIctory (`third_party/victory`, fork `fxceless/victory-gta6` no commit `7b0f736`): o mundo é exibido e jogável a cerca de 4 fps (observado pelo mantenedor, Windows 11, RTX 4070 Super); o dispositivo host é perdido após alguns minutos até cerca de 13 minutos | 🟡 em andamento |
| Exceções SEH x64 (`.pdata`), múltiplas threads | ⏳ a fazer |
| Carregamento dinâmico de uma DLL durante a execução (`LoadLibrary` + `DllMain`) | ⏳ a fazer |
| Gráficos D3D12.X para Direct3D 12 / Vulkan | ⏳ a fazer |
| Áudio XMA2 do console: decodificado em WAV pelo port em Rust do decodificador do FFmpeg feito pelo TomBox (LGPL, a 1 LSB do FFmpeg na amostra pública do FATE); `anyxboxx_xma <entrada.xma> <saida.wav>`, arquivos de um fluxo | 🟡 em andamento |

<table>
<tr>
<td><img src="../images/demo-virage.png" alt="O carro vira para a direita" width="380"></td>
<td><img src="../images/rapport-compatibilite.png" alt="Relatório de compatibilidade da demo" width="380"></td>
</tr>
<tr>
<td align="center">A demo responde às setas do teclado.</td>
<td align="center">O log exibe o relatório de compatibilidade.</td>
</tr>
</table>

## Experimentar a demo

No Windows, instale o Python 3.12 de 64 bits com Tcl/Tk e abra o PowerShell na raiz do repositório.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --demo
```

O modo nativo precisa do runtime C++. Ele é compilado com o Visual Studio 2022 ou 2026 (carga de trabalho C++) e o CMake:

```powershell
cmake -S runtime -B runtime/build -A x64
cmake --build runtime/build --config Release
```

A fila de tarefas reaproveita o módulo `Task` da [libHttpClient](https://github.com/microsoft/libHttpClient) (licença MIT, `runtime/third_party/libhttpclient-task`). As DLLs vão para `runtime/build/bin`, ou para a pasta indicada por `ANYXBOXX_RUNTIME`. `ANYXBOXX_SYSTEM_RUNTIME=0` desativa a delegação ao runtime GDK do Windows.

O programa de demonstração compilado é `PrototypeScarlett/demo.pe`; o código-fonte dele é `PrototypeScarlett/demo.c`.

## Executar um jogo em modo nativo

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --natif <dossier ou fichier .exe> [dossiers de DLL…]
```

![SimpleTriangle iniciado pelo AnyXboxX em modo nativo](../images/simpletriangle-anyxboxx.png)

O AnyXboxX carrega o próprio executável e o executa diretamente no processador, como o Wine. O runtime do Xbox (`xgameruntime.dll`) é fornecido pelo AnyXboxX; a janela e o DirectX 12 são os do PC. **Atenção: no modo nativo, o programa não é isolado.** Reserve esse modo para programas de confiança; `--rapport` e `--banc` continuam isolados dentro do Unicorn. `ANYXBOXX_TRACE=1` exibe as chamadas interceptadas. Detalhes: [docs/test-game.md](../test-game.md).

## Executar um pacote em modo isolado

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --lancer <dossier du paquet ou fichier .exe> [dossiers de DLL…]
```

Com uma pasta, o AnyXboxX lê o `MicrosoftGame.Config`, pega o executável declarado para `Scarlett` e o executa na máquina isolada (Unicorn): o programa não toca no PC. O relatório indica as importações não resolvidas e depois as chamadas não emuladas, da mais frequente à mais rara: é a lista de trabalho para completar o emulador. Se o executável estiver ausente, a mensagem o nomeia. Com `--md rapport.md`, o mesmo relatório é escrito em Markdown, com as importações ausentes agrupadas por DLL.

## Analisar um programa

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --rapport <dossier ou fichier .exe>
```

A bancada de testes carrega todos os módulos PE de uma pasta e executa a inicialização deles:

```powershell
.\.venv\Scripts\python.exe .\PrototypeScarlett\scarlett.py --banc <dossier>
```

![Bancada de testes nas DLLs de um pacote Scarlett](../images/banc-dll.svg)

Resultados detalhados: [docs/progress.md](../progress.md). Jogo de teste livre comparado com a execução nativa dele: [docs/test-game.md](../test-game.md). Uma pasta de DLLs adicional (por exemplo, as DLLs do Visual C++) pode acompanhar o alvo: `--rapport <cible> <dossier>`.

O relatório lista as funções importadas, a porcentagem já emulada e as funções que faltam. Na interface, o botão **Open an Xbox folder…** (Abrir uma pasta Xbox) lê `MicrosoftGame.Config`, exibe esse relatório e depois inicia o programa; cada chamada não emulada aparece no log.

## Arquitetura

![Esquema dos módulos do AnyXboxX](../images/architecture.svg)

| Módulo | Função |
|---|---|
| `emu/config.py` | lê o manifesto do pacote GDK |
| `emu/loader.py` | carrega a imagem PE e prepara importações, exportações e TLS |
| `emu/machine.py` | processador Unicorn, pilha, heap, TEB/PEB, despacho das chamadas |
| `emu/hle/` | funções emuladas: `gdk.py`, `kernel.py`, `crt.py`, `libm.py`, `guest.py` |
| `emu/report.py` | relatório de compatibilidade |
| `emu/modules.py` | carrega as DLLs do pacote, vincula as importações, ordena as inicializações |
| `emu/bench.py` | bancada de testes sobre uma pasta de módulos |
| `emu/native/` | execução nativa no estilo Wine: carregador, importações reais, runtime GDK do AnyXboxX |
| `scarlett.py` | interface Tkinter e linha de comando |

Para adicionar uma função, decore um manipulador em `emu/hle/`:

```python
@hle("gdk")
def XSystemGetDeviceType(c):
    return XBOX_SERIES_X
```

## Pesquisa

- [Arquitetura de hardware do Xbox Series X](../research/xbox-series-x-architecture.md): CPU Zen 2, GPU RDNA 2, memória, Velocity Architecture, segurança.
- [Emuladores e camadas de compatibilidade existentes](../research/state-of-the-art.md): WinDurango, XWine1, Xenia, ferramentas XVD.
- [Notas de engenharia reversa do pacote Scarlett estudado](../research/package/README.md) (escritas pelo Codex): tabelas RDS5/ETPF, cabeçalhos RPF, organização do pacote.
- [TomBox e sua continuação](../research/tombox.md): DLLs de console em Rust, Direct3D 12.x, tradutor de shaders RDNA 2, o que o AnyXboxX reaproveita (MIT, citado).
- [Xbox2Windows](../research/xbox2windows.md): pesquisa sobre recompilação estática; BC7 e tiling GFX10 reaproveitados pelo AnyXboxX (MIT, citado).
- [Primeira inicialização do executável 1.0.2.1](../research/first-boot-1021.md): paradas medidas no `gta6rt` do Leonida em ordem, os pull requests do Leonida que as tratam, lista de trabalho do AnyXboxX.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

## Contribuir

A branch `main` é protegida: toda contribuição passa por uma pull request revisada, e os testes precisam passar. Bugs e funções a emular são reportados nas issues. As regras completas estão em [CONTRIBUTING.md](../../CONTRIBUTING.md) (em francês).

Discussão, ajuda e relatos de teste: [Discord](https://discord.gg/TcX42vRyPU)

## Licença

O AnyXboxX é distribuído sob a [GNU GPL 3.0 ou posterior](../../LICENSE). As partes de terceiros mantêm a própria licença: o módulo `Task` do libHttpClient (MIT, `runtime/third_party/libhttpclient-task`) e as tabelas RDNA 2 geradas a partir dos testes de codificação públicos do LLVM (Apache 2.0 com exceção LLVM, `PrototypeScarlett/emu/rdna2_ops.py` e `rdna2_shapes.py`).

Componentes de terceiros e créditos: [THIRD_PARTY.md](../../THIRD_PARTY.md).
