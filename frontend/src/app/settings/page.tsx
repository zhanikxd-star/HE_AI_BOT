"use client";

import { FormEvent, useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type Settings = {
  name: string;
  timezone: string;
  corporate_chat_configured: boolean;
  corporate_chat_id: number | null;
  corporate_chat_title: string | null;
  corporate_chat_type: string | null;
  bot_username: string | null;
  super_admin_telegram_username: string | null;
  llm_model_name: string;
  llm_provider: string;
  llm_mode: string;
  greeting_lead_days: number;
  currency: string;
  payment_method: string;
  payment_phone: string;
  payment_fixed_amount: string;
  payment_details: string;
  notion_database_id: string | null;
  notion_database_title: string | null;
  notion_database_type: string | null;
  notion_ready: boolean;
  onboarding_files: { name: string; url: string }[];
};
type Admin = { id: string; email: string; full_name: string; role: string; telegram_username: string | null };
type Me = { role: string };
type Audit = { id: string; action: string; created_at: string; entity_type: string };

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api<Settings>("/api/settings").then(setSettings).catch((err: Error) => setMessage(err.message));
    api<Me>("/api/auth/me").then(setMe).catch(() => undefined);
    api<Audit[]>("/api/audit").then(setAudit).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (me?.role === "super_admin") api<Admin[]>("/api/admins").then(setAdmins).catch(() => undefined);
  }, [me]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const next = await api<Settings>("/api/settings", {
        method: "PATCH",
        body: JSON.stringify({
          name: form.get("name"),
          timezone: form.get("timezone"),
          llm_model_name: form.get("llm_model_name"),
          llm_provider: form.get("llm_provider"),
          greeting_lead_days: Number(form.get("greeting_lead_days")),
          bot_username: form.get("bot_username"),
          super_admin_telegram_username: form.get("super_admin_telegram_username"),
          payment_phone: form.get("payment_phone"),
          payment_fixed_amount: form.get("payment_fixed_amount"),
          notion_database_id: form.get("notion_database_id"),
        }),
      });
      setSettings(next);
      setMessage("Сохранено");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  async function addAdmin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/admins", {
      method: "POST",
      body: JSON.stringify({
        email: form.get("email"),
        password: form.get("password"),
        full_name: form.get("full_name"),
        role: "hr_admin",
      }),
    });
    setAdmins(await api<Admin[]>("/api/admins"));
  }

  return (
    <Shell>
      <h1 className="mb-2 text-xl font-semibold">{t("settings.title")}</h1>
      <p className="mb-2 text-sm">{t("settings.token")}</p>
      <p className="mb-2 text-sm">{t("settings.address")}</p>
      <p className="mb-2 text-sm">{t("settings.llm")}</p>
      <p className="mb-2 text-sm">{t("settings.notion")}</p>
      <p className="mb-4 text-sm">
        {settings?.corporate_chat_configured
          ? `Корпоративный чат: ${settings.corporate_chat_title || "без названия"} (${settings.corporate_chat_type || "чат"}), id ${settings.corporate_chat_id}.`
          : t("settings.chatEmpty")}
      </p>
      {settings && (
        <form onSubmit={save} className="mb-6 grid gap-2 rounded border border-line bg-white p-4 md:grid-cols-2">
          <input name="name" defaultValue={settings.name} className="rounded border border-line px-3 py-2" />
          <input name="timezone" defaultValue={settings.timezone} className="rounded border border-line px-3 py-2" />
          <input name="bot_username" defaultValue={settings.bot_username || ""} className="rounded border border-line px-3 py-2" />
          <input name="super_admin_telegram_username" defaultValue={settings.super_admin_telegram_username || ""} className="rounded border border-line px-3 py-2" />
          <input name="llm_model_name" defaultValue={settings.llm_model_name} aria-label="Имя модели" className="rounded border border-line px-3 py-2" />
          <select name="llm_provider" defaultValue={settings.llm_provider} aria-label="Провайдер модели" className="rounded border border-line px-3 py-2"><option value="openai">openai</option><option value="test">test</option></select>
          <input name="payment_phone" defaultValue={settings.payment_phone} aria-label="Телефон для Kaspi" className="rounded border border-line px-3 py-2" />
          <input name="payment_fixed_amount" defaultValue={settings.payment_fixed_amount} aria-label="Фиксированный взнос" className="rounded border border-line px-3 py-2" />
          <p className="text-sm md:col-span-2">{settings.payment_details}. Режим модели: {settings.llm_mode}.</p>
          <input name="notion_database_id" defaultValue={settings.notion_database_id || ""} aria-label="ID базы Notion" className="rounded border border-line px-3 py-2 md:col-span-2" />
          <p className="text-sm md:col-span-2">{settings.notion_database_title || "База Notion"} ({settings.notion_database_type || "database"}). {settings.onboarding_files.length ? `Файлов обучения: ${settings.onboarding_files.length}` : t("settings.trainingEmpty")} Notion: {settings.notion_ready ? "готово" : "пропуск, ключа нет"}.</p>
          <input name="greeting_lead_days" type="number" defaultValue={settings.greeting_lead_days} className="rounded border border-line px-3 py-2" />
          <button className="rounded bg-pine px-3 py-2 text-white disabled:opacity-50" type="submit" disabled={me?.role !== "super_admin"}>{t("common.save")}</button>
        </form>
      )}
      {message && <p className="mb-3 text-sm">{message}</p>}
      {me?.role === "super_admin" && (
        <section className="mb-6">
          <h2 className="mb-2 font-medium">HR-администраторы</h2>
          <form onSubmit={addAdmin} className="mb-3 grid gap-2 md:grid-cols-4">
            <input name="full_name" required placeholder="Имя" className="rounded border border-line px-3 py-2" />
            <input name="email" type="email" required placeholder="Почта" className="rounded border border-line px-3 py-2" />
            <input name="password" type="password" required minLength={8} placeholder="Пароль" className="rounded border border-line px-3 py-2" />
            <button className="rounded bg-pine px-3 py-2 text-white" type="submit">Назначить</button>
          </form>
          {admins.map((admin) => <p key={admin.id} className="text-sm">{admin.full_name} · {admin.email} · {admin.role} · @{admin.telegram_username || "—"}</p>)}
        </section>
      )}
      <section>
        <h2 className="mb-2 font-medium">Журнал</h2>
        {audit.slice(0, 30).map((row) => <p key={row.id} className="text-sm">{row.created_at} · {row.action} · {row.entity_type}</p>)}
      </section>
    </Shell>
  );
}
