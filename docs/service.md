# Run AI-Shop as a separate API

The website sends messages from its backend; only AI-Shop installs and runs the
model. GitHub stores source code and is not an inference endpoint. No Google,
OpenAI or other inference-provider key is involved.

## Install on the AI host

Use Python 3.12 on Linux with enough RAM (the existing CPU profile targets 2 cores
and 8 GB). In the AI-Shop checkout:

```bash
bash scripts/setup.sh
```

The native runtime and verified model are installed once. Keep the `models/`
directory on persistent storage. CPU responses can take minutes; configure the
reverse proxy to allow at least 330 seconds. Run one process to avoid several
copies of the model in RAM.

## Register a website

Set these in the **AI server's** hosting environment or private service environment
file outside the public web directory:

| Variable | Value |
| --- | --- |
| `AI_SHOP_SITE_ORIGIN` | Exact public website origin, for example `https://example.com` |
| `AI_SHOP_SITE_ID` | Stable identifier, default `default` |
| `AI_SHOP_SITE_TOKEN` | Random printable ASCII secret, 32–256 characters |
| `AI_SHOP_DATA_DIR` | Private persistent directory, default `private` |
| `AI_SHOP_MODEL_DIR` | Persistent model directory, default `models` |
| `AI_SHOP_THREADS` | `2` for the existing CPU profile |

Generate a token once with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Save the same value in the website backend. Never place it in Git, browser code,
URLs, chat prompts or logs. Environment variables are not automatically loaded
from a `.env` file.

```bash
.venv/bin/python -m ai_shop serve --preload
```

This binds to `127.0.0.1:8090`. Two project folders on one machine can communicate
over that loopback address. For separate hosts, expose the AI service through
HTTPS with a TLS reverse proxy and suitable network restrictions. If the hosting
provider manages TLS and needs an external bind, use:

```bash
.venv/bin/python -m ai_shop serve --host 0.0.0.0 --preload
```

Port defaults to the provider's `PORT`, otherwise 8090. `--preload` fails startup
if the model cannot load. Use a supervisor to keep the process running; copying
folders or buying a domain does not start Python services. For several websites,
use `--config private/sites.json` and the existing
[example configuration](../examples/sites.example.json), with a different token
for each site. The token selects the site independently of body fields.

## Send a chat from the website backend

For CPU inference, use `POST /v1/chat/jobs` with the same JSON body below. It
returns HTTP 202 and a random `job_id` immediately. Poll authenticated
`GET /v1/chat/jobs/JOB_ID` about every four seconds. A pending reply has
`status: "pending"`; a completed reply has `status: "completed"` and the normal
response in `result`. Failures have `status: "failed"` and a machine error code.
Do not resubmit the message while polling. Every network request is short, so a
slow generation does not hold an HTTP connection open through hosting proxies.

Only one generation job is accepted at a time; there is no unbounded queue.
The requesting site's token is required for both submission and polling, and
another site's token cannot read the result. At most 64 results are retained,
in RAM only, for ten minutes after completion. No job payload/chat archive is
written to disk. Restarting the AI process loses pending jobs and results.
The client gives up after twenty minutes; CPU time remains bounded by model
token limits. A timed-out message is never automatically regenerated.

The synchronous route below remains available for existing clients, but can
exceed HTTP proxy timeouts on a small CPU host.

POST `/v1/chat` with `Authorization: Bearer <site-token>` and JSON:

```json
{
  "message": "What tea do you have?",
  "history": [],
  "learning_consent": false,
  "public_data": {
    "origin": "https://example.com",
    "brand": "Example Store",
    "currency": {"code": "USD", "decimals": 2, "label": "dollars"},
    "products": [],
    "pages": []
  }
}
```

Build `public_data` from current public products, final package prices and pages
on every request. AI-Shop validates and uses that exact request's snapshot even
if another request updates the stored catalogue concurrently. An explicit
`origin` must match the registered website. Never forward a browser-supplied
catalogue or include customer accounts, orders, passwords or private pages.

Omitting `public_data` remains supported for clients using `POST /v1/sync`.
Those clients must manage their own refresh schedule. Chat bodies are limited
to 5 MB and keep the existing message/history limits. See the
[response contract](integration.md).

The browser calls its own website backend; it never receives the service token.
No public browser CORS endpoint is needed. Escape response text, validate links
and display integer prices. Do not automatically retry timed-out chat requests:
generation may still be running.

## Readiness and learning

- `GET /healthz`: process health only.
- Authenticated `POST /v1/ready` with `{}`: loads/verifies the model and returns
  `ready`, `service`, `protocol`, the registered `origin` and
  `capabilities: ["chat_public_data", "chat_jobs"]`. A 503 means the model is unavailable.
- Missing/wrong token returns 401; wrong origin returns 403.
- Public index and reviewed learning live on the AI host at
  `AI_SHOP_DATA_DIR/knowledge.sqlite3`. Run `ai-shop pending`, `approve` and
  `forget` there with the registered site ID, origin and data directory.
  See [learning.md](learning.md). Readiness does not submit a chat or save learning.
