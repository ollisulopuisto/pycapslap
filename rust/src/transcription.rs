use crate::rpc::RpcEvent;
use crate::types::{CaptionSegment, TranscribeSegmentsParams, TranscribeSegmentsResult};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{Mutex, OnceCell};

static WORKER: OnceCell<Mutex<OrukeetWorker>> = OnceCell::const_new();

struct OrukeetWorker {
    child: Child,
    input: ChildStdin,
    output: tokio::io::Lines<tokio::io::BufReader<tokio::process::ChildStdout>>,
}

impl OrukeetWorker {
    async fn start() -> anyhow::Result<Self> {
        let worker = std::env::var("CAPSLAP_ORUKEET_WORKER")
            .map(PathBuf::from)
            .map_err(|_| anyhow::anyhow!("Orukeet worker is not configured"))?;
        let mut command = if worker.extension().is_some_and(|ext| ext == "py") {
            let python = std::env::var("CAPSLAP_PYTHON").unwrap_or_else(|_| "python3".into());
            let mut command = Command::new(python);
            command.arg(worker);
            command
        } else {
            let mut command = Command::new(worker);
            command.arg("--worker");
            command
        };
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()?;
        let input = child
            .stdin
            .take()
            .ok_or_else(|| anyhow::anyhow!("Orukeet worker has no stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow::anyhow!("Orukeet worker has no stdout"))?;
        if let Some(mut stderr) = child.stderr.take() {
            tokio::spawn(async move {
                let _ = tokio::io::copy(&mut stderr, &mut tokio::io::sink()).await;
            });
        }
        Ok(Self {
            child,
            input,
            output: tokio::io::BufReader::new(stdout).lines(),
        })
    }

    async fn request(&mut self, request: serde_json::Value) -> anyhow::Result<serde_json::Value> {
        let request_id = request.get("id").and_then(|v| v.as_str()).unwrap_or_default().to_owned();
        self.input
            .write_all(serde_json::to_string(&request)?.as_bytes())
            .await?;
        self.input.write_all(b"\n").await?;
        let response = loop {
            let Some(line) = self.output.next_line().await? else {
                let status = self.child.try_wait()?;
                anyhow::bail!("Orukeet worker exited (status: {status:?})");
            };
            let response: serde_json::Value = serde_json::from_str(&line)?;
            if response.get("id").and_then(|v| v.as_str()) == Some(request_id.as_str()) {
                break response;
            }
        };
        if let Some(error) = response.get("error").and_then(|v| v.as_str()) {
            anyhow::bail!("Orukeet: {error}");
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Orukeet worker returned no result"))
    }
}

pub fn orukeet_installation_path() -> PathBuf {
    let root = std::env::var_os("CAPSLAP_ORUKEET_CACHE")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            if cfg!(target_os = "macos") {
                std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(std::env::temp_dir)
                    .join("Library/Caches/PyCapSlap/orukeet")
            } else if cfg!(target_os = "windows") {
                std::env::var_os("LOCALAPPDATA")
                    .map(PathBuf::from)
                    .or_else(|| std::env::var_os("USERPROFILE").map(PathBuf::from))
                    .unwrap_or_else(std::env::temp_dir)
                    .join("PyCapSlap/orukeet")
            } else {
                std::env::var_os("XDG_CACHE_HOME")
                    .map(PathBuf::from)
                    .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")))
                    .unwrap_or_else(std::env::temp_dir)
                    .join("pycapslap/orukeet")
            }
        });
    root.join("installation.json")
}

pub fn orukeet_installed() -> bool {
    orukeet_installation_path().is_file()
}

pub async fn install_orukeet(id: &str, mut emit: impl FnMut(RpcEvent)) -> anyhow::Result<serde_json::Value> {
    emit(RpcEvent::Progress {
        id: id.into(),
        status: "Installing verified Orukeet model and runtime…".into(),
        progress: 0.05,
    });
    let mutex = WORKER
        .get_or_try_init(|| async { Ok::<_, anyhow::Error>(Mutex::new(OrukeetWorker::start().await?)) })
        .await?;
    let mut worker = mutex.lock().await;
    if worker.child.try_wait()?.is_some() {
        *worker = OrukeetWorker::start().await?;
    }
    let result = worker.request(serde_json::json!({"id": id, "action": "install"})).await?;
    emit(RpcEvent::Progress { id: id.into(), status: "Orukeet is ready for offline transcription".into(), progress: 1.0 });
    Ok(result)
}

pub async fn transcribe_segments_with_temp(
    id: &str,
    params: TranscribeSegmentsParams,
    temp_dir: Option<&PathBuf>,
    mut emit: impl FnMut(RpcEvent),
) -> anyhow::Result<TranscribeSegmentsResult> {
    emit(RpcEvent::Progress { id: id.into(), status: "Transcribing locally with Orukeet…".into(), progress: 0.05 });
    let mutex = WORKER
        .get_or_try_init(|| async { Ok::<_, anyhow::Error>(Mutex::new(OrukeetWorker::start().await?)) })
        .await?;
    let mut worker = mutex.lock().await;
    if worker.child.try_wait()?.is_some() {
        *worker = OrukeetWorker::start().await?;
    }
    let output = worker
        .request(serde_json::json!({
            "id": id,
            "action": "transcribe",
            "audio": params.audio,
            "keepFillers": params.keep_fillers,
        }))
        .await?;
    let full_text = output.get("text").and_then(|v| v.as_str()).unwrap_or_default().to_owned();
    let mut segments = Vec::new();
    if let Some(raw_segments) = output.get("segments").and_then(|v| v.as_array()) {
        for segment in raw_segments {
            let (Some(start), Some(end), Some(text)) = (
                segment.get("start").and_then(|v| v.as_f64()),
                segment.get("end").and_then(|v| v.as_f64()),
                segment.get("text").and_then(|v| v.as_str()),
            ) else { continue };
            let start_ms = (start.max(0.0) * 1000.0).round() as u64;
            let end_ms = (end.max(start) * 1000.0).round() as u64;
            if !text.trim().is_empty() && end_ms > start_ms {
                segments.push(CaptionSegment { start_ms, end_ms, text: text.trim().to_owned(), words: vec![] });
            }
        }
    }
    let duration = output.get("duration").and_then(|v| v.as_f64()).or_else(|| segments.last().map(|s| s.end_ms as f64 / 1000.0));
    let json_path = if let Some(dir) = temp_dir {
        dir.join(format!("transcription_{id}.json"))
    } else {
        let base = params.video_file.as_deref().unwrap_or(&params.audio);
        Path::new(base).with_extension("json")
    };
    let serialized = serde_json::json!({
        "segments": segments,
        "fullText": full_text,
        "duration": duration,
        "model": "orukeet-q8",
        "generatedAt": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs()
    });
    tokio::fs::write(&json_path, serde_json::to_vec_pretty(&serialized)?).await?;
    emit(RpcEvent::Progress { id: id.into(), status: "Orukeet transcription complete".into(), progress: 1.0 });
    Ok(TranscribeSegmentsResult {
        segments,
        full_text,
        duration,
        json_file: json_path.to_string_lossy().into_owned(),
    })
}
