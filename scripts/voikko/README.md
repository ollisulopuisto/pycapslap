# Voikko bundling

`ci_collect_macos.py` and `bundle_native.py` are adapted from Punakynä's
LibreOffice adapter at the commit in `pyside/punakyna/UPSTREAM_COMMIT`.
Their MIT licence is in this directory. The source archive destination and
packaging references were changed for Tekstitys; native staging logic is shared.

On macOS: `brew install libvoikko`, then
`uv run python scripts/voikko/ci_collect_macos.py` before PyInstaller.
The collector gathers the native dependency closure, dictionary, licence texts,
and matching upstream source archives. It rewrites dylib references before
signing. Release packaging includes the notices inside the app and corresponding
sources alongside the app in the DMG. No parser or neural model is bundled.

Licensing warning: Punakynä's MIT licence does not relicense libvoikko or its
Finnish dictionary. GPL obligations are not avoided merely by dynamic linking.
Tekstitys currently has no top-level licence. The combined distribution's
licensing must be settled before publishing a release with this integration.

Untested until macOS CI: dylib dependency closure, re-signing, hardened-runtime
loading, dictionary discovery in the frozen app and the signed-app smoke test.
