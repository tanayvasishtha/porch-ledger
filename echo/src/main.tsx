import './styles.css';

import { render } from 'preact';

import { App } from './App';
import { houseKey, mcpUrlFromEnv, PorchMcp } from './mcp';
import { OfflineApp } from './OfflineApp';

const root = document.getElementById('app');
if (root === null) throw new Error('missing #app root');

PorchMcp.connect(mcpUrlFromEnv(), houseKey())
  .then((client) => render(<App client={client} />, root))
  .catch(() => render(<OfflineApp />, root));
