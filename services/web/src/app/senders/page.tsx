"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SendersPage() {
  const [senders, setSenders] = useState<any[]>([]);
  const [platform, setPlatform] = useState("whatsapp");
  const [identifier, setIdentifier] = useState("");
  const [label, setLabel] = useState("");

  useEffect(() => {
    api("/senders").then(setSenders).catch(() => {});
  }, []);

  async function add() {
    if (!identifier) return;
    const created = await api("/senders", {
      method: "POST",
      body: { platform, identifier, label },
    });
    setSenders((s) => [...s, created]);
    setIdentifier("");
    setLabel("");
  }

  async function remove(id: string) {
    await api(`/senders/${id}`, { method: "DELETE" });
    setSenders((s) => s.filter((x) => x.id !== id));
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Allowed senders</h2>
      <div className="flex gap-3">
        <select value={platform} onChange={(e) => setPlatform(e.target.value)} className="rounded-md bg-neutral-800 px-3 py-2">
          <option value="whatsapp">whatsapp</option>
          <option value="instagram">instagram</option>
        </select>
        <input
          placeholder="phone / username (or '*')"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          className="rounded-md bg-neutral-800 px-3 py-2"
        />
        <input
          placeholder="label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="rounded-md bg-neutral-800 px-3 py-2"
        />
        <button onClick={add} className="rounded-md bg-emerald-600 px-4 py-2">
          Add
        </button>
      </div>
      <ul className="space-y-2">
        {senders.map((s) => (
          <li key={s.id} className="flex justify-between items-center rounded-lg border border-neutral-800 px-4 py-3">
            <span>
              <span className="text-sm text-neutral-500 uppercase">{s.platform}</span>{" "}
              <span className="font-medium">{s.identifier}</span>
              {s.label && <span className="ml-2 text-neutral-500">{s.label}</span>}
            </span>
            <button onClick={() => remove(s.id)} className="text-red-400 hover:text-red-300">
              remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}