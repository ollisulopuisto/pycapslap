/// Whether verbose tracing is on, read once from `CAPSLAP_DEBUG`.
///
/// A shared switch for verbose diagnostics across the desktop app and core.
pub fn debug_enabled() -> bool {
    use std::sync::OnceLock;
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| {
        matches!(
            std::env::var("CAPSLAP_DEBUG").as_deref(),
            Ok("1") | Ok("true")
        )
    })
}

/// Trace to stderr, but only when `CAPSLAP_DEBUG` is set.
#[macro_export]
macro_rules! debug_log {
    ($($arg:tt)*) => {
        if $crate::debug_enabled() {
            eprintln!($($arg)*);
        }
    };
}

pub mod audio;
pub mod captions;
pub mod justify;
pub mod media_tools;
pub mod placement;
pub mod rpc;
pub mod text_metrics;
pub mod types;
pub mod video;
pub mod transcription;
