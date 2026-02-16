"use client";

import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import type { Channel, Workspace } from "@/lib/types";

export default function SettingsPage() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [newChannelId, setNewChannelId] = useState("");
  const [newChannelName, setNewChannelName] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    apiGet<Workspace>("/api/workspace")
      .then(setWorkspace)
      .catch((e) => setError(e.message));
    apiGet<Channel[]>("/api/workspace/channels")
      .then(setChannels)
      .catch(() => {});
  }, []);

  const addChannel = async () => {
    if (!newChannelId.trim()) return;
    setError("");
    try {
      const ch = await apiPost<Channel>("/api/workspace/channels", {
        channel_id: newChannelId.trim(),
        channel_name: newChannelName.trim() || null,
      });
      setChannels((prev) => [...prev, ch]);
      setNewChannelId("");
      setNewChannelName("");
      setSuccess("Channel added");
      setTimeout(() => setSuccess(""), 3000);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const removeChannel = async (channelId: string) => {
    try {
      await apiDelete(`/api/workspace/channels/${channelId}`);
      setChannels((prev) => prev.filter((c) => c.channel_id !== channelId));
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const connectJira = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      await apiPost("/api/workspace/integrations/jira", {
        domain: form.get("jira_domain"),
        email: form.get("jira_email"),
        api_token: form.get("jira_token"),
      });
      setSuccess("Jira connected");
      setTimeout(() => setSuccess(""), 3000);
      const ws = await apiGet<Workspace>("/api/workspace");
      setWorkspace(ws);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const connectGitHub = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      await apiPost("/api/workspace/integrations/github", {
        org: form.get("gh_org"),
        repo: form.get("gh_repo"),
        token: form.get("gh_token"),
      });
      setSuccess("GitHub connected");
      setTimeout(() => setSuccess(""), 3000);
      const ws = await apiGet<Workspace>("/api/workspace");
      setWorkspace(ws);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const triggerBackfill = async () => {
    try {
      await apiPost("/api/workspace/backfill");
      setSuccess("Backfill started");
      setTimeout(() => setSuccess(""), 3000);
      const ws = await apiGet<Workspace>("/api/workspace");
      setWorkspace(ws);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-white">Settings</h1>

      {error && (
        <div className="mt-4 rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-sm text-red-400">
          {error}
        </div>
      )}
      {success && (
        <div className="mt-4 rounded-lg border border-green-800/50 bg-green-950/30 p-3 text-sm text-green-400">
          {success}
        </div>
      )}

      {/* Workspace info */}
      {workspace && (
        <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="font-semibold text-white">Workspace</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-zinc-500">Team</dt>
              <dd className="text-zinc-200">{workspace.team_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Slack Team ID</dt>
              <dd className="font-mono text-zinc-400">
                {workspace.slack_team_id}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Backfill Status</dt>
              <dd className="text-zinc-200">
                {workspace.backfill_status || "Not started"}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {/* Channels */}
      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
        <h2 className="font-semibold text-white">Monitored Channels</h2>
        {channels.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-500">No channels monitored</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {channels.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-zinc-300">
                  #{c.channel_name || c.channel_id}
                </span>
                <button
                  onClick={() => removeChannel(c.channel_id)}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 flex gap-2">
          <input
            type="text"
            placeholder="Channel ID"
            value={newChannelId}
            onChange={(e) => setNewChannelId(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <input
            type="text"
            placeholder="Name (optional)"
            value={newChannelName}
            onChange={(e) => setNewChannelName(e.target.value)}
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <button
            onClick={addChannel}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Add
          </button>
        </div>
      </section>

      {/* Jira */}
      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-white">Jira Integration</h2>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              workspace?.jira_domain
                ? "bg-green-900/50 text-green-300"
                : "bg-zinc-800 text-zinc-500"
            }`}
          >
            {workspace?.jira_domain ? "Connected" : "Not connected"}
          </span>
        </div>
        <form onSubmit={connectJira} className="mt-4 space-y-3">
          <input
            name="jira_domain"
            placeholder="your-org.atlassian.net"
            defaultValue={workspace?.jira_domain || ""}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <input
            name="jira_email"
            type="email"
            placeholder="Email"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <input
            name="jira_token"
            type="password"
            placeholder="API Token"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <button
            type="submit"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Connect Jira
          </button>
        </form>
      </section>

      {/* GitHub */}
      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-white">GitHub Integration</h2>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              workspace?.github_org
                ? "bg-green-900/50 text-green-300"
                : "bg-zinc-800 text-zinc-500"
            }`}
          >
            {workspace?.github_org ? "Connected" : "Not connected"}
          </span>
        </div>
        <form onSubmit={connectGitHub} className="mt-4 space-y-3">
          <input
            name="gh_org"
            placeholder="Organization"
            defaultValue={workspace?.github_org || ""}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <input
            name="gh_repo"
            placeholder="Repository"
            defaultValue={workspace?.github_repo || ""}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <input
            name="gh_token"
            type="password"
            placeholder="Personal Access Token"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
          />
          <button
            type="submit"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Connect GitHub
          </button>
        </form>
      </section>

      {/* Backfill */}
      <section className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-5">
        <h2 className="font-semibold text-white">History Backfill</h2>
        <p className="mt-2 text-sm text-zinc-400">
          Scan the last 90 days of monitored channels for past decisions.
        </p>
        <button
          onClick={triggerBackfill}
          disabled={workspace?.backfill_status === "in_progress"}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-40"
        >
          {workspace?.backfill_status === "in_progress"
            ? "Backfill Running..."
            : "Start Backfill"}
        </button>
      </section>
    </div>
  );
}
