use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptionSegment {
    pub start_ms: u64,
    pub end_ms: u64,
    pub text: String,
    // Optional word-level timing (used when split_by_words = true)
    #[serde(default)]
    pub words: Vec<WordSpan>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WordSpan {
    pub start_ms: u64,
    pub end_ms: u64,
    pub text: String,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct TranscribeSegmentsParams {
    pub audio: String,              // Path to audio file to transcribe
    pub model: Option<String>,      // Whisper model to use (default: "whisper-1")
    pub language: Option<String>,   // Language hint for better accuracy
    pub split_by_words: bool,       // Whether to split by words or segments
    pub api_key: Option<String>,    // OpenAI API key
    pub prompt: Option<String>,     // Context prompt to improve accuracy
    pub video_file: Option<String>, // Original video file path (for JSON output location)
    #[serde(default)]
    pub whisper_base_url: Option<String>, // Optional OpenAI-compatible Whisper server base URL (e.g. a whisper.cpp server on another machine)
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct TranscribeSegmentsResult {
    pub segments: Vec<CaptionSegment>, // Caption segments with timing
    pub full_text: String,             // Complete transcription text
    pub duration: Option<f64>,         // Total audio duration
    pub json_file: String,             // Path to saved JSON captions file
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct BurnResult {
    pub video: String, // Path to video with burned-in subtitles
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WhisperCacheEntry {
    pub audio_hash: String,    // blake3 hash of audio file content
    pub params_hash: String,   // blake3 hash of transcription parameters
    pub response_path: String, // path to cached JSON response file
    pub timestamp: u64,        // unix timestamp for LRU eviction
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct WhisperCacheIndex {
    pub entries: Vec<WhisperCacheEntry>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WhisperSegment {
    pub id: u32,
    pub start: f64,
    pub end: f64,
    pub text: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WhisperWord {
    pub word: String,
    pub start: f64,
    pub end: f64,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct WhisperResponse {
    pub task: Option<String>,
    pub language: Option<String>,
    pub duration: Option<f64>,
    pub text: String,
    pub segments: Option<Vec<WhisperSegment>>,
    pub words: Option<Vec<WhisperWord>>,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ExtractAudioParams {
    pub input: String,         // Path to input video file
    pub codec: Option<String>, // Audio codec to use (default: "aac")
    pub out: Option<String>,   // Output path (default: input filename with .m4a extension)
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ExtractAudioResult {
    pub audio: String, // Path to the extracted audio file
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct GenerateCaptionsParams {
    pub input_video: String,         // Path to input video file
    pub export_formats: Vec<String>, // List of aspect ratios to export (e.g., ["9:16", "16:9"])
    pub karaoke: bool,               // Whether to use karaoke-style highlighting
    #[serde(default)]
    pub multiline: bool, // Whether to allow multiple lines (karaoke)
    pub font_name: Option<String>,   // Font name for captions (defaults to "Montserrat Black")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub font_size: Option<u32>, // Base font size (at 1080p reference)
    pub split_by_words: bool,        // Whether to split transcription by words or segments
    pub model: Option<String>,       // Whisper model to use (default: "whisper-1")
    pub language: Option<String>,    // Language hint for better accuracy
    pub prompt: Option<String>,      // Context prompt to improve accuracy
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text_color: Option<String>, // Text color as hex string (e.g., "#ffffff")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub highlight_word_color: Option<String>, // Highlight word color as hex string
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outline_color: Option<String>, // Outline color as hex string
    #[serde(default)]
    pub glow_effect: bool, // Whether to apply glow effect
    #[serde(skip_serializing_if = "Option::is_none")]
    pub position: Option<String>, // Caption position: "bottom" or "center"
    pub api_key: Option<String>,     // OpenAI API key
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_size: Option<String>, // Target output size (e.g., "1080p", "original")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub crop_strategy: Option<String>, // "start", "center", "end", "fit" (letterbox)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub whisper_base_url: Option<String>, // Optional OpenAI-compatible Whisper server base URL
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct GenerateCaptionsResult {
    pub probe_result: crate::video::ProbeResult, // Original video information
    pub audio_file: String,                      // Path to extracted audio file
    pub transcription: TranscribeSegmentsResult, // Transcription results and segments
    pub captioned_videos: Vec<CaptionedVideoResult>, // List of generated videos with captions
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct BurnCaptionsParams {
    pub input_video: String,           // Path to input video file
    pub segments: Vec<CaptionSegment>, // The edited segments to burn
    pub export_formats: Vec<String>,   // List of aspect ratios to export
    pub karaoke: bool,                 // Whether to use karaoke-style highlighting
    #[serde(default)]
    pub multiline: bool, // Whether to allow multiple lines (karaoke)
    pub font_name: Option<String>,     // Font name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub font_size: Option<u32>, // Base font size
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text_color: Option<String>, // Text color
    #[serde(skip_serializing_if = "Option::is_none")]
    pub highlight_word_color: Option<String>, // Highlight word color
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outline_color: Option<String>, // Outline color
    #[serde(default)]
    pub glow_effect: bool, // Whether to apply glow effect
    #[serde(skip_serializing_if = "Option::is_none")]
    pub position: Option<String>, // Caption position
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_size: Option<String>, // Target output size
    #[serde(skip_serializing_if = "Option::is_none")]
    pub crop_strategy: Option<String>, // Crop strategy
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct CaptionedVideoResult {
    pub format: String,          // The aspect ratio format (e.g., "9:16")
    pub raw_video: String,       // Path to reformatted video without captions
    pub captioned_video: String, // Path to final video with captions
    pub width: u32,              // Video width
    pub height: u32,             // Video height
}

// Model download types
#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct DownloadModelParams {
    pub model: String, // Model name: "tiny", "base", "small", "medium", "large"
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct DownloadModelResult {
    pub model: String, // Model name that was downloaded
    pub path: String,  // Path where model was saved
    pub size: u64,     // Downloaded file size in bytes
}

// Frame extraction types
#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ExtractFirstFrameParams {
    pub video_path: String,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ExtractFirstFrameResult {
    pub image_data: String, // Base64 encoded image
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewLayoutParams {
    pub segments: Vec<CaptionSegment>,
    pub width: u32,
    pub height: u32,
    pub font_name: Option<String>,
    pub font_size: Option<u32>,
    pub text_color: Option<String>,
    pub highlight_word_color: Option<String>,
    pub outline_color: Option<String>,
    pub position: Option<String>,
    pub karaoke: bool,
    #[serde(default)]
    pub multiline: bool,
    pub glow_effect: bool,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewLayoutResult {
    pub cues: Vec<PreviewCue>,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewCue {
    pub start_ms: u64,
    pub end_ms: u64,
    pub lines: Vec<PreviewLine>,
    pub y_pct: f32, // Vertical position as percentage from top
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewLine {
    pub words: Vec<PreviewWord>,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewWord {
    pub text: String,
    pub is_highlighted: bool,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct SaveCaptionsParams {
    pub video_path: String,
    pub segments: Vec<CaptionSegment>,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct LoadCaptionsParams {
    pub video_path: String,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct LoadCaptionsResult {
    pub segments: Option<Vec<CaptionSegment>>,
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewFrameParams {
    pub input_video: String,           // Path to input video file
    pub segments: Vec<CaptionSegment>, // The edited segments (we usually only need the one at timestamp)
    pub timestamp_ms: u64,             // Time in ms to extract frame from
    pub export_format: String,         // Aspect ratio format (e.g., "9:16")
    pub fit_mode: Option<String>,      // "cover" or "contain" (default "cover" aka "fit")
    pub karaoke: bool,                 // Whether to use karaoke-style highlighting
    #[serde(default)]
    pub multiline: bool, // Whether to allow multiple lines (karaoke)
    pub font_name: Option<String>,     // Font name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub font_size: Option<u32>, // Base font size
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text_color: Option<String>, // Text color
    #[serde(skip_serializing_if = "Option::is_none")]
    pub highlight_word_color: Option<String>, // Highlight word color
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outline_color: Option<String>, // Outline color
    #[serde(default)]
    pub glow_effect: bool, // Whether to apply glow effect
    #[serde(skip_serializing_if = "Option::is_none")]
    pub position: Option<String>, // Caption position
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_size: Option<String>, // Target output size
    #[serde(skip_serializing_if = "Option::is_none")]
    pub crop_strategy: Option<String>, // Crop strategy
}

#[derive(Serialize, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PreviewFrameResult {
    pub image_data: String, // Base64 encoded image data
}
