-- krusgraph-sales — negativa RLS-tester
-- Körs SIST (efter schema.sql, policies.sql, seed.sql) i Supabase SQL Editor, i en transaktion som rullas tillbaka.
-- Varje test skriver PASS i Messages; ett FAIL avbryter med felmeddelande. Testerna agerar som demoanvändarna i
-- seed.sql genom att sätta request.jwt.claims (det auth.uid() läser) och byta till rollen authenticated.
--
-- Vad som INTE ska gå:
--   partner: se affärer hen inte är tilldelad; se andra företags kontakter; ändra en otilldelad affär;
--            läsa påståenden i draft; tilldela någon; skapa kundlänk; läsa audit_log; ändra sin egen roll
--   seller:  se en kollegas affär hen inte är medlem i; godkänna ett påstående; godkänna ett förslag;
--            skicka ett förslag med löften utan granskning; läsa audit_log
--   reviewer: skriva i en affär
--   anon:    se någonting alls
--   inaktiv användare: se någonting alls

begin;

create or replace function pg_temp.become(u text) returns void language sql as $$
  select set_config('request.jwt.claims', json_build_object('sub', u, 'role', 'authenticated')::text, true);
$$;
create or replace function pg_temp.check(name text, ok boolean) returns void language plpgsql as $$
begin
  if ok then raise notice 'PASS %', name; else raise exception 'FAIL %', name; end if;
end $$;

-- fasta id:n från seed.sql
-- seller1  11111111-1111-1111-1111-000000000001   (affär 1 och 3)
-- seller2  11111111-1111-1111-1111-000000000002   (affär 2)
-- partner  11111111-1111-1111-1111-000000000003   (tilldelad affär 1, egen affär 4)
-- reviewer 11111111-1111-1111-1111-000000000004

-- ================================================================ PARTNER
select pg_temp.become('11111111-1111-1111-1111-000000000003');
set local role authenticated;

select pg_temp.check('P1 partner ser bara tilldelade affärer (1 och 4)',
  (select count(*) from public.deals) = 2
  and (select bool_and(id in ('44444444-4444-4444-4444-000000000001', '44444444-4444-4444-4444-000000000004')) from public.deals));

select pg_temp.check('P2 partner ser inte affär 2 (Testgrossisten)',
  not exists (select 1 from public.deals where id = '44444444-4444-4444-4444-000000000002'));

select pg_temp.check('P3 partner ser inte Testgrossistens kontakter',
  not exists (select 1 from public.contacts where organisation_id = '22222222-2222-2222-2222-000000000002'));

select pg_temp.check('P4 partner ser inte företag utan tilldelning (Testgrossisten, Demobruket)',
  (select count(*) from public.organisations) = 2);

update public.deals set title = 'hackad' where id = '44444444-4444-4444-4444-000000000002';
select pg_temp.check('P5 partner kan inte ändra otilldelad affär (0 rader)',
  not exists (select 1 from public.deals where title = 'hackad'));

do $$
begin
  insert into public.deal_members (deal_id, user_id, assigned_by)
  values ('44444444-4444-4444-4444-000000000002', '11111111-1111-1111-1111-000000000003', '11111111-1111-1111-1111-000000000003');
  perform pg_temp.check('P6 partner kan inte tilldela sig själv en affär', false);
exception when insufficient_privilege then
  perform pg_temp.check('P6 partner kan inte tilldela sig själv en affär', true);
end $$;

select pg_temp.check('P7 partner ser inga påståenden i draft (bara approved/imported)',
  not exists (select 1 from public.claims where status not in ('approved', 'imported')));

select pg_temp.check('P8 partner ser inga problemkort i draft (seedens kort är draft tills Gustav godkänt)',
  not exists (select 1 from public.problem_cards));

select pg_temp.check('P9 partner läser inte audit_log',
  (select count(*) from public.audit_log) = 0);

do $$
begin
  insert into public.proposal_links (proposal_id, created_by)
  values ('77777777-7777-7777-7777-000000000001', '11111111-1111-1111-1111-000000000003');
  perform pg_temp.check('P10 partner kan inte skapa kundlänk', false);
exception when others then
  perform pg_temp.check('P10 partner kan inte skapa kundlänk', true);
end $$;

do $$
begin
  update public.profiles set role = 'admin' where id = '11111111-1111-1111-1111-000000000003';
  perform pg_temp.check('P11 partner kan inte ändra sin egen roll', false);
exception when insufficient_privilege then
  perform pg_temp.check('P11 partner kan inte ändra sin egen roll', true);
end $$;

select pg_temp.check('P12 partner ser inte en annan säljares förslag (förslag 1 på affär 2)',
  not exists (select 1 from public.proposals where id = '77777777-7777-7777-7777-000000000001'));

reset role;

-- ================================================================ SELLER (seller1)
select pg_temp.become('11111111-1111-1111-1111-000000000001');
set local role authenticated;

select pg_temp.check('S1 säljare ser bara affärer hen är medlem i (1 och 3), inte kollegans (2) eller partnerns (4)',
  (select count(*) from public.deals) = 2
  and not exists (select 1 from public.deals where id in ('44444444-4444-4444-4444-000000000002', '44444444-4444-4444-4444-000000000004')));

select pg_temp.check('S2 säljare ser hela företagsregistret (4 företag)',
  (select count(*) from public.organisations) = 4);

update public.deals set stage = 'Won' where id = '44444444-4444-4444-4444-000000000002';
select pg_temp.check('S3 säljare kan inte ändra kollegans affär (0 rader)',
  (select stage from public.deals where id = '44444444-4444-4444-4444-000000000002') is null);

update public.claims set status = 'approved' where slug = 'live_run_summary';
select pg_temp.check('S4 säljare kan inte godkänna ett påstående (0 rader; status kvar imported)',
  (select status from public.claims where slug = 'live_run_summary') = 'imported');

do $$
begin
  insert into public.claims (slug, text, scope, source, source_date, owner_id, status)
  values ('test.approved_by_seller', 'x', 'x', 'x', current_date, '11111111-1111-1111-1111-000000000001', 'approved');
  perform pg_temp.check('S5 säljare kan inte lägga in ett påstående som approved (bara draft)', false);
exception when insufficient_privilege then
  perform pg_temp.check('S5 säljare kan inte lägga in ett påstående som approved (bara draft)', true);
end $$;

do $$
begin
  update public.proposals set status = 'approved' where id = '77777777-7777-7777-7777-000000000002';
  perform pg_temp.check('S6 säljare kan inte godkänna sitt förslag', false);
exception when others then
  perform pg_temp.check('S6 säljare kan inte godkänna sitt förslag', true);
end $$;

do $$
begin
  update public.proposals set status = 'sent' where id = '77777777-7777-7777-7777-000000000002';
  perform pg_temp.check('S7 ett förslag med löften kan inte skickas utan granskning', false);
exception when others then
  perform pg_temp.check('S7 ett förslag med löften kan inte skickas utan granskning', true);
end $$;

select pg_temp.check('S8 säljare läser inte audit_log',
  (select count(*) from public.audit_log) = 0);

do $$
begin
  insert into public.deal_members (deal_id, user_id, assigned_by)
  values ('44444444-4444-4444-4444-000000000002', '11111111-1111-1111-1111-000000000001', '11111111-1111-1111-1111-000000000001');
  perform pg_temp.check('S9 säljare kan inte tilldela sig själv kollegans affär', false);
exception when insufficient_privilege then
  perform pg_temp.check('S9 säljare kan inte tilldela sig själv kollegans affär', true);
end $$;

select pg_temp.check('S10 säljare ser inte mallar i draft (bara approved/imported)',
  not exists (select 1 from public.templates where status not in ('approved', 'imported')));

reset role;

-- ================================================================ REVIEWER
select pg_temp.become('11111111-1111-1111-1111-000000000004');
set local role authenticated;

select pg_temp.check('R1 granskare ser alla affärer (4)', (select count(*) from public.deals) = 4);

update public.deals set title = 'ändrad av granskare' where id = '44444444-4444-4444-4444-000000000001';
select pg_temp.check('R2 granskare skriver inte i affärer (0 rader)',
  not exists (select 1 from public.deals where title = 'ändrad av granskare'));

select pg_temp.check('R3 granskare läser inte audit_log', (select count(*) from public.audit_log) = 0);

-- positivt kontrolltest: granskaren FÅR godkänna ett förslag med löften (så att S6/S7 inte passerar av fel skäl)
update public.proposals set status = 'approved' where id = '77777777-7777-7777-7777-000000000002';
select pg_temp.check('R4 granskare kan godkänna ett förslag (kontroll)',
  (select status from public.proposals where id = '77777777-7777-7777-7777-000000000002') = 'approved');

reset role;

-- ================================================================ INAKTIV ANVÄNDARE (ny inloggning utan inbjudan)
insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data,
                        raw_user_meta_data, created_at, updated_at, confirmation_token, recovery_token, email_change_token_new, email_change)
values ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-000000000099', 'authenticated', 'authenticated',
        'nobody.demo@example.com', '', now(), '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', '');
select pg_temp.check('I0 oinbjuden blir partner och inaktiv',
  (select role = 'partner' and not active from public.profiles where id = '11111111-1111-1111-1111-000000000099'));

select pg_temp.become('11111111-1111-1111-1111-000000000099');
set local role authenticated;
select pg_temp.check('I1 inaktiv ser inga affärer', (select count(*) from public.deals) = 0);
select pg_temp.check('I2 inaktiv ser inga företag', (select count(*) from public.organisations) = 0);
select pg_temp.check('I3 inaktiv ser inga påståenden', (select count(*) from public.claims) = 0);
select pg_temp.check('I4 inaktiv ser bara sin egen profil', (select count(*) from public.profiles) = 1);
reset role;

-- ================================================================ ANON
select set_config('request.jwt.claims', '', true);
set local role anon;
do $$
begin
  perform count(*) from public.deals;
  perform pg_temp.check('A1 anon kan inte läsa deals', false);
exception when insufficient_privilege then
  perform pg_temp.check('A1 anon kan inte läsa deals', true);
end $$;
do $$
begin
  perform count(*) from public.claims;
  perform pg_temp.check('A2 anon kan inte läsa claims', false);
exception when insufficient_privilege then
  perform pg_temp.check('A2 anon kan inte läsa claims', true);
end $$;
do $$
begin
  perform app.is_admin();
  perform pg_temp.check('A3 anon kan inte anropa app-funktionerna', false);
exception when insufficient_privilege then
  perform pg_temp.check('A3 anon kan inte anropa app-funktionerna', true);
end $$;
reset role;

select 'ALLA NEGATIVA TESTER PASSERADE — allt rullas tillbaka' as result;

rollback;
