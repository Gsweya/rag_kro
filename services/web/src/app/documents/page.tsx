"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<any[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("pdf");

  useEffect(() => {
    api("/documents").then(setDocs).catch(() => {});
  }, []);

  async function upload() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    fd.append("tenant_id", "00000000-0000-0000-0000-000000000001");
    const res = await fetch("/api/back/documents/upload", {
      method: "POST",
      headers: {
        "x-tenant-id": "00000000-0000-0000-0000-000000000001",
        "x-tenant-key": process.env.NEXT_PUBLIC_TENANT_KEY || "admin",
      },
      body: fd,
    });
    const data: any = await res.json();
    if (!res.ok) throw new Error(data.detail || "upload failed");
    setDocs((d) => [{ id: data.doc_id, type: docType, title: file.name, status: data.status }, ...d]);
    setFile(null);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Documents</h2>
      <div className="flex gap-3 items-center">
        <select value={docType} onChange={(e) => setDocType(e.target.value)} className="rounded-md bg-neutral-800 px-3 py-2">
          <option value="pdf">PDF</option>
          <option value="image">Image</option>
        </select>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
        <button onClick={upload} className="rounded-md bg-emerald-600 px-4 py-2">
          Upload & Index
        </button>
      </div>
      <ul className="space-y-2">
        {docs.map((d) => (
          <li key={d.id} className="flex justify-between rounded-lg border border-neutral-800 px-4 py-3">
            <span>
              <span className="text-sm text-neutral-500 uppercase">{d.type}</span>{" "}
              <span className="font-medium">{d.title}</span>
            </span>
            <span className="text-sm">{d.status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}