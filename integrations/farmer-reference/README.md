# Native Farmer-reference notification receiver

The external contract remains `farmer_reference.changed.v1`, WebSub topic
`oan.farmer-reference.changed.v1`, Kafka topic `oan_farmer_reference_changed_v1`
and native model `FARMER_REFERENCE_CHANGED_V1`. Crop keeps its existing wire,
metadata, document and section identifiers. Livestock owns separate receiver
configuration, tasks and decisions. Its new deterministic IDs do not represent
an activated subscription or a connector created by this branch.

Use the standard outgestion and ingestion pipelines. Source approval publishes
through native outgestion, WebSub/Kafka and the independently operated receiving
connector. The configured native key paths retain signed payload verification.
The first classification pass resolves the Farmer's native functional ID; the
second selects the existing Farmer identity section for UPDATE. A notice for a Farmer
with no live record classifies as ADD onto the pipeline-only intake form
`farmer_registry_notice_to_farmer_reference_form` (the same identity section, nothing
else; zz-oan/97_farmer_notice_first_reference.sql). The ingest worker saves the Farmer ID
and Fayda ID as a Farmer intake, and the registered intake service, instead of starting
an approval, repeats the signed, consented lookup and queues the Farmer reference ADD
for the normal two-stage approval; the intake is closed as cancelled with the change
request id in its remarks, so no approval, deduplication or register write follows from it.

The registered native enricher validates the event type, event ID and string
Farmer ID plus Fayda ID pair (the 16-digit FAN or the 12-digit FIN, whichever the
Farmer registry holds). It returns only the pair. The Jinja transformation emits
only those fields; notification demographics never become trusted data. The
registered CR service requires the configured source partner and a matching
approved local reference and identity pair, then fetches the current signed,
consented authoritative source. It creates/reuses the versioned local UPDATE CR
and durable AWE outbox. When the service receives a notice for a Farmer that has
no approved reference, it takes the Farmer ID and Fayda ID pair of the notice,
does the same signed, consented lookup as a typed Farmer ID, and queues the
first reference ADD CR for the normal two-stage approval; a repeat notice, or an
update before that ADD is approved, returns the same pending CR. Approved local values remain until native target approval.
The receiving registry's existing approved Woreda selects the reviewer; proposed
geography cannot select its own reviewer. Domain intake approvals are not replayed.

New reference ADD approval sets native functional_record_id from the verified
Farmer ID in the registered service, so the unmodified native classifier can
find it later. The internal UUID and domain-owned Farmer ID remain stable.
Existing nonempty identifiers are not rewritten. Existing records with missing
or divergent native identifiers require an explicit preserved-data migration
rehearsal and review; no automatic sweep or identifier deletion is supplied.

Seeds use native metadata tables and template catalog references and tolerate
repeated execution. Existing rows/document pointers are not overwritten. The
template belongs to the registry extension's templates directory for native
seeding/object storage. Compare the existing document, content and semantic
bindings using native staff configuration before any promotion. New Dev's
semantic-pattern detail API and known-template document read returned error
envelopes; that limitation is recorded, not interpreted as missing data.

Retain source publication state, topic/subscription contracts, callback Secrets,
signature verification, connector ownership, event deduplication and checkpoints.
No deployment script here creates a connector, resets its checkpoint, replays
historical events or enables a subscription. Keep Livestock's dedicated receiver
inactive until configured through its owner with independent partner access.
Do not replay all DLQ records to recover one event; native bounded failures and
per-event/operator recovery remain authoritative.

Local evidence covers metadata/identity guards and native classification,
transformation validation, payload construction, CR/history/outbox approval.
Live Kafka transport, object-store template content, real UID16 source response,
actual AWE engine tasks and preserved existing data remain acceptance gates.

References: [OpenG2P outgestion](https://docs.openg2p.org/products/registry/registry/design/outgestion-pipeline),
[OpenG2P ingestion](https://docs.openg2p.org/products/registry/registry/design/ingestion-pipeline).

The connector must explicitly select `FARMER_REFERENCE_CHANGED_V1`; it must not
fall back to a wildcard DCI model. The model's response-template pointer stays
null so the native correlation-ID acknowledgement reaches the connector.
Native raw-ingestion auditing and any existing environment delivery indexes
remain owned by the platform/environment. This extension deduplicates local
Farmer CRs by verified source version; local tests do not certify end-to-end
connector lost-acknowledgement recovery. Preserve existing delivery constraints
and prove that recovery with the real receiver before promotion.

Notifications with a corrected UID do not authorize identity changes. The
receiving service resolves the same immutable source person using the approved
local identity and requires the signed response to establish the corrected UID.
The correction stays pending until local approval and never modifies IAM grants.

The receiving connector's definition validates the notice with
`notification.schema.json`: a Farmer ID and either `fayda_fan_id` (16 digits) or
`fayda_fin` (12 digits), under either notice name (`farmer_reference.changed.v1`
or `farmer-registry.farmer.changed.v1`). The Farmer registry sends `fayda_fin` for
a farmer registered with a FIN only; a schema that requires `fayda_fan_id` fails
those notices at the connector, before they reach this registry.
