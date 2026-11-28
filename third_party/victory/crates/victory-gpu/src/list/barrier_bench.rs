//! What the barriers and commands of ours recorded among the title's cost on
//! the card, in a frame shaped like the title's: 330 lists, about 6,900
//! draws and 1,000 dispatches (the 4060 Laptop timing run of VIctory #3505).
//! Ignored by default; run it with
//! `cargo test -p victory-gpu --release --lib list::barrier_bench -- --ignored --nocapture --test-threads=1`.
//! It needs no title files: the draws and dispatches are ours.
//!
//! `bench_barrier_costs` inserts each barrier shape the layer records
//! (`list::host_barriers`, `barrier_groups`, `sync`, `ensure_state`, the
//! placed copies' `wait_for_all`, the closing of a list) a known number of
//! times into the frame and reads the card's time of the whole frame from
//! two timestamps, so each shape's cost is the difference from the same
//! frame without it, per instance. `bench_timed_lists` submits the lists one
//! at a time and waits for each, as `VICTORY_GPU_TIMING` does, and splits the
//! time from sending to the signal into the stamped commands and the rest.
//!
//! RTX 4060 Laptop, 2026-11-28, 7 rounds (light frame 2.15 ms / 8x work
//! 5.0 ms): a UAV barrier on nothing costs 0.18-0.29 us between draws and
//! 0.39-0.76 us in front of a dispatch, the same as one on the buffer, and a
//! second one in a row costs nothing; transitions of textures that are not
//! targets cost nothing, in one call or four; the enhanced `wait_for_all` is
//! 1.3-2.3 us, and a placed 256-byte copy 3.2-4.2 us with its two waits
//! whether they are all syncs, narrowed to the copy, or legacy (1.5-2.5 us
//! bare); a list's closing copy 1.9 us. One list at a time, as timing runs
//! send them, costs 52-60 us a list between the stamps (sending, signal,
//! waking): 17-20 ms for 330 lists.

use std::time::Instant;

use windows::Win32::Graphics::Direct3D::Fxc::D3DCompile;
use windows::Win32::Graphics::Direct3D::{D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP, ID3DBlob};
use windows::Win32::Graphics::Direct3D12::*;
use windows::Win32::Graphics::Dxgi::Common::{DXGI_FORMAT_R8G8B8A8_UNORM, DXGI_SAMPLE_DESC};
use windows::Win32::System::Threading::{CreateEventW, INFINITE, WaitForSingleObject};
use windows::core::{Interface, PCSTR, s};

use crate::host::transition;

/// The frame's shape (VIctory #3505, 4060 Laptop, ~6,900 draws).
const LISTS: usize = 330;
const DRAWS: usize = 6900;
const DISPATCHES: usize = 1000;
/// Rounds of every variant, interleaved (the 4060 Laptop's clock moves
/// between two speeds from round to round).
const ROUNDS: usize = 7;
/// Instances of a barrier shape inserted into a frame.
const INSERTED: usize = 2000;

const WIDTH: u32 = 1920;
const HEIGHT: u32 = 1080;
/// Small textures the inserted transitions move (not drawn to).
const SIDES: usize = 4;

const SHADERS: &str = r#"
cbuffer Draw : register(b0) { float2 at; uint seed; uint work; };
#define GRS "RootConstants(num32BitConstants=4, b0)"
[RootSignature(GRS)]
float4 vs(uint v : SV_VertexID) : SV_Position {
    // A 48-pixel square at `at` (in clip space).
    float2 p = at + float2((v & 1) ? 0.05 : 0.0, (v & 2) ? 0.09 : 0.0);
    return float4(p, 0.5, 1);
}
[RootSignature(GRS)]
float4 ps(float4 pos : SV_Position) : SV_Target {
    float x = pos.x * 0.001 + seed;
    [loop] for (uint i = 0; i < work; i++) { x = frac(x * 1.618 + 0.25); }
    return float4(x, 0.5, 0.25, 1);
}
#define CRS "RootConstants(num32BitConstants=4, b0), UAV(u0)"
RWByteAddressBuffer data : register(u0);
[RootSignature(CRS)]
[numthreads(64, 1, 1)]
void cs(uint3 id : SV_DispatchThreadID) {
    // Its own 8 KiB, read and written (`seed` is the dispatch's place).
    uint at = (seed * 2048u + id.x) * 4u;
    uint x = data.Load(at);
    [loop] for (uint i = 0; i < work; i++) { x = x * 1664525u + 1013904223u; }
    data.Store(at, x);
}
"#;

fn compile(entry: &str, target: &str) -> Vec<u8> {
    let entry = std::ffi::CString::new(entry).unwrap();
    let target = std::ffi::CString::new(target).unwrap();
    let mut code: Option<ID3DBlob> = None;
    // SAFETY: the source and names outlive the call.
    unsafe {
        D3DCompile(
            SHADERS.as_ptr().cast(),
            SHADERS.len(),
            s!("barrier bench"),
            None,
            None,
            PCSTR(entry.as_ptr().cast()),
            PCSTR(target.as_ptr().cast()),
            0,
            0,
            &mut code,
            None,
        )
        .unwrap();
        let code = code.unwrap();
        std::slice::from_raw_parts(code.GetBufferPointer().cast::<u8>(), code.GetBufferSize())
            .to_vec()
    }
}

/// A barrier shape the layer records, inserted between two of the frame's
/// commands.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(super) enum Shape {
    /// Nothing (the frame as it is).
    None,
    /// A UAV barrier on no resource (`UAV_BARRIER`: the title's barrier
    /// groups, its pipeline syncs, a barrier batch naming a buffer).
    GlobalUav,
    /// The same twice in a row (a batch naming a buffer next to a group).
    GlobalUavTwice,
    /// A UAV barrier on the one buffer the dispatches write.
    TargetedUav,
    /// The enhanced global barrier of a placed copy (`wait_for_all`): all
    /// syncs, common access.
    EnhancedAll,
    /// The same with the sync of a copy after it (what a placed copy needs
    /// in front of it).
    EnhancedToCopy,
    /// A placed copy (`HostList::place_copy`): 256 bytes copied between two
    /// `wait_for_all`s (enhanced, all syncs).
    PlacedAll,
    /// The same copy between narrowed enhanced barriers: all work before
    /// the copy, the copy before all work after.
    PlacedNarrow,
    /// The same copy between the legacy `wait_for_all`s.
    PlacedLegacy,
    /// The same copy with no barrier (wrong; the floor).
    PlacedBare,
    /// The legacy form of `wait_for_all`: an aliasing barrier on nothing
    /// and a UAV barrier on nothing in one call.
    AliasAndUav,
    /// A side texture moved out of the shader read state and back, in two
    /// calls (a state change and its undo with nothing between).
    TransitionPair,
    /// Four side textures moved, each in its own call (`ensure_state` per
    /// bound texture).
    FourCalls,
    /// The same four in one call (`VICTORY_JOIN_BARRIERS=1`).
    FourJoined,
}

/// Where the inserted shapes go.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Context {
    /// Between draws (one every few draws).
    Draws,
    /// In front of dispatches (one before every dispatch, the rest between
    /// draws).
    Dispatches,
}

struct Bench {
    device: ID3D12Device,
    queue: ID3D12CommandQueue,
    allocators: Vec<ID3D12CommandAllocator>,
    lists: Vec<ID3D12GraphicsCommandList>,
    fence: ID3D12Fence,
    fenced: u64,
    event: windows::Win32::Foundation::HANDLE,
    frequency: f64,
    stamps: ID3D12QueryHeap,
    back: ID3D12Resource,
    graphics_root: ID3D12RootSignature,
    compute_root: ID3D12RootSignature,
    draw_pso: ID3D12PipelineState,
    dispatch_pso: ID3D12PipelineState,
    rtv: D3D12_CPU_DESCRIPTOR_HANDLE,
    data: ID3D12Resource,
    sides: Vec<ID3D12Resource>,
    /// The four side textures' state now (they alternate).
    sides_read: bool,
    copy_from: ID3D12Resource,
    copy_to: ID3D12Resource,
    /// Where a closing copies (common, promoted).
    closing_dest: ID3D12Resource,
    /// Pixel shader and compute loop lengths.
    pixel_work: u32,
    compute_work: u32,
}

/// The card's time of a frame in ms and the CPU's time from sending to the
/// signal.
struct Took {
    gpu: f64,
    wall: f64,
}

impl Bench {
    /// # Safety
    /// Plain D3D12 object creation.
    unsafe fn new(host: &crate::host::Host) -> Bench {
        let device = host.device.clone();
        unsafe {
            let queue: ID3D12CommandQueue = device
                .CreateCommandQueue(&D3D12_COMMAND_QUEUE_DESC {
                    Type: D3D12_COMMAND_LIST_TYPE_DIRECT,
                    ..Default::default()
                })
                .unwrap();
            let mut allocators = Vec::new();
            let mut lists = Vec::new();
            for _ in 0..LISTS {
                let a: ID3D12CommandAllocator = device
                    .CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT)
                    .unwrap();
                let l: ID3D12GraphicsCommandList = device
                    .CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, &a, None)
                    .unwrap();
                l.Close().unwrap();
                allocators.push(a);
                lists.push(l);
            }
            let fence: ID3D12Fence = device.CreateFence(0, D3D12_FENCE_FLAG_NONE).unwrap();
            let event = CreateEventW(None, false, false, None).unwrap();
            let frequency = queue.GetTimestampFrequency().unwrap() as f64;
            let mut stamps: Option<ID3D12QueryHeap> = None;
            device
                .CreateQueryHeap(
                    &D3D12_QUERY_HEAP_DESC {
                        Type: D3D12_QUERY_HEAP_TYPE_TIMESTAMP,
                        Count: 4096,
                        NodeMask: 0,
                    },
                    &mut stamps,
                )
                .unwrap();
            let stamps = stamps.unwrap();
            let back = buffer(
                &device,
                D3D12_HEAP_TYPE_READBACK,
                4096 * 8,
                D3D12_RESOURCE_STATE_COPY_DEST,
                false,
            );

            let (vs, ps, cs) = (
                compile("vs", "vs_5_1"),
                compile("ps", "ps_5_1"),
                compile("cs", "cs_5_1"),
            );
            let graphics_root: ID3D12RootSignature = device.CreateRootSignature(0, &vs).unwrap();
            let compute_root: ID3D12RootSignature = device.CreateRootSignature(0, &cs).unwrap();
            let mut desc = D3D12_GRAPHICS_PIPELINE_STATE_DESC {
                pRootSignature: std::mem::transmute_copy(&graphics_root),
                VS: D3D12_SHADER_BYTECODE {
                    pShaderBytecode: vs.as_ptr().cast(),
                    BytecodeLength: vs.len(),
                },
                PS: D3D12_SHADER_BYTECODE {
                    pShaderBytecode: ps.as_ptr().cast(),
                    BytecodeLength: ps.len(),
                },
                SampleMask: u32::MAX,
                RasterizerState: D3D12_RASTERIZER_DESC {
                    FillMode: D3D12_FILL_MODE_SOLID,
                    CullMode: D3D12_CULL_MODE_NONE,
                    DepthClipEnable: true.into(),
                    ..Default::default()
                },
                PrimitiveTopologyType: D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE,
                NumRenderTargets: 1,
                SampleDesc: DXGI_SAMPLE_DESC {
                    Count: 1,
                    Quality: 0,
                },
                ..Default::default()
            };
            desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
                D3D12_COLOR_WRITE_ENABLE_ALL.0 as u8;
            desc.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
            let draw_pso: ID3D12PipelineState = device.CreateGraphicsPipelineState(&desc).unwrap();
            let dispatch_pso: ID3D12PipelineState = device
                .CreateComputePipelineState(&D3D12_COMPUTE_PIPELINE_STATE_DESC {
                    pRootSignature: std::mem::transmute_copy(&compute_root),
                    CS: D3D12_SHADER_BYTECODE {
                        pShaderBytecode: cs.as_ptr().cast(),
                        BytecodeLength: cs.len(),
                    },
                    ..Default::default()
                })
                .unwrap();
            let target = texture(
                &device,
                WIDTH,
                HEIGHT,
                true,
                D3D12_RESOURCE_STATE_RENDER_TARGET,
            );
            let rtvs: ID3D12DescriptorHeap = device
                .CreateDescriptorHeap(&D3D12_DESCRIPTOR_HEAP_DESC {
                    Type: D3D12_DESCRIPTOR_HEAP_TYPE_RTV,
                    NumDescriptors: 1,
                    ..Default::default()
                })
                .unwrap();
            let rtv = rtvs.GetCPUDescriptorHandleForHeapStart();
            device.CreateRenderTargetView(&target, None, rtv);
            // Alive for the whole run: the lists draw to them.
            std::mem::forget(target);
            std::mem::forget(rtvs);
            let data = buffer(
                &device,
                D3D12_HEAP_TYPE_DEFAULT,
                (DISPATCHES as u64 + INSERTED as u64 + 64) * 8192,
                D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                true,
            );
            let sides = (0..SIDES)
                .map(|_| {
                    texture(
                        &device,
                        256,
                        256,
                        false,
                        D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
                    )
                })
                .collect();
            let copy_from = buffer(
                &device,
                D3D12_HEAP_TYPE_DEFAULT,
                1 << 16,
                D3D12_RESOURCE_STATE_COPY_SOURCE,
                false,
            );
            let copy_to = buffer(
                &device,
                D3D12_HEAP_TYPE_DEFAULT,
                1 << 16,
                D3D12_RESOURCE_STATE_COPY_DEST,
                false,
            );
            let closing_dest = buffer(
                &device,
                D3D12_HEAP_TYPE_DEFAULT,
                1 << 16,
                D3D12_RESOURCE_STATE_COMMON,
                false,
            );
            let work = std::env::var("BARRIER_BENCH_WORK")
                .ok()
                .and_then(|v| v.parse::<u32>().ok())
                .unwrap_or(1);
            Bench {
                closing_dest,
                device,
                queue,
                allocators,
                lists,
                fence,
                fenced: 0,
                event,
                frequency,
                stamps,
                back,
                graphics_root,
                compute_root,
                draw_pso,
                dispatch_pso,
                rtv,
                data,
                sides,
                sides_read: true,
                copy_from,
                copy_to,
                pixel_work: 16 * work,
                compute_work: 64 * work,
            }
        }
    }

    /// Records `shape` into `l`.
    ///
    /// # Safety
    /// An open list.
    unsafe fn insert(&mut self, l: &ID3D12GraphicsCommandList, shape: Shape) {
        let global_uav = D3D12_RESOURCE_BARRIER {
            Type: D3D12_RESOURCE_BARRIER_TYPE_UAV,
            Flags: D3D12_RESOURCE_BARRIER_FLAG_NONE,
            Anonymous: D3D12_RESOURCE_BARRIER_0 {
                UAV: std::mem::ManuallyDrop::new(D3D12_RESOURCE_UAV_BARRIER {
                    pResource: std::mem::ManuallyDrop::new(None),
                }),
            },
        };
        unsafe {
            match shape {
                Shape::None => {}
                Shape::GlobalUav => l.ResourceBarrier(&[global_uav]),
                Shape::GlobalUavTwice => {
                    l.ResourceBarrier(std::slice::from_ref(&global_uav));
                    l.ResourceBarrier(&[global_uav]);
                }
                Shape::TargetedUav => l.ResourceBarrier(&[D3D12_RESOURCE_BARRIER {
                    Type: D3D12_RESOURCE_BARRIER_TYPE_UAV,
                    Flags: D3D12_RESOURCE_BARRIER_FLAG_NONE,
                    Anonymous: D3D12_RESOURCE_BARRIER_0 {
                        UAV: std::mem::ManuallyDrop::new(D3D12_RESOURCE_UAV_BARRIER {
                            pResource: std::mem::transmute_copy(&self.data),
                        }),
                    },
                }]),
                Shape::EnhancedAll | Shape::EnhancedToCopy => {
                    let l7: ID3D12GraphicsCommandList7 = l.cast().unwrap();
                    let (access_before, sync_after, access_after) = if shape == Shape::EnhancedAll {
                        (
                            D3D12_BARRIER_ACCESS_COMMON,
                            D3D12_BARRIER_SYNC_ALL,
                            D3D12_BARRIER_ACCESS_COMMON,
                        )
                    } else {
                        // (Common access only pairs with common access.)
                        (
                            D3D12_BARRIER_ACCESS_UNORDERED_ACCESS
                                | D3D12_BARRIER_ACCESS_RENDER_TARGET
                                | D3D12_BARRIER_ACCESS_COPY_DEST,
                            D3D12_BARRIER_SYNC_COPY,
                            D3D12_BARRIER_ACCESS_COPY_SOURCE | D3D12_BARRIER_ACCESS_COPY_DEST,
                        )
                    };
                    let all = [D3D12_GLOBAL_BARRIER {
                        SyncBefore: D3D12_BARRIER_SYNC_ALL,
                        SyncAfter: sync_after,
                        AccessBefore: access_before,
                        AccessAfter: access_after,
                    }];
                    l7.Barrier(&[D3D12_BARRIER_GROUP {
                        Type: D3D12_BARRIER_TYPE_GLOBAL,
                        NumBarriers: 1,
                        Anonymous: D3D12_BARRIER_GROUP_0 {
                            pGlobalBarriers: all.as_ptr(),
                        },
                    }]);
                }
                Shape::PlacedAll
                | Shape::PlacedNarrow
                | Shape::PlacedLegacy
                | Shape::PlacedBare => {
                    let (before, after) = match shape {
                        Shape::PlacedAll => (Shape::EnhancedAll, Some(Shape::EnhancedAll)),
                        Shape::PlacedNarrow => (Shape::EnhancedToCopy, None),
                        Shape::PlacedLegacy => (Shape::AliasAndUav, Some(Shape::AliasAndUav)),
                        _ => (Shape::None, Some(Shape::None)),
                    };
                    self.insert(l, before);
                    l.CopyBufferRegion(&self.copy_to, 0, &self.copy_from, 0, 256);
                    match after {
                        Some(after) => self.insert(l, after),
                        None => {
                            let l7: ID3D12GraphicsCommandList7 = l.cast().unwrap();
                            let all = [D3D12_GLOBAL_BARRIER {
                                SyncBefore: D3D12_BARRIER_SYNC_COPY,
                                SyncAfter: D3D12_BARRIER_SYNC_ALL,
                                AccessBefore: D3D12_BARRIER_ACCESS_COPY_DEST,
                                AccessAfter: D3D12_BARRIER_ACCESS_VERTEX_BUFFER
                                    | D3D12_BARRIER_ACCESS_INDEX_BUFFER
                                    | D3D12_BARRIER_ACCESS_CONSTANT_BUFFER
                                    | D3D12_BARRIER_ACCESS_SHADER_RESOURCE
                                    | D3D12_BARRIER_ACCESS_UNORDERED_ACCESS
                                    | D3D12_BARRIER_ACCESS_INDIRECT_ARGUMENT
                                    | D3D12_BARRIER_ACCESS_COPY_SOURCE,
                            }];
                            l7.Barrier(&[D3D12_BARRIER_GROUP {
                                Type: D3D12_BARRIER_TYPE_GLOBAL,
                                NumBarriers: 1,
                                Anonymous: D3D12_BARRIER_GROUP_0 {
                                    pGlobalBarriers: all.as_ptr(),
                                },
                            }]);
                        }
                    }
                }
                Shape::AliasAndUav => {
                    let alias = D3D12_RESOURCE_BARRIER {
                        Type: D3D12_RESOURCE_BARRIER_TYPE_ALIASING,
                        Flags: D3D12_RESOURCE_BARRIER_FLAG_NONE,
                        Anonymous: D3D12_RESOURCE_BARRIER_0 {
                            Aliasing: std::mem::ManuallyDrop::new(
                                D3D12_RESOURCE_ALIASING_BARRIER {
                                    pResourceBefore: std::mem::ManuallyDrop::new(None),
                                    pResourceAfter: std::mem::ManuallyDrop::new(None),
                                },
                            ),
                        },
                    };
                    l.ResourceBarrier(&[alias, global_uav]);
                }
                Shape::TransitionPair => {
                    let side = &self.sides[0];
                    l.ResourceBarrier(&[transition(
                        side,
                        D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
                        D3D12_RESOURCE_STATE_COPY_SOURCE,
                    )]);
                    l.ResourceBarrier(&[transition(
                        side,
                        D3D12_RESOURCE_STATE_COPY_SOURCE,
                        D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
                    )]);
                }
                Shape::FourCalls | Shape::FourJoined => {
                    let (from, to) = if self.sides_read {
                        (
                            D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
                            D3D12_RESOURCE_STATE_COPY_SOURCE,
                        )
                    } else {
                        (
                            D3D12_RESOURCE_STATE_COPY_SOURCE,
                            D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,
                        )
                    };
                    self.sides_read = !self.sides_read;
                    let all: Vec<_> = self.sides.iter().map(|s| transition(s, from, to)).collect();
                    if shape == Shape::FourJoined {
                        l.ResourceBarrier(&all);
                    } else {
                        for b in &all {
                            l.ResourceBarrier(std::slice::from_ref(b));
                        }
                    }
                }
            }
        }
    }

    /// Records the frame into the lists: `shape` inserted `inserted` times
    /// in `context`; `closing` adds a list end like the host list's (two
    /// buffers back to common). `stamp_each` notes every command as the
    /// timing run does (a timestamp in front of each).
    ///
    /// # Safety
    /// The lists are not in flight.
    unsafe fn record(
        &mut self,
        shape: Shape,
        inserted: usize,
        context: Context,
        closing: bool,
        stamp_each: bool,
    ) -> Vec<u32> {
        let mut stamp = 0u32;
        let mut firsts = Vec::with_capacity(LISTS + 1);
        let mut draw = 0usize;
        let mut dispatch = 0usize;
        let mut done_inserted = 0usize;
        // Where the inserted shapes go: in front of every `every`-th draw
        // (between draws) or in front of every dispatch, then draws.
        let commands = DRAWS + DISPATCHES;
        let slots_wanted = inserted;
        unsafe {
            for i in 0..LISTS {
                let a = &self.allocators[i];
                let l = self.lists[i].clone();
                a.Reset().unwrap();
                l.Reset(a, None).unwrap();
                firsts.push(stamp);
                if i == 0 || stamp_each {
                    l.EndQuery(&self.stamps, D3D12_QUERY_TYPE_TIMESTAMP, stamp);
                    stamp += 1;
                }
                let draws_here = DRAWS * (i + 1) / LISTS - draw;
                let dispatches_here = DISPATCHES * (i + 1) / LISTS - dispatch;
                // A pass of draws, then a pass of dispatches.
                l.OMSetRenderTargets(1, Some(&self.rtv), false, None);
                l.RSSetViewports(&[D3D12_VIEWPORT {
                    Width: WIDTH as f32,
                    Height: HEIGHT as f32,
                    MaxDepth: 1.0,
                    ..Default::default()
                }]);
                l.RSSetScissorRects(&[windows::Win32::Foundation::RECT {
                    left: 0,
                    top: 0,
                    right: WIDTH as i32,
                    bottom: HEIGHT as i32,
                }]);
                l.SetGraphicsRootSignature(&self.graphics_root);
                l.SetPipelineState(&self.draw_pso);
                l.IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
                for _ in 0..draws_here {
                    let n = draw + dispatch;
                    let wanted = match context {
                        Context::Draws => {
                            slots_wanted * (n + 1) / commands - slots_wanted * n / commands
                        }
                        Context::Dispatches => {
                            let left = slots_wanted.saturating_sub(DISPATCHES);
                            left * (draw + 1) / DRAWS - left * draw / DRAWS
                        }
                    };
                    for _ in 0..wanted {
                        self.insert(&l, shape);
                        done_inserted += 1;
                    }
                    if stamp_each && stamp < 4095 {
                        l.EndQuery(&self.stamps, D3D12_QUERY_TYPE_TIMESTAMP, stamp);
                        stamp += 1;
                    }
                    let x = (draw % 37) as f32 / 37.0 * 1.9 - 0.95;
                    let y = (draw / 37 % 21) as f32 / 21.0 * 1.8 - 0.9;
                    let constants = [x.to_bits(), y.to_bits(), draw as u32, self.pixel_work];
                    l.SetGraphicsRoot32BitConstants(0, 4, constants.as_ptr().cast(), 0);
                    l.DrawInstanced(4, 1, 0, 0);
                    draw += 1;
                }
                l.SetComputeRootSignature(&self.compute_root);
                l.SetPipelineState(&self.dispatch_pso);
                l.SetComputeRootUnorderedAccessView(1, self.data.GetGPUVirtualAddress());
                for _ in 0..dispatches_here {
                    if context == Context::Dispatches && done_inserted < slots_wanted {
                        self.insert(&l, shape);
                        done_inserted += 1;
                    } else if context == Context::Draws {
                        let n = draw + dispatch;
                        let wanted =
                            slots_wanted * (n + 1) / commands - slots_wanted * n / commands;
                        for _ in 0..wanted {
                            self.insert(&l, shape);
                            done_inserted += 1;
                        }
                    }
                    if stamp_each && stamp < 4095 {
                        l.EndQuery(&self.stamps, D3D12_QUERY_TYPE_TIMESTAMP, stamp);
                        stamp += 1;
                    }
                    let constants = [0, 0, dispatch as u32, self.compute_work];
                    l.SetComputeRoot32BitConstants(0, 4, constants.as_ptr().cast(), 0);
                    l.Dispatch(32, 1, 1);
                    dispatch += 1;
                }
                if closing {
                    // A host list's end (`batches_common`, `indirect_common`):
                    // its buffers back to common, then the copy of its
                    // budget words (`card_budget_out`).
                    l.ResourceBarrier(&[transition(
                        &self.copy_to,
                        D3D12_RESOURCE_STATE_COPY_DEST,
                        D3D12_RESOURCE_STATE_COPY_SOURCE,
                    )]);
                    l.CopyBufferRegion(&self.closing_dest, 0, &self.copy_to, 0, 16);
                    l.ResourceBarrier(&[transition(
                        &self.copy_to,
                        D3D12_RESOURCE_STATE_COPY_SOURCE,
                        D3D12_RESOURCE_STATE_COPY_DEST,
                    )]);
                }
                if i + 1 == LISTS || stamp_each {
                    l.EndQuery(&self.stamps, D3D12_QUERY_TYPE_TIMESTAMP, stamp);
                    stamp += 1;
                }
                if i + 1 == LISTS && !stamp_each {
                    l.ResolveQueryData(
                        &self.stamps,
                        D3D12_QUERY_TYPE_TIMESTAMP,
                        0,
                        stamp,
                        &self.back,
                        0,
                    );
                }
                if stamp_each {
                    // Each list on its own, read after it ran (stamps
                    // restart per list).
                    l.ResolveQueryData(
                        &self.stamps,
                        D3D12_QUERY_TYPE_TIMESTAMP,
                        0,
                        stamp,
                        &self.back,
                        0,
                    );
                    firsts[i] = stamp;
                    stamp = 0;
                }
                if let Err(e) = l.Close() {
                    panic!("{shape:?} {context:?} closing={closing}: {e}");
                }
            }
        }
        assert!(
            shape == Shape::None || done_inserted == inserted,
            "{shape:?} {context:?}: {done_inserted} of {inserted}"
        );
        firsts.push(stamp);
        firsts
    }

    /// Runs `lists` in one submission and waits.
    ///
    /// # Safety
    /// Closed lists.
    unsafe fn run(&mut self, lists: &[Option<ID3D12CommandList>]) -> f64 {
        let started = Instant::now();
        unsafe {
            self.queue.ExecuteCommandLists(lists);
            self.fenced += 1;
            self.queue.Signal(&self.fence, self.fenced).unwrap();
            self.fence
                .SetEventOnCompletion(self.fenced, self.event)
                .unwrap();
            WaitForSingleObject(self.event, INFINITE);
        }
        started.elapsed().as_secs_f64() * 1e3
    }

    fn stamps(&self, count: usize) -> Vec<u64> {
        let mut data = std::ptr::null_mut();
        // SAFETY: the read-back buffer the finished frame resolved into.
        unsafe {
            self.back
                .Map(
                    0,
                    Some(&D3D12_RANGE {
                        Begin: 0,
                        End: count * 8,
                    }),
                    Some(&mut data),
                )
                .unwrap();
            let s = std::slice::from_raw_parts(data.cast::<u64>(), count).to_vec();
            self.back.Unmap(0, None);
            s
        }
    }

    /// One frame, all lists in one submission (as the title's lists go
    /// when the card is not timed).
    fn frame(&mut self, shape: Shape, inserted: usize, context: Context, closing: bool) -> Took {
        // SAFETY: the previous frame was waited for.
        unsafe {
            self.record(shape, inserted, context, closing, false);
            let lists: Vec<Option<ID3D12CommandList>> =
                self.lists.iter().map(|l| Some(l.cast().unwrap())).collect();
            let wall = self.run(&lists);
            let s = self.stamps(2);
            Took {
                gpu: (s[1].saturating_sub(s[0])) as f64 * 1e3 / self.frequency,
                wall,
            }
        }
    }
}

fn buffer(
    device: &ID3D12Device,
    kind: D3D12_HEAP_TYPE,
    size: u64,
    state: D3D12_RESOURCE_STATES,
    uav: bool,
) -> ID3D12Resource {
    let mut made: Option<ID3D12Resource> = None;
    // SAFETY: a valid description.
    unsafe {
        device
            .CreateCommittedResource(
                &D3D12_HEAP_PROPERTIES {
                    Type: kind,
                    ..Default::default()
                },
                D3D12_HEAP_FLAG_NONE,
                &D3D12_RESOURCE_DESC {
                    Dimension: D3D12_RESOURCE_DIMENSION_BUFFER,
                    Width: size,
                    Height: 1,
                    DepthOrArraySize: 1,
                    MipLevels: 1,
                    SampleDesc: DXGI_SAMPLE_DESC {
                        Count: 1,
                        Quality: 0,
                    },
                    Layout: D3D12_TEXTURE_LAYOUT_ROW_MAJOR,
                    Flags: if uav {
                        D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS
                    } else {
                        D3D12_RESOURCE_FLAG_NONE
                    },
                    ..Default::default()
                },
                state,
                None,
                &mut made,
            )
            .unwrap();
    }
    made.unwrap()
}

fn texture(
    device: &ID3D12Device,
    width: u32,
    height: u32,
    target: bool,
    state: D3D12_RESOURCE_STATES,
) -> ID3D12Resource {
    let mut made: Option<ID3D12Resource> = None;
    // SAFETY: a valid description.
    unsafe {
        device
            .CreateCommittedResource(
                &D3D12_HEAP_PROPERTIES {
                    Type: D3D12_HEAP_TYPE_DEFAULT,
                    ..Default::default()
                },
                D3D12_HEAP_FLAG_NONE,
                &D3D12_RESOURCE_DESC {
                    Dimension: D3D12_RESOURCE_DIMENSION_TEXTURE2D,
                    Width: u64::from(width),
                    Height: height,
                    DepthOrArraySize: 1,
                    MipLevels: 1,
                    Format: DXGI_FORMAT_R8G8B8A8_UNORM,
                    SampleDesc: DXGI_SAMPLE_DESC {
                        Count: 1,
                        Quality: 0,
                    },
                    Flags: if target {
                        D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET
                    } else {
                        D3D12_RESOURCE_FLAG_NONE
                    },
                    ..Default::default()
                },
                state,
                None,
                &mut made,
            )
            .unwrap();
    }
    made.unwrap()
}

fn adapter_name(device: &ID3D12Device) -> String {
    use windows::Win32::Graphics::Dxgi::{
        CreateDXGIFactory2, DXGI_CREATE_FACTORY_FLAGS, IDXGIAdapter1, IDXGIFactory4,
    };
    // SAFETY: plain queries.
    unsafe {
        let luid = device.GetAdapterLuid();
        CreateDXGIFactory2::<IDXGIFactory4>(DXGI_CREATE_FACTORY_FLAGS(0))
            .and_then(|f| f.EnumAdapterByLuid::<IDXGIAdapter1>(luid))
            .and_then(|a| a.GetDesc1())
            .map(|d| {
                String::from_utf16_lossy(&d.Description)
                    .trim_end_matches('\0')
                    .to_owned()
            })
            .unwrap_or_else(|_| "an unnamed adapter".to_owned())
    }
}

fn median(v: &mut [f64]) -> f64 {
    v.sort_by(f64::total_cmp);
    v[v.len() / 2]
}

#[test]
#[ignore = "benchmark; see the module notes"]
fn bench_barrier_costs() {
    let Some(host) = crate::host::host() else {
        eprintln!("no host GPU");
        return;
    };
    // SAFETY: plain object creation.
    let mut bench = unsafe { Bench::new(host) };
    eprintln!(
        "barrier costs on {}: {LISTS} lists, {DRAWS} draws, {DISPATCHES} dispatches a frame; {INSERTED} of each shape inserted; {ROUNDS} rounds",
        adapter_name(&bench.device)
    );
    let shapes = [
        (Shape::GlobalUav, Context::Dispatches),
        (Shape::TargetedUav, Context::Dispatches),
        (Shape::GlobalUavTwice, Context::Dispatches),
        (Shape::GlobalUav, Context::Draws),
        (Shape::GlobalUavTwice, Context::Draws),
        (Shape::EnhancedAll, Context::Draws),
        (Shape::EnhancedToCopy, Context::Draws),
        (Shape::AliasAndUav, Context::Draws),
        (Shape::PlacedBare, Context::Draws),
        (Shape::PlacedAll, Context::Draws),
        (Shape::PlacedNarrow, Context::Draws),
        (Shape::PlacedLegacy, Context::Draws),
        (Shape::TransitionPair, Context::Draws),
        (Shape::FourCalls, Context::Draws),
        (Shape::FourJoined, Context::Draws),
    ];
    // Enhanced barriers where the adapter has them (`place::wait_for_all`
    // uses the legacy form otherwise).
    let enhanced = {
        let mut o = D3D12_FEATURE_DATA_D3D12_OPTIONS12::default();
        // SAFETY: a feature structure of its size.
        unsafe {
            bench.device.CheckFeatureSupport(
                D3D12_FEATURE_D3D12_OPTIONS12,
                (&raw mut o).cast(),
                size_of::<D3D12_FEATURE_DATA_D3D12_OPTIONS12>() as u32,
            )
        }
        .is_ok()
            && o.EnhancedBarriersSupported.as_bool()
    };
    let shapes: Vec<_> = shapes
        .into_iter()
        .filter(|(s, _)| {
            enhanced
                || !matches!(
                    s,
                    Shape::EnhancedAll
                        | Shape::EnhancedToCopy
                        | Shape::PlacedAll
                        | Shape::PlacedNarrow
                )
        })
        .collect();
    eprintln!("  enhanced barriers: {enhanced}");
    // Warm up.
    for _ in 0..3 {
        bench.frame(Shape::None, 0, Context::Draws, false);
    }
    let mut base = Vec::new();
    let mut closing = Vec::new();
    let mut by: Vec<Vec<f64>> = vec![Vec::new(); shapes.len()];
    let mut deltas: Vec<Vec<f64>> = vec![Vec::new(); shapes.len()];
    for _ in 0..ROUNDS {
        let b = bench.frame(Shape::None, 0, Context::Draws, false).gpu;
        base.push(b);
        // Paired with the frame just before: the clock moves between rounds.
        closing.push(bench.frame(Shape::None, 0, Context::Draws, true).gpu - b);
        for (i, &(shape, context)) in shapes.iter().enumerate() {
            let b = bench.frame(Shape::None, 0, context, false).gpu;
            let t = bench.frame(shape, INSERTED, context, false).gpu;
            by[i].push(t);
            deltas[i].push((t - b) * 1e3 / INSERTED as f64);
        }
    }
    eprintln!(
        "  frame without any: {:.2} ms (median; {:?})",
        median(&mut base.clone()),
        base.iter()
            .map(|v| (v * 100.0).round() / 100.0)
            .collect::<Vec<_>>()
    );
    eprintln!(
        "  closing each list like a host list (2 transitions + a 16-byte copy): {:+.3} ms a frame ({:.2} us a list)",
        median(&mut closing.clone()),
        median(&mut closing.clone()) * 1e3 / LISTS as f64
    );
    for (i, &(shape, context)) in shapes.iter().enumerate() {
        let mut d = deltas[i].clone();
        d.sort_by(f64::total_cmp);
        eprintln!(
            "  {shape:?} ({context:?}): frame {:.2} ms; {:+.2} us each (median; min {:+.2}, max {:+.2})",
            median(&mut by[i].clone()),
            d[d.len() / 2],
            d[0],
            d[d.len() - 1]
        );
    }
}

#[test]
#[ignore = "benchmark; see the module notes"]
fn bench_timed_lists() {
    let Some(host) = crate::host::host() else {
        eprintln!("no host GPU");
        return;
    };
    // SAFETY: plain object creation.
    let mut bench = unsafe { Bench::new(host) };
    eprintln!(
        "timed lists on {}: {LISTS} lists, each sent alone and waited for",
        adapter_name(&bench.device)
    );
    for round in 0..ROUNDS.min(5) {
        // SAFETY: lists not in flight; each is waited for.
        unsafe {
            let counts = bench.record(Shape::None, 0, Context::Draws, true, true);
            let (mut wall, mut noted, mut least) = (0.0, 0.0, f64::MAX);
            for i in 0..LISTS {
                let l: ID3D12CommandList = bench.lists[i].cast().unwrap();
                let w = bench.run(&[Some(l)]);
                let s = bench.stamps(counts[i] as usize);
                for k in 0..s.len().saturating_sub(1) {
                    noted += s[k + 1].saturating_sub(s[k]) as f64 * 1e3 / bench.frequency;
                }
                wall += w;
                least = least.min(w);
            }
            let together = bench.frame(Shape::None, 0, Context::Draws, true);
            eprintln!(
                "  round {round}: one at a time {wall:.2} ms from sending to signal ({:.1} us a list, least {:.1} us);                  stamped commands {noted:.2} ms, the rest {:.2} ms ({:.1} us a list); all in one submission: card {:.2} ms,                  sending to signal {:.2} ms",
                wall * 1e3 / LISTS as f64,
                least * 1e3,
                wall - noted,
                (wall - noted) * 1e3 / LISTS as f64,
                together.gpu,
                together.wall
            );
        }
    }
}
