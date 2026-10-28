# Session safety and B-roll cancellation

Project edits have an uncapped, branch-preserving history for the current window.
Edit > Undo Project Edit and Redo Project Edit cover captions, word timing,
cue additions/deletions/imports/transcription, style/position, trims and thumbnail
state. Edit > Session Branches selects an alternate leaf. Editing after Undo does
not delete the other branch. Unchanged snapshots do not add an edit. Histories
are separate by source path and remain available until the window closes.

History is not saved in sidecars and does not survive close, refresh or crash.
It is not crash recovery or autosave. It can grow substantially in long sessions;
there is no silent pruning. External files, exports, portal actions, preferences
and model installation are not undone. Source reload reads saved data; it does
not secretly replace it with a discarded branch. Old branch tips remain selectable.

Close, Quit and source changes commit the active caption editor and ask Save,
Discard or Cancel when dirty. A failed save keeps the window/project open.
Sidecar saving writes and fsyncs a temporary sibling, then replaces the previous
file. Failure before replacement leaves the previous save intact. This is not a
backup or an absolute guarantee against disk/hardware failure.

B-roll media downloads use 256 KiB chunks and a temporary file, removed on
failure/cancel. A finished download is renamed into place. Downloads check cancel
between chunks; a stalled network read can take up to ten seconds to return.
Metadata resolvers use the same cancellation-aware request budget. Search before
the picker is not cancelled by the build button. Small media/encoder probes have
separate bounded timeouts; cancellation may wait for one of those checks.

The active build has a Cancel B-roll button. FFmpeg is terminated, then killed
if it does not exit within three seconds; stderr retains only its last 128 KiB.
Rendering goes to a partial MP4, then replaces the final movie only on success.
An existing finished movie is preserved on cancellation/failure. Sidecar/credits
are written after the render; this is not a multi-file transaction. Temporary work
assets may remain for retry, but incomplete downloads/render files are removed.
Opening another source is blocked until the active build is cancelled/finished.
Closing the app requests cancellation. The picker/search itself is not a new
background monitoring service.

Tests include a 1,100-edit tree, branch/snapshot isolation, actual Qt text/style/
trim undo, close/source cancellation, failed atomic replacement, chunk/log bounds,
child termination, partial cleanup and preservation of an existing finished movie.
Native macOS/CoreML and a packaged Rust-core session still need acceptance testing.
