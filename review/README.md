# Caption review page

A static page for clients to check and correct captions made in PyCapSlap. No
build step, no dependencies, no server: open `index.html` from any static host
(GitHub Pages publishes it from `main`, see `.github/workflows/review-page.yml`).

- **In:** the video and a `.capslap.json` (from *Client Review → Export for
  Review…* in the app, or any sidecar). Pick them, drop them on the page, or link
  them: `?video=<url>&captions=<url>` (the captions URL has to allow CORS).
- **Out:** `<video>.reviewed.capslap.json` — the same sidecar with the edited
  captions, plus `review: { status, reviewer, reviewedAt, comments, changes }`.
  Import it in the app with *Client Review → Import Reviewed Captions…*.

Captions are edited, never added or removed, so the file lines up with the
project cue by cue. `core.js` holds the logic and is tested with
`node --test review/*.test.js`; `review.js` is the page.
