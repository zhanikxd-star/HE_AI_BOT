"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Employee = { id: string; preferred_name: string };
type Collection = { id: string; title: string; status: string; deadline: string | null };
type OrgPayment = { payment_details: string; payment_fixed_amount: string; currency: string };

export default function CollectionsPage() {
  const [rows, setRows] = useState<Collection[]>([]);
  const [people, setPeople] = useState<Employee[]>([]);
  const [payment, setPayment] = useState<OrgPayment | null>(null);
  const [message, setMessage] = useState("");

  function load() {
    api<Collection[]>("/api/collections").then(setRows).catch((err: Error) => setMessage(err.message));
  }
  useEffect(() => {
    load();
    api<Employee[]>("/api/employees?status=active").then(setPeople).catch(() => undefined);
    api<OrgPayment>("/api/settings").then(setPayment).catch(() => undefined);
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/collections", {
        method: "POST",
        body: JSON.stringify({
          employee_id: form.get("employee_id"),
          title: form.get("title"),
          scope: { all: true, department_ids: [], employee_ids: [] },
        }),
      });
      setMessage("Черновик сбора создан");
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  return (
    <Shell>
      <h1 className="mb-2 text-xl font-semibold">{t("collections.title")}</h1>
      <p className="mb-2 text-sm text-stone-600">{t("collections.hrOnly")}</p>
      <p className="mb-4 text-sm text-stone-600">
        {t("collections.paymentFromOrg")}
        {payment ? ` ${payment.payment_details}. Фиксированный взнос: ${payment.payment_fixed_amount} ${payment.currency}.` : ""}
      </p>
      <form onSubmit={create} className="mb-4 grid gap-2 rounded border border-line bg-white p-4 md:grid-cols-2">
        <select name="employee_id" required className="rounded border border-line px-3 py-2">
          <option value="">Именинник</option>
          {people.map((person) => <option key={person.id} value={person.id}>{person.preferred_name}</option>)}
        </select>
        <input name="title" required placeholder="Название" className="rounded border border-line px-3 py-2" />
        <button className="rounded bg-pine px-3 py-2 text-white" type="submit">{t("common.create")}</button>
      </form>
      {message && <p className="mb-3 text-sm">{message}</p>}
      <div className="grid gap-2">
        {rows.map((row) => (
          <Link key={row.id} href={`/collections/${row.id}`} className="rounded border border-line bg-white p-3 text-sm">{row.title} · {row.status}</Link>
        ))}
      </div>
    </Shell>
  );
}
