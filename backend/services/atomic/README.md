# Atomic services

Each atomic service owns exactly one entity and its storage. Rules:

- Owns its own table(s); nothing else writes to them.
- Exposes CRUD over HTTP.
- Never calls another service — orchestration belongs in `../composite`.

| Service | Entity |
| --- | --- |
| [`user/`](user/README.md) | Users |
| [`event/`](event/README.md) | Events |
