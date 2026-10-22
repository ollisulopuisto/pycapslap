# Roadmap

## Done
- Export shape choice with Fit (letterbox) or Crop (centred fill) when the export's aspect differs from the source's. Editor preview, render and caption placement follow it. (v26.10.22.2; see CHANGELOG.)

## Done (verified)
- Crop render checked end to end: a 1920x1080 clip to 4:5 has black bars in Fit and fills the frame in Fill. The burn test passes with the libass ffmpeg (`/opt/homebrew/opt/ffmpeg-full/bin`); the plain Homebrew ffmpeg lacks libass and fails it.

## Open
- **Crop position.** Crop is centred only. A 16:9 source cut to 9:16 often needs the subject left or right of centre; the Rust side already names `start` and `end` in its `crop_strategy` comment but does not implement them.
