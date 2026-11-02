-- krusgraph-sales — schema (Supabase / Postgres)
-- Kör i Supabase SQL Editor i ordning: schema.sql → policies.sql → seed.sql → tests/rls_negative.sql.
-- Allt ligger i schemat public (Supabase exponerar det via PostgREST) plus hjälpfunktioner i schemat app.
-- Inga priser, provisionssatser eller svarstider här. Ingen kund-, Fabric- eller tokendata någonsin.

create extension if not exists pgcrypto with schema extensions;

create schema if not exists app;

-- ---------------------------------------------------------------- enum-typer
create type public.user_role as enum ('admin', 'seller', 'partner', 'reviewer');
create type public.deal_stage as enum ('New', 'Qualified', 'Demo', 'Pilot proposal', 'Decision', 'Won', 'Lost');
create type public.activity_kind as enum ('meeting', 'call', 'email', 'demo', 'note');
create type public.review_status as enum ('draft', 'imported', 'approved', 'withdrawn');
create type public.proposal_status as enum ('draft', 'needs_review', 'approved', 'sent', 'accepted', 'declined', 'withdrawn');
create type public.problem_status as enum ('open', 'matched', 'no_match');
create type public.lawful_basis as enum ('business_contact', 'consent', 'contract');
create type public.app_language as enum ('sv', 'en');

-- ---------------------------------------------------------------- inställningar
create table public.app_settings (
  key         text primary key,
  value       text,                       -- null = inte beslutat (docs/DECISIONS-FOR-GUSTAV.md)
  description text not null,
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- användare och roller
create table public.profiles (
  id               uuid primary key references auth.users (id) on delete cascade,
  email            text not null unique,
  full_name        text not null,
  role             public.user_role not null default 'partner',
  partner_company  text,                  -- partnerns bolag, bara för role = partner
  language         public.app_language not null default 'sv',
  active           boolean not null default false,  -- admin aktiverar; inaktiv ser ingenting
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint partner_company_only_for_partner check (role = 'partner' or partner_company is null)
);

-- Inbjudan: e-post → roll. Används av triggern på auth.users när personen loggar in första gången.
create table public.role_invitations (
  email            text primary key,
  role             public.user_role not null,
  partner_company  text,
  full_name        text,
  invited_by       uuid references public.profiles (id),
  created_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------- företag och kontakter
create table public.organisations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  org_number  text,                       -- organisationsnummer, valfritt
  country     text not null default 'SE',
  industry    text,
  website     text,
  size_band   text check (size_band in ('<50', '50-249', '250-999', '1000+')),
  notes       text,                       -- om affären, aldrig om personer, aldrig kundens data
  owner_id    uuid references public.profiles (id),
  created_by  uuid not null references public.profiles (id),
  archived_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index on public.organisations (lower(name));

-- Personuppgifter: namn, titel, e-post, telefon. Se README, Dataskydd.
create table public.contacts (
  id                 uuid primary key default gen_random_uuid(),
  organisation_id    uuid not null references public.organisations (id) on delete cascade,
  full_name          text not null,
  title              text,
  email              text,
  phone              text,
  lawful_basis       public.lawful_basis not null default 'business_contact',
  consent_note       text,                -- när/hur samtycke gavs, om lawful_basis = consent
  last_contact_at    timestamptz,
  retain_until       date,                -- sätts från app_settings.contact_retention_months (null tills beslut)
  erase_requested_at timestamptz,         -- begäran om radering från den registrerade
  created_by         uuid not null references public.profiles (id),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create index on public.contacts (organisation_id);

-- ---------------------------------------------------------------- affärer
create table public.deals (
  id                  uuid primary key default gen_random_uuid(),
  organisation_id     uuid not null references public.organisations (id) on delete restrict,
  primary_contact_id  uuid references public.contacts (id) on delete set null,
  title               text not null,
  stage               public.deal_stage not null default 'New',
  owner_id            uuid not null references public.profiles (id),
  expected_decision   date,
  next_step           text,
  next_step_due       date,
  lost_reason         text,
  won_at              timestamptz,
  lost_at             timestamptz,
  created_by          uuid not null references public.profiles (id),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index on public.deals (organisation_id);
create index on public.deals (owner_id);
create index on public.deals (stage);

-- Tilldelning. Synlighet för seller och partner går ENBART via den här tabellen (README, Roller).
create table public.deal_members (
  deal_id      uuid not null references public.deals (id) on delete cascade,
  user_id      uuid not null references public.profiles (id) on delete cascade,
  member_role  text not null default 'member' check (member_role in ('owner', 'member')),
  assigned_by  uuid references public.profiles (id),
  assigned_at  timestamptz not null default now(),
  primary key (deal_id, user_id)
);
create index on public.deal_members (user_id);

create table public.activities (
  id               uuid primary key default gen_random_uuid(),
  deal_id          uuid references public.deals (id) on delete cascade,
  organisation_id  uuid not null references public.organisations (id) on delete cascade,
  contact_id       uuid references public.contacts (id) on delete set null,
  kind             public.activity_kind not null,
  happened_at      timestamptz not null default now(),
  summary          text not null,         -- med ord; inga tabellnamn, siffror eller radvärden ur kundens data
  next_step        text,
  next_step_due    date,
  created_by       uuid not null references public.profiles (id),
  created_at       timestamptz not null default now()
);
create index on public.activities (deal_id);
create index on public.activities (organisation_id);

-- ---------------------------------------------------------------- påståenden (claims) och trust-svar
-- Registret för godkända påståenden om Krusgraph. Texten är ordagrann från källan; omfattning säger var den gäller.
create table public.claims (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null unique,
  text          text not null,            -- ordagrant
  scope         text not null,            -- omfattning: vad påståendet gäller och inte gäller
  source        text not null,            -- fil, avsnitt eller funktion i fabric-backend
  source_commit text,                     -- commit i fabric-backend
  source_date   date not null,            -- datumet påståendet avser
  captured_at   date not null default current_date,  -- när det hämtades
  language      public.app_language not null default 'en',
  translation_of uuid references public.claims (id),  -- en svensk rad pekar på sin engelska källa
  owner_id      uuid references public.profiles (id), -- ansvarig för att det fortfarande stämmer
  status        public.review_status not null default 'draft',
  review_note   text,
  reviewed_by   uuid references public.profiles (id),
  reviewed_at   timestamptz,
  valid_until   date,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index on public.claims (status);

create table public.trust_answers (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null unique,
  question_sv   text not null,
  question_en   text not null,
  answer        text not null,            -- ordagrant från krusgraph.com/it (engelska)
  answer_sv     text,                     -- svensk översättning, tom tills Gustav godkänt en
  source        text not null,
  source_commit text,
  source_date   date not null,
  owner_id      uuid references public.profiles (id),
  status        public.review_status not null default 'draft',
  review_note   text,
  reviewed_by   uuid references public.profiles (id),
  reviewed_at   timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------- problemkort och kundproblem
create table public.problem_cards (
  id                      uuid primary key default gen_random_uuid(),
  slug                    text not null unique,
  title_sv                text not null,
  title_en                text not null,
  symptom_sv              text not null,  -- hur kunden märker problemet
  symptom_en              text not null,
  how_krusgraph_helps_sv  text not null,  -- bara det som claims täcker
  how_krusgraph_helps_en  text not null,
  questions_sv            text[] not null default '{}',  -- frågor säljaren kan ställa
  questions_en            text[] not null default '{}',
  example_sv              text,           -- fiktivt exempel (syntetisk butik), aldrig en kund
  example_en              text,
  keywords                text[] not null default '{}',  -- för sökningen i mötesstödet
  owner_id                uuid references public.profiles (id),
  status                  public.review_status not null default 'draft',
  review_note             text,
  reviewed_by             uuid references public.profiles (id),
  reviewed_at             timestamptz,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create table public.problem_card_claims (
  problem_card_id uuid not null references public.problem_cards (id) on delete cascade,
  claim_id        uuid not null references public.claims (id) on delete cascade,
  primary key (problem_card_id, claim_id)
);

-- Kundens problem, som säljaren hörde det. Kopplas till ett problemkort när ett passar.
create table public.problems (
  id               uuid primary key default gen_random_uuid(),
  deal_id          uuid references public.deals (id) on delete cascade,
  organisation_id  uuid not null references public.organisations (id) on delete cascade,
  contact_id       uuid references public.contacts (id) on delete set null,
  title            text not null,
  description      text,                  -- med ord; inga tabellnamn eller siffror ur kundens data
  problem_card_id  uuid references public.problem_cards (id) on delete set null,
  status           public.problem_status not null default 'open',
  created_by       uuid not null references public.profiles (id),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index on public.problems (deal_id);

-- ---------------------------------------------------------------- mallar, förslag, länkar
create table public.templates (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,       -- data_review | bounded_pilot | continuation
  name_sv     text not null,
  name_en     text not null,
  body_sv     text not null,              -- Markdown med platshållare {{organisation}} {{contact}} {{seller}} {{date}} [PRIS]
  body_en     text not null,
  version     integer not null default 1,
  status      public.review_status not null default 'draft',
  reviewed_by uuid references public.profiles (id),
  reviewed_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table public.proposals (
  id               uuid primary key default gen_random_uuid(),
  deal_id          uuid not null references public.deals (id) on delete cascade,
  template_id      uuid not null references public.templates (id),
  template_version integer not null default 1,
  title            text not null,
  language         public.app_language not null default 'sv',
  body             text not null,         -- mallens text ifylld; en kopia, mallen kan ändras senare
  price            numeric(12, 2),        -- TOMT i v1 (docs/DECISIONS-FOR-GUSTAV.md, beslut 1)
  currency         text not null default 'SEK',
  price_note       text,
  promises         text,                  -- löften utanför claims; kräver granskning
  status           public.proposal_status not null default 'draft',
  review_note      text,
  created_by       uuid not null references public.profiles (id),
  reviewed_by      uuid references public.profiles (id),
  reviewed_at      timestamptz,
  sent_at          timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index on public.proposals (deal_id);
create index on public.proposals (status);

-- Vilka påståenden ett förslag använder (så ett tillbakadraget påstående kan spåras till förslagen).
create table public.proposal_claims (
  proposal_id uuid not null references public.proposals (id) on delete cascade,
  claim_id    uuid not null references public.claims (id),
  primary key (proposal_id, claim_id)
);

create table public.proposal_links (
  id             uuid primary key default gen_random_uuid(),
  proposal_id    uuid not null references public.proposals (id) on delete cascade,
  token          text not null unique default encode(extensions.gen_random_bytes(24), 'hex'),
  requires_login boolean not null default true,   -- beslut 6
  recipient_email text,                   -- kontaktens e-post när requires_login (magic link)
  expires_at     timestamptz not null,
  opened_count   integer not null default 0,
  last_opened_at timestamptz,
  revoked_at     timestamptz,
  created_by     uuid not null references public.profiles (id),
  created_at     timestamptz not null default now()
);
create index on public.proposal_links (proposal_id);

-- ---------------------------------------------------------------- audit_log
create table public.audit_log (
  id         bigint generated always as identity primary key,
  at         timestamptz not null default now(),
  actor_id   uuid,                        -- auth.uid(); null för systemåtgärder
  action     text not null check (action in ('insert', 'update', 'delete')),
  table_name text not null,
  row_id     text not null,
  old_row    jsonb,
  new_row    jsonb
);
create index on public.audit_log (table_name, row_id);
create index on public.audit_log (at);

-- ---------------------------------------------------------------- hjälpfunktioner (RLS)
-- security definer + fast search_path: läser profiles och deal_members utan att själva gå genom RLS.

create or replace function app.current_user_role()
returns public.user_role language sql stable security definer set search_path = public as $$
  select p.role from public.profiles p where p.id = auth.uid() and p.active
$$;

create or replace function app.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce(app.current_user_role() = 'admin', false)
$$;

create or replace function app.is_reviewer()
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce(app.current_user_role() in ('admin', 'reviewer'), false)
$$;

create or replace function app.is_staff()
returns boolean language sql stable security definer set search_path = public as $$
  -- anställda: admin, reviewer, seller. Partner är inte staff.
  select coalesce(app.current_user_role() in ('admin', 'reviewer', 'seller'), false)
$$;

create or replace function app.is_active_user()
returns boolean language sql stable security definer set search_path = public as $$
  select app.current_user_role() is not null
$$;

-- Läsa en affär: admin och reviewer allt; seller och partner bara affärer de är medlem i.
create or replace function app.can_read_deal(p_deal_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select app.is_reviewer()
      or exists (select 1 from public.deal_members m where m.deal_id = p_deal_id and m.user_id = auth.uid()
                   and app.is_active_user())
$$;

-- Skriva i en affär: admin allt; seller/partner bara som medlem. Reviewer skriver inte i affärer.
create or replace function app.can_write_deal(p_deal_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select app.is_admin()
      or exists (select 1 from public.deal_members m where m.deal_id = p_deal_id and m.user_id = auth.uid()
                   and app.current_user_role() in ('seller', 'partner'))
$$;

-- Se ett företag: staff ser hela registret; partner bara företag hen skapat eller har en tilldelad affär hos.
create or replace function app.can_read_organisation(p_org_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select app.is_staff()
      or (app.current_user_role() = 'partner' and (
            exists (select 1 from public.organisations o where o.id = p_org_id and o.created_by = auth.uid())
         or exists (select 1 from public.deals d join public.deal_members m on m.deal_id = d.id
                     where d.organisation_id = p_org_id and m.user_id = auth.uid())))
$$;

create or replace function app.can_write_organisation(p_org_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select app.is_admin()
      or (app.current_user_role() = 'seller')
      or (app.current_user_role() = 'partner' and app.can_read_organisation(p_org_id))
$$;

-- ---------------------------------------------------------------- triggers
create or replace function app.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['profiles', 'organisations', 'contacts', 'deals', 'claims', 'trust_answers',
                           'problem_cards', 'problems', 'templates', 'proposals', 'app_settings']
  loop
    execute format('create trigger set_updated_at before update on public.%I for each row execute function app.set_updated_at()', t);
  end loop;
end $$;

-- audit: vem ändrade vad. Kontakter loggas utan personuppgifterna (bara id och organisation).
create or replace function app.audit()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_old jsonb; v_new jsonb; v_id text;
begin
  if tg_table_name = 'contacts' then
    v_old := case when old is null then null else jsonb_build_object('id', old.id, 'organisation_id', old.organisation_id) end;
    v_new := case when new is null then null else jsonb_build_object('id', new.id, 'organisation_id', new.organisation_id) end;
  else
    v_old := to_jsonb(old); v_new := to_jsonb(new);
  end if;
  v_id := coalesce(v_new ->> 'id', v_old ->> 'id', coalesce(v_new ->> 'deal_id', v_old ->> 'deal_id') || ':' || coalesce(v_new ->> 'user_id', v_old ->> 'user_id'));
  insert into public.audit_log (actor_id, action, table_name, row_id, old_row, new_row)
  values (auth.uid(), lower(tg_op), tg_table_name, v_id, v_old, v_new);
  return coalesce(new, old);
end $$;

do $$
declare t text;
begin
  foreach t in array array['profiles', 'contacts', 'deals', 'deal_members', 'claims', 'trust_answers',
                           'problem_cards', 'templates', 'proposals', 'proposal_links']
  loop
    execute format('create trigger audit after insert or update or delete on public.%I for each row execute function app.audit()', t);
  end loop;
end $$;

-- Ny inloggning → profil, rollen från role_invitations; utan inbjudan partner + inaktiv.
create or replace function app.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare inv public.role_invitations%rowtype;
begin
  select * into inv from public.role_invitations where lower(email) = lower(new.email);
  insert into public.profiles (id, email, full_name, role, partner_company, active)
  values (new.id, new.email,
          coalesce(inv.full_name, new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1)),
          coalesce(inv.role, 'partner'),
          case when coalesce(inv.role, 'partner') = 'partner' then inv.partner_company else null end,
          inv.email is not null);
  -- Första admin (Gustav) blir ansvarig för registerrader utan ansvarig (seeden kan inte känna hans id).
  if inv.role = 'admin' then
    update public.claims set owner_id = new.id where owner_id is null;
    update public.trust_answers set owner_id = new.id where owner_id is null;
    update public.problem_cards set owner_id = new.id where owner_id is null;
    update public.role_invitations set invited_by = new.id where invited_by is null;
  end if;
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function app.handle_new_user();

-- Affär: skaparen blir medlem (owner). Ägaren måste vara staff eller skaparen själv.
create or replace function app.deal_after_insert()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.deal_members (deal_id, user_id, member_role, assigned_by)
  values (new.id, new.created_by, 'owner', new.created_by)
  on conflict do nothing;
  if new.owner_id <> new.created_by then
    insert into public.deal_members (deal_id, user_id, member_role, assigned_by)
    values (new.id, new.owner_id, 'owner', new.created_by)
    on conflict do nothing;
  end if;
  return new;
end $$;
create trigger deal_after_insert after insert on public.deals for each row execute function app.deal_after_insert();

-- Stadier: Won/Lost sätter datum; Lost kräver skäl.
create or replace function app.deal_stage_rules()
returns trigger language plpgsql as $$
begin
  if new.stage = 'Won' and new.won_at is null then new.won_at := now(); end if;
  if new.stage = 'Lost' then
    if new.lost_at is null then new.lost_at := now(); end if;
    if coalesce(new.lost_reason, '') = '' then raise exception 'Lost needs lost_reason'; end if;
  end if;
  if new.stage not in ('Won', 'Lost') then new.won_at := null; new.lost_at := null; end if;
  return new;
end $$;
create trigger deal_stage_rules before insert or update on public.deals for each row execute function app.deal_stage_rules();

-- Kontakt: retain_until från app_settings.contact_retention_months (bara när den är satt).
create or replace function app.contact_retention()
returns trigger language plpgsql security definer set search_path = public as $$
declare months integer;
begin
  select nullif(value, '')::integer into months from public.app_settings where key = 'contact_retention_months';
  if months is not null then
    new.retain_until := (coalesce(new.last_contact_at, now())::date + (months || ' months')::interval)::date;
  end if;
  return new;
end $$;
create trigger contact_retention before insert or update of last_contact_at on public.contacts
  for each row execute function app.contact_retention();

-- Gallringslista för Administration.
create or replace function public.contacts_due_for_erasure()
returns setof public.contacts language sql stable security invoker as $$
  select * from public.contacts
  where (retain_until is not null and retain_until < current_date) or erase_requested_at is not null
$$;

-- Granskning: bara admin/reviewer sätter status approved/withdrawn på claims, trust_answers, problem_cards, templates.
create or replace function app.review_rules()
returns trigger language plpgsql as $$
begin
  if new.status is distinct from old.status and new.status in ('approved', 'withdrawn') then
    if not app.is_reviewer() then raise exception 'only admin or reviewer may set status %', new.status; end if;
    new.reviewed_by := auth.uid(); new.reviewed_at := now();
  end if;
  if new.status = 'imported' and old.status <> 'imported' then
    raise exception 'imported is set only by the seed';
  end if;
  return new;
end $$;
do $$
declare t text;
begin
  foreach t in array array['claims', 'trust_answers', 'problem_cards', 'templates'] loop
    execute format('create trigger review_rules before update on public.%I for each row execute function app.review_rules()', t);
  end loop;
end $$;

-- Förslag: pris eller löften kräver granskning (Gustav) innan approved/sent. Bara admin/reviewer godkänner.
-- Utan pris och utan löften får skaparen skicka direkt (mallens godkända text).
create or replace function app.proposal_rules()
returns trigger language plpgsql as $$
declare needs boolean;
begin
  needs := new.price is not null or coalesce(new.promises, '') <> '';
  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    if new.status = 'approved' then
      if not app.is_reviewer() then raise exception 'only admin or reviewer may approve a proposal'; end if;
      new.reviewed_by := auth.uid(); new.reviewed_at := now();
    elsif new.status = 'sent' then
      if needs and old.status <> 'approved' then
        raise exception 'a proposal with a price or promises must be approved before it is sent';
      end if;
      new.sent_at := now();
    elsif new.status in ('accepted', 'declined') and old.status <> 'sent' then
      raise exception 'only a sent proposal can be accepted or declined';
    end if;
  end if;
  -- ändrat pris eller löften efter godkännande → tillbaka till needs_review
  if tg_op = 'UPDATE' and old.status in ('approved', 'sent') and new.status = old.status
     and (new.price is distinct from old.price or new.promises is distinct from old.promises) then
    new.status := 'needs_review'; new.reviewed_by := null; new.reviewed_at := null;
  end if;
  if tg_op = 'INSERT' and new.status not in ('draft', 'needs_review') then
    raise exception 'a new proposal starts as draft or needs_review';
  end if;
  if needs and new.status = 'draft' and tg_op = 'INSERT' then new.status := 'needs_review'; end if;
  return new;
end $$;
create trigger proposal_rules before insert or update on public.proposals for each row execute function app.proposal_rules();

-- Länk bara för godkänt eller skickat förslag; utgång från app_settings.
create or replace function app.proposal_link_rules()
returns trigger language plpgsql security definer set search_path = public as $$
declare st public.proposal_status; days integer;
begin
  select status into st from public.proposals where id = new.proposal_id;
  if st not in ('approved', 'sent', 'accepted') then
    raise exception 'a link needs an approved or sent proposal (status is %)', st;
  end if;
  if new.expires_at is null then
    select coalesce(nullif(value, '')::integer, 30) into days from public.app_settings where key = 'proposal_link_days';
    new.expires_at := now() + (coalesce(days, 30) || ' days')::interval;
  end if;
  return new;
end $$;
create trigger proposal_link_rules before insert on public.proposal_links for each row execute function app.proposal_link_rules();

-- ---------------------------------------------------------------- vyer
-- Min dag: nästa steg att göra, per affär den inloggade ser. RLS på underliggande tabeller gäller (security_invoker).
create view public.v_my_day with (security_invoker = true) as
select d.id as deal_id, d.title, d.stage, o.name as organisation, d.next_step, d.next_step_due,
       (select max(a.happened_at) from public.activities a where a.deal_id = d.id) as last_activity_at,
       (select count(*) from public.proposals p where p.deal_id = d.id and p.status = 'needs_review') as proposals_needing_review
from public.deals d
join public.organisations o on o.id = d.organisation_id
where d.stage not in ('Won', 'Lost');

-- Mötesstödets sökning: godkända (och importerade) problemkort med sina påståenden. Används av knappen
-- "Hur kan Krusgraph hjälpa?" — bara det som finns här får visas; inget annat svar än "otillräckligt underlag".
create view public.v_meeting_support with (security_invoker = true) as
select pc.id as problem_card_id, pc.slug, pc.title_sv, pc.title_en, pc.symptom_sv, pc.symptom_en,
       pc.how_krusgraph_helps_sv, pc.how_krusgraph_helps_en, pc.questions_sv, pc.questions_en,
       pc.example_sv, pc.example_en, pc.keywords, pc.status as card_status,
       c.id as claim_id, c.text as claim_text, c.scope as claim_scope, c.source as claim_source,
       c.source_date as claim_date, c.status as claim_status
from public.problem_cards pc
left join public.problem_card_claims pcc on pcc.problem_card_id = pc.id
left join public.claims c on c.id = pcc.claim_id and c.status in ('approved', 'imported')
where pc.status in ('approved', 'imported');

-- Textsökning för mötesstödet (ingen LLM): matchar ord mot problemkortens nyckelord, titlar och symptom.
create or replace function public.search_meeting_support(q text, lang public.app_language default 'sv')
returns table (problem_card_id uuid, slug text, title text, score integer)
language sql stable security invoker as $$
  with words as (select distinct lower(w) as w from regexp_split_to_table(coalesce(q, ''), '\s+') w where length(w) >= 3),
  scored as (
    select pc.id, pc.slug,
           case when lang = 'sv' then pc.title_sv else pc.title_en end as title,
           (select count(*) from words
             where exists (select 1 from unnest(pc.keywords) k where lower(k) like '%' || words.w || '%')
                or lower(pc.title_sv || ' ' || pc.title_en || ' ' || pc.symptom_sv || ' ' || pc.symptom_en) like '%' || words.w || '%')::integer as score
    from public.problem_cards pc
    where pc.status in ('approved', 'imported'))
  select id, slug, title, score from scored where score > 0 order by score desc, slug
$$;
-- Tomt resultat = gränssnittet svarar "otillräckligt underlag" / "insufficient basis". Ingen LLM, inget annat svar.

-- ---------------------------------------------------------------- rättigheter
-- Supabase ger normalt authenticated/anon rättigheter på nya tabeller via default privileges; här sägs det
-- uttryckligen, och anon får ingenting. RLS (policies.sql) avgör sedan raderna.
grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;
revoke insert, update, delete on public.audit_log from authenticated;   -- bara triggern skriver
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke all on all functions in schema public from anon;
grant usage on schema app to authenticated;
revoke all on all functions in schema app from public;
grant execute on all functions in schema app to authenticated;
