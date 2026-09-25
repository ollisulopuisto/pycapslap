# Videoiden hyväksyntä

The PyCapSlap review portal.

A small server where clients watch the renders of their episodes, fix the
captions and leave feedback, and where the editor collects both. It runs next
to PyCapSlap: the app publishes a render with its captions, and imports what
comes back.

- **Series and episodes.** Every series has one secret link
  (`/s/<token>`). Whoever has it sees that series' episodes and nothing else.
  A new link can be made at any time; the old one stops working.
- **An episode** lists its videos (the small proof renders PyCapSlap makes,
  good for phones and for sharing), each with a player and a download button.
- **Captions.** *Check captions* opens the caption review page on the video.
  The client fixes wording and timing and presses *Send*; the corrected file is
  stored as a new version. The editor downloads it from the admin page (or
  the app fetches it) and imports it into PyCapSlap as is.
- **Feedback.** Free-form notes on the episode, optionally tied to a video and
  a moment in it.
- **Admin** (`/admin`, with the admin token): series, their links, episodes,
  videos, every captions version and all feedback.

## Running it

```sh
cd portal
PORTAL_ADMIN_TOKEN=$(openssl rand -hex 24) uv run capslap-portal
```

| Variable | Default | |
|---|---|---|
| `PORTAL_ADMIN_TOKEN` | (required) | Secret for `/admin` and for the app |
| `PORTAL_DATA` | `./data` | Database and videos |
| `PORTAL_HOST` / `PORTAL_PORT` | `127.0.0.1` / `8080` | Where to listen |
| `PORTAL_MAX_UPLOAD_MB` | `8192` | Largest video accepted |

It speaks plain HTTP; put it behind HTTPS. With Docker and Caddy (which gets
the certificate itself), from the repository root:

```sh
PORTAL_DOMAIN=review.example.com PORTAL_ADMIN_TOKEN=... \
  docker compose -f portal/compose.yaml up -d
```

Back up `PORTAL_DATA`: `portal.sqlite3` holds everything but the videos.

## Tests

```sh
cd portal && uv run pytest
```
