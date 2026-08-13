"use client";

const ADMIN_TOKEN = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_ADMIN_TOKEN) || "";
const TENANT_ID =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_TENANT_ID) ||
  "00000000-0000-0000-0000-000000000001";
const TENANT_KEY =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_TENANT_KEY) || "admin";

export async function api<T = any>(
  path: string,
  options: Omit<RequestInit, "body"> & { body?: unknown; file?: File } = {}
): Promise<T> {
  const { file, body, headers, ...rest } = options;
  const headers_ = new Headers(headers);
  if (ADMIN_TOKEN) headers_.set("x-admin-token", ADMIN_TOKEN);
  headers_.set("x-tenant-id", TENANT_ID);
  headers_.set("x-tenant-key", TENANT_KEY);

  let body_: BodyInit | undefined;
  if (file) {
    const fd = new FormData();
    fd.append("file", file);
    body_ = fd;
  } else if (body && !(body instanceof FormData)) {
    headers_.set("Content-Type", "application/json");
    body_ = JSON.stringify(body);
  }

  const res = await fetch(`/api/back${path}`, {
    ...rest,
    headers: headers_,
    body: body_,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}