//! The submission-lock census in the shape of fork #1375, on the relay.
//!
//! `VICTORY_RELAY=2 VICTORY_RELAY_COPY=1 VICTORY_CARD_STEPS=2 cargo test -p
//! victory-gpu --release --lib host::census::bench -- --ignored --nocapture
//! --test-threads=1`
//!
//! A submitting thread sends `CENSUS_FLIGHTS` flights a frame, each with
//! `CENSUS_COPIES` buffer copies of card work, a refresh of title memory
//! the title threads keep writing (copied up while the lock is held) and a
//! range its "shader" writes (landed by the relay). `CENSUS_RECORDERS`
//! threads record the lists; `CENSUS_TITLE` title threads each block on a
//! fence `CENSUS_FENCES` times a frame (`settle_for_fence`, which settles
//! under the submission lock), and recording threads every
//! `CENSUS_RECORDER_FENCE`-th list (0: never), as the bake paths do.

use super::super::{
    FINISHED, Host, HostList, LATE_WAITED, WHY_FENCE, host, relay_exact, settle_for_fence,
    transition,
};
use super::count;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::{Duration, Instant};
use windows::Win32::Graphics::Direct3D12::*;

const TITLE_LEN: usize = 8 << 20;
const HALF: usize = TITLE_LEN / 2;
const SLOW_LEN: u64 = 16 << 20;
const WRITE_LEN: usize = 64 << 10;

fn knob(name: &str, default: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|v| v.trim().parse().ok())
        .unwrap_or(default)
}

/// Title memory of our own (write-watched) and its host copy.
fn title(host_resource: usize) -> (usize, Arc<crate::shadow::Shadow>) {
    use windows_sys::Win32::System::Memory::{
        MEM_COMMIT, MEM_RESERVE, PAGE_READWRITE, VirtualAlloc,
    };
    const WRITE_WATCH: u32 = 0x20_0000;
    // SAFETY: memory of our own, never freed.
    let base = unsafe {
        VirtualAlloc(
            std::ptr::null(),
            TITLE_LEN,
            MEM_RESERVE | MEM_COMMIT | WRITE_WATCH,
            PAGE_READWRITE,
        )
    };
    assert!(!base.is_null());
    crate::shadow::register(host_resource, base as u64, TITLE_LEN as u64);
    (
        base as usize,
        crate::shadow::find(base as u64, 64).expect("a copy"),
    )
}

/// Card work: `copies` copies of 16 MiB, then a "shader" write of 64 KiB
/// into the second half of the copy.
struct Work {
    from: ID3D12Resource,
    to: ID3D12Resource,
    upload: ID3D12Resource,
}

// SAFETY: D3D12 resources are free-threaded.
unsafe impl Send for Work {}
unsafe impl Sync for Work {}

impl Work {
    fn new(host: &Host) -> Work {
        let (upload, data) = host.upload_buffer(WRITE_LEN as u64).unwrap();
        // SAFETY: the mapping holds WRITE_LEN bytes.
        unsafe { data.write_bytes(0x5a, WRITE_LEN) };
        Work {
            from: host.uav_buffer(SLOW_LEN).unwrap(),
            to: host.uav_buffer(SLOW_LEN).unwrap(),
            upload,
        }
    }

    fn record(
        &self,
        list: &HostList,
        shadow: &Arc<crate::shadow::Shadow>,
        base: usize,
        slot: usize,
        copies: usize,
    ) {
        shadow.refresh(list, base as u64, HALF as u64);
        let at = HALF + (slot % (HALF / WRITE_LEN)) * WRITE_LEN;
        shadow.gpu_writes(list, (base + at) as u64, WRITE_LEN as u64);
        // SAFETY: an open list; live buffers.
        unsafe {
            for _ in 0..copies {
                list.list
                    .CopyBufferRegion(&self.to, 0, &self.from, 0, SLOW_LEN);
                list.list.ResourceBarrier(&[transition(
                    &self.to,
                    D3D12_RESOURCE_STATE_COPY_DEST,
                    D3D12_RESOURCE_STATE_COMMON,
                )]);
            }
            list.list.CopyBufferRegion(
                &shadow.buffer,
                at as u64,
                &self.upload,
                0,
                WRITE_LEN as u64,
            );
            list.list.ResourceBarrier(&[transition(
                &shadow.buffer,
                D3D12_RESOURCE_STATE_COPY_DEST,
                D3D12_RESOURCE_STATE_COMMON,
            )]);
        }
        list.keep(&self.upload);
    }
}

/// A closed list on its way to the submitting thread.
struct Sent(HostList);

// SAFETY: a closed list nothing records into; D3D12 objects are free-threaded.
unsafe impl Send for Sent {}

struct Shape {
    frames: usize,
    flights: usize,
    copies: usize,
    recorders: usize,
    titles: usize,
    fences: usize,
    recorder_fence: usize,
}

/// One run: ms per frame (median, mean) and the census per frame.
fn run(
    host: &'static Host,
    shape: &Shape,
    base: usize,
    shadow: &Arc<crate::shadow::Shadow>,
    work: &Arc<Work>,
) -> (f64, f64) {
    let stop = Arc::new(AtomicBool::new(false));
    let frame = Arc::new(AtomicU64::new(0));
    let (tx, rx) = std::sync::mpsc::sync_channel::<Sent>(shape.flights * 2);
    std::thread::scope(|s| {
        for r in 0..shape.recorders {
            let (tx, stop, work, shadow) = (tx.clone(), stop.clone(), work.clone(), shadow.clone());
            let every = shape.recorder_fence;
            let copies = shape.copies;
            s.spawn(move || {
                let mut made = 0usize;
                while !stop.load(Ordering::Relaxed) {
                    let list = host.new_list().unwrap();
                    work.record(&list, &shadow, base, r * 1000 + made, copies);
                    list.close();
                    if tx.send(Sent(list)).is_err() {
                        break;
                    }
                    made += 1;
                    if every > 0 && made.is_multiple_of(every) {
                        settle_for_fence();
                    }
                }
            });
        }
        drop(tx);
        for t in 0..shape.titles {
            let (stop, frame) = (stop.clone(), frame.clone());
            let fences = shape.fences;
            s.spawn(move || {
                let mut seen = 0;
                let mut byte = 0u8;
                while !stop.load(Ordering::Relaxed) {
                    let now = frame.load(Ordering::Acquire);
                    if now == seen {
                        std::thread::sleep(Duration::from_micros(200));
                        continue;
                    }
                    seen = now;
                    for f in 0..fences {
                        // The title writes some pages the next refresh copies up.
                        for page in 0..16 {
                            let at = base + ((t * 131 + f * 17 + page * 61) % (HALF / 4096)) * 4096;
                            byte = byte.wrapping_add(1);
                            // SAFETY: title memory of our own.
                            unsafe { (at as *mut u8).write_volatile(byte) };
                        }
                        std::thread::sleep(Duration::from_millis(2));
                        settle_for_fence();
                    }
                }
            });
        }
        let mut kept: std::collections::VecDeque<(u64, HostList)> =
            std::collections::VecDeque::new();
        let mut times = Vec::with_capacity(shape.frames);
        let mut lasts = std::collections::VecDeque::new();
        for _ in 0..shape.frames {
            let began = Instant::now();
            frame.fetch_add(1, Ordering::Release);
            for _ in 0..shape.flights {
                let Sent(list) = rx.recv().unwrap();
                let (number, _) = host.execute_own(&list);
                kept.push_back((number, list));
                let finished = FINISHED.load(Ordering::Acquire);
                while kept.front().is_some_and(|(n, _)| *n <= finished) {
                    kept.pop_front();
                }
            }
            // The present's throttle: two frames in the air at most.
            lasts.push_back(kept.back().map_or(0, |(n, _)| *n));
            if lasts.len() > 2 {
                let old = lasts.pop_front().unwrap();
                while FINISHED.load(Ordering::Acquire) < old {
                    std::thread::sleep(Duration::from_micros(100));
                }
            }
            times.push(began.elapsed().as_secs_f64() * 1e3);
        }
        stop.store(true, Ordering::Relaxed);
        // Let the recorders out of a full channel, then let everything land.
        while rx.try_recv().is_ok() {}
        drop(rx);
        super::super::settle_now(super::super::WHY_SYNC);
        drop(kept);
        times.sort_by(f64::total_cmp);
        (
            times[times.len() / 2],
            times.iter().sum::<f64>() / times.len() as f64,
        )
    })
}

/// Card ms of one flight's work, run alone.
fn card_ms(
    host: &Host,
    shadow: &Arc<crate::shadow::Shadow>,
    base: usize,
    work: &Work,
    copies: usize,
) -> f64 {
    let mut best = f64::MAX;
    for i in 0..5 {
        let list = host.new_list().unwrap();
        work.record(&list, shadow, base, i, copies);
        list.close();
        let began = Instant::now();
        host.execute(&[&list]);
        best = best.min(began.elapsed().as_secs_f64() * 1e3);
    }
    best
}

fn report(frames: usize, median: f64, mean: f64) {
    let n = frames as f64;
    eprintln!("  frame: median {median:.2} ms, mean {mean:.2} ms");
    for (p, (taken, waited, held, longest, behind)) in count::take().into_iter().enumerate() {
        if taken == 0 && waited == 0.0 {
            continue;
        }
        let behind: Vec<String> = behind
            .iter()
            .enumerate()
            .filter(|(_, ms)| **ms > 0.0)
            .map(|(h, ms)| {
                format!(
                    "{} {:.2}",
                    if h == 0 { "free" } else { count::name(h - 1) },
                    ms / n
                )
            })
            .collect();
        eprintln!(
            "  {:<20} {:>6.1}x/frame, held {:>7.2} ms/frame (longest {:>6.2}), waited {:>7.2} ms/frame [behind: {}]",
            count::name(p),
            taken as f64 / n,
            held / n,
            longest,
            waited / n,
            behind.join(", ")
        );
    }
    let w: Vec<f64> = LATE_WAITED
        .iter()
        .map(|w| w.swap(0, Ordering::Relaxed) as f64 / 1000.0 / n)
        .collect();
    eprintln!(
        "  waiting for landings per frame: sync {:.2}, title read {:.2}, stale {:.2}, lists in the air {:.2}, fence {:.2} ms",
        w[super::super::WHY_SYNC],
        w[super::super::WHY_READ],
        w[super::super::WHY_STALE],
        w[super::super::WHY_MOST],
        w[WHY_FENCE]
    );
}

#[test]
#[ignore = "wants VICTORY_RELAY=2 VICTORY_RELAY_COPY=1 VICTORY_CARD_STEPS=2 and a process of its own"]
fn lock_census() {
    let Some(host) = host() else {
        eprintln!("lock_census skipped: no host D3D12 device");
        return;
    };
    assert!(relay_exact(), "set VICTORY_RELAY=2");
    let shape = Shape {
        frames: knob("CENSUS_FRAMES", 60),
        flights: knob("CENSUS_FLIGHTS", 8),
        copies: knob("CENSUS_COPIES", 4),
        recorders: knob("CENSUS_RECORDERS", 4),
        titles: knob("CENSUS_TITLE", 2),
        fences: knob("CENSUS_FENCES", 2),
        recorder_fence: knob("CENSUS_RECORDER_FENCE", 0),
    };
    let rounds = knob("CENSUS_ROUNDS", 3);
    let (base, shadow) = title(0xC3C5);
    let work = Arc::new(Work::new(host));
    let card = card_ms(host, &shadow, base, &work, shape.copies);
    eprintln!(
        "lock_census: {} frames of {} flights ({} copies, {card:.2} card ms alone each: {:.1} card ms a frame), \
         {} recorders (fence every {} lists), {} title threads x {} fence waits a frame",
        shape.frames,
        shape.flights,
        shape.copies,
        card * shape.flights as f64,
        shape.recorders,
        shape.recorder_fence,
        shape.titles,
        shape.fences
    );
    // Warm up, then count.
    run(
        host,
        &Shape {
            frames: 10,
            ..shape
        },
        base,
        &shadow,
        &work,
    );
    count::take();
    LATE_WAITED
        .iter()
        .for_each(|w| w.store(0, Ordering::Relaxed));
    for round in 0..rounds {
        let (median, mean) = run(host, &shape, base, &shadow, &work);
        eprintln!("round {round}:");
        report(shape.frames, median, mean);
    }
}
