"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Decision, DecisionDetail, PaginatedDecisions } from "@/lib/types";

const CATEGORIES = [
  "architecture",
  "schema",
  "api",
  "infrastructure",
  "deprecation",
  "dependency",
  "naming",
  "process",
  "security",
  "performance",
  "tooling",
];

const STATUS_OPTIONS = ["pending", "active", "ignored", "expired"];

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-900/50 text-yellow-300",
  active: "bg-green-900/50 text-green-300",
  ignored: "bg-zinc-800 text-zinc-400",
  expired: "bg-red-900/50 text-red-400",
};

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<DecisionDetail | null>(null);
  const [error, setError] = useState("");
  const perPage = 20;

  const fetchDecisions = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", String(perPage));
      if (status) params.set("status", status);
      if (category) params.set("category", category);
      if (search) params.set("tag", search);
      const data = await apiGet<PaginatedDecisions>(
        `/api/decisions?${params.toString()}`
      );
      setDecisions(data.items);
      setTotal(data.total);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }, [page, status, category, search]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  const toggleExpand = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(id);
    try {
      const d = await apiGet<DecisionDetail>(`/api/decisions/${id}`);
      setDetail(d);
    } catch {
      setDetail(null);
    }
  };

  const handleAction = async (id: string, action: "confirm" | "ignore") => {
    await apiPost(`/api/decisions/${id}/${action}`);
    fetchDecisions();
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Decisions</h1>

      {/* Filters */}
      <div className="mt-4 flex flex-wrap gap-3">
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Filter by tag..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
        />
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Decision list */}
      <div className="mt-4 space-y-3">
        {decisions.map((d) => (
          <div
            key={d.id}
            className="rounded-lg border border-zinc-800 bg-zinc-900"
          >
            <button
              onClick={() => toggleExpand(d.id)}
              className="w-full px-5 py-4 text-left"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium text-white">{d.title}</h3>
                  {d.summary && (
                    <p className="mt-1 text-sm text-zinc-400 line-clamp-2">
                      {d.summary}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {d.tags?.map((t) => (
                      <span
                        key={t}
                        className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400"
                      >
                        {t}
                      </span>
                    ))}
                    {d.owner_name && (
                      <span className="text-xs text-zinc-500">
                        by {d.owner_name}
                      </span>
                    )}
                    <span className="text-xs text-zinc-600">
                      {new Date(d.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_COLORS[d.status] || "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {d.status}
                </span>
              </div>
            </button>

            {expanded === d.id && detail && (
              <div className="border-t border-zinc-800 px-5 py-4">
                {detail.rationale && (
                  <div className="mb-3">
                    <p className="mb-1 text-xs font-medium uppercase text-zinc-500">
                      Rationale
                    </p>
                    <p className="text-sm text-zinc-300">{detail.rationale}</p>
                  </div>
                )}
                {detail.source_channel_name && (
                  <p className="text-xs text-zinc-500">
                    Source: #{detail.source_channel_name}
                  </p>
                )}
                {detail.links.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-1 text-xs font-medium uppercase text-zinc-500">
                      Links
                    </p>
                    <ul className="space-y-1">
                      {detail.links.map((l) => (
                        <li key={l.id}>
                          <a
                            href={l.link_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-blue-400 hover:underline"
                          >
                            {l.link_title || l.link_url}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {d.status === "pending" && (
                  <div className="mt-4 flex gap-2">
                    <button
                      onClick={() => handleAction(d.id, "confirm")}
                      className="rounded-lg bg-green-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-green-500"
                    >
                      Confirm
                    </button>
                    <button
                      onClick={() => handleAction(d.id, "ignore")}
                      className="rounded-lg bg-zinc-700 px-4 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-zinc-600"
                    >
                      Ignore
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {decisions.length === 0 && !error && (
          <p className="py-12 text-center text-zinc-500">No decisions found</p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-between">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-zinc-500">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
