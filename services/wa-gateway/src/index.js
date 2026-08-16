import 'dotenv/config';
import express from 'express';
import pino from 'pino';
import fs from 'fs';

import { createSocket, statusFor, disconnect as disconnectSocket } from './socket.js';
import { registerSendRoute } from './send.js';

const app = express();
const logger = pino({ name: 'wa-gateway' });

const PORT = process.env.WA_GATEWAY_PORT || 8100;
const INTERNAL_KEY = process.env.WA_GATEWAY_INTERNAL_KEY || process.env.INTERNAL_API_KEY || 'internal-key';

app.use(express.json());

async function requireKey(req, res, next) {
  if ((req.headers['x-internal-key'] || '') !== INTERNAL_KEY) {
    return res.status(403).json({ error: 'invalid internal key' });
  }
  next();
}

// health + status
app.get('/health', (_req, res) => res.json({ service: 'wa-gateway', status: 'ok' }));
app.get('/status/:tenantId', (req, res) => res.json(statusFor(req.params.tenantId)));

// connect: spawn a Baileys socket for a tenant and stream the QR page
app.get('/connect/:tenantId', requireKey, async (req, res) => {
  const { tenantId } = req.params;
  logger.info({ tenantId }, 'connect requested');
  try {
    const started = await createSocket(tenantId, logger);
    if (!started) return res.status(409).json({ error: 'socket already connected or linking' });
    // QR is streamed by polling /status/:tenantId
    res.json({ status: 'linking', qr: statusFor(tenantId).qr });
  } catch (err) {
    logger.error({ err, tenantId }, 'connect failed');
    res.status(500).json({ error: err.message });
  }
});

// disconnect (pause-ish control at transport level)
app.post('/disconnect/:tenantId', requireKey, async (req, res) => {
  disconnectSocket(req.params.tenantId);
  res.json({ disconnected: req.params.tenantId });
});

registerSendRoute(app, requireKey, logger);

const DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001';

app.listen(PORT, () => {
  logger.info(`wa-gateway listening on :${PORT}`);
  const tenantId = process.env.WA_GATEWAY_TENANT_ID || process.env.TENANT_DEFAULT_ID || DEFAULT_TENANT_ID;
  const credsPath = `./wa-sessions/${tenantId}/creds.json`;
  let hasSession = false;
  try {
    const creds = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
    hasSession = creds.registered === true || (creds.me && creds.me.id);
  } catch {
    hasSession = false;
  }
  if (hasSession) {
    createSocket(tenantId, logger)
      .then((started) => logger.info({ tenantId, started }, 'restored saved session (auto-reconnect)'))
      .catch((err) => logger.error({ err, tenantId }, 'auto-reconnect failed'));
  } else {
    logger.info({ tenantId }, 'no registered session — manual Connect (QR) required once, then auto-reconnects');
  }
});