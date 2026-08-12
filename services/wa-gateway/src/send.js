import { sendText } from './socket.js';

export function registerSendRoute(app, requireKey, logger) {
  app.post('/send', requireKey, async (req, res) => {
    const { tenant_id, contact_identifier, body } = req.body || {};
    if (!tenant_id || !contact_identifier || !body) {
      return res.status(400).json({ error: 'tenant_id, contact_identifier, body required' });
    }
    try {
      await sendText(tenant_id, contact_identifier, body);
      res.json({ sent: true, to: contact_identifier });
    } catch (err) {
      logger.error({ err, tenant_id }, 'send failed');
      res.status(500).json({ error: err.message });
    }
  });
}