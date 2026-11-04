# AI-Shop

A reusable, self-hosted shopping assistant powered by a local language model.
Each website supplies its own public catalogue and information. There are no
proprietary inference API keys and no bundled store data.

## What it does

- Runs a quantized Qwen language model locally using Python and llama.cpp.
- Connects through a Python SDK, a server-to-server HTTP service, or a public JSON feed.
- Indexes bounded, same-origin public pages; skips accounts, checkout and administration.
- Resolves product links and prices from validated catalogue data, including package totals.
- Separates site indexes and reviewed learning by site ID.
- Screens inputs, source content and outputs for known abusive language.
- Accepts optional, non-personal FAQ suggestions from chats only with consent. Suggestions
  require owner review and a matching public source before they can influence answers.

## Run locally

Python 3.10+ is required; Python 3.12 and an 8 GB RAM machine are recommended.

```bash
bash scripts/setup.sh
```

The first setup downloads approximately 2.5 GB of pinned GGUF weights and verifies
their SHA-256. Model weights, private configuration, databases and chats are not
published in this repository. Inference after setup runs on your own host.

```python
from ai_shop import Assistant, KnowledgeBase

assistant = Assistant(
    site_id="example-store",
    origin="https://example.com",
    knowledge=KnowledgeBase("private/knowledge.sqlite3"),
)
assistant.sync_public_data(public_snapshot)  # See examples/public-feed.json
result = assistant.answer("Which products fit my budget?")
```

For dynamic shops, use a structured feed or an application adapter so prices and
availability are current. A crawler cannot reliably reconstruct every JavaScript
application or infer authoritative prices from arbitrary prose.

## Integration and operation

- [Persian setup guide](README_FA.md)
- [Public data contract and integration](docs/integration.md)
- [Reviewed learning and privacy](docs/learning.md)
- [Security controls and limitations](SECURITY.md)
- [Model attribution](NOTICE.md)

GitHub stores the source code; it does not run the model. Host the SDK inside your
application or run the HTTP service on a machine with enough memory. A 2-core CPU
can run this model but responses may take tens of seconds or several minutes.
The default configuration processes one generation at a time. This is a pretrained
open-weight model integration, not base-model training from scratch.

Profanity filters and model instructions reduce unwanted output but cannot guarantee
perfect detection in every language or an absolute “never.” Extend and evaluate the
policy for your audience. The model has no account, purchase, shell or administration tools.

## Checks

```bash
python -m unittest discover -s tests -v
```

Run the optional real-model smoke check after downloading weights:

```bash
.venv/bin/python scripts/check_model.py
```

Application code is MIT licensed. The Qwen model uses its own Apache 2.0 license;
weights are downloaded separately and are not part of the application license.
