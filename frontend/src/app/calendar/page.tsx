"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Day = { date: string; birthdays: { preferred_name: string; public_greeting_consent: boolean; bot_status: string }[] };

export default function CalendarPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [days, setDays] = useState<Day[]>([]);

  useEffect(() => {
    api<{ days: Day[] }>(`/api/calendar?year=${year}&month=${month}`).then((data) => setDays(data.days)).catch(() => undefined);
  }, [year, month]);

  return (
    <Shell>
      <h1 className="mb-4 text-xl font-semibold">{t("calendar.title")}</h1>
      <div className="mb-4 flex gap-2">
        <input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} className="w-28 rounded border border-line px-3 py-2" />
        <input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} className="w-20 rounded border border-line px-3 py-2" />
      </div>
      <div className="grid gap-3">
        {days.map((day) => (
          <article key={day.date} className="rounded border border-line bg-white p-3">
            <h2 className="font-medium">{day.date}</h2>
            {day.birthdays.map((person) => (
              <p key={person.preferred_name} className="text-sm">{person.preferred_name} · согласие {person.public_greeting_consent ? "да" : "нет"} · бот {person.bot_status}</p>
            ))}
          </article>
        ))}
        {!days.length && <p>{t("common.empty")}</p>}
      </div>
    </Shell>
  );
}
