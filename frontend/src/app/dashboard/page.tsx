"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Dashboard = {
  upcoming_birthdays: { preferred_name: string; occasion_date: string; days_until: number; public_greeting_consent: boolean; bot_status: string; greeting_status: string | null }[];
  active_collections: { id: string; title: string; deadline: string | null }[];
  scheduled_announcements: { id: string; title: string; scheduled_for: string | null }[];
  bot_attention: { not_started: number; blocked: number };
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  useEffect(() => {
    api<Dashboard>("/api/dashboard").then(setData).catch(() => undefined);
  }, []);
  return (
    <Shell>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded border border-line bg-white p-4">
          <h2 className="mb-3 font-semibold">{t("dash.birthdays")}</h2>
          {data?.upcoming_birthdays.length ? data.upcoming_birthdays.map((row) => (
            <p key={row.preferred_name + row.occasion_date} className="text-sm">
              {row.preferred_name} · {row.occasion_date} · {row.days_until} дн. · {row.public_greeting_consent ? "согласие есть" : "без согласия"} · бот {row.bot_status}
            </p>
          )) : <p className="text-sm">{t("common.empty")}</p>}
        </section>
        <section className="rounded border border-line bg-white p-4">
          <h2 className="mb-3 font-semibold">{t("dash.collections")}</h2>
          {data?.active_collections.length ? data.active_collections.map((row) => <p key={row.id} className="text-sm">{row.title}</p>) : <p className="text-sm">{t("common.empty")}</p>}
        </section>
        <section className="rounded border border-line bg-white p-4">
          <h2 className="mb-3 font-semibold">{t("dash.announcements")}</h2>
          {data?.scheduled_announcements.length ? data.scheduled_announcements.map((row) => <p key={row.id} className="text-sm">{row.title}</p>) : <p className="text-sm">{t("common.empty")}</p>}
        </section>
        <section className="rounded border border-line bg-white p-4">
          <h2 className="mb-3 font-semibold">{t("dash.bots")}</h2>
          <p className="text-sm">Не запустили: {data?.bot_attention.not_started ?? "—"}</p>
          <p className="text-sm">Заблокировали: {data?.bot_attention.blocked ?? "—"}</p>
        </section>
      </div>
    </Shell>
  );
}
