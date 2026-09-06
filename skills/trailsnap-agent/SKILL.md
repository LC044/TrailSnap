---
name: trailsnap-agent
description: Query a user's TrailSnap photo library through the read-only MCP tools to find photos, reconstruct memories, build person timelines, or create evidence-backed travel and album narratives. Use when the user asks about their own albums or memories; do not use for unrelated image collections or claim that read-only tools changed the library.
---

# TrailSnap Agent

Use the `trailsnap_*` tools supplied by the TrailSnap Pi extension. They are read-only and already scoped to the Agent Token owner.

- Start with the narrowest tool that answers the request. Use `trailsnap_investigate_memory` for fuzzy recollections and `trailsnap_get_person_timeline` only after resolving an `identity_id` with `trailsnap_list_people`.
- Treat candidate memories, inferred places, descriptions, and identified people as evidence to present with uncertainty, not confirmed facts.
- Paginate when the first result says more data is available. Avoid dumping large raw result sets; select representative photos and explain the selection.
- Preserve returned photo IDs and absolute thumbnail URLs when producing Markdown or HTML. Never invent a media URL or expose a local file path.
- Do not say that a photo, album, tag, date, or file was changed. TrailSnap MCP currently exposes no mutation tools.

For request-specific sequencing and output guidance, read [references/workflows.md](references/workflows.md).
