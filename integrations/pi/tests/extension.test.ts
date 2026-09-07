import assert from "node:assert/strict";
import test from "node:test";

import trailsnapMcpExtension, { deriveMcpUrl } from "../extensions/trailsnap-mcp.ts";

test("derives the Streamable HTTP MCP endpoint from public app URLs", () => {
  assert.equal(deriveMcpUrl("https://photos.example.com").href, "https://photos.example.com/api/mcp/");
  assert.equal(deriveMcpUrl("https://photos.example.com/api/").href, "https://photos.example.com/api/mcp/");
  assert.equal(deriveMcpUrl("https://photos.example.com/api/mcp").href, "https://photos.example.com/api/mcp/");
});

test("registers the scoped TrailSnap tool surface and status command", () => {
  const tools: string[] = [];
  const commands: string[] = [];
  const events: string[] = [];
  const fakePi = {
    registerTool(tool: { name: string }) {
      tools.push(tool.name);
    },
    registerCommand(name: string) {
      commands.push(name);
    },
    on(name: string) {
      events.push(name);
    },
  };

  trailsnapMcpExtension(fakePi as never);

  assert.deepEqual(tools, [
    "trailsnap_search_photos",
    "trailsnap_list_albums",
    "trailsnap_list_people",
    "trailsnap_investigate_memory",
    "trailsnap_get_person_timeline",
    "trailsnap_propose_album_organization",
  ]);
  assert.deepEqual(commands, ["trailsnap-status"]);
  assert.deepEqual(events, ["session_shutdown"]);
});
