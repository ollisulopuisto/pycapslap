# Sentinel's Journal

## 2026-10-31 - Clickjacking Defense on Review Portal Endpoints
**Vulnerability:** The review portal serves secret link endpoints (`/s/<token>`, `/s/<token>/e/<id>`) and administrative interfaces (`/admin`) without `X-Frame-Options` or Content Security Policy `frame-ancestors` restrictions. This allowed any third-party malicious website to embed portal pages in an iframe and attempt clickjacking attacks (e.g. tricking client reviewers or editors into approving social posts or deleting episodes/feedback).
**Learning:** Even when links are unguessable secrets ("link is the key") and referrer policies prevent token leakage, web applications without framing protections remain vulnerable to framing-based attacks from external origins.
**Prevention:** Include defense-in-depth framing controls (`X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`) in HTTP middleware for all web responses.
