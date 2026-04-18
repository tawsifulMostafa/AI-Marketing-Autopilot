export type UUID = string;

export type ApiList<T> = {
  items: T[];
};

export type ActionProposal = {
  id: UUID;
  status: string;
  target_type: string;
  target_id: UUID | null;
  payload: Record<string, unknown>;
  requires_approval: boolean;
  created_at?: string;
};

export type AIDecision = {
  id: UUID;
  organization_id: UUID;
  store_id: UUID | null;
  status: string;
  title: string;
  summary: string;
  action_type: string;
  risk_level: string;
  confidence: string | number;
  expected_impact: Record<string, unknown>;
  reasoning: Record<string, unknown>;
  model_name?: string | null;
  prompt_version?: string | null;
  created_at: string;
  proposals: ActionProposal[];
};

export type ApprovalRequest = {
  id: UUID;
  organization_id: UUID;
  status: string;
  requested_message: string;
  approver_user_id?: UUID | null;
  approver_note?: string | null;
  decided_at?: string | null;
  expires_at?: string | null;
  created_at: string;
  proposal: ActionProposal | null;
  decision: Omit<AIDecision, "proposals"> | null;
};

export type DailyPlanPayload = {
  organization_id: UUID;
  product_pages?: number;
  order_pages?: number;
  page_size?: number;
  lookback_days?: number;
};

export type DailyPlanResult = {
  ingestion: {
    store_id: UUID;
    products_fetched: number;
    orders_fetched: number;
    observations: unknown[];
  };
  decisions_count: number;
  creative_assets: unknown[];
  approval_requests: unknown[];
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function searchParams(params: Record<string, string | number | undefined | null>) {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }

  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export const marketFlowApi = {
  baseUrl: API_BASE_URL,

  health() {
    return request<{
      ok: boolean;
      app: string;
      version: string;
      environment: string;
      database_configured: boolean;
    }>("/health");
  },

  approvals(params?: {
    organizationId?: UUID;
    status?: string | null;
    limit?: number;
  }) {
    return request<ApiList<ApprovalRequest>>(
      `/v1/approvals${searchParams({
        organization_id: params?.organizationId,
        status_filter: params?.status ?? "pending",
        limit: params?.limit ?? 25
      })}`
    );
  },

  decisions(params?: { organizationId?: UUID; storeId?: UUID; limit?: number }) {
    return request<ApiList<AIDecision>>(
      `/v1/decisions${searchParams({
        organization_id: params?.organizationId,
        store_id: params?.storeId,
        limit: params?.limit ?? 25
      })}`
    );
  },

  runDailyPlan(storeId: UUID, payload: DailyPlanPayload) {
    return request<DailyPlanResult>(`/v1/stores/${storeId}/daily-plan`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  approve(approvalRequestId: UUID, note?: string) {
    return request(`/v1/approvals/${approvalRequestId}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? "Approved from MarketFlow dashboard." })
    });
  },

  reject(approvalRequestId: UUID, note?: string) {
    return request(`/v1/approvals/${approvalRequestId}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? "Rejected from MarketFlow dashboard." })
    });
  }
};
