# Sentinel's Journal

## 2026-11-04 - Restrict Network Fetching Protocols to HTTP/HTTPS
**Vulnerability:** Network media retrieval helper routines passed untrusted or dynamically resolved URLs directly to `urllib.request.urlopen()` without protocol scheme restrictions. This opened risks of unintended protocol execution, SSRF, or local file disclosure via `file://`, `ftp://`, or custom handlers.
**Learning:** Standard library HTTP clients like Python's `urllib.request` support arbitrary URL schemes by default, including local filesystem access, unless explicitly constrained before dispatch.
**Prevention:** Always validate URL schemes with `urllib.parse.urlsplit()` against an allowlist of permitted protocols (`http`, `https`) before calling `urlopen()`.

## 2026-11-03 - Enforce Payload Limits on Caption Ingestion Endpoints
**Vulnerability:** Caption ingestion endpoints (`/review` and `/captions`) buffered request bodies entirely into memory and persisted them directly into SQLite without payload size bounds. This exposed the portal to resource exhaustion and disk bloat denial-of-service via oversized JSON payloads.
**Learning:** Endpoints that consume raw request bodies with `request.body()` bypass typical framework per-field size validations, allowing arbitrary memory allocation before deserialization.
**Prevention:** Stream and measure request bodies against strict byte budgets (`MAX_CAPTIONS_BYTES`) and pre-check `Content-Length` headers, rejecting oversized payloads early with HTTP 413.

## 2026-10-31 - Clickjacking Defense on Review Portal Endpoints
**Vulnerability:** The review portal serves secret link endpoints (`/s/<token>`, `/s/<token>/e/<id>`) and administrative interfaces (`/admin`) without `X-Frame-Options` or Content Security Policy `frame-ancestors` restrictions. This allowed any third-party malicious website to embed portal pages in an iframe and attempt clickjacking attacks (e.g. tricking client reviewers or editors into approving social posts or deleting episodes/feedback).
**Learning:** Even when links are unguessable secrets ("link is the key") and referrer policies prevent token leakage, web applications without framing protections remain vulnerable to framing-based attacks from external origins.
**Prevention:** Include defense-in-depth framing controls (`X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`) in HTTP middleware for all web responses.
