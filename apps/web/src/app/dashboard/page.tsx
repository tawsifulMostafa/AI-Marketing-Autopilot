"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  AIDecision,
  ApprovalRequest,
  DailyPlanResult,
  marketFlowApi
} from "@/lib/api";

const organizationId = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
const storeId = process.env.NEXT_PUBLIC_STORE_ID ?? "";

type LoadState = "idle" | "loading" | "ready" | "error";

function compactId(id?: string | null) {
  if (!id) return "not configured";
  return `${id.slice(0, 8)}...${id.slice(-6)}`;
}

function titleCase(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function stringify(value: unknown) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) {
    return "No extra details yet.";
  }

  return JSON.stringify(value, null, 2);
}

function payloadText(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export default function DashboardPage() {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [decisions, setDecisions] = useState<AIDecision[]>([]);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string>("");
  const [busyApprovalId, setBusyApprovalId] = useState<string | null>(null);
  const [planResult, setPlanResult] = useState<DailyPlanResult | null>(null);

  const canRunPlan = Boolean(organizationId && storeId);
  const pendingCount = approvals.filter((approval) => approval.status === "pending").length;

  const storeStatus = useMemo(() => {
    if (!storeId) return "Missing store id";
    if (apiOnline === true) return "Shopify simulation ready";
    if (apiOnline === false) return "API offline";
    return "Checking connection";
  }, [apiOnline]);

  async function loadDashboard() {
    setState("loading");
    setMessage("");

    try {
      const [healthResult, approvalsResult, decisionsResult] = await Promise.all([
        marketFlowApi.health(),
        marketFlowApi.approvals({
          organizationId: organizationId || undefined,
          status: "pending"
        }),
        marketFlowApi.decisions({
          organizationId: organizationId || undefined,
          storeId: storeId || undefined
        })
      ]);

      setApiOnline(Boolean(healthResult));
      setApprovals(approvalsResult.items);
      setDecisions(decisionsResult.items);
      setState("ready");
    } catch (error) {
      setApiOnline(false);
      setState("error");
      setMessage(error instanceof Error ? error.message : "Unable to load dashboard.");
    }
  }

  async function runDailyPlan() {
    if (!canRunPlan) {
      setMessage("Add NEXT_PUBLIC_ORGANIZATION_ID and NEXT_PUBLIC_STORE_ID before running the plan.");
      return;
    }

    setMessage("Running the agent loop. The tiny robot committee is convening...");

    try {
      const result = await marketFlowApi.runDailyPlan(storeId, {
        organization_id: organizationId,
        product_pages: 2,
        order_pages: 2,
        page_size: 50,
        lookback_days: 30
      });
      setPlanResult(result);
      setMessage(`Daily analysis complete: ${result.decisions_count} decision(s) created.`);
      await loadDashboard();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Daily analysis failed.");
    }
  }

  async function decide(approvalId: string, action: "approve" | "reject") {
    setBusyApprovalId(approvalId);
    setMessage("");

    try {
      if (action === "approve") {
        await marketFlowApi.approve(approvalId);
        setMessage("Approved. Simulation payload has been logged for Meta Ads.");
      } else {
        await marketFlowApi.reject(approvalId);
        setMessage("Rejected. The proposal stays safely parked.");
      }
      await loadDashboard();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} approval.`);
    } finally {
      setBusyApprovalId(null);
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  return (
    <main className="dashboard-grid min-h-screen overflow-hidden px-5 py-6 sm:px-8 lg:px-10">
      <section className="mx-auto flex max-w-7xl flex-col gap-7">
        <header className="rise-in relative overflow-hidden rounded-[2rem] border border-ink/10 bg-parchment/80 p-6 shadow-card backdrop-blur md:p-8">
          <div className="absolute -right-20 -top-20 h-56 w-56 rounded-full bg-ember/20 blur-3xl" />
          <div className="absolute bottom-0 right-24 h-28 w-28 rounded-full bg-brass/30 blur-2xl" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="mb-3 inline-flex rounded-full bg-ink px-4 py-2 text-xs font-bold uppercase tracking-[0.32em] text-parchment">
                MarketFlow AI Command Deck
              </p>
              <h1 className="font-display text-4xl leading-none tracking-[-0.04em] text-ink sm:text-6xl">
                Your autonomous CMO, waiting for launch clearance.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-ink/70">
                Review agent recommendations, inspect creative direction, and approve simulated
                ad execution from one cockpit.
              </p>
            </div>

            <button
              onClick={runDailyPlan}
              disabled={!canRunPlan || state === "loading"}
              className="group rounded-2xl bg-ember px-6 py-4 text-left font-bold text-white shadow-card transition hover:-translate-y-0.5 hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/30"
            >
              <span className="block text-xs uppercase tracking-[0.25em] text-white/70">
                Daily Plan
              </span>
              <span className="text-lg">Run Daily Analysis</span>
            </button>
          </div>
        </header>

        {message ? (
          <div className="rise-in rounded-2xl border border-ink/10 bg-white/70 px-5 py-4 text-sm text-ink shadow-card backdrop-blur">
            {message}
          </div>
        ) : null}

        <section className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="rise-in rounded-[1.75rem] border border-ink/10 bg-white/75 p-5 shadow-card backdrop-blur">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.25em] text-moss">
                  Store Status
                </p>
                <h2 className="mt-2 font-display text-3xl tracking-[-0.03em]">{storeStatus}</h2>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ${
                  apiOnline ? "bg-moss text-white" : "bg-ember/15 text-ember"
                }`}
              >
                {apiOnline ? "online" : "check"}
              </span>
            </div>

            <dl className="mt-6 grid gap-3 text-sm">
              <div className="rounded-2xl bg-parchment/80 p-4">
                <dt className="text-ink/50">API Base URL</dt>
                <dd className="mt-1 font-bold text-ink">{marketFlowApi.baseUrl}</dd>
              </div>
              <div className="rounded-2xl bg-parchment/80 p-4">
                <dt className="text-ink/50">Store ID</dt>
                <dd className="mt-1 font-bold text-ink">{compactId(storeId)}</dd>
              </div>
              <div className="rounded-2xl bg-parchment/80 p-4">
                <dt className="text-ink/50">Pending Approvals</dt>
                <dd className="mt-1 font-display text-4xl">{pendingCount}</dd>
              </div>
            </dl>
          </div>

          <div className="rise-in rounded-[1.75rem] border border-ink/10 bg-tide p-5 text-white shadow-card">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.25em] text-white/55">
                  Latest Agent Run
                </p>
                <h2 className="mt-2 font-display text-3xl tracking-[-0.03em]">
                  {planResult ? "Fresh plan generated" : "No run in this session yet"}
                </h2>
              </div>
              <button
                onClick={loadDashboard}
                className="rounded-full border border-white/20 px-4 py-2 text-sm font-bold text-white transition hover:bg-white hover:text-tide"
              >
                Refresh
              </button>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <Metric label="Products" value={planResult?.ingestion.products_fetched ?? "-"} />
              <Metric label="Orders" value={planResult?.ingestion.orders_fetched ?? "-"} />
              <Metric label="Decisions" value={planResult?.decisions_count ?? decisions.length} />
            </div>
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
          <Panel eyebrow="Human-in-the-loop" title="Pending Approvals">
            <div className="space-y-4">
              {approvals.length === 0 ? (
                <EmptyState text="No pending approvals. Run the daily analysis to generate proposals." />
              ) : (
                approvals.map((approval) => (
                  <article key={approval.id} className="rounded-3xl border border-ink/10 bg-white p-5">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.22em] text-ember">
                          {approval.decision?.action_type
                            ? titleCase(approval.decision.action_type)
                            : "Proposal"}
                        </p>
                        <h3 className="mt-2 font-display text-2xl tracking-[-0.02em]">
                          {approval.decision?.title ?? "Approval request"}
                        </h3>
                        <p className="mt-2 text-sm leading-6 text-ink/65">
                          {approval.requested_message}
                        </p>
                      </div>
                      <RiskPill risk={approval.decision?.risk_level ?? "medium"} />
                    </div>

                    <pre className="mt-4 max-h-36 overflow-auto rounded-2xl bg-ink p-4 text-xs leading-5 text-parchment">
                      {stringify(approval.decision?.reasoning)}
                    </pre>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <button
                        onClick={() => decide(approval.id, "approve")}
                        disabled={busyApprovalId === approval.id}
                        className="rounded-full bg-moss px-5 py-3 text-sm font-bold text-white transition hover:bg-ink disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => decide(approval.id, "reject")}
                        disabled={busyApprovalId === approval.id}
                        className="rounded-full border border-ink/15 px-5 py-3 text-sm font-bold text-ink transition hover:border-ember hover:text-ember disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </Panel>

          <Panel eyebrow="Strategist + Creative" title="AI Decisions">
            <div className="space-y-4">
              {decisions.length === 0 ? (
                <EmptyState text="No decisions yet. Once agents run, their reasoning and creative prompts appear here." />
              ) : (
                decisions.map((decision) => (
                  <article key={decision.id} className="rounded-3xl border border-ink/10 bg-white p-5">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.22em] text-tide">
                          {titleCase(decision.action_type)} · {titleCase(decision.status)}
                        </p>
                        <h3 className="mt-2 font-display text-2xl tracking-[-0.02em]">
                          {decision.title}
                        </h3>
                        <p className="mt-2 text-sm leading-6 text-ink/65">{decision.summary}</p>
                      </div>
                      <RiskPill risk={decision.risk_level} />
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <pre className="max-h-44 overflow-auto rounded-2xl bg-parchment p-4 text-xs leading-5 text-ink/75">
                        {stringify(decision.reasoning)}
                      </pre>
                      <CreativePreview decision={decision} />
                    </div>
                  </article>
                ))
              )}
            </div>
          </Panel>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-2xl bg-white/10 p-4">
      <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/50">{label}</p>
      <p className="mt-2 font-display text-4xl">{value}</p>
    </div>
  );
}

function Panel({
  eyebrow,
  title,
  children
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rise-in rounded-[1.75rem] border border-ink/10 bg-white/65 p-5 shadow-card backdrop-blur">
      <p className="text-xs font-bold uppercase tracking-[0.25em] text-moss">{eyebrow}</p>
      <h2 className="mt-2 font-display text-3xl tracking-[-0.03em]">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function RiskPill({ risk }: { risk: string }) {
  const className =
    risk === "high" || risk === "critical"
      ? "bg-ember/15 text-ember"
      : risk === "low"
        ? "bg-moss/15 text-moss"
        : "bg-brass/20 text-ink";

  return (
    <span className={`w-fit rounded-full px-3 py-1 text-xs font-bold uppercase ${className}`}>
      {risk} risk
    </span>
  );
}

function CreativePreview({ decision }: { decision: AIDecision }) {
  const proposal = decision.proposals.find((item) => item.payload);
  const payload = proposal?.payload ?? {};
  const imagePrompt = payloadText(payload, "image_prompt");
  const primaryText = payloadText(payload, "primary_text");
  const headline = payloadText(payload, "headline");
  const description = payloadText(payload, "description");

  return (
    <div className="rounded-2xl border border-dashed border-ink/20 bg-gradient-to-br from-brass/20 to-ember/10 p-4">
      <p className="text-xs font-bold uppercase tracking-[0.22em] text-ink/45">
        Creative Preview
      </p>
      <h4 className="mt-3 font-display text-xl">{headline ?? "Creative pending"}</h4>
      <p className="mt-2 text-sm leading-6 text-ink/70">
        {primaryText ?? description ?? "The creative agent will attach copy and image prompts here."}
      </p>
      {imagePrompt ? (
        <div className="mt-4 rounded-2xl bg-white/65 p-4 text-xs leading-5 text-ink/70">
          <span className="font-bold text-ink">Image prompt:</span> {imagePrompt}
        </div>
      ) : null}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-ink/20 bg-parchment/70 p-8 text-center text-sm leading-6 text-ink/60">
      {text}
    </div>
  );
}
