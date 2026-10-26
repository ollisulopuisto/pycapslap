use std::path::{Path, PathBuf};
use std::process::Command;

pub fn binary_runnable(path: &Path) -> bool {
    path.is_file() && Command::new(path).arg("-version").output().is_ok_and(|o| o.status.success())
}

pub async fn find_ffmpeg_binary() -> anyhow::Result<String> {
    let path = crate::video::get_ffmpeg_path_sync();
    if binary_runnable(Path::new(&path)) {
        Ok(path)
    } else {
        anyhow::bail!("FFmpeg binary not found in any location")
    }
}

pub async fn find_ffprobe_binary() -> anyhow::Result<String> {
    let name = if cfg!(target_os = "windows") { "ffprobe.exe" } else { "ffprobe" };
    let mut candidates = Vec::<PathBuf>::new();
    if let Some(path) = std::env::var_os("FFPROBE_PATH") {
        candidates.push(PathBuf::from(path));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            candidates.extend([parent.join("bin").join(name), parent.join(name)]);
        }
    }
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    candidates.extend([root.join("bin").join(name), root.join("bin-win").join(name), root.join("bin-linux").join(name)]);
    for path in candidates {
        if binary_runnable(&path) {
            return Ok(path.to_string_lossy().into_owned());
        }
    }
    if let Ok(path) = which::which(name) {
        if binary_runnable(&path) {
            return Ok(path.to_string_lossy().into_owned());
        }
    }
    anyhow::bail!("ffprobe binary not found in any location")
}
