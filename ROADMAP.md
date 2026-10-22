# Roadmap

## Done
- Export shape choice with Fit (letterbox) or Crop (centred fill) when the export's aspect differs from the source's. Editor preview, render and caption placement follow it. (v26.10.22.2; see CHANGELOG.)

## Open
- **Crop position.** Crop is centred only. A 16:9 source cut to 9:16 often needs the subject left or right of centre; the Rust side already names `start` and `end` in its `crop_strategy` comment but does not implement them.
- **Caption render tests need libass.** `test_core_client_burn_captions` fails on the local Homebrew ffmpeg, which lacks the `ass` filter. Pre-existing, not related to crop.
- **Crop not verified end-to-end.** The fill path is covered by Rust filter tests and the editor preview by Python tests; a real render of a 16:9 clip to 4:5 with captions is still to be checked on a libass build of ffmpeg.
