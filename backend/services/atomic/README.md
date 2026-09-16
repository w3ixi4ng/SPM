# Atomic services

Each atomic service owns exactly one entity and its storage. Rules:

- Owns its own table(s); nothing else writes to them.
- Exposes CRUD over HTTP.
- Never calls another service — orchestration belongs in `../composite`.

| Service | Entity |
| --- | --- |
| [`users/`](users/README.md) | Users — account, session and profile |
| [`events/`](events/README.md) | Events |
