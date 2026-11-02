-- krusgraph-sales — Row Level Security
-- Körs efter schema.sql. Regeln (README, Roller):
--   admin     allt
--   reviewer  läser alla affärer, förslag, påståenden, problemkort; godkänner; skriver inte i affärer
--   seller    hela registret av företag/kontakter; affärer bara som medlem i deal_members
--   partner   bara uttryckligen tilldelade affärer (deal_members) och företag/kontakter som hör till dem
--             eller som hen själv registrerat
--   anon      ingenting
-- Negativa tester: tests/rls_negative.sql.

-- ---------------------------------------------------------------- lås allt
do $$
declare t text;
begin
  foreach t in array array['app_settings', 'profiles', 'role_invitations', 'organisations', 'contacts', 'deals',
                           'deal_members', 'activities', 'claims', 'trust_answers', 'problem_cards',
                           'problem_card_claims', 'problems', 'templates', 'proposals', 'proposal_claims',
                           'proposal_links', 'audit_log']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
  end loop;
end $$;

-- ---------------------------------------------------------------- app_settings
create policy settings_read on public.app_settings for select to authenticated using (app.is_active_user());
create policy settings_admin on public.app_settings for all to authenticated using (app.is_admin()) with check (app.is_admin());

-- ---------------------------------------------------------------- profiles
-- Alla aktiva ser namn och roll på andra (för tilldelning och "ägare"); bara admin ändrar roll och aktivering.
create policy profiles_read on public.profiles for select to authenticated
  using (app.is_active_user() or id = auth.uid());
create policy profiles_update_self on public.profiles for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid()
              and role = (select p.role from public.profiles p where p.id = auth.uid())
              and active = (select p.active from public.profiles p where p.id = auth.uid()));
create policy profiles_admin on public.profiles for all to authenticated using (app.is_admin()) with check (app.is_admin());

-- ---------------------------------------------------------------- role_invitations
create policy invitations_admin on public.role_invitations for all to authenticated using (app.is_admin()) with check (app.is_admin());

-- ---------------------------------------------------------------- organisations
create policy organisations_read on public.organisations for select to authenticated
  using (app.can_read_organisation(id));
create policy organisations_insert on public.organisations for insert to authenticated
  with check (app.current_user_role() in ('admin', 'seller', 'partner') and created_by = auth.uid());
create policy organisations_update on public.organisations for update to authenticated
  using (app.can_write_organisation(id)) with check (app.can_write_organisation(id));
create policy organisations_delete on public.organisations for delete to authenticated using (app.is_admin());

-- ---------------------------------------------------------------- contacts (personuppgifter)
create policy contacts_read on public.contacts for select to authenticated
  using (app.can_read_organisation(organisation_id));
create policy contacts_insert on public.contacts for insert to authenticated
  with check (app.can_write_organisation(organisation_id) and created_by = auth.uid());
create policy contacts_update on public.contacts for update to authenticated
  using (app.can_write_organisation(organisation_id)) with check (app.can_write_organisation(organisation_id));
create policy contacts_delete on public.contacts for delete to authenticated using (app.is_admin());  -- gallring: admin

-- ---------------------------------------------------------------- deals
create policy deals_read on public.deals for select to authenticated using (app.can_read_deal(id));
create policy deals_insert on public.deals for insert to authenticated
  with check (app.current_user_role() in ('admin', 'seller', 'partner')
              and created_by = auth.uid()
              and app.can_read_organisation(organisation_id)
              and (owner_id = auth.uid() or app.is_admin()));
create policy deals_update on public.deals for update to authenticated
  using (app.can_write_deal(id)) with check (app.can_write_deal(id));
create policy deals_delete on public.deals for delete to authenticated using (app.is_admin());

-- ---------------------------------------------------------------- deal_members
-- Läsa: den som ser affären. Tilldela: admin, eller en seller som själv är medlem (kan ta in en partner eller kollega).
-- En partner kan inte tilldela någon.
create policy members_read on public.deal_members for select to authenticated using (app.can_read_deal(deal_id));
create policy members_insert on public.deal_members for insert to authenticated
  with check (app.is_admin()
              or (app.current_user_role() = 'seller' and app.can_write_deal(deal_id) and assigned_by = auth.uid()));
create policy members_delete on public.deal_members for delete to authenticated
  using (app.is_admin() or (app.current_user_role() = 'seller' and app.can_write_deal(deal_id) and user_id <> auth.uid()));

-- ---------------------------------------------------------------- activities
create policy activities_read on public.activities for select to authenticated
  using ((deal_id is not null and app.can_read_deal(deal_id)) or (deal_id is null and app.can_read_organisation(organisation_id)));
create policy activities_insert on public.activities for insert to authenticated
  with check (created_by = auth.uid()
              and ((deal_id is not null and app.can_write_deal(deal_id)) or (deal_id is null and app.can_write_organisation(organisation_id))));
create policy activities_update on public.activities for update to authenticated
  using (app.is_admin() or created_by = auth.uid()) with check (app.is_admin() or created_by = auth.uid());
create policy activities_delete on public.activities for delete to authenticated using (app.is_admin() or created_by = auth.uid());

-- ---------------------------------------------------------------- problems
create policy problems_read on public.problems for select to authenticated
  using ((deal_id is not null and app.can_read_deal(deal_id)) or (deal_id is null and app.can_read_organisation(organisation_id)));
create policy problems_insert on public.problems for insert to authenticated
  with check (created_by = auth.uid()
              and ((deal_id is not null and app.can_write_deal(deal_id)) or (deal_id is null and app.can_write_organisation(organisation_id))));
create policy problems_update on public.problems for update to authenticated
  using (app.is_admin() or (deal_id is not null and app.can_write_deal(deal_id)) or created_by = auth.uid())
  with check (app.is_admin() or (deal_id is not null and app.can_write_deal(deal_id)) or created_by = auth.uid());
create policy problems_delete on public.problems for delete to authenticated using (app.is_admin() or created_by = auth.uid());

-- ---------------------------------------------------------------- claims, trust_answers, problem_cards, templates
-- Läsa: seller/partner bara approved och imported; reviewer/admin allt (även draft, withdrawn).
-- Föreslå (insert som draft): staff. Ändra text/status: reviewer/admin (status-triggern i schema.sql skyddar
-- dessutom approved/withdrawn). Partner läser bara.
create policy claims_read on public.claims for select to authenticated
  using (app.is_reviewer() or (app.is_active_user() and status in ('approved', 'imported')));
create policy claims_propose on public.claims for insert to authenticated
  with check (app.is_staff() and status = 'draft' and owner_id = auth.uid());
create policy claims_review on public.claims for update to authenticated using (app.is_reviewer()) with check (app.is_reviewer());
create policy claims_delete on public.claims for delete to authenticated using (app.is_admin());

create policy trust_read on public.trust_answers for select to authenticated
  using (app.is_reviewer() or (app.is_active_user() and status in ('approved', 'imported')));
create policy trust_propose on public.trust_answers for insert to authenticated
  with check (app.is_staff() and status = 'draft' and owner_id = auth.uid());
create policy trust_review on public.trust_answers for update to authenticated using (app.is_reviewer()) with check (app.is_reviewer());
create policy trust_delete on public.trust_answers for delete to authenticated using (app.is_admin());

create policy cards_read on public.problem_cards for select to authenticated
  using (app.is_reviewer() or (app.is_active_user() and status in ('approved', 'imported')));
create policy cards_propose on public.problem_cards for insert to authenticated
  with check (app.is_staff() and status = 'draft' and owner_id = auth.uid());
create policy cards_review on public.problem_cards for update to authenticated using (app.is_reviewer()) with check (app.is_reviewer());
create policy cards_delete on public.problem_cards for delete to authenticated using (app.is_admin());

create policy card_claims_read on public.problem_card_claims for select to authenticated using (app.is_active_user());
create policy card_claims_write on public.problem_card_claims for all to authenticated using (app.is_reviewer()) with check (app.is_reviewer());

create policy templates_read on public.templates for select to authenticated
  using (app.is_reviewer() or (app.is_active_user() and status in ('approved', 'imported')));
create policy templates_admin on public.templates for all to authenticated using (app.is_admin()) with check (app.is_admin());

-- ---------------------------------------------------------------- proposals
-- Läsa: den som ser affären (reviewer ser alla). Skapa: den som får skriva i affären, från en godkänd/importerad mall.
-- Ändra: skaparen eller en medlem i affären, och reviewer/admin (för granskning). Triggern i schema.sql ser till att
-- bara reviewer/admin kan sätta approved, och att pris/löften kräver approved före sent.
create policy proposals_read on public.proposals for select to authenticated using (app.can_read_deal(deal_id));
create policy proposals_insert on public.proposals for insert to authenticated
  with check (created_by = auth.uid() and app.can_write_deal(deal_id)
              and exists (select 1 from public.templates t where t.id = template_id and t.status in ('approved', 'imported')));
create policy proposals_update on public.proposals for update to authenticated
  using (app.is_reviewer() or app.can_write_deal(deal_id))
  with check (app.is_reviewer() or app.can_write_deal(deal_id));
create policy proposals_delete on public.proposals for delete to authenticated
  using (app.is_admin() or (created_by = auth.uid() and status = 'draft'));

create policy proposal_claims_read on public.proposal_claims for select to authenticated
  using (exists (select 1 from public.proposals p where p.id = proposal_id and app.can_read_deal(p.deal_id)));
create policy proposal_claims_write on public.proposal_claims for all to authenticated
  using (exists (select 1 from public.proposals p where p.id = proposal_id and (app.is_reviewer() or app.can_write_deal(p.deal_id))))
  with check (exists (select 1 from public.proposals p where p.id = proposal_id and (app.is_reviewer() or app.can_write_deal(p.deal_id))
                        and exists (select 1 from public.claims c where c.id = claim_id and c.status in ('approved', 'imported'))));

-- ---------------------------------------------------------------- proposal_links
-- Skapa: en medlem i affären (seller) eller admin; partner skapar inga kundlänkar i v1 (beslut 2 och 6).
create policy links_read on public.proposal_links for select to authenticated
  using (exists (select 1 from public.proposals p where p.id = proposal_id and app.can_read_deal(p.deal_id)));
create policy links_insert on public.proposal_links for insert to authenticated
  with check (created_by = auth.uid() and app.current_user_role() in ('admin', 'seller')
              and exists (select 1 from public.proposals p where p.id = proposal_id and app.can_write_deal(p.deal_id)));
create policy links_revoke on public.proposal_links for update to authenticated
  using (app.is_admin() or created_by = auth.uid()) with check (app.is_admin() or created_by = auth.uid());

-- ---------------------------------------------------------------- audit_log
create policy audit_admin_read on public.audit_log for select to authenticated using (app.is_admin());
-- inga insert/update/delete-policyer: bara triggern (security definer) skriver.

-- ---------------------------------------------------------------- anon
-- Inga policyer för anon, och grants är borttagna i schema.sql: en oinloggad ser och gör ingenting.
-- En kundlänk (proposal_links) öppnas i v1 bara av en inloggad kontakt (requires_login = true, beslut 6);
-- kontakten är inte en profil i portalen utan får magic link till förslaget i en senare version.
