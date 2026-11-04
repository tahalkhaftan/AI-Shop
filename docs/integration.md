# Connect a website

## Python SDK: recommended

Install the project into the same Python environment as your application:

```bash
pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu '.[local]'
python -m ai_shop download-model
```

Construct one `Assistant(site_id=..., origin=..., knowledge=...)` for each site.
`site_id` and `origin` are trusted server configuration, never browser-supplied selectors.
Pass a fresh public snapshot on each question:

```python
result = bot.answer(
    message,
    history,
    public_data=build_public_snapshot(),
    learning_consent=explicit_visitor_opt_in is True,
)
```

Use the SDK inside your existing web framework. Your route should enforce its normal
origin/CSRF policy, JSON-only bodies, input limits and per-visitor rate limits. Do not
hold an application-wide database lock during model generation. The engine serializes
generation and returns `busy` rather than creating an unbounded queue.

## Public data contract

The complete example is [public-feed.json](../examples/public-feed.json).

| Key | Contract |
|---|---|
| `brand` | Public site name |
| `currency` | `code`, decimal places, public display label |
| `categories` | Public category names |
| `public_info` | Public phone, email, address, hours, shipping, returns, about or payment text |
| `products` | Published products only: ID, name, same-origin URL, category, description, availability, packages |
| `variants[].price_minor` | Integer **final payable package price** in the currency's smallest unit, after valid discounts |
| `pages` | Public URL, title and visible text |

For USD with two decimals, 1250 means **$12.50**. For IRT with zero decimals,
1250 means **1,250 toman**. Do not pass binary floating-point prices or silently mix
currencies. The assistant resolves inline price and quantity references on the server.
Shipping and final checkout charges remain the application's responsibility.

Package indices are explicit in the model context. If both the request and reply
uniquely name the same package label, that label takes precedence over a mistaken
numeric index. A conflicting label without an unambiguous request is rejected;
ambiguous comparisons are not silently rewritten. This reduces a common size/price
mix-up but is not a guarantee of perfect natural-language interpretation.

Unknown top-level and product fields are discarded, but a library cannot prove that
arbitrary strings supplied by your application are public. Build an explicit public
adapter; do not pass a database dump or a whole authenticated page. Exclude inactive,
unpublished, private and staff-only products. Private routes and foreign URLs are rejected.

`reply`, typed `parts`, verified `products`, translated `labels`, `currency`, `moderation`
and `learning` are returned. Render text as text, links from validated `url` fields,
and amounts from integer `amount_minor` plus `decimals`. Do not interpret model prose as HTML.

## Non-Python applications: self-hosted HTTP service

1. Install AI-Shop and download the model on your own AI host.
2. Copy `examples/sites.example.json` to ignored `private/sites.json`.
3. Set a different, random token of at least 32 ASCII characters in the environment
   variable named by `token_env` for each site. Keep tokens out of browser JavaScript,
   URLs, chat prompts, logs and source control.
4. Start the service:

```bash
.venv/bin/python -m ai_shop serve --config private/sites.json --data-dir private
```

The default bind is loopback port **8090**. For remote backends, deploy behind a TLS
reverse proxy and appropriate network restrictions. Allow enough proxy response time
for CPU generation, which can take minutes. Use one process for the 8 GB CPU profile;
additional worker processes load additional model copies.

| Endpoint | Use |
|---|---|
| `GET /healthz` | Process health; it does not claim the model is installed |
| `POST /v1/sync` | Authenticated server sends the site's current public snapshot |
| `POST /v1/chat` | Authenticated server sends `message`, optional `history`, explicit `learning_consent` |

Both POST routes require `Authorization: Bearer <site-token>` and JSON. The token chooses
the site; sending another `site_id` in a body cannot access that site's index or memory.
Keep a same-origin proxy in your website. This service is not a browser CORS endpoint.
Refresh `/v1/sync` after catalogue changes, through your publish webhook, or before a
price-sensitive chat. Indexing is explicit; this project does not secretly run background
jobs or guarantee live prices if the owner never refreshes a cached snapshot.

## Optional widget

Self-host `ai_shop/static/widget.js` as, for example, `/assets/ai-shop.js`. Connect your
own-origin chat route to the SDK or authenticated server-to-server service:

```html
<script defer src="/assets/ai-shop.js"
        data-endpoint="/api/ai-shop/chat" data-language="fa"></script>
```

The widget sends JSON with `X-AI-Shop-Client: 1`. Your proxy should validate the
Origin and that header along with its normal abuse controls. The widget has no
inference key, stores recent history only in page memory, and offers an unchecked
opt-in for a non-personal FAQ suggestion. Accent colour can be set with
`--ai-shop-accent`. It never uses browser cloud speech recognition.

## Crawler or feed

Use `ai-shop index --site ... --origin ... --feed ...` for a public JSON feed.
Without `--feed`, the crawler reads bounded public HTML and Product/Offer JSON-LD.
It cannot inspect logged-in pages, execute arbitrary JavaScript, bypass bot checks,
or discover authoritative variants and discounts on every platform. Use an adapter
for dynamic sites and accurate catalogue prices.
