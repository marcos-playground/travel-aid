# Planning observability

PostHog connects product events, AI traces and sanitized errors through one anonymous planning
journey. It observes the workflow; validation, cabin expansion and ranking remain application
decisions. Observability does not add a second model or change the flight-search contract.

## Current environments

The US **Default project** (`682506`) is reserved for development/test. Local ingestion is
configured in ignored environment files. A separate production project is deferred because
the current PostHog organization allows one project. Production collection remains disabled;
do not deploy the development key as a production setting.

- [Development dashboard](https://us.posthog.com/project/682506/dashboard/2252789)
- [AI traces](https://us.posthog.com/project/682506/ai-observability/traces)
- [Error tracking](https://us.posthog.com/project/682506/error_tracking)

The dashboard shows the planning funnel, terminal turn outcomes, median/p95 duration in
milliseconds, skipped-cabin reasons, and error codes. These are application event counts,
not approved business metrics. A distinct ID represents a **plan**, not a unique person.
Interrupted turns are terminal outcomes, not successful searches. Multiple errors or ranking
events can occur in one turn; counting them does not count failed turns or unique results.

## Correlation and recovery

`Session.analyticsId` is a random public UUID, separate from the HTTP-only recovery cookie and
its database hash. It persists with the plan. Existing JSON sessions receive an ID atomically
on recovery; no new table migration is required. A new planning session gets a new ID, even
in the same browser. There is no cross-plan visitor identity or account association.

Both browser and API events carry `planning_session_id`; AI events also carry
`$ai_session_id`. The browser's request UUID is `turn_id` and `$ai_trace_id` across chat
submission, graph/model callbacks, search decisions and failures. Selection links to the
latest accepted turn. An error before a session can be recovered uses an ephemeral UUID,
since no canonical plan ID is available yet.

Browser PostHog persistence is memory-only. No PostHog cookies, local-storage identifiers,
person profiles, automatic pageviews, DOM autocapture or session replay are enabled.
The application recovery cookie continues to work independently.

## What is captured

| Area | Events / metadata |
| --- | --- |
| Product | Plan created/recovered/opened, message/edit/retry/more-options intent, first streamed results viewed, confirmed flight selection, stop/leave during a turn |
| Extraction | Model/provider, prompt version, proposed trip/preference **field names**, validation rejection codes, missing-detail count and clarification/readiness |
| Search | Cache reuse/refresh, depth, cabin, duration, HTTP request count, priced/filtered offer counts, skip reasons such as `budget_headroom`, `explicit_cabin_preference`, `cached_cabin` |
| Ranking | Policy version, category, cabin, score, stops, duration and relative/over-budget ratios; no raw fare or flight budget |
| Reliability | Turn outcome/duration, static error codes/classes, relative application stack locations on the API; browser errors use static codes without original messages or stacks |
| AI | LangGraph stages, model-call latency, input/output/reasoning/cache tokens, and PostHog's estimated model costs |

Strict final `before_send` allowlists run after SDK enrichment. In metadata-only mode they
remove prompts and responses. Even with development content capture enabled, they remove
graph state, encrypted reasoning blocks, tool definitions, request URLs, browser/device/session IDs, cookie
values/hashes, raw error messages, source context and locals. The public PostHog ingestion
key is retained in browser event envelopes because PostHog requires it to ingest events.
GeoIP enrichment is disabled. PostHog still receives network connections as the service
provider; these controls do not make transport anonymous.

The application does not capture hidden model reasoning. It records explicit workflow and
ranking decisions, plus reasoning-token counts where the model reports them.

## Local configuration

In `apps/api/.env`:

```dotenv
POSTHOG_ENABLED=true
POSTHOG_PROJECT_KEY=<development project ingestion key>
POSTHOG_HOST=https://us.i.posthog.com
POSTHOG_CAPTURE_DEBUG_CONTENT=true
```

In `apps/web/.env.local`:

```dotenv
NEXT_PUBLIC_POSTHOG_ENABLED=true
NEXT_PUBLIC_POSTHOG_KEY=<same development project ingestion key>
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
NEXT_PUBLIC_POSTHOG_ENVIRONMENT=development
```

These are project ingestion keys, not personal PostHog API keys. Restart the API and web
processes after changing configuration. Browser settings are embedded at build time, so a
deployment needs a rebuild. Leaving collection disabled or omitting key/host makes capture a
no-op. The tracked `.env.example` files contain no credentials and default to disabled.

For Vercel Preview, use the nonproduction project on both services and set the environment
to `preview`. For Production, keep both enabled flags false until its own project is ready.
Then configure matching production ingestion keys/hosts and production environment values.
Production chat-content capture is forced off even if its debug flag is accidentally true,
including when `VERCEL_ENV=production` disagrees with the application environment.

## Optional development debugging

The local API currently has `POSTHOG_CAPTURE_DEBUG_CONTENT=true` for testing. Set it to
`false` to return to metadata-only capture. The checked-in default is false, and content
capture is allowed only in development/test/preview.

When enabled, model generation events include native `$ai_input` and `$ai_output_choices`,
with the message structure preserved. This shows the actual system instructions, context
and messages sent to the model, and its returned output (including the structured JSON
interpretation). Redaction runs at the final capture boundary. Each native content field is
bounded to 64,000 text characters, 100 entries per collection and 12 levels of nesting; very
large inputs may be truncated. Graph/span state stays excluded, and no duplicate debug span
or model generation is created. Existing metadata-only generations cannot be backfilled.

In [AI generations](https://us.posthog.com/project/682506/ai-observability/generations), open
a new generation and inspect **Input** and **Output**. The same generation is nested under
its planning-turn trace. No browser setting or PostHog dashboard change is required.

The redactor removes common credentials, email addresses, phone-like numbers, URLs and
connection strings. It is best-effort: names, addresses or unusual personal details may
remain. Prefer synthetic data, and disable the flag after the investigation. PostHog's
[AI content retention](https://posthog.com/docs/ai-observability/data-retention) is 30 days
for these native input/output fields; metadata follows the project's analytics retention.
See also [privacy mode](https://posthog.com/docs/ai-observability/privacy-mode).

## Investigating a run

1. Find a failed/slow turn or cabin-skip event in the development dashboard or event explorer.
2. Filter events by `planning_session_id` to see the plan journey; use `turn_id` for one request.
3. Open the matching trace in AI Observability. The extract/validate/respond spans and
   `flight_cabin_search` spans show where time went. Expand the generation for usage/cost
   and, when development capture was enabled for that call, its redacted input/output.
4. Read skip, validation, cache and ranking metadata to explain the decision. Metadata-only
   mode deliberately cannot reconstruct the exact user's wording or extracted values.
5. For an extraction problem requiring content, reproduce with synthetic input and temporarily
   enable the development-only debug capture.

Costs are PostHog estimates based on model usage and its pricing catalog, not an OpenAI bill.
Luna usage and cost ingestion were verified with a small live synthetic clarification turn.
No flight provider request was needed for that smoke check. Priced search behavior and
decision telemetry are covered by deterministic provider-stub tests.

Telemetry is best-effort: SDK failures are isolated, queues are bounded, and API flushing waits
at most one second with short SDK HTTP timeouts. A worker may finish after that wait, and a
terminated browser/function can lose events. This is not a durable audit log. Unit tests
disable real analytics regardless of a developer's local settings. Browser automation is
normally filtered by PostHog's bot protection; a local test may need to bypass that signal
in its isolated test page without changing the application's production SDK configuration.
