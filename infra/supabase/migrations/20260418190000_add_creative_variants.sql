-- Adds generated copy variants linked to creative assets.

create table if not exists creative_variants (
    id uuid primary key default gen_random_uuid(),
    creative_asset_id uuid not null references creative_assets(id) on delete cascade,
    variant_index integer not null,
    primary_text text not null,
    headline text not null,
    description text not null,
    call_to_action text,
    score numeric(5,4),
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    unique (creative_asset_id, variant_index)
);

create index if not exists idx_creative_variants_asset on creative_variants(creative_asset_id);

alter table creative_variants enable row level security;
