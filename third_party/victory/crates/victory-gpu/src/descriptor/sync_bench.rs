//! The heap sync with and without renderer port #2 (`VICTORY_PORT_DESCRIPTORS`),
//! in the shape of the title's frames. One thread plays the submitting
//! thread: each frame it copies view records as bytes into
//! `SYNC_BENCH_CHANGED` (48) slots of each of `SYNC_BENCH_PAGES` (200)
//! random 64 KiB pages of a placed, write-watched view heap of
//! `SYNC_BENCH_SLOTS` (2^20) slots (about 9,600 slots a frame), and runs one
//! [`sync_heaps`]. Meanwhile `SYNC_BENCH_THREADS` (5) title threads each write
//! a placed buffer view through the device method every `SYNC_BENCH_WORK_US`
//! (20) microseconds, into pages of their own.
//!
//! With `VICTORY_PORT_DESCRIPTORS=1` the copies mark their slots as the
//! title's six patched record stores do (`port_descriptors::mark`, the same
//! bytes the stubs of `victory_loader::descriptor_sites` set), except one in
//! a thousand times `SYNC_BENCH_UNMARKED` (0): a writer the patches miss,
//! which only the port's fallback (16 written pages a frame) finds.
//!
//! Prints the sync time and the title threads' view writes per frame
//! (medians over `SYNC_BENCH_FRAMES` (30) frames after three).
//!
//! Checks, the run fails otherwise: after each sync, every record a marked
//! (or, port off, any) copy wrote before it is the one the sync last saw in
//! its slot, and a null view's slot is made from it; after the last frame,
//! with the title threads stopped and one more sync, every slot is. Unmarked
//! copies are counted instead: how many frames until the sync saw them, and
//! how many it had not after the quiet sync.
//!
//! Run with `cargo test -p victory-gpu --release --lib port_sync_bench --
//! --ignored --nocapture --test-threads=1`, once with
//! `VICTORY_PORT_DESCRIPTORS=1` and once without (the switch is read once
//! a process).

use super::*;
use std::sync::atomic::{
    AtomicBool, AtomicU64, AtomicUsize,
    Ordering::{Relaxed, SeqCst},
};
use std::time::{Duration, Instant};
use windows_sys::Win32::System::Memory::{
    MEM_COMMIT, MEM_RELEASE, MEM_RESERVE, PAGE_READWRITE, VirtualAlloc, VirtualFree,
};

const MEM_WRITE_WATCH: u32 = 0x20_0000;

fn env(name: &str, default: usize) -> usize {
    std::env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(default)
}

fn spin(d: Duration) {
    let until = Instant::now() + d;
    while Instant::now() < until {
        std::hint::spin_loop();
    }
}

fn median(v: &mut [f64]) -> f64 {
    v.sort_by(f64::total_cmp);
    v.get(v.len() / 2).copied().unwrap_or(0.0)
}

/// Write-watched title memory of `bytes`, as the title's heap is.
fn watched(bytes: usize) -> usize {
    // SAFETY: a fresh allocation, freed by `free`.
    let p = unsafe {
        VirtualAlloc(std::ptr::null(), bytes, MEM_RESERVE | MEM_COMMIT | MEM_WRITE_WATCH, PAGE_READWRITE)
    } as usize;
    assert_ne!(p, 0, "title memory");
    p
}

fn free(p: usize) {
    // SAFETY: from `watched`.
    unsafe { VirtualFree(p as *mut _, 0, MEM_RELEASE) };
}

/// A placed buffer view's record of 16 4-byte elements at `address`,
/// written by the device method at `at`.
fn buffer_view(address: u64, at: u64) {
    let mut resource = [0u32; 14];
    (resource[0], resource[4]) = (1, 64);
    let mut view = [0u32; 16];
    (view[1], view[2], view[6], view[7]) =
        (1, windows::Win32::Graphics::Direct3D12::D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING, 16, 4);
    (view[10], view[11]) = (address as u32, (address >> 32) as u32);
    create_placed_srv(std::ptr::null(), &resource, &view, at);
}

#[repr(C)]
struct Extended(HeapDesc, Placement);

/// A copied record: its bytes and whether it is a null view (made by the
/// sync at once, whatever the draws do).
type Record = ([u8; 32], bool);

fn records(address: impl Fn(u64) -> u64) -> Vec<Record> {
    (0..65_536u64)
        .map(|k| {
            let mut slot = [0u8; 32];
            let at = slot.as_mut_ptr() as u64;
            let null = k % 4 == 0;
            match k % 8 {
                0 | 4 => create_srv(std::ptr::null(), std::ptr::null(), std::ptr::null(), at),
                2 => create_cbv(std::ptr::null(), &[(k as u32) << 8, 6, 256, 0], at),
                _ => buffer_view(address(k * 7), at),
            }
            (slot, null)
        })
        .collect()
}

#[test]
#[ignore = "a benchmark: needs a D3D12 adapter and a quiet machine"]
fn port_sync_bench() {
    if crate::host::host().is_none() {
        eprintln!("port_sync_bench: no host D3D12 device");
        return;
    }
    let port = crate::port_descriptors::on();
    let slots = env("SYNC_BENCH_SLOTS", 1 << 20);
    let pages = env("SYNC_BENCH_PAGES", 200);
    let changed = env("SYNC_BENCH_CHANGED", 48);
    let threads = env("SYNC_BENCH_THREADS", 5);
    let work = Duration::from_micros(env("SYNC_BENCH_WORK_US", 20) as u64);
    let frames = env("SYNC_BENCH_FRAMES", 30);
    let unmarked = env("SYNC_BENCH_UNMARKED", 0);
    const OWN_PAGES: usize = 4;
    const WARM: usize = 3;
    const WINDOW: usize = 36 << 10;
    let page = crate::watch::PAGE;
    let per_page = page / 32;
    if port {
        // As the launcher says once the six stores are patched.
        crate::port_descriptors::hooked(0, 0, 6);
    }

    let memory = watched(slots * 32);
    const BUFFER: usize = 16;
    let buffer = watched(BUFFER * page);
    crate::shadow::register(buffer, buffer as u64, (BUFFER * page) as u64);
    let addresses = (BUFFER * page / 16 - 16) as u64;
    let address = move |k: u64| buffer as u64 + 16 * (k % addresses);

    let ext = Extended(
        HeapDesc { kind: VIEWS_KIND, count: slots as u32, flags: SHADER_VISIBLE, nodes: 1 },
        Placement { address: memory as u64, size: (slots * 32) as u64 },
    );
    let mut h: This = std::ptr::null();
    assert_eq!(create_heap(std::ptr::null(), &ext.0, &HEAP_IIDS[0], &mut h), crate::object::S_OK);
    assert_eq!(crate::port_descriptors::adopted(memory as u64), port, "the heap is marked iff the port is on");
    let host = heap(h).host().expect("a host view heap");
    let mirrored = (host.count() as usize).min(slots);
    let heap_pages = mirrored / per_page;
    assert!(heap_pages > threads * OWN_PAGES + 16, "a heap too small");
    let shared_pages = heap_pages - threads * OWN_PAGES;

    let pool = records(address);
    let handle = |slot: usize| (memory + slot * 32) as u64;
    // The copy of record `record` into `slot`, marked as a patched store
    // marks unless `mark` is false. Whether it is a null view.
    let put = |slot: usize, record: usize, mark: bool| -> bool {
        let (bytes, null) = &pool[record % pool.len()];
        // SAFETY: `slot` is inside the heap.
        unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), handle(slot) as *mut u8, 32) };
        if port && mark {
            crate::port_descriptors::mark(handle(slot));
        }
        *null
    };
    // Whether the sync saw slot `slot`'s record, and (a null view) made it.
    let landed = |slot: usize, null: bool| {
        let (seen, made) = host.synced(slot as u32, handle(slot));
        seen && (!null || made)
    };
    for slot in 0..slots {
        put(slot, slot.wrapping_mul(7), true);
    }
    let started = Instant::now();
    sync_heaps();
    crate::frame::test_advance();
    let first_sync = started.elapsed();
    let wrong = (0..mirrored).filter(|&s| !landed(s, false)).count();
    assert_eq!(wrong, 0, "slots the first sync did not see");

    let own_slots = OWN_PAGES * per_page;
    let own = |t: usize| (shared_pages + t * OWN_PAGES) * per_page;
    let title_address = |t: usize, n: u64| address(n * 5 + t as u64 * 7919);
    let frame_now = AtomicUsize::new(usize::MAX);
    let stop = AtomicBool::new(false);
    let done: Vec<AtomicU64> = (0..threads).map(|_| AtomicU64::new(0)).collect();

    let (mut sync_ms, mut lost, mut lost_shown) = (Vec::new(), 0usize, 0usize);
    // Unmarked copies not seen yet: (slot, frame written); and how many
    // frames the seen ones took.
    let mut waiting: Vec<(usize, usize)> = Vec::new();
    let mut late: Vec<f64> = Vec::new();
    let mut unmarked_n = 0usize;
    let samples: Vec<Vec<(usize, u32)>> = std::thread::scope(|s| {
        let workers: Vec<_> = (0..threads)
            .map(|t| {
                let (frame_now, stop, done) = (&frame_now, &stop, &done[t]);
                s.spawn(move || {
                    let mut samples = Vec::with_capacity(1 << 20);
                    let mut n = 0u64;
                    while !stop.load(Relaxed) {
                        let frame = frame_now.load(Relaxed);
                        let slot = own(t) + (n % own_slots as u64) as usize;
                        let at = Instant::now();
                        buffer_view(title_address(t, n), handle(slot));
                        let took = at.elapsed().as_nanos().min(u32::MAX as u128) as u32;
                        n += 1;
                        done.store(n, SeqCst);
                        samples.push((frame, took));
                        spin(work);
                    }
                    samples
                })
            })
            .collect();
        struct Stop<'a>(&'a AtomicBool);
        impl Drop for Stop<'_> {
            fn drop(&mut self) {
                self.0.store(true, Relaxed);
            }
        }
        let stopping = Stop(&stop);
        std::thread::sleep(Duration::from_millis(300));
        let mut next = 0x9E37_79B9_7F4A_7C15u64;
        let mut rand = move || {
            next ^= next << 13;
            next ^= next >> 7;
            next ^= next << 17;
            next as usize
        };
        for frame in 0..frames + WARM {
            frame_now.store(frame, Relaxed);
            let mut chosen: Vec<usize> = (0..pages).map(|_| rand() % shared_pages).collect();
            chosen.sort_unstable();
            chosen.dedup();
            let mut told: Vec<(usize, bool)> = Vec::new();
            for &p in &chosen {
                let first = p * per_page;
                // The window's bytes again, as a title copying its table in.
                // SAFETY: inside the page, inside the heap.
                unsafe {
                    let at = (memory + first * 32) as *mut u8;
                    for k in (0..WINDOW).step_by(4096) {
                        at.add(k).write_volatile(at.add(k).read_volatile());
                    }
                }
                for _ in 0..changed {
                    let slot = first + rand() % (WINDOW / 32);
                    let mark = rand() % 1000 >= unmarked;
                    let null = put(slot, rand(), mark);
                    told.retain(|&(s, _)| s != slot);
                    waiting.retain(|&(s, _)| s != slot);
                    if mark || !port {
                        told.push((slot, null));
                    } else {
                        unmarked_n += 1;
                        waiting.push((slot, frame));
                    }
                }
            }
            let at = Instant::now();
            sync_heaps();
            let synced = at.elapsed();
            crate::frame::test_advance();
            for &(slot, null) in &told {
                if !landed(slot, null) {
                    lost += 1;
                    if lost_shown < 5 {
                        lost_shown += 1;
                        eprintln!("frame {frame}: slot {slot} (null view {null}) not seen or not made after the sync");
                    }
                }
            }
            waiting.retain(|&(slot, written)| {
                let seen = host.synced(slot as u32, handle(slot)).0;
                if seen {
                    late.push((frame - written) as f64);
                }
                !seen
            });
            if frame >= WARM {
                sync_ms.push(synced.as_secs_f64() * 1e3);
            }
        }
        frame_now.store(usize::MAX, Relaxed);
        drop(stopping);
        workers.into_iter().map(|w| w.join().unwrap()).collect()
    });

    // Quiet now: one more sync.
    sync_heaps();
    crate::frame::test_advance();
    let unseen_after_quiet = waiting.len();
    let waited = |w: &[(usize, usize)]| w.iter().map(|&(s, _)| s).collect::<std::collections::HashSet<_>>();
    let pending = waited(&waiting);
    let stale: Vec<usize> = (0..mirrored).filter(|&s| !pending.contains(&s) && !landed(s, false)).collect();
    // How many more quiet frames until the fallback saw every unmarked copy.
    let mut quiet_frames = 0;
    while !waiting.is_empty() && quiet_frames < 256 {
        sync_heaps();
        crate::frame::test_advance();
        quiet_frames += 1;
        waiting.retain(|&(slot, _)| !host.synced(slot as u32, handle(slot)).0);
    }

    let mut base: Vec<f64> =
        samples.iter().flatten().filter(|&&(f, _)| f == usize::MAX).map(|&(_, ns)| f64::from(ns)).collect();
    let base_ns = median(&mut base);
    let mut per_frame = vec![(0f64, 0f64); frames];
    for &(f, ns) in samples.iter().flatten() {
        if f == usize::MAX || f < WARM {
            continue;
        }
        let row = &mut per_frame[f - WARM];
        row.0 += f64::from(ns) / 1e6;
        row.1 += (f64::from(ns) - base_ns).max(0.0) / 1e6;
    }
    let mut in_calls: Vec<f64> = per_frame.iter().map(|r| r.0).collect();
    let mut waits: Vec<f64> = per_frame.iter().map(|r| r.1).collect();
    let (lo, hi) = (sync_ms.iter().copied().fold(f64::MAX, f64::min), sync_ms.iter().copied().fold(0.0, f64::max));
    let late_max = late.iter().copied().fold(0.0, f64::max);
    println!(
        "port_sync_bench: port {}, {mirrored} slots, {pages} pages x {changed} records, {threads} title threads; \
         median of {frames} frames: sync {:.3} ms (min {:.3}, max {:.3}); title threads per frame {:.2} ms in view writes, \
         {:.2} ms waiting; first sync {:.0} ms; lost after a sync {lost}, stale at the end {}; unmarked {unmarked_n}: \
         seen after {:.0} frames (median, max {late_max:.0}), {unseen_after_quiet} unseen after the quiet sync, \
         {} still unseen after {quiet_frames} more",
        u8::from(port),
        median(&mut sync_ms),
        lo,
        hi,
        median(&mut in_calls),
        median(&mut waits),
        first_sync.as_secs_f64() * 1e3,
        stale.len(),
        median(&mut late),
        waiting.len(),
    );
    assert_eq!(lost, 0, "records copied before a sync not seen or made after it");
    assert!(stale.is_empty(), "slots not seen after the quiet sync");
    assert!(waiting.is_empty(), "unmarked records the fallback never saw");
    assert_eq!(release(h), 0);
    crate::shadow::unregister(buffer, buffer as u64);
    free(buffer);
    free(memory);
}
