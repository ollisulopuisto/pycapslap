use crate::rpc::RpcEvent;
use crate::types::{CaptionSegment, TranscribeSegmentsResult};
use anyhow::{anyhow, Context, Result};
use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::io::AsyncBufReadExt;
use tokio::process::Command;

pub const MODELS: &[&str] = &["tiny", "base", "small", "medium", "large", "turbo"];

struct PartialDownload(PathBuf);

impl Drop for PartialDownload {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

fn model_filename(model: &str) -> Result<&'static str> {
    match model {
        "tiny" => Ok("ggml-tiny.bin"),
        "base" => Ok("ggml-base.bin"),
        "small" => Ok("ggml-small.bin"),
        "medium" => Ok("ggml-medium.bin"),
        "large" => Ok("ggml-large-v3.bin"),
        "turbo" => Ok("ggml-large-v3-turbo.bin"),
        _ => Err(anyhow!(
            "Unknown Whisper model '{model}'. Choose one of: {}",
            MODELS.join(", ")
        )),
    }
}

fn model_dir() -> PathBuf {
    if let Some(path) = std::env::var_os("CAPSLAP_WHISPER_MODELS") {
        return PathBuf::from(path);
    }
    #[cfg(target_os = "macos")]
    let root = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("Library/Application Support/PyCapSlap/whisper");
    #[cfg(target_os = "windows")]
    let root = std::env::var_os("LOCALAPPDATA")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("PyCapSlap/whisper");
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let root = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")))
        .unwrap_or_else(std::env::temp_dir)
        .join("pycapslap/whisper");
    root
}

pub fn model_exists(model: &str) -> Result<bool> {
    let path = model_dir().join(model_filename(model)?);
    Ok(path
        .metadata()
        .map(|metadata| metadata.is_file() && metadata.len() >= 1_000_000)
        .unwrap_or(false))
}

pub async fn download_model(
    id: &str,
    model: &str,
    mut emit: impl FnMut(RpcEvent),
) -> Result<serde_json::Value> {
    let filename = model_filename(model)?;
    let directory = model_dir();
    tokio::fs::create_dir_all(&directory).await?;
    let target = directory.join(filename);
    let partial = directory.join(format!("{filename}.{}.part", uuid::Uuid::new_v4()));
    let _partial_download = PartialDownload(partial.clone());
    let url = format!("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{filename}");
    emit(RpcEvent::Progress {
        id: id.into(),
        status: format!("Downloading Whisper {model} model…"),
        progress: -1.0,
    });
    let status = Command::new("curl")
        .args([
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--output",
        ])
        .arg(&partial)
        .arg(url)
        .kill_on_drop(true)
        .status()
        .await
        .context("Could not start curl to download the Whisper model")?;
    if !status.success() {
        let _ = tokio::fs::remove_file(&partial).await;
        return Err(anyhow!(
            "Whisper model download failed (curl exited with {status})"
        ));
    }
    if tokio::fs::metadata(&partial).await?.len() < 1_000_000 {
        let _ = tokio::fs::remove_file(&partial).await;
        return Err(anyhow!("Downloaded Whisper model is unexpectedly small"));
    }
    tokio::fs::rename(&partial, &target).await?;
    emit(RpcEvent::Progress {
        id: id.into(),
        status: format!("Whisper {model} model is ready"),
        progress: 1.0,
    });
    Ok(serde_json::json!({"model": model, "path": target}))
}

fn whisper_binary() -> Result<PathBuf> {
    if let Some(path) = std::env::var_os("CAPSLAP_WHISPER_CLI") {
        let path = PathBuf::from(path);
        if path.is_file() {
            return Ok(path);
        }
    }
    let mut candidates = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("rust/bin/whisper-cli-macos-arm64"));
            candidates.push(dir.join("whisper-cli-macos-arm64"));
            if let Some(rust_dir) = dir.parent().and_then(Path::parent) {
                candidates.push(rust_dir.join("bin/whisper-cli-macos-arm64"));
            }
            if let Some(contents) = dir.parent() {
                candidates.push(contents.join("Resources/rust/bin/whisper-cli-macos-arm64"));
            }
        }
    }
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("bin/whisper-cli-macos-arm64"));
    candidates.into_iter().find(|path| path.is_file()).ok_or_else(|| {
        anyhow!("The Whisper CLI is missing. Reinstall PyCapSlap or rebuild its bundled whisper.cpp runtime.")
    })
}

fn whisper_library_dir(binary: &Path) -> Option<PathBuf> {
    binary.parent().map(|dir| dir.join("lib/libinternal"))
}

pub async fn transcribe(
    id: &str,
    audio: &str,
    model: &str,
    language: Option<&str>,
    temp_dir: &Path,
    mut emit: impl FnMut(RpcEvent),
) -> Result<TranscribeSegmentsResult> {
    let filename = model_filename(model)?;
    let model_path = model_dir().join(filename);
    if !model_path.is_file() {
        return Err(anyhow!("Whisper {model} model is not installed. Open Transcription Settings and download it first."));
    }
    let binary = whisper_binary()?;
    let prefix = temp_dir.join("whisper-transcription");
    let mut command = Command::new(&binary);
    command
        .arg("--model")
        .arg(&model_path)
        .arg("--file")
        .arg(audio)
        .arg("--output-json-full")
        .arg("--output-file")
        .arg(&prefix)
        .arg("--print-progress");
    if let Some(lib_dir) = whisper_library_dir(&binary) {
        #[cfg(target_os = "macos")]
        {
            let old = std::env::var_os("DYLD_LIBRARY_PATH").unwrap_or_default();
            let mut paths = vec![lib_dir];
            paths.extend(std::env::split_paths(&old));
            command.env("DYLD_LIBRARY_PATH", std::env::join_paths(paths)?);
        }
    }
    let language = language.filter(|value| !value.is_empty()).unwrap_or("auto");
    command.arg("--language").arg(language);
    command
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let mut child = command.spawn().context("Could not start whisper.cpp")?;
    let mut stderr_tail = VecDeque::with_capacity(12);
    if let Some(stderr) = child.stderr.take() {
        let mut lines = tokio::io::BufReader::new(stderr).lines();
        while let Some(line) = lines.next_line().await? {
            if stderr_tail.len() == 12 {
                stderr_tail.pop_front();
            }
            stderr_tail.push_back(line.chars().take(500).collect::<String>());
            if let Some(value) = line
                .split("progress = ")
                .nth(1)
                .and_then(|s| s.split('%').next())
            {
                if let Ok(percent) = value.trim().parse::<f32>() {
                    emit(RpcEvent::Progress {
                        id: id.into(),
                        status: format!("Whisper transcribing… {percent:.0}%"),
                        progress: (percent / 100.0).clamp(0.0, 0.99),
                    });
                }
            }
        }
    }
    let status = child.wait().await?;
    if !status.success() {
        let details = stderr_tail.into_iter().collect::<Vec<_>>().join("\n");
        return Err(anyhow!(
            "whisper.cpp failed with exit status {status}: {details}"
        ));
    }
    let json_path = prefix.with_extension("json");
    let json: serde_json::Value = serde_json::from_slice(&tokio::fs::read(&json_path).await?)
        .context("whisper.cpp output was not valid JSON")?;
    let mut segments = Vec::new();
    if let Some(rows) = json.get("transcription").and_then(|v| v.as_array()) {
        for row in rows {
            let Some(text) = row.get("text").and_then(|v| v.as_str()) else {
                continue;
            };
            let offsets = row.get("offsets").unwrap_or(&serde_json::Value::Null);
            let (Some(start), Some(end)) = (
                offsets.get("from").and_then(|v| v.as_u64()),
                offsets.get("to").and_then(|v| v.as_u64()),
            ) else {
                continue;
            };
            let text = text.trim();
            if !text.is_empty() && end > start {
                segments.push(CaptionSegment {
                    start_ms: start,
                    end_ms: end,
                    text: text.into(),
                    words: Vec::new(),
                });
            }
        }
    }
    if segments.is_empty() {
        return Err(anyhow!("Whisper returned no timed speech segments"));
    }
    let full_text = segments
        .iter()
        .map(|s| s.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    let duration = segments.last().map(|s| s.end_ms as f64 / 1000.0);
    let result_path = temp_dir.join("transcription-whisper.json");
    tokio::fs::write(
        &result_path,
        serde_json::to_vec_pretty(&serde_json::json!({
            "segments": segments,
            "fullText": full_text,
            "duration": duration,
            "model": format!("whisper-{model}")
        }))?,
    )
    .await?;
    Ok(TranscribeSegmentsResult {
        segments,
        full_text,
        duration,
        json_file: result_path.to_string_lossy().into_owned(),
    })
}
