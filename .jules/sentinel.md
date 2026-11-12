# Sentinel's Journal

## 2026-11-11 - Enforce Cache-Control Restrictions on Private Portal Endpoints
**Vulnerability:** Private review portal routes (including series token links, client episode reviews, caption data, video streams, feedback entries, and administrative endpoints) were served without cache directives. Browsers and intermediary network caches could retain sensitive unreleased footage, transcripts, secret tokens, and review comments in shared caches or on local disk.
**Learning:** Security controls like `Referrer-Policy: no-referrer` and unguessable tokens protect credentials in transit between origins, but do not stop client-side disk caches or proxy caches from persisting confidential media and API payloads unless caching headers explicitly forbid it.
**Prevention:** Enforce `Cache-Control: no-store` and `Pragma: no-cache` headers across all non-static authenticated and secret-token-protected endpoints while permitting caching on publicly static asset bundles.

## 2026-11-08 - Enforce Comprehensive Content-Security-Policy on Portal Endpoints
**Vulnerability:** Review portal endpoints and admin interfaces served Content-Security-Policy headers containing only `frame-ancestors 'none'`. Without resource-level restrictions, endpoints lacked defense-in-depth against malicious script execution, plug-in embedding, or unauthorized outbound resource loading.
**Learning:** Framing protections alone leave other browser capabilities unrestricted. Applying least-privilege resource policies (`default-src`, `img-src`, `media-src`, `object-src`, `base-uri`) prevents untrusted script injection or rogue media embeds while maintaining compatibility with necessary local media blobs and inline data URIs.
**Prevention:** Always pair framing controls with defense-in-depth resource directives (`default-src 'self'`, `object-src 'none'`, and explicit allowlists for images/media) across all application-served HTTP responses.

## 2026-11-07 - Validate PBKDF2 Iteration Bounds and KDF Metadata
**Vulnerability:** Encrypted review files unpack untrusted JSON payloads containing KDF parameters (`iterations`, `kdf`, `format`) directly into derivation routines. Without bounds checking, attackers can specify exorbitant iteration counts to trigger CPU-exhaustion denial of service or trivial iteration counts to downgrade password strength.
**Learning:** Relying on user-controlled cryptographic parameters in container formats without server/client bounds validation exposes consumers to algorithmic complexity DoS and cryptographic downgrade attacks.
**Prevention:** Constrain untrusted key derivation parameters to a strict, validated range (`MIN_ITERATIONS` to `MAX_ITERATIONS`) and verify that format and KDF algorithm identifiers match known, expected standards before initiating derivation.

## 2026-11-06 - Enforce Same-Origin Resolution on Client API Paths
**Vulnerability:** Client API request dispatchers that concatenate base URLs with endpoint paths or accept dynamically resolved paths can route authenticated requests (including administrative Bearer tokens) to cross-origin or alternate-scheme destinations if paths are protocol-relative, absolute URLs, or have mismatched schemes.
**Learning:** Naive URL concatenation (`base_url + path`) or unvalidated path resolutions permit cross-origin escapes or scheme mutations when paths are not checked against the client's configured base origin.
**Prevention:** In API clients that attach authentication credentials, parse and validate the resolved target against the base URL's scheme and netloc before dispatching requests, rejecting cross-origin or non-matching scheme paths.

## 2026-11-05 - Enforce Scheme Validation in Client Origin Checks
**Vulnerability:** Same-origin validation checking `new URL(url, location.href).origin === location.origin` permitted non-HTTP schemes such as `blob:` URLs because `URL.origin` for blob URLs inherits the creator origin (e.g., `blob:https://example.com/UUID` has origin `https://example.com`). Additionally, dynamic fetch calls accepted arbitrary URL schemes.
**Learning:** Browser URL origin resolution differs between schemes; origin equality alone is not sufficient to guarantee that a destination URL is a standard HTTP or HTTPS endpoint.
**Prevention:** In client-side URL validation helpers, always verify both that `parsed.origin === base.origin` and that `parsed.protocol` strictly matches `http:` or `https:`.

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
