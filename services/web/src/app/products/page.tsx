"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ProductsPage() {
  const [products, setProducts] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("0");
  const [description, setDescription] = useState("");

  useEffect(() => {
    api("/products").then(setProducts).catch(() => {});
  }, []);

  async function add() {
    const created = await api("/products", {
      method: "POST",
      body: {
        name,
        price: price ? Number(price) : null,
        stock: Number(stock),
        description,
      },
    });
    setProducts((p) => [created, ...p]);
    setName(""); setPrice(""); setStock("0"); setDescription("");
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Products</h2>
      <div className="grid grid-cols-2 gap-3 max-w-lg">
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="rounded-md bg-neutral-800 px-3 py-2" />
        <div className="flex gap-3">
          <input placeholder="Price" value={price} onChange={(e) => setPrice(e.target.value)} className="rounded-md bg-neutral-800 px-3 py-2 w-full" />
          <input placeholder="Stock" value={stock} onChange={(e) => setStock(e.target.value)} className="rounded-md bg-neutral-800 px-3 py-2 w-24" />
        </div>
        <input
          placeholder="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="rounded-md bg-neutral-800 px-3 py-2 col-span-2"
        />
        <button onClick={add} className="rounded-md bg-emerald-600 px-4 py-2">
          Add product
        </button>
      </div>
      <ul className="space-y-2">
        {products.map((p) => (
          <li key={p.id} className="flex justify-between rounded-lg border border-neutral-800 px-4 py-3">
            <span className="font-medium">{p.name}</span>
            <span className="text-sm">
              {p.price !== null ? `$${p.price}` : "—"} · stock {p.stock}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}