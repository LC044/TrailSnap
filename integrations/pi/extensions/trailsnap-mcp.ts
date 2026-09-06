import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { Type, type TSchema } from "typebox";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

type TrailSnapConfig = { mcpUrl: URL; token: string };

function configFilePath(): string {
  if (process.platform === "win32" && process.env.APPDATA) {
    return join(process.env.APPDATA, "trailsnap", ".env");
  }
  const configHome = process.env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(configHome, "trailsnap", ".env");
}

function readEnvFile(): Record<string, string> {
  const path = configFilePath();
  if (!existsSync(path)) return {};
  const values: Record<string, string> = {};
  for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    values[line.slice(0, index).trim()] = line.slice(index + 1).trim();
  }
  return values;
}

export function deriveMcpUrl(apiUrl: string): URL {
  const url = new URL(apiUrl);
  const path = url.pathname.replace(/\/+$/, "");
  url.pathname = path.endsWith("/mcp")
    ? `${path}/`
    : path.endsWith("/api")
      ? `${path}/mcp/`
      : `${path}/api/mcp/`;
  url.search = "";
  url.hash = "";
  return url;
}

export function loadTrailSnapConfig(): TrailSnapConfig {
  const file = readEnvFile();
  const token = process.env.TRAILSNAP_API_TOKEN || file.TRAILSNAP_API_TOKEN;
  const endpoint = process.env.TRAILSNAP_MCP_URL || file.TRAILSNAP_MCP_URL;
  const apiUrl = process.env.TRAILSNAP_API_URL || file.TRAILSNAP_API_URL;
  if (!token || !token.startsWith("ts_")) {
    throw new Error("缺少 TrailSnap Agent Token。请先运行 trailsnap config set --url <地址> --token <ts_令牌>");
  }
  if (!endpoint && !apiUrl) {
    throw new Error("缺少 TrailSnap 地址。请先运行 trailsnap config set --url <地址> --token <ts_令牌>");
  }
  return { mcpUrl: deriveMcpUrl(endpoint || apiUrl), token };
}

function absoluteMediaUrls(value: unknown, endpoint: URL): unknown {
  if (Array.isArray(value)) return value.map((item) => absoluteMediaUrls(item, endpoint));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      typeof item === "string" && key.endsWith("_url") && item.startsWith("/")
        ? new URL(item, endpoint.origin).toString()
        : absoluteMediaUrls(item, endpoint),
    ]));
  }
  return value;
}

const toolDefinitions: Array<{
  localName: string;
  remoteName: string;
  label: string;
  description: string;
  parameters: TSchema;
}> = [
  {
    localName: "trailsnap_search_photos",
    remoteName: "search_photos",
    label: "Search TrailSnap Photos",
    description: "按日期、地点、OCR、人物和评分搜索当前用户的 TrailSnap 照片。只读。",
    parameters: Type.Object({
      start_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      end_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      location: Type.Optional(Type.String()),
      ocr_text: Type.Optional(Type.String()),
      media_type: Type.Optional(Type.String()),
      orientation: Type.Optional(Type.String({ description: "landscape、portrait 或 square" })),
      has_people: Type.Optional(Type.Boolean()),
      min_quality_score: Type.Optional(Type.Number()),
      min_memory_score: Type.Optional(Type.Number()),
      cursor: Type.Optional(Type.Integer({ minimum: 0 })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 30 })),
    }),
  },
  {
    localName: "trailsnap_list_albums",
    remoteName: "list_albums",
    label: "List TrailSnap Albums",
    description: "列出当前用户可访问的 TrailSnap 相册、封面和照片数量。只读。",
    parameters: Type.Object({
      cursor: Type.Optional(Type.Integer({ minimum: 0 })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })),
    }),
  },
  {
    localName: "trailsnap_list_people",
    remoteName: "list_people",
    label: "List TrailSnap People",
    description: "列出当前用户相册中已识别的可见人物及 identity_id。只读。",
    parameters: Type.Object({
      cursor: Type.Optional(Type.Integer({ minimum: 0 })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })),
    }),
  },
  {
    localName: "trailsnap_investigate_memory",
    remoteName: "investigate_memory",
    label: "Investigate TrailSnap Memory",
    description: "融合模糊日期、地点、人物和文字线索，查找可解释的候选回忆事件。只读。",
    parameters: Type.Object({
      query_text: Type.String(),
      start_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      end_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      locations: Type.Optional(Type.Array(Type.String())),
      persons: Type.Optional(Type.Array(Type.String())),
      text_terms: Type.Optional(Type.Array(Type.String())),
      semantic_photo_ids: Type.Optional(Type.Array(Type.String())),
      max_events: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })),
    }),
  },
  {
    localName: "trailsnap_get_person_timeline",
    remoteName: "get_person_timeline",
    label: "Get TrailSnap Person Timeline",
    description: "按人物聚合年份、事件、地点、同行者和代表照片。只读。",
    parameters: Type.Object({
      identity_id: Type.String(),
      start_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      end_date: Type.Optional(Type.String({ description: "YYYY-MM-DD" })),
      max_events: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
    }),
  },
  {
    localName: "trailsnap_propose_album_organization",
    remoteName: "propose_album_organization",
    label: "Propose TrailSnap Album Organization",
    description: "创建等待用户在 TrailSnap 页面确认的相册整理方案。不会直接执行，需要 albums:propose 权限。",
    parameters: Type.Object({
      name: Type.String({ minLength: 1, maxLength: 100 }),
      photo_ids: Type.Array(Type.String(), { minItems: 1, maxItems: 500 }),
      description: Type.Optional(Type.String({ maxLength: 4000 })),
      cover_photo_id: Type.Optional(Type.String()),
      tags: Type.Optional(Type.Array(Type.String(), { maxItems: 10 })),
      summary: Type.Optional(Type.String({ maxLength: 2000 })),
    }),
  },
];

export default function trailsnapMcpExtension(pi: ExtensionAPI) {
  let client: Client | undefined;
  let endpoint: URL | undefined;

  async function closeClient() {
    const active = client;
    client = undefined;
    endpoint = undefined;
    if (active) await active.close().catch(() => undefined);
  }

  async function getClient(): Promise<Client> {
    if (client) return client;
    const config = loadTrailSnapConfig();
    const nextClient = new Client({ name: "trailsnap-pi-agent", version: "0.2.0" });
    const transport = new StreamableHTTPClientTransport(config.mcpUrl, {
      requestInit: { headers: { Authorization: `Bearer ${config.token}` } },
    });
    await nextClient.connect(transport);
    client = nextClient;
    endpoint = config.mcpUrl;
    return nextClient;
  }

  for (const definition of toolDefinitions) {
    pi.registerTool({
      name: definition.localName,
      label: definition.label,
      description: definition.description,
      promptSnippet: definition.description,
      promptGuidelines: [`Use ${definition.localName} when the user asks about their TrailSnap photo library.`],
      parameters: definition.parameters,
      async execute(_toolCallId, params, signal) {
        if (signal.aborted) throw new Error("TrailSnap 请求已取消");
        try {
          const activeClient = await getClient();
          const result = await activeClient.callTool({
            name: definition.remoteName,
            arguments: params as Record<string, unknown>,
          });
          const blocks = Array.isArray(result.content)
            ? result.content as Array<{ type: string; text?: string }>
            : [];
          if (result.isError) {
            const message = blocks
              .filter((item) => item.type === "text" && item.text)
              .map((item) => item.text)
              .join("\n");
            throw new Error(message || "TrailSnap MCP 工具调用失败");
          }
          const structured = absoluteMediaUrls(result.structuredContent, endpoint!);
          const text = structured
            ? JSON.stringify(structured, null, 2)
            : blocks.filter((item) => item.type === "text" && item.text).map((item) => item.text).join("\n");
          return {
            content: [{ type: "text" as const, text: text || "TrailSnap 返回了空结果" }],
            details: { tool: definition.remoteName, structuredContent: structured },
          };
        } catch (error) {
          await closeClient();
          throw new Error(error instanceof Error ? error.message : "TrailSnap MCP 连接失败");
        }
      },
    });
  }

  pi.registerCommand("trailsnap-status", {
    description: "检查 TrailSnap MCP 连接和可用工具",
    handler: async (_args, ctx) => {
      try {
        const activeClient = await getClient();
        const tools = await activeClient.listTools();
        ctx.ui.notify(`TrailSnap 已连接：${tools.tools.length} 个 MCP 工具`, "info");
      } catch (error) {
        await closeClient();
        ctx.ui.notify(error instanceof Error ? error.message : "TrailSnap MCP 连接失败", "error");
      }
    },
  });

  pi.on("session_shutdown", closeClient);
}
