import makeWASocket, { useMultiFileAuthState, DisconnectReason } from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import crypto from 'crypto';

const sockets = new Map(); // tenantId -> { socket, status, qr }

export function statusFor(tenantId) {
  const entry = sockets.get(tenantId);
  return {
    tenantId,
    status: entry ? entry.status : 'disconnected',
    qr: entry ? entry.qr : null,
  };
}

export function forwardToApi(tenantId, body, mediaUrl = null) {
  const cbUrl = process.env.WA_API_CALLBACK_URL || 'http://localhost:8000/webhook/message';
  const internalKey = process.env.WA_GATEWAY_INTERNAL_KEY || process.env.INTERNAL_API_KEY || 'internal-key';
  const tenantKey = process.env.WA_GATEWAY_TENANT_KEY || process.env.TENANT_DEFAULT_KEY || 'admin';
  const payload = {
    tenant_id: tenantId,
    platform: 'whatsapp',
    contact_identifier: body.key?.remoteJid,
    body: body.message?.conversation
      || body.message?.extendedTextMessage?.text
      || body.message?.imageMessage?.caption
      || null,
    media_url: mediaUrl,
  };
  // fire-and-forget; API service is the orchestrator. Tenant auth via headers.
  fetch(cbUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Internal-Key': internalKey,
      'X-Tenant-Id': process.env.WA_GATEWAY_TENANT_ID || process.env.TENANT_DEFAULT_ID || '00000000-0000-0000-0000-000000000001',
      'X-Tenant-Key': tenantKey,
    },
    body: JSON.stringify(payload),
  }).catch((err) => {
    console.error('[wa-gateway] webhook forward failed:', err.message);
  });
}

export async function createSocket(tenantId, logger) {
  if (sockets.has(tenantId)) return null;

  const entry = { socket: null, status: 'starting', qr: null, intentional: false };
  sockets.set(tenantId, entry);

  const sessionDir = `./wa-sessions/${tenantId}`;
  const { state, saveCreds } = await useMultiFileAuthState(sessionDir);

  const sock = makeWASocket({
    auth: state,
    logger,
    defaultQueryTimeoutMs: 30000,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });
  entry.socket = sock;

  let qrDataUrl = null;

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      entry.status = 'linking';
      entry.qr = await QRCode.toDataURL(qr);
      qrDataUrl = entry.qr;
      return;
    }
    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = !entry.intentional && statusCode !== DisconnectReason.loggedOut;
      if (shouldReconnect) {
        // keep the entry visible as 'reconnecting' while we retry, so the
        // dashboard doesn't flap to 'disconnected' during the backoff window
        entry.status = 'reconnecting';
        entry.qr = null;
        entry.socket = null;
        setTimeout(() => {
          if (sockets.get(tenantId) === entry) {
            sockets.delete(tenantId);
            createSocket(tenantId, logger);
          }
        }, 3000);
      } else {
        entry.status = 'disconnected';
        sockets.delete(tenantId);
      }
    } else if (connection === 'open') {
      entry.status = 'connected';
      entry.qr = null;
    }
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const msg of messages) {
      if (msg.message && !msg.key.fromMe) {
        let mediaUrl = null;
        if (msg.message?.imageMessage?.url) {
          mediaUrl = await sock.downloadMediaMessage(msg).then((b) =>
            `data:image/jpeg;base64,${b.toString('base64')}`
          );
        }
        forwardToApi(tenantId, msg, mediaUrl);
      }
    }
  });

  return true; // caller polls /status/:tenantId to stream the qr
}

export async function sendText(tenantId, remoteJid, text) {
  const entry = sockets.get(tenantId);
  if (!entry || entry.status !== 'connected') {
    throw new Error(`no connected socket for tenant ${tenantId}`);
  }
  await entry.socket.sendMessage(remoteJid, { text });
}

export function disconnect(tenantId) {
  const entry = sockets.get(tenantId);
  if (entry) {
    entry.intentional = true;
    entry.status = 'disconnected';
    entry.socket.end(new Error('disconnected by admin'));
    sockets.delete(tenantId);
  }
}

export const socketRegistry = sockets;