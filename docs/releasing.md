# Releasing PyCapSlap

Releases are calendar-versioned (`vYY.MM.DD.N`) and built by GitHub Actions
for Apple Silicon macOS. Pushing a `v*` tag starts
`.github/workflows/release.yml`, which builds the app and publishes
`PyCapSlap-macos-arm64.dmg` to the GitHub release for that tag.

## Prepare a release

1. Finish the release notes in `CHANGELOG.md`, moving the completed entries
   under a dated version heading and leaving an empty `Unreleased` section.
2. Check the change set and the app's static build checks. The release job
   builds the Rust core, installs the locked Python dependencies, packages
   the PySide app, Orukeet worker, Whisper CLI and runtime libraries, and smoke-tests the packaged Rust core.
3. Commit the release changes and push the branch.
4. Create and push the next calendar tag, for example:

   ```sh
   git tag -a v26.10.26.1 -m "Release v26.10.26.1"
   git push origin v26.10.26.1
   ```

5. Follow the **Release** workflow in GitHub Actions. The job creates a
   compressed DMG from `PyCapSlap.app` and attaches it to the tag's GitHub
   release.

The bundled Whisper runtime requires macOS 15 or later, and the app's minimum
system version is set to match. The release workflow signs the app with the
Developer ID Application certificate and enables Hardened Runtime, then signs,
submits, and staples the DMG. Configure these repository Actions secrets:

- `BUILD_CERTIFICATE_BASE64`: base64-encoded Developer ID `.p12` certificate.
- `P12_PASSWORD`: password used when exporting the `.p12` certificate.
- `KEYCHAIN_PASSWORD`: temporary CI keychain password.
- `APPLE_ID`: Apple Developer account email used for notarization.
- `APPLE_APP_PASSWORD`: app-specific password for that Apple ID.

The workflow checks that all five secrets are present before building. Apple
notarization failures stop the release before the DMG artifact is uploaded.

## Local DMG packaging

After building `pyside/dist/PyCapSlap.app`, create the same compressed disk
image with:

```sh
cd pyside/dist
mkdir -p installer
ditto PyCapSlap.app installer/PyCapSlap.app
ln -sfn /Applications installer/Applications
hdiutil create -volname "PyCapSlap" -srcfolder installer \
  -ov -format UDZO PyCapSlap-macos-arm64.dmg
```
