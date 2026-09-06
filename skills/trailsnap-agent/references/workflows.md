# TrailSnap Agent workflows

## Find photos

Translate explicit dates, places, OCR text, orientation, people presence, and score thresholds into `trailsnap_search_photos`. If a request is vague (for example “那次在海边看日落”), prefer `trailsnap_investigate_memory`, then use returned photo IDs and explanations to answer.

## Person timeline

Call `trailsnap_list_people` to resolve the intended person. If names collide or the person is unnamed, show the candidates instead of guessing. Pass the chosen `identity_id` to `trailsnap_get_person_timeline`; summarize changes over time and retain the event evidence.

## Travel story or journal

1. Establish the requested time range and destinations with memory investigation or photo search.
2. Paginate only until the narrative has adequate coverage.
3. Choose representative photos across dates and locations rather than only the highest-scoring cluster.
4. Separate observed metadata from generated prose. Mention missing dates or locations instead of filling gaps as facts.
5. When asked for HTML, create a standalone responsive document in the user's requested style. Use returned absolute thumbnail URLs, semantic HTML, accessible alt text, and no script that mutates TrailSnap data.

## Connection troubleshooting

Run `/trailsnap-status`. The Pi extension reads `TRAILSNAP_MCP_URL` and `TRAILSNAP_API_TOKEN` from the environment first, then the TrailSnap CLI config. Configure it with:

```shell
trailsnap config set --url <TrailSnap地址> --token <ts_开头的Agent Token>
```

Do not print, log, or commit the token.
