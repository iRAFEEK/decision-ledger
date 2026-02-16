"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { AnalyticsOverview } from "@/lib/types";

export default function DashboardPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<AnalyticsOverview>("/api/analytics/overview")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-800/50 bg-red-950/30 p-4 text-red-400">
        Failed to load analytics: {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-zinc-500">Loading...</div>
    );
  }

  const stats = [
    { label: "Total Decisions", value: data.total_decisions },
    { label: "This Week", value: data.decisions_this_week },
    { label: "Queries This Week", value: data.queries_this_week },
    {
      label: "Confirmation Rate",
      value: `${(data.confirmation_rate * 100).toFixed(0)}%`,
    },
  ];

  const maxCategory = Math.max(
    ...data.decisions_by_category.map((c) => c.count),
    1
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Dashboard</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-lg border border-zinc-800 bg-zinc-900 p-5"
          >
            <p className="text-sm text-zinc-400">{s.label}</p>
            <p className="mt-1 text-3xl font-bold text-white">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {/* Top Owners */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="mb-4 font-semibold text-white">Top Decision Owners</h2>
          {data.top_owners.length === 0 ? (
            <p className="text-sm text-zinc-500">No data yet</p>
          ) : (
            <ul className="space-y-3">
              {data.top_owners.map((o, i) => (
                <li key={i} className="flex items-center justify-between">
                  <span className="text-sm text-zinc-300">
                    {o.owner_name || o.owner_slack_id || "Unknown"}
                  </span>
                  <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-300">
                    {o.count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Categories */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="mb-4 font-semibold text-white">
            Decisions by Category
          </h2>
          {data.decisions_by_category.length === 0 ? (
            <p className="text-sm text-zinc-500">No data yet</p>
          ) : (
            <ul className="space-y-3">
              {data.decisions_by_category.map((c, i) => (
                <li key={i}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="text-zinc-300">
                      {c.category || "uncategorized"}
                    </span>
                    <span className="text-zinc-500">{c.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-zinc-800">
                    <div
                      className="h-2 rounded-full bg-blue-500"
                      style={{
                        width: `${(c.count / maxCategory) * 100}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
