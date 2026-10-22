"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { t } from "@/i18n";
import { api } from "@/lib/api";

type View = {
  id: string;
  title: string;
  status: string;
  payment_details: string;
  participants: { id: string; preferred_name: string; status: string; amount: string | null; delivery_status: string }[];
};

export default function CollectionPage() {
  const params = useParams<{ id: string }>();
  const [view, setView] = useState<View | null>(null);
  const [message, setMessage] = useState("");

  function load() {
    api<View>(`/api/collections/${params.id}`).then(setView).catch((err: Error) => setMessage(err.message));
  }
  useEffect(() => { if (params.id) load(); }, [params.id]);

  async function act(path: string) {
    try {
      await api(path, { method: "POST", body: "{}" });
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка");
    }
  }

  if (!view) return <Shell><p>{message || "…"}</p></Shell>;
  return (
    <Shell>
      <h1 className="mb-2 text-xl font-semibold">{view.title}</h1>
      <p className="mb-4 text-sm">{t("collections.hrOnly")} Статус: {view.status}</p>
      <div className="mb-4 flex flex-wrap gap-2">
        {view.status === "draft" && <button className="rounded bg-pine px-3 py-2 text-white" type="button" onClick={() => act(`/api/collections/${view.id}/open`)}>Открыть и пригласить</button>}
        {view.status === "open" && <button className="rounded border border-line bg-white px-3 py-2" type="button" onClick={() => act(`/api/collections/${view.id}/close`)}>Закрыть</button>}
        {view.status !== "cancelled" && view.status !== "closed" && <button className="rounded border border-line bg-white px-3 py-2" type="button" onClick={() => act(`/api/collections/${view.id}/cancel`)}>{t("common.cancel")}</button>}
      </div>
      {message && <p className="mb-3 text-sm">{message}</p>}
      <div className="overflow-x-auto rounded border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b border-line"><th className="p-2">Кто</th><th className="p-2">Ответ</th><th className="p-2">Сумма</th><th className="p-2">Доставка</th><th /></tr></thead>
          <tbody>
            {view.participants?.map((row) => (
              <tr key={row.id} className="border-b border-line">
                <td className="p-2">{row.preferred_name}</td>
                <td className="p-2">{row.status}</td>
                <td className="p-2">{row.amount || "—"}</td>
                <td className="p-2">{row.delivery_status}</td>
                <td className="p-2">{row.status === "payment_declared" && <button type="button" className="underline" onClick={() => act(`/api/collections/participants/${row.id}/confirm`)}>Подтвердить</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
