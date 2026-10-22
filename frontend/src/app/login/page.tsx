"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { t } from "@/i18n";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      window.localStorage.setItem("hr_token", result.access_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
      <form onSubmit={submit} className="rounded border border-line bg-white p-6">
        <h1 className="mb-4 text-xl font-semibold">{t("login.title")}</h1>
        <label className="mb-3 block text-sm">
          {t("login.email")}
          <input name="email" type="email" required className="mt-1 w-full rounded border border-line px-3 py-2" />
        </label>
        <label className="mb-4 block text-sm">
          {t("login.password")}
          <input name="password" type="password" required className="mt-1 w-full rounded border border-line px-3 py-2" />
        </label>
        {error && <p className="mb-3 text-sm text-red-700">{error}</p>}
        <button className="w-full rounded bg-pine px-3 py-2 text-white" type="submit">{t("login.submit")}</button>
        <p className="mt-4 text-xs text-stone-600">{t("login.local")}</p>
      </form>
    </main>
  );
}
