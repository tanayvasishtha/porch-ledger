// Typed MCP wrapper for the porch-ledger server.
// Connects over Streamable HTTP at protocol 2025-11-25 (the legacy
// handshake pinned via supportedProtocolVersions; `pin` mode in this SDK
// only accepts 2026-07-28 and later revisions).

import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

import {
  type HouseInfo,
  type Inbox,
  isHouseInfo,
  isInbox,
  isVisitCard,
  type VisitCard,
} from './types.ts';

export const MCP_PROTOCOL = '2025-11-25';

const DEFAULT_URL = 'http://localhost:8000/mcp';

export class ToolShapeError extends Error {
  constructor(tool: string) {
    super(`unexpected structured output from ${tool}`);
    this.name = 'ToolShapeError';
  }
}

export class PorchMcp {
  private readonly client: Client;
  readonly serverOrigin: string;

  private constructor(client: Client, serverOrigin: string) {
    this.client = client;
    this.serverOrigin = serverOrigin;
  }

  static async connect(mcpUrl: string = DEFAULT_URL, houseKey?: string): Promise<PorchMcp> {
    const headers = houseKey ? { Authorization: `Bearer ${houseKey}` } : undefined;
    const transport = new StreamableHTTPClientTransport(new URL(mcpUrl), {
      requestInit: headers ? { headers } : {},
    });
    const client = new Client(
      { name: 'porch-ledger-echo', version: '1.0.0' },
      {
        versionNegotiation: { mode: 'legacy' },
        supportedProtocolVersions: [MCP_PROTOCOL],
      },
    );
    await client.connect(transport);
    return new PorchMcp(client, new URL(mcpUrl).origin);
  }

  async disconnect(): Promise<void> {
    await this.client.close();
  }

  async houseInfo(): Promise<HouseInfo> {
    const result = await this.client.callTool({ name: 'house_info', arguments: {} });
    if (result.isError) throw new ToolShapeError('house_info');
    if (isHouseInfo(result.structuredContent)) return result.structuredContent;
    throw new ToolShapeError('house_info');
  }

  async anythingForMe(residentId: string): Promise<Inbox> {
    const result = await this.client.callTool({
      name: 'anything_for_me',
      arguments: { resident_id: residentId },
    });
    if (result.isError) throw new ToolShapeError('anything_for_me');
    if (isInbox(result.structuredContent)) return result.structuredContent;
    throw new ToolShapeError('anything_for_me');
  }

  async claimBox(visitId: string, residentId: string): Promise<VisitCard> {
    const result = await this.client.callTool({
      name: 'claim_box',
      arguments: { visit_id: visitId, resident_id: residentId },
    });
    if (result.isError) throw new ToolShapeError('claim_box');
    if (isVisitCard(result.structuredContent)) return result.structuredContent;
    throw new ToolShapeError('claim_box');
  }
}

// import.meta.env reads; undefined means "no key configured".
export const mcpUrlFromEnv = (): string =>
  (import.meta.env.VITE_MCP_URL as string | undefined) ?? DEFAULT_URL;

export const houseKeyFromEnv = (): string | undefined =>
  (import.meta.env.VITE_HOUSE_KEY as string | undefined) ?? undefined;
