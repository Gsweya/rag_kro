import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata = {
  title: "rag_kro — WhatsApp RAG Assistant",
  description: "RAG-grounded auto-responder for WhatsApp & Instagram with allowlist, pause/resume and order handling.",
};

const ADMIN_TOKEN = typeof process !== "undefined" ? process.env.ADMIN_TOKEN : undefined;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="bg-neutral-950 text-neutral-100 antialiased min-h-screen">
        <nav className="border-b border-neutral-800 px-6 py-3 flex items-center gap-6">
          <a href="/" className="font-semibold tracking-tight">
            rag_kro
          </a>
          <div className="flex gap-4 text-sm text-neutral-400">
            <a href="/admin" className="hover:text-neutral-100">Admin</a>
            <a href="/senders" className="hover:text-neutral-100">Allowlist</a>
            <a href="/documents" className="hover:text-neutral-100">Documents</a>
            <a href="/products" className="hover:text-neutral-100">Products</a>
          </div>
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}