"use client";

import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Employee = {
  id: string;
  full_name: string;
  preferred_name: string;
  birth_date: string;
  position: string;
  bot_status: string;
  status: string;
  public_greeting_consent: boolean;
};

export default function EmployeesPage() {
  const [rows, setRows] = useState<Employee[]>([]);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");

  function load(q = query) {
    api<Employee[]>(`/api/employees?q=${encodeURIComponent(q)}`).then(setRows).catch((err: Error) => setMessage(err.message));
  }

  useEffect(() => { load(""); }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/employees", {
        method: "POST",
        body: JSON.stringify({
          full_name: form.get("full_name"),
          preferred_name: form.get("preferred_name"),
          birth_date: form.get("birth_date"),
          position: form.get("position") || "",
          public_greeting_consent: form.get("consent") === "on",
        }),
      });
      event.currentTarget.reset();
      setMessage("Сотрудник добавлен");
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const report = await api<{ created: number; duplicates: unknown[] }>("/api/employees/import", { method: "POST", body: form });
      setMessage(`Создано: ${report.created}, дубликаты: ${report.duplicates.length}`);
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 text-xl font-semibold">{t("employees.title")}</h1>
      <div className="mb-4 flex gap-2">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("common.search")} className="rounded border border-line px-3 py-2" />
        <button type="button" className="rounded bg-pine px-3 py-2 text-white" onClick={() => load(query)}>{t("common.search")}</button>
      </div>
      <form onSubmit={create} className="mb-4 grid gap-2 rounded border border-line bg-white p-4 md:grid-cols-2">
        <input name="full_name" required placeholder="ФИО" className="rounded border border-line px-3 py-2" />
        <input name="preferred_name" required placeholder="Имя для обращения" className="rounded border border-line px-3 py-2" />
        <input name="birth_date" required type="date" className="rounded border border-line px-3 py-2" />
        <input name="position" placeholder="Должность" className="rounded border border-line px-3 py-2" />
        <label className="text-sm"><input name="consent" type="checkbox" className="mr-2" />{t("employees.consent")}</label>
        <button className="rounded bg-pine px-3 py-2 text-white" type="submit">{t("employees.add")}</button>
      </form>
      <form onSubmit={upload} className="mb-4 flex flex-wrap items-center gap-2">
        <input name="file" type="file" accept=".csv,.xlsx" required />
        <button className="rounded border border-line bg-white px-3 py-2" type="submit">{t("employees.import")}</button>
      </form>
      {message && <p className="mb-3 text-sm">{message}</p>}
      <div className="overflow-x-auto rounded border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b border-line"><th className="p-2">ФИО</th><th className="p-2">Обращение</th><th className="p-2">Дата</th><th className="p-2">{t("employees.bot")}</th><th className="p-2">Согласие</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-line">
                <td className="p-2">{row.full_name}</td>
                <td className="p-2">{row.preferred_name}</td>
                <td className="p-2">{row.birth_date}</td>
                <td className="p-2">{row.bot_status}</td>
                <td className="p-2">{row.public_greeting_consent ? "да" : "нет"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
