# ASVS 5.0 Traceability Matrix

This document maps the hardened HTTPS API to selected OWASP ASVS 5.0 controls.

It is a traceability and gap-analysis artifact, not a certification claim.

Status values:

- `implemented`
- `partially implemented`
- `not implemented`
- `not applicable`

## Scope

This matrix covers the private HTTPS API under `/v1/...`:

- transport security
- Bearer authentication
- request validation
- error handling
- logging and monitoring
- configuration and deployment hardening

It does not claim full ASVS coverage for every part of the repository.

## Mapping

| ASVS area | Control intent | Status | Evidence | Notes |
| --- | --- | --- | --- | --- |
| V1 Architecture | Clear trust boundary between untrusted HTTP input and business logic | implemented | `src/omnifocus/http_api.py`, `src/omnifocus/api_service.py` | FastAPI transport validates and delegates to `StoreBackedApiService` |
| V2 Authentication | All endpoints require authentication | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | Bearer auth middleware protects health and OpenAPI too |
| V2 Authentication | Resist trivial brute-force attempts | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | In-memory auth failure limiter returns `429` |
| V3 Access Control | Deny unauthenticated access by default | implemented | `src/omnifocus/http_api.py` | No anonymous route exceptions |
| V4 Input Validation | Typed request and query validation | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | FastAPI + Pydantic v2 validation |
| V4 Input Validation | Reject malformed content types and oversized bodies | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | JSON-only body guard and 1 MiB cap |
| V6 Stored Cryptography | In-transit protection for API transport | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | TLS 1.3 minimum required |
| V6 Stored Cryptography | Plaintext transport disabled | implemented | `src/omnifocus/http_api.py`, `docs/http.md` | No plaintext HTTP mode |
| V7 Error Handling | Generic server errors without sensitive leakage | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | `500` envelope hides internal details |
| V8 Data Protection | Secrets excluded from logs | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | No Authorization, WebDAV credentials, passphrases, or bodies in normal logs |
| V9 Communications | HSTS and anti-sniffing headers | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | `Strict-Transport-Security`, `X-Content-Type-Options`, `Cache-Control`, `Pragma` |
| V9 Communications | Host header validation | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | Trusted-host allowlist via `OF_HTTP_ALLOWED_HOSTS` |
| V10 Malicious Controls | Rate limiting | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | Applied to auth failures |
| V10 Malicious Controls | Request timeout limits | implemented | `src/omnifocus/http_api.py`, `docs/http.md`, `tests/test_http_api.py` | 30-second default timeout with `504` |
| V11 Business Logic | Stable-ID writes only over HTTP | implemented | `docs/http.md`, `src/omnifocus/http_api.py` | Avoids fuzzy remote mutations |
| V13 Configuration | Secure-by-default localhost bind | implemented | `src/omnifocus/http_api.py`, `docs/http.md` | `127.0.0.1:8443` by default |
| V13 Configuration | Startup refuses missing TLS/auth config | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py`, `.github/workflows/ci.yml` | Mandatory env vars enforced |
| V14 Logging | Structured operational and security logs | implemented | `src/omnifocus/http_api.py`, `tests/test_http_api.py` | OTel-style JSON logs with request ID and trace ID |
| V14 Logging | External SIEM / OTLP export | not implemented | n/a | Log format is OTel-aligned, but no exporter is included |
| V15 API Security | Machine-readable API schema | implemented | `/v1/openapi.json`, `src/omnifocus/http_api.py`, `tests/test_http_api.py` | Spec endpoint is authenticated |
| V15 API Security | Interactive API docs in production | not applicable | n/a | Swagger UI and Redoc are intentionally disabled |

## Current Gaps

The following controls remain only partially addressed or intentionally out of scope:

- persistent/shared rate limiting across multiple replicas or processes
- multi-key rotation and key lifecycle management
- mTLS
- OTLP export pipeline
- formal ASVS audit or certification process

## Repo Cross-Checks

- quality gate: `.github/workflows/ci.yml`
- HTTP transport implementation: `src/omnifocus/http_api.py`
- transport-neutral business logic: `src/omnifocus/api_service.py`
- human-readable API docs: `docs/http.md`
- automated transport coverage: `tests/test_http_api.py`
