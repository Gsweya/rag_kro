"use client";

const ADMIN_TOKEN = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_ADMIN_TOKEN) || "";

export async function api<T = any>(
  path: string,
  options: RequestInit & { file?: File } = {}
): Promise<T> {
  const { file, body, headers, ...rest } = options;
  const headers_ = new Headers(headers);
  if (ADMIN_TOKEN) headers_.set("x-admin-token", ADMIN_TOKEN);

  let body_ = body;
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