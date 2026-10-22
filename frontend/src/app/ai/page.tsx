"use client";

import { FormEvent, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Draft = {
  id: string;
  status: string;
  text: string;
  received_fields: string[];
  request_fields: Record<string, unknown>;
  data: Record<string, unknown>;
  provider: string;
  executed: boolean;
};

export default function AiPage() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [message, setMessage] = useState("");

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const created = await api<Draft>("/api/ai/drafts", {
        method: "POST",
        body: JSON.stringify({ task: "nl_command", instruction: form.get("instruction") }),
      });
      setDraft(created);
      setMessage(t("ai.hint"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  async function approve() {
    if (!draft) return;
    const approved = await api<Draft>(`/api/ai/drafts/${draft.id}/approve`, { method: "POST", body: "{}" });
    setDraft(approved);
    setMessage("Черновики созданы. Отправка и открытие сбора остаются отдельными действиями HR.");
  }

  return (
    <Shell>
      <h1 className="mb-2 text-xl font-semibold">{t("ai.title")}</h1>
      <p className="mb-4 text-sm text-stone-600">{t("ai.hint")}</p>
      <form onSubmit={create} className="mb-4 grid gap-2">
        <textarea name="instruction" required className="min-h-28 rounded border border-line px-3 py-2" placeholder="Поздравь завтра Аружан и подготовь сбор на подарок на 25 000 тенге" />
        <button className="w-fit rounded bg-pine px-3 py-2 text-white" type="submit">Подготовить</button>
      </form>
      {message && <p className="mb-3 text-sm">{message}</p>}
      {draft && (
        <article className="rounded border border-line bg-white p-4 text-sm">
          <p>Провайдер: {draft.provider}. Статус: {draft.status}. Исполнено: {draft.executed ? "да" : "нет"}.</p>
          <h2 className="mt-3 font-medium">{t("ai.fields")}</h2>
          <pre className="mt-1 overflow-auto whitespace-pre-wrap">{draft.received_fields.join(", ")}</pre>
          <pre className="mt-3 overflow-auto whitespace-pre-wrap">{JSON.stringify(draft.request_fields, null, 2)}</pre>
          <p className="mt-3 whitespace-pre-wrap">{draft.text}</p>
          {draft.status === "draft" && <button className="mt-3 rounded bg-pine px-3 py-2 text-white" type="button" onClick={approve}>{t("ai.approve")}</button>}
        </article>
      )}
    </Shell>
  );
}
