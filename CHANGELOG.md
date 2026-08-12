# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`vYY.MM.DD.N`).

## [v26.08.12.52] - 2026-08-12

### Fixed
- Fixed memory leaks and OOM connection drops in remote Whisper uploads by streaming audio files directly from disk instead of loading full file byte buffers into RAM.
- Improved error handling and surfacing for remote Whisper server connection drops and non-JSON error responses.

### Added
- Added `tokio-util` dependency with stream features for efficient async I/O streaming.
