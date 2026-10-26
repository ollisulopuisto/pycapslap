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
   the PySide app and Orukeet worker, and smoke-tests the packaged Rust core.
3. Commit the release changes and push the branch.
4. Create and push the next calendar tag, for example:

   ```sh
   git tag -a v26.10.26.1 -m "Release v26.10.26.1"
   git push origin v26.10.26.1
   ```

5. Follow the **Release** workflow in GitHub Actions. The job creates a
   compressed DMG from `PyCapSlap.app` and attaches it to the tag's GitHub
   release.

The app is unsigned and not notarized. On first launch, users may need to
right-click the app and choose **Open**, or allow it in System Settings under
**Privacy & Security**.

## Local DMG packaging

After building `pyside/dist/PyCapSlap.app`, create the same compressed disk
image with:

```sh
cd pyside/dist
hdiutil create -volname "PyCapSlap" -srcfolder PyCapSlap.app \
  -ov -format UDZO PyCapSlap-macos-arm64.dmg
```
