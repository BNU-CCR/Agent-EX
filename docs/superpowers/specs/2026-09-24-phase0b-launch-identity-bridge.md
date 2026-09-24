# Phase 0B preliminary launch identity bridge

Status: owner approved the independent pre-service launch-intent approach on 2026-09-24. This amendment applies only to the preliminary N=20/T=2 diagnostic; it does not freeze Paper 1 formal parameters.

## Problem

The existing service lifecycle requires a `manifest_hash` before it starts. Its start-identity hash is generated only after startup. The Phase 0B adapter binding needs that start-identity hash, the diagnostic authorization needs the adapter-binding hash, and the twelve run manifests need the authorization hash. Passing any final Phase 0B authorization or run-manifest hash to the service would therefore create a cycle. Reusing the completed judge's service identity would incorrectly attribute Phase 0B requests to Phase 0A-1.

## Approved sequence

1. Create an immutable, preliminary-only launch intent before service startup. Bind the clean source commit and bundle SHA-256, explicit diagnostic candidate configuration and artifact hashes, pinned model/tokenizer revisions, environment lock, service configuration, and two distinct external archive roots. It must contain neither a service-start identity nor a final authorization hash.
2. After independent source/Linux checks and verified terminal Phase 0A-1 judge evidence, stop the old judge-owned service using its own identity and retain its stop evidence. Never resume or merge its run.
3. Perform and hash a fresh, real preliminary environment inspection before startup. Start one fresh vLLM service using the approved launch-intent hash as the lifecycle script's `manifest_hash` and the actual inspection record hash as its `preliminary-inspection` binding. Neither the intent hash nor the environment-lock hash may be substituted for an inspection. Record and verify the newly generated service-start identity and a bridge record linking launch intent, inspection, old-service stop evidence, and new-service start evidence. If no valid inspection can be produced, do not start the service.
4. Derive the Phase 0B adapter binding, diagnostic authorization and twelve manifests from that start identity. Verify their exact hashes and seek owner approval of the final derived packet before dispatching any Phase 0B model request.
5. Run a two-event preflight in its own archive, validate committed prefix and provider identity, then launch the 480-event matrix in a separate fresh archive. A failed or ambiguous preflight cannot be spliced into the matrix or blindly retried.

## Safety invariants

- All candidate values remain `preliminary`, `not_frozen`, and `formal_parameter_authority=false`; no test fixture becomes a production default.
- Every create-only file and external archive root must be absent before creation. Raw prompt/response evidence stays outside Git and out of chat.
- A service or client failure with unresolved dispatch intent blocks automatic resend. Successful events are never repeated under a new identity.
- The old judge service identity cannot be used as the Phase 0B adapter binding, even though both serve the same pinned model files.
- The bridge verifier checks the old run's terminal projection/manifest/lock against the stop evidence and checks the new service-start schema, `manifest_hash`, inspection `binding_kind`/hash, model and service command against observed evidence before providing its start hash to the adapter binding. The legacy stop script alone does not establish these cross-run relationships.
- The final authorization and twelve manifests must be derivable and re-verifiable from the approved intent, actual service start evidence, and explicit inputs; no identity field is edited in place after hashing.

## Acceptance evidence

Focused contract/CLI/preflight tests must show the intended red-then-green behavior, including rejection of circular identity fields, altered hashes, archive collisions and ambiguous dispatch. A cloud launch additionally requires source-bundle and intent approval, verified judge handoff and new service evidence, followed by exact final authorization/manifest approval.
