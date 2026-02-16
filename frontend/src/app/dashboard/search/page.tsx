"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { SearchResult } from "@/lib/types";
import { Search } from "lucide-react";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    try {
      const data = await apiPost<SearchResult>("/api/search", {
        query: query.trim(),
        limit: 5,
      });
      setResult(data);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-white">Search Decisions</h1>

      <form onSubmit={handleSearch} className="mt-6">
        <div className="relative">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a question about your team's decisions..."
            className="w-full rounded-xl border border-zinc-700 bg-zinc-900 py-4 pl-12 pr-4 text-zinc-200 placeholder:text-zinc-500 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="mt-3 rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-40"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-8">
          {/* AI Answer */}
          <div className="rounded-lg border border-blue-800/40 bg-blue-950/20 p-5">
            <p className="mb-2 text-xs font-medium uppercase text-blue-400">
              AI Answer
            </p>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
              {result.answer}
            </div>
          </div>

          {/* Response time */}
          <p className="mt-3 text-xs text-zinc-600">
            {result.decisions.length} results in {result.response_time_ms}ms
          </p>

          {/* Source decisions */}
          {result.decisions.length > 0 && (
            <div className="mt-6 space-y-3">
              <h2 className="text-sm font-medium text-zinc-400">
                Source Decisions
              </h2>
              {result.decisions.map((d) => (
                <div
                  key={d.id}
                  className="rounded-lg border border-zinc-800 bg-zinc-900 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-medium text-white">{d.title}</h3>
                      {d.summary && (
                        <p className="mt-1 text-sm text-zinc-400">
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
                      </div>
                    </div>
                    <span className="shrink-0 rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
                      {(d.combined_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="mt-16 text-center text-zinc-600">
          Ask a question about your team&apos;s decisions
        </div>
      )}
    </div>
  );
}
