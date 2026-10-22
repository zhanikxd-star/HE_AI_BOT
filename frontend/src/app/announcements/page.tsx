"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Item = { id: string; title: string; status: string; type: string; scheduled_for: string | null };

export default function AnnouncementsPage() {
  const [rows, setRows] = useState<Item[]>([]);
  const [message, setMessage] = useState("");

  function load() {
    api<Item[]>("/api/announcements").then(setRows).catch((err: Error) => setMessage(err.message));
  }
  useEffect(() => { load(); }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/announcements", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          body: form.get("body"),
          type: form.get("type"),
          requires_rsvp: form.get("rsvp") === "on",
          segment: { all: form.get("segment") === "all", department_ids: [], employee_ids: [] },
        }),
      });
      setMessage("Черновик создан");
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 text-xl font-semibold">{t("announcements.title")}</h1>
      <form onSubmit={create} className="mb-4 grid gap-2 rounded border border-line bg-white p-4">
        <input name="title" required placeholder="Заголовок" className="rounded border border-line px-3 py-2" />
        <textarea name="body" required placeholder="Текст" className="rounded border border-line px-3 py-2" />
        <select name="type" className="rounded border border-line px-3 py-2">
          {["event", "meeting", "news", "schedule", "training", "survey", "reminder"].map((kind) => <option key={kind}>{kind}</option>)}
        </select>
        <label className="text-sm"><input name="rsvp" type="checkbox" className="mr-2" />Нужен ответ «Буду / Не смогу»</label>
        <label className="text-sm"><input name="segment" type="checkbox" value="all" className="mr-2" />Всем активным</label>
        <button className="w-fit rounded bg-pine px-3 py-2 text-white" type="submit">{t("common.create")}</button>
      </form>
      {message && <p className="mb-3 text-sm">{message}</p>}
      <div className="grid gap-2">
        {rows.map((row) => <Link key={row.id} className="rounded border border-line bg-white p-3 text-sm" href={`/announcements/${row.id}`}>{row.title} · {row.type} · {row.status}</Link>)}
      </div>
    </Shell>
  );
}
