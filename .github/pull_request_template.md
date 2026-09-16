Story:

<!-- The story id and name. -->

Task:

<!-- The task id, verbatim, dots and dashes included: `Task: S-01.T-01`.
     One line per task if this PR covers more than one. If you were not given
     an id, ask before opening the PR -- do not invent one. -->

## What this changes

<!-- Two or three lines. What a reviewer needs to know before reading the
     diff: what it does and why, not which files moved. -->

## Database

<!-- Delete this section if nothing under backend/sql/ changed. -->

- [ ] SQL is committed in `backend/sql/<service>.sql`
- [ ] Applied to the **dev** project
- [ ] Applied to the **test** project
- [ ] Schema is exposed (Data API → Settings → Exposed schemas) in both

## Config

<!-- Delete if nothing changed. -->

- [ ] Every new variable is in `.env.example` with an empty value
- [ ] New port registered in all four places: Dockerfile, `.env.example`,
      `docker-compose.yml`, `backend/kong/kong.yml`


## Definition of Done

- [ ] All acceptance criteria on the story are demonstrably met
- [ ] Code is written, self-reviewed, and adhered to team's coding standards
- [ ] At least one other team member has reviewed and approved the change (PR review)
- [ ] Any schema change in `backend/sql/` has been applied to both the dev and
      test Supabase projects, and the schema is exposed and granted in both
- [ ] Story's behaviour is covered at the cheapest tier that can prove it, unit
      by default, integration for a real boundary, e2e only for a whole journey
- [ ] The CI pipeline (SAST, DAST, unit, integration and e2e tests) passes on
      the merged code
- [ ] Any new setup steps, environment variables, or API changes are reflected
      in the README/docs
