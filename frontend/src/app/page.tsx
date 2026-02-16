const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="max-w-2xl text-center">
        <h1 className="text-5xl font-bold tracking-tight text-white">
          Decision Ledger
        </h1>
        <p className="mt-4 text-xl text-zinc-400">
          Your engineering team&apos;s decision memory
        </p>

        <a
          href={`${API_URL}/auth/slack`}
          className="mt-10 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-base font-semibold text-zinc-900 transition hover:bg-zinc-200"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.124 2.521a2.528 2.528 0 0 1 2.52-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.52V8.834zm-1.271 0a2.528 2.528 0 0 1-2.521 2.521 2.528 2.528 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.166 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.124a2.528 2.528 0 0 1 2.521 2.52A2.528 2.528 0 0 1 15.166 24a2.528 2.528 0 0 1-2.521-2.522v-2.52h2.521zm0-1.271a2.528 2.528 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.312A2.528 2.528 0 0 1 24 15.166a2.528 2.528 0 0 1-2.522 2.521h-6.312z" />
          </svg>
          Connect to Slack
        </a>

        <div className="mt-16 grid gap-8 text-left sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 p-6">
            <h3 className="font-semibold text-white">Passive Capture</h3>
            <p className="mt-2 text-sm text-zinc-400">
              Automatically detects engineering decisions from your Slack
              conversations. No manual logging required.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 p-6">
            <h3 className="font-semibold text-white">Natural Language Search</h3>
            <p className="mt-2 text-sm text-zinc-400">
              Ask questions in plain English. AI synthesizes answers from your
              team&apos;s decision history.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 p-6">
            <h3 className="font-semibold text-white">Full Context</h3>
            <p className="mt-2 text-sm text-zinc-400">
              Every decision links back to the original discussion, Jira
              tickets, and GitHub PRs.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
