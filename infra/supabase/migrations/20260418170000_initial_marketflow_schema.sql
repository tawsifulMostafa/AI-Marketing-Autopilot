-- MarketFlow AI initial Supabase/PostgreSQL schema.
-- This migration creates the MVP foundation for multi-tenant auth, stores,
-- campaigns, AI decisions, approval gates, and execution audit logs.

create extension if not exists pgcrypto;
create extension if not exists citext;

do $$ begin
    create type user_role as enum ('owner', 'admin', 'marketer', 'viewer');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type store_platform as enum ('shopify', 'woocommerce');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type store_status as enum ('connecting', 'active', 'needs_attention', 'disabled');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type product_status as enum ('active', 'draft', 'archived');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type product_performance_label as enum ('winning', 'stable', 'underperforming', 'new', 'at_risk');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type ad_platform as enum ('meta', 'google', 'tiktok', 'email');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type campaign_status as enum ('draft', 'pending_approval', 'scheduled', 'active', 'paused', 'completed', 'failed');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type decision_status as enum ('draft', 'pending_approval', 'approved', 'rejected', 'executed', 'failed', 'expired');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type approval_status as enum ('pending', 'approved', 'rejected', 'expired', 'cancelled');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type action_type as enum ('launch_campaign', 'pause_campaign', 'scale_budget', 'reduce_budget', 'create_discount', 'generate_creative', 'update_targeting');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type risk_level as enum ('low', 'medium', 'high', 'critical');
exception when duplicate_object then null;
end $$;

do $$ begin
    create type agent_type as enum ('observer', 'strategist', 'creative', 'execution_optimizer');
exception when duplicate_object then null;
end $$;

create table if not exists organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    billing_email text,
    default_currency char(3) not null default 'USD',
    timezone text not null default 'UTC',
    plan_key text not null default 'starter',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    auth_user_id uuid not null unique,
    email citext not null unique,
    full_name text,
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists organization_members (
    organization_id uuid not null references organizations(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    role user_role not null default 'viewer',
    created_at timestamptz not null default now(),
    primary key (organization_id, user_id)
);

create table if not exists stores (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    platform store_platform not null,
    status store_status not null default 'connecting',
    name text not null,
    domain text not null,
    external_store_id text,
    currency char(3) not null default 'USD',
    timezone text not null default 'UTC',
    access_token_encrypted text,
    refresh_token_encrypted text,
    token_expires_at timestamptz,
    last_synced_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, platform, domain)
);

create table if not exists customers (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references stores(id) on delete cascade,
    external_customer_id text,
    email_hash text,
    first_seen_at timestamptz,
    last_seen_at timestamptz,
    total_spend numeric(14,2) not null default 0,
    order_count integer not null default 0,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (store_id, external_customer_id)
);

create table if not exists products (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references stores(id) on delete cascade,
    external_product_id text not null,
    title text not null,
    handle text,
    description text,
    product_type text,
    vendor text,
    status product_status not null default 'active',
    image_url text,
    price numeric(14,2),
    cost numeric(14,2),
    inventory_quantity integer,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (store_id, external_product_id)
);

create table if not exists product_variants (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references products(id) on delete cascade,
    external_variant_id text not null,
    sku text,
    title text,
    price numeric(14,2),
    cost numeric(14,2),
    inventory_quantity integer,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (product_id, external_variant_id)
);

create table if not exists orders (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references stores(id) on delete cascade,
    customer_id uuid references customers(id) on delete set null,
    external_order_id text not null,
    order_number text,
    currency char(3) not null,
    subtotal_price numeric(14,2) not null default 0,
    total_price numeric(14,2) not null default 0,
    total_tax numeric(14,2) not null default 0,
    total_discount numeric(14,2) not null default 0,
    financial_status text,
    fulfillment_status text,
    ordered_at timestamptz not null,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (store_id, external_order_id)
);

create table if not exists order_items (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null references orders(id) on delete cascade,
    product_id uuid references products(id) on delete set null,
    product_variant_id uuid references product_variants(id) on delete set null,
    external_line_item_id text,
    quantity integer not null,
    unit_price numeric(14,2) not null,
    total_discount numeric(14,2) not null default 0,
    created_at timestamptz not null default now()
);

create table if not exists ad_accounts (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    platform ad_platform not null,
    external_account_id text not null,
    name text not null,
    currency char(3) not null default 'USD',
    access_token_encrypted text,
    refresh_token_encrypted text,
    token_expires_at timestamptz,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, platform, external_account_id)
);

create table if not exists campaigns (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    store_id uuid not null references stores(id) on delete cascade,
    ad_account_id uuid references ad_accounts(id) on delete set null,
    platform ad_platform not null,
    external_campaign_id text,
    name text not null,
    objective text not null,
    status campaign_status not null default 'draft',
    daily_budget numeric(14,2),
    lifetime_budget numeric(14,2),
    start_at timestamptz,
    end_at timestamptz,
    metadata jsonb not null default '{}',
    created_by_decision_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists ad_groups (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references campaigns(id) on delete cascade,
    external_ad_group_id text,
    name text not null,
    targeting jsonb not null default '{}',
    daily_budget numeric(14,2),
    status campaign_status not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists creative_assets (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    store_id uuid references stores(id) on delete cascade,
    product_id uuid references products(id) on delete set null,
    asset_type text not null,
    provider text,
    storage_path text,
    public_url text,
    prompt text,
    generation_metadata jsonb not null default '{}',
    created_at timestamptz not null default now()
);

create table if not exists ads (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references campaigns(id) on delete cascade,
    ad_group_id uuid references ad_groups(id) on delete cascade,
    creative_asset_id uuid references creative_assets(id) on delete set null,
    external_ad_id text,
    name text not null,
    primary_text text,
    headline text,
    description text,
    call_to_action text,
    destination_url text,
    status campaign_status not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists store_metric_snapshots (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references stores(id) on delete cascade,
    snapshot_date date not null,
    revenue numeric(14,2) not null default 0,
    orders_count integer not null default 0,
    conversion_rate numeric(8,4),
    average_order_value numeric(14,2),
    total_ad_spend numeric(14,2) not null default 0,
    blended_roas numeric(10,4),
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    unique (store_id, snapshot_date)
);

create table if not exists product_insights (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references products(id) on delete cascade,
    snapshot_date date not null,
    performance_label product_performance_label not null,
    units_sold integer not null default 0,
    revenue numeric(14,2) not null default 0,
    gross_margin numeric(14,2),
    inventory_velocity numeric(10,4),
    stockout_risk numeric(5,4),
    attributed_ad_spend numeric(14,2) not null default 0,
    attributed_roas numeric(10,4),
    confidence numeric(5,4) not null default 0,
    explanation text,
    created_at timestamptz not null default now(),
    unique (product_id, snapshot_date)
);

create table if not exists campaign_metrics (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references campaigns(id) on delete cascade,
    metric_date date not null,
    impressions integer not null default 0,
    clicks integer not null default 0,
    spend numeric(14,2) not null default 0,
    conversions integer not null default 0,
    revenue numeric(14,2) not null default 0,
    roas numeric(10,4),
    ctr numeric(10,4),
    cpc numeric(14,4),
    cpa numeric(14,4),
    created_at timestamptz not null default now(),
    unique (campaign_id, metric_date)
);

create table if not exists agent_runs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    store_id uuid references stores(id) on delete cascade,
    agent agent_type not null,
    status text not null default 'running',
    input_ref jsonb not null default '{}',
    output_ref jsonb not null default '{}',
    error_message text,
    trace_id text,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists ai_decisions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    store_id uuid references stores(id) on delete cascade,
    agent_run_id uuid references agent_runs(id) on delete set null,
    status decision_status not null default 'draft',
    title text not null,
    summary text not null,
    action_type action_type not null,
    risk_level risk_level not null default 'medium',
    confidence numeric(5,4) not null default 0,
    expected_impact jsonb not null default '{}',
    reasoning jsonb not null default '{}',
    model_name text,
    prompt_version text,
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

do $$ begin
    alter table campaigns
        add constraint campaigns_created_by_decision_id_fkey
        foreign key (created_by_decision_id) references ai_decisions(id) on delete set null;
exception when duplicate_object then null;
end $$;

create table if not exists action_proposals (
    id uuid primary key default gen_random_uuid(),
    ai_decision_id uuid not null references ai_decisions(id) on delete cascade,
    target_type text not null,
    target_id uuid,
    payload jsonb not null,
    requires_approval boolean not null default true,
    status decision_status not null default 'pending_approval',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists approval_requests (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    ai_decision_id uuid references ai_decisions(id) on delete cascade,
    action_proposal_id uuid references action_proposals(id) on delete cascade,
    requested_by_agent_run_id uuid references agent_runs(id) on delete set null,
    status approval_status not null default 'pending',
    requested_message text not null,
    approver_user_id uuid references users(id) on delete set null,
    approver_note text,
    decided_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists execution_logs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    action_proposal_id uuid references action_proposals(id) on delete set null,
    platform ad_platform,
    operation text not null,
    request_payload jsonb not null default '{}',
    response_payload jsonb not null default '{}',
    external_object_id text,
    status text not null,
    error_message text,
    created_at timestamptz not null default now()
);

create table if not exists automation_policies (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    store_id uuid references stores(id) on delete cascade,
    name text not null,
    is_enabled boolean not null default false,
    max_daily_budget_increase_pct numeric(6,4) not null default 0.1000,
    max_daily_budget_amount numeric(14,2),
    min_roas_to_scale numeric(10,4),
    max_cpa_to_keep_active numeric(14,4),
    allow_auto_pause boolean not null default true,
    allow_auto_scale boolean not null default false,
    rules jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists audit_events (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid references organizations(id) on delete cascade,
    user_id uuid references users(id) on delete set null,
    event_type text not null,
    entity_type text,
    entity_id uuid,
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now()
);

create index if not exists idx_organization_members_user on organization_members(user_id);
create index if not exists idx_stores_org on stores(organization_id);
create index if not exists idx_products_store on products(store_id);
create index if not exists idx_orders_store_ordered_at on orders(store_id, ordered_at desc);
create index if not exists idx_ad_accounts_org on ad_accounts(organization_id);
create index if not exists idx_campaigns_org_status on campaigns(organization_id, status);
create index if not exists idx_campaign_metrics_date on campaign_metrics(metric_date desc);
create index if not exists idx_agent_runs_org_started_at on agent_runs(organization_id, started_at desc);
create index if not exists idx_ai_decisions_org_status on ai_decisions(organization_id, status);
create index if not exists idx_action_proposals_decision on action_proposals(ai_decision_id);
create index if not exists idx_approval_requests_org_status on approval_requests(organization_id, status);
create index if not exists idx_execution_logs_org_created_at on execution_logs(organization_id, created_at desc);
create index if not exists idx_audit_events_org_created_at on audit_events(organization_id, created_at desc);

alter table organizations enable row level security;
alter table users enable row level security;
alter table organization_members enable row level security;
alter table stores enable row level security;
alter table customers enable row level security;
alter table products enable row level security;
alter table product_variants enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;
alter table ad_accounts enable row level security;
alter table campaigns enable row level security;
alter table ad_groups enable row level security;
alter table creative_assets enable row level security;
alter table ads enable row level security;
alter table store_metric_snapshots enable row level security;
alter table product_insights enable row level security;
alter table campaign_metrics enable row level security;
alter table agent_runs enable row level security;
alter table ai_decisions enable row level security;
alter table action_proposals enable row level security;
alter table approval_requests enable row level security;
alter table execution_logs enable row level security;
alter table automation_policies enable row level security;
alter table audit_events enable row level security;
