# Security model and limits

AI-Shop is a read-only conversational assistant. It has no shell, order placement,
account access, payment or administration tools. The local model receives a bounded
public snapshot and recent request-supplied conversation. Service tokens, private
settings and database internals are never inserted into model prompts.

## Controls

- Public snapshots use explicit schemas; arbitrary application-state keys are dropped.
- Site ID and origin are bound by trusted configuration. Tokens select HTTP tenants;
  a caller-supplied site ID does not. Every index and memory query is site-scoped.
- Product/page links are validated against the exact site origin. Private paths,
  credential URLs and foreign origins are rejected.
- The crawler permits HTTPS on port 443, validates all resolved addresses as public,
  pins the connection to an approved address, preserves TLS hostname validation,
  and revalidates same-origin redirects. It sends no credentials or browser cookies.
- HTML scripts, hidden content and style blocks are not used as visible page knowledge.
  Only explicit public Product/Offer JSON-LD is extracted from structured scripts.
- Prompt delimiters in source/customer text are escaped. Retrieved data is bounded,
  marked untrusted and screened for known instruction overrides.
- Native model inference is serialized. Request bodies, HTTP workers, index sizes,
  context tokens, output length, pending learning and per-site traffic are bounded.
- Inputs, history, public source labels and outgoing reply/product/package labels
  are screened for known abusive terms, including some obfuscated forms.
- Learning is off by default, consented, filtered, reviewed and tied to public sources.
  It does not automatically alter model weights or share knowledge across sites.
- Chat bodies and authorization values are not logged by the service. Runtime
  databases, keys, weights and private configuration are ignored by source control.

## Limits you must account for

Profanity dictionaries, personal-data screening and prompt-injection phrase checks
are incomplete and can have false positives and false negatives. A prompt is not an
authorization boundary and cannot guarantee that an LLM will never use offensive
language or make a factual mistake. Extend policies and evaluate real audience
languages, adversarial inputs and catalogue edge cases before public deployment.

An application adapter is responsible for supplying only published data. A public
feed is owner-authoritative, not proof of correctness. A matching learning excerpt
proves source consistency, not that a public source is harmless or factually right.
Keep the model read-only and require your application's normal checkout validation.

Do not put the HTTP site token into the widget. Use backend-to-backend requests over
TLS and your normal same-origin proxy, CSRF and abuse controls. Use persistent storage,
backups, network restrictions and an appropriate TLS proxy for a hosted deployment.
The standard-library HTTP adapter is intentionally small; use the SDK within your
production web stack when you need its process supervision, observability and scaling.

The 2-core/8-GB profile is suitable for low-volume local inference, not high-throughput
customer support. Model weights are external, pinned public downloads under their
own license. No claim of security certification or a perfect safety guarantee is made.

## Design references

- [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP prompt injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [OWASP RAG security](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html)
