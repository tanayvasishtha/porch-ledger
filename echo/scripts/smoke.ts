/// <reference types="node" />
// CI smoke: connect to a running demo server and ask for Priya's inbox.
// Run with `node scripts/smoke.ts` (Node 24 strips the types) while
// `uv run python -m porch demo --serve` is up.

import { MCP_PROTOCOL, PorchMcp } from '../src/mcp.ts';

const url = process.env.VITE_MCP_URL ?? 'http://localhost:8000/mcp';
const key = process.env.VITE_HOUSE_KEY;

const client = await PorchMcp.connect(url, key);
try {
  const inbox = await client.anythingForMe('priya');
  if (!inbox.spoken.startsWith('You have a box')) {
    console.error(`unexpected spoken line: ${inbox.spoken}`);
    process.exit(1);
  }
  console.log(`smoke ok at ${MCP_PROTOCOL}: ${inbox.spoken}`);
} finally {
  await client.disconnect();
}
