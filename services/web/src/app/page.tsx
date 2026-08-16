"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const TENANT_ID = "00000000-0000-0000-0000-000000000001";

export default function HomePage() {
  const [sessions, setSessions] = useState<any>({ whatsapp: { status: "…" }, instagram: { status: "…" } });
  const [conversations, setConversations] = useState<any[]>([]);
  const [qr, setQr] = useState<string | null>(null);

  async function waStatus() {
    const key = process.env.NEXT_PUBLIC_INTERNAL_KEY || "internal-key";
    return fetch(`/api/wa/status/${TENANT_ID}`, {
      headers: { "x-internal-key": key },
    }).then((r) => r.json());
  }

  useEffect(() => {
    api("/sessions").then(setSessions).catch(() => {});
    api("/conversations").then(setConversations).catch(() => {});
    const refresh = async () => {
      try {
        const res = await waStatus();
        setSessions((s) => ({ ...s, whatsapp: { status: res.status } }));
        if (res.status === "connected") setQr(null);
        if (res.qr) {
          setQr(res.qr);
          sessionStorage.setItem("rag_kro_qr", res.qr);
        }
      } catch {}
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);

  async function connect() {
    const key = process.env.NEXT_PUBLIC_INTERNAL_KEY || "internal-key";
    await fetch(`/api/wa/connect/${TENANT_ID}`, {
      headers: { "x-internal-key": key },
    });
    // stream the QR by polling the gateway status endpoint
    const timer = setInterval(async () => {
      const res = await waStatus();
      if (res.qr) {
        setQr(res.qr);
        sessionStorage.setItem("rag_kro_qr", res.qr);
      } else if (!res.qr && res.status === "connected") {
        clearInterval(timer);
        setSessions((s) => ({ ...s, whatsapp: { status: "connected" } }));
      }
    }, 2000);
  }

  async function disconnectWhatsApp() {
    const key = process.env.NEXT_PUBLIC_INTERNAL_KEY || "internal-key";
    await fetch(`/api/wa/disconnect/${TENANT_ID}`, {
      method: "POST",
      headers: { "x-internal-key": key },
    });
    setSessions((s) => ({ ...s, whatsapp: { status: "disconnected" } }));
    setQr(null);
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold mb-4">Dashboard</h1>
        <div className="grid grid-cols-2 gap-4 max-w-md">
          <div className="rounded-lg border border-neutral-800 p-4">
            <p className="text-sm text-neutral-400">WhatsApp</p>
            <p className="text-lg">{sessions.whatsapp?.status}</p>
          </div>
          <div className="rounded-lg border border-neutral-800 p-4">
            <p className="text-sm text-neutral-400">Instagram</p>
            <p className="text-lg">{sessions.instagram?.status}</p>
          </div>
        </div>
        {sessions.whatsapp?.status === "connected" ? (
          <button
            onClick={disconnectWhatsApp}
            className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium"
          >
            Disconnect WhatsApp
          </button>
        ) : (
          <button
            onClick={connect}
            className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium"
          >
            Connect WhatsApp
          </button>
        )}
        {qr && (
          <div className="mt-4">
            <p className="text-sm text-neutral-400 mb-2">Scan with WhatsApp &gt; Linked Devices</p>
            <img src={qr} alt="WhatsApp QR" className="rounded-lg border border-neutral-800" />
          </div>
        )}
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Conversations</h2>
        <ul className="space-y-2">
          {conversations.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded-lg border border-neutral-800 px-4 py-3">
              <div>
                <p className="font-medium">{c.contact_identifier}</p>
                <p className="text-sm text-neutral-500">{c.platform}</p>
              </div>
              <span className={`text-sm ${c.status === "paused" ? "text-amber-400" : "text-emerald-400"}`}>
                {c.status}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}