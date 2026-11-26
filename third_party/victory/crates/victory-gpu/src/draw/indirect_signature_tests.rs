//! The host command signature an indirect execution names, made once and
//! remembered by each thread instead of looked up under a shared lock and
//! cloned on every call.

use super::*;

/// A command signature is made once: every thread, and the same thread
/// asking again after another, gets the same object.
#[test]
fn host_signatures_are_made_once() {
    if crate::host::host().is_none() {
        return; // no host GPU here
    }
    let dispatch = host_signature(2, 12).unwrap();
    let draw = host_signature(0, 16).unwrap();
    assert!(!std::ptr::eq(dispatch, draw));
    assert!(std::ptr::eq(host_signature(2, 12).unwrap(), dispatch));
    let other = std::thread::spawn(|| host_signature(2, 12).unwrap() as *const _ as usize).join().unwrap();
    assert_eq!(other, dispatch as *const _ as usize);
    assert_eq!(dispatch.as_raw(), host_signature(2, 12).unwrap().as_raw());
}
