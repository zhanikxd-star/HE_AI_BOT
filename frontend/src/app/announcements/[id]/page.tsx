"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";

type Stats = { delivered: number; not_started: number; blocked: number; notifications_off: number; simulated: number; will_attend: number; cannot_attend: number; rows: { preferred_name: string; delivery_status: string; rsvp_status: string; bot_status: string }[] };

export default function AnnouncementPage() {
  const params = useParams<{ id: string }>();
  const [stats, setStats] = useState<Stats | null>(null);
  const [message, setMessage] = useState("");

  function load() {
    api<Stats>(`/api/announcements/${params.id}/stats`).then(setStats).catch(() => undefined);
  }
  useEffect(() => { if (params.id) load(); }, [params.id]);

  async function send() {
    try {
      setStats(await api<Stats>(`/api/announcements/${params.id}/send`, { method: "POST", body: "{}" }));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 text-xl font-semibold">Рассылка</h1>
      <button className="mb-4 rounded bg-pine px-3 py-2 text-white" type="button" onClick={send}>Отправить сейчас</button>
      {message && <p className="mb-3 text-sm">{message}</p>}
      {stats && (
        <div className="rounded border border-line bg-white p-4 text-sm">
          <p>Доставлено в Telegram: {stats.delivered}. Тестовый адаптер: {stats.simulated}. Не запустили бота: {stats.not_started}. Заблокировали: {stats.blocked}. Уведомления выключены: {stats.notifications_off}.</p>
          <p className="mt-2">Буду: {stats.will_attend}. Не смогу: {stats.cannot_attend}.</p>
          <ul className="mt-3 space-y-1">
            {stats.rows?.map((row) => <li key={row.preferred_name}>{row.preferred_name} · {row.delivery_status} · {row.rsvp_status} · бот {row.bot_status}</li>)}
          </ul>
        </div>
      )}
    </Shell>
  );
}
