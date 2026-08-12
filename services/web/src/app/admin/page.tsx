"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AdminPage() {
  const [activity, setActivity] = useState<any[]>([]);
  const [conversations, setConversations] = useState<any[]>([]);

  useEffect(() => {
    api("/activity?limit=30").then(setActivity).catch(() => {});
    api("/conversations").then(setConversations).catch(() => {});
  }, []);

  async function toggle(c: any) {
    const next = c.status === "paused" ? "bot_active" : "paused";
    await api(`/conversations/${c.id}`, {
      method: "PATCH",
      body: { status: next },
    });
    setConversations((cs) => cs.map((x) => (x.id === c.id ? { ...x, status: next } : x)));
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xl font-semibold mb-3">Pause / Resume</h2>
        <ul className="space-y-2">
          {conversations.map((c) => (
            <li key={c.id} className="flex justify-between items-center rounded-lg border border-neutral-800 px-4 py-3">
              <div>
                <p className="font-medium">{c.contact_identifier}</p>
                <p className="text-sm text-neutral-500">{c.platform}</p>
              </div>
              <button
                onClick={() => toggle(c)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  c.status === "paused" ? "bg-emerald-600" : "bg-amber-600"
                }`}
              >
                {c.status === "paused" ? "Resume" : "Pause"}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Activity feed</h2>
        <ul className="space-y-1 text-sm">
          {activity.map((a) => (
            <li key={a.id} className="flex justify-between border-b border-neutral-800/60 py-2">
              <span>
                <span className="text-neutral-400">{a.event_type}</span>
                <span className="ml-3 text-neutral-600">{JSON.stringify(a.payload)}</span>
              </span>
              <span className="text-neutral-600">{a.created_at}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}