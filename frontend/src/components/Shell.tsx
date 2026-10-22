"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { t } from "@/i18n";
import { api } from "@/lib/api";

const links = [
  ["/dashboard", "nav.dashboard"],
  ["/employees", "nav.employees"],
  ["/calendar", "nav.calendar"],
  ["/collections", "nav.collections"],
  ["/announcements", "nav.announcements"],
  ["/ai", "nav.ai"],
  ["/settings", "nav.settings"],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [health, setHealth] = useState<{ telegram: string; llm: string } | null>(null);
  const [chatConfigured, setChatConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    if (!window.localStorage.getItem("hr_token")) {
      router.replace("/login");
      return;
    }
    api<{ telegram: string; llm: string }>("/api/health").then(setHealth).catch(() => undefined);
    api<{ corporate_chat_configured: boolean }>("/api/settings").then((row) => setChatConfigured(row.corporate_chat_configured)).catch(() => undefined);
  }, [router]);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className={`${open ? "block" : "hidden"} border-b border-line bg-white md:block md:border-b-0 md:border-r`}>
        <div className="flex items-center justify-between px-4 py-4">
          <Link href="/dashboard" className="font-semibold text-pine">{t("app.title")}</Link>
          <button className="md:hidden" onClick={() => setOpen(false)} type="button">×</button>
        </div>
        <nav className="flex flex-col gap-1 px-2 pb-4">
          {links.map(([href, key]) => (
            <Link key={href} href={href} className={`rounded px-3 py-2 text-sm ${path.startsWith(href) ? "bg-pine text-white" : "hover:bg-paper"}`}>
              {t(key)}
            </Link>
          ))}
          <button
            className="rounded px-3 py-2 text-left text-sm hover:bg-paper"
            type="button"
            onClick={() => {
              window.localStorage.removeItem("hr_token");
              router.replace("/login");
            }}
          >
            {t("nav.logout")}
          </button>
        </nav>
      </aside>
      <div>
        <header className="flex items-center gap-3 border-b border-line bg-white px-4 py-3 md:hidden">
          <button type="button" onClick={() => setOpen(true)}>Меню</button>
          <span className="font-semibold">{t("app.title")}</span>
        </header>
        {(health?.telegram === "test" || health?.llm === "test") && (
          <p className="bg-amber-50 px-4 py-2 text-sm text-amber-950">{t("banner.test")}</p>
        )}
        {chatConfigured === false && <p className="bg-paper px-4 py-2 text-sm">{t("banner.chat")}</p>}
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </div>
    </div>
  );
}
