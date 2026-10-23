# Roadmap

## Done
- Export shape choice with Fit (letterbox) or Crop (centred fill) when the export's aspect differs from the source's. Editor preview, render and caption placement follow it. (v26.10.22.2; see CHANGELOG.)

## Done (verified)
- Crop render checked end to end: a 1920x1080 clip to 4:5 has black bars in Fit and fills the frame in Fill. The burn test passes with the libass ffmpeg (`/opt/homebrew/opt/ffmpeg-full/bin`); the plain Homebrew ffmpeg lacks libass and fails it.

## Done (verified)
- Crop position. Crop can be centred ("fill"), from the start (top/left, "start") or from the end (bottom/right, "end"). The Rust side implements all three in `build_fitpad_filter_with_options`/`build_gpu_fitpad_filter`, and the editor offers them in the crop combo; the choice reaches the render and the caption placement.

## Open
- None.
