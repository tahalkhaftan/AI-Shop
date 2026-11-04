# Reviewed learning

Learning is **opt-in, site-scoped public FAQ memory**, not automatic training of
model weights and not an archive of customer conversations.

1. The visitor explicitly permits a non-personal FAQ suggestion in a chat request.
2. The LLM may suggest one general question. Recognized personal data, credentials,
   insults, instruction overrides and volatile or numerical facts are rejected
   before writing. No raw chat transcript is saved.
3. A bounded pending question is saved for that site only, for at most seven days
   of logical availability. It is never treated as an authoritative answer.
4. The site owner reviews the question and supplies an answer excerpt and a public
   source URL already indexed for that site. The excerpt must occur in the source.
5. Approved public knowledge is available for thirty days and is invalidated if
   its source disappears or no longer contains the excerpt.

Expired rows are physically pruned on database startup and the next review/read
access. If the host is stopped, no timed background cleanup job is running.

This prevents a visitor's statement about a price, stock level, policy or private
information from becoming store truth. Prices and availability always come from
the current supplied catalogue, not learned chat content. PII and language
screening are imperfect, so consent and human review are additional controls.

Review pending suggestions on the AI host:

```bash
ai-shop pending --site example-store --origin https://example.com
```

Write a short excerpt from an indexed public page into a local, private UTF-8 file:

```bash
ai-shop approve --site example-store --origin https://example.com \
  --id PENDING_ID --source-url https://example.com/delivery \
  --excerpt-file private/excerpt.txt
```

To forget that site's learned and pending knowledge, without touching another site:

```bash
ai-shop forget --site example-store --origin https://example.com
```

The command requires typing `YES`. Run only on the trusted owner/admin host. Never
expose learning approval or deletion as unauthenticated customer routes. Do not
commit `private/`, SQLite files, chat-derived text or real site configurations.
