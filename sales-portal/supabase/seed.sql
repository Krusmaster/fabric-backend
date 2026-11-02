-- krusgraph-sales — seed
-- Körs efter schema.sql och policies.sql, som postgres (bypass RLS) i Supabase SQL Editor.
-- ALLT här är fiktivt: företag, kontakter, affärer och demoanvändare. Inga riktiga personer, inga riktiga kunder.
-- Undantag: Gustav Kruse (admin) som inbjudan, och påståendena/trust-svaren, som är ordagranna citat ur fabric-backend
-- (commit 7799ef7, hämtade 2026-11-01) med status 'imported' tills Gustav bekräftat dem i Administration.
-- Genererad av ett skript som verifierar varje citat mot källan; redigera källan, inte citaten.

-- ---------------------------------------------------------------- inställningar (tomma = beslut för Gustav)
insert into public.app_settings (key, value, description) values
  ('contact_retention_months', null, 'Månader efter senaste kontakt innan en kontakt gallras. Tom tills Gustav beslutat (docs/DECISIONS-FOR-GUSTAV.md, 4). Tom = inget retain_until sätts.'),
  ('proposal_link_days', '30', 'Hur många dagar en förslagslänk gäller från att den skapas (beslut 6).'),
  ('default_language', 'sv', 'Standardspråk för nya användare (beslut 5).'),
  ('claims_source_commit', '7799ef7', 'Commit i Krusmaster/fabric-backend som påståendena och trust-svaren hämtades från.'),
  ('claims_captured_at', '2026-11-01', 'Datum då påståendena hämtades.');

-- ---------------------------------------------------------------- inbjudningar (e-post → roll)
insert into public.role_invitations (email, role, full_name) values
  ('fagerstagustav@gmail.com', 'admin', 'Gustav Kruse');

-- ---------------------------------------------------------------- demoanvändare (FIKTIVA; kan inte logga in: tomt lösenord)
-- Radera före skarp drift:  delete from auth.users where email like '%@example.com';
-- Fasta id:n så att tests/rls_negative.sql kan agera som dem.
insert into public.role_invitations (email, role, full_name, partner_company) values
  ('seller.demo@example.com',  'seller',   'Säljare Demo (fiktiv)',      null),
  ('seller2.demo@example.com', 'seller',   'Säljare Två Demo (fiktiv)',  null),
  ('partner.demo@example.com', 'partner',  'Partner Demo (fiktiv)',      'Fiktiva Partnerbyrån AB'),
  ('reviewer.demo@example.com','reviewer', 'Granskare Demo (fiktiv)',    null);

insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data,
                        raw_user_meta_data, created_at, updated_at, confirmation_token, recovery_token, email_change_token_new, email_change)
values
  ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-000000000001', 'authenticated', 'authenticated', 'seller.demo@example.com',  '', now(), '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', ''),
  ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-000000000002', 'authenticated', 'authenticated', 'seller2.demo@example.com', '', now(), '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', ''),
  ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-000000000003', 'authenticated', 'authenticated', 'partner.demo@example.com', '', now(), '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', ''),
  ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-000000000004', 'authenticated', 'authenticated', 'reviewer.demo@example.com','', now(), '{"provider":"email","providers":["email"]}', '{}', now(), now(), '', '', '', '');
-- triggern app.handle_new_user() har nu skapat profiles för de fyra, aktiva, med rollerna ovan.

-- ---------------------------------------------------------------- fiktiva företag
insert into public.organisations (id, name, country, industry, size_band, notes, owner_id, created_by) values
  ('22222222-2222-2222-2222-000000000001', 'Exempelbolaget Nord AB (fiktivt)', 'SE', 'Grossist', '50-249',
   'Fiktivt bolag för demo. Har Fabric-kapacitet på prov; orderdata i en lakehouse.', '11111111-1111-1111-1111-000000000001', '11111111-1111-1111-1111-000000000001'),
  ('22222222-2222-2222-2222-000000000002', 'Testgrossisten Syd AB (fiktivt)', 'SE', 'Handel', '250-999',
   'Fiktivt bolag för demo. Vill ha en Power BI-modell över försäljning.', '11111111-1111-1111-1111-000000000002', '11111111-1111-1111-1111-000000000002'),
  ('22222222-2222-2222-2222-000000000003', 'Demobruket i Fjällstad AB (fiktivt)', 'SE', 'Tillverkning', '50-249',
   'Fiktivt bolag för demo. Första samtal bokat.', '11111111-1111-1111-1111-000000000001', '11111111-1111-1111-1111-000000000001'),
  ('22222222-2222-2222-2222-000000000004', 'Partnerprospekt Väst AB (fiktivt)', 'SE', 'Tjänster', '<50',
   'Fiktivt bolag för demo, registrerat av partnern.', '11111111-1111-1111-1111-000000000003', '11111111-1111-1111-1111-000000000003');

-- ---------------------------------------------------------------- fiktiva kontakter (personuppgifter i skarp drift; här påhittade roller)
insert into public.contacts (id, organisation_id, full_name, title, email, lawful_basis, last_contact_at, created_by) values
  ('33333333-3333-3333-3333-000000000001', '22222222-2222-2222-2222-000000000001', 'Fiktiv Ekonomichef', 'Ekonomichef', 'ekonomichef@exempelbolaget-nord.example.com', 'business_contact', now() - interval '3 days', '11111111-1111-1111-1111-000000000001'),
  ('33333333-3333-3333-3333-000000000002', '22222222-2222-2222-2222-000000000001', 'Fiktiv BI-ansvarig', 'BI-ansvarig', 'bi@exempelbolaget-nord.example.com', 'business_contact', now() - interval '3 days', '11111111-1111-1111-1111-000000000001'),
  ('33333333-3333-3333-3333-000000000003', '22222222-2222-2222-2222-000000000002', 'Fiktiv IT-chef', 'IT-chef', 'it-chef@testgrossisten-syd.example.com', 'business_contact', now() - interval '10 days', '11111111-1111-1111-1111-000000000002'),
  ('33333333-3333-3333-3333-000000000004', '22222222-2222-2222-2222-000000000003', 'Fiktiv Controller', 'Controller', 'controller@demobruket.example.com', 'business_contact', null, '11111111-1111-1111-1111-000000000001'),
  ('33333333-3333-3333-3333-000000000005', '22222222-2222-2222-2222-000000000004', 'Fiktiv Verksamhetschef', 'Verksamhetschef', 'vc@partnerprospekt-vast.example.com', 'business_contact', now() - interval '1 day', '11111111-1111-1111-1111-000000000003');

-- ---------------------------------------------------------------- fiktiva affärer (skaparen blir medlem via trigger)
insert into public.deals (id, organisation_id, primary_contact_id, title, stage, owner_id, next_step, next_step_due, created_by) values
  ('44444444-4444-4444-4444-000000000001', '22222222-2222-2222-2222-000000000001', '33333333-3333-3333-3333-000000000001',
   'Datagenomgång av orderdata', 'Demo', '11111111-1111-1111-1111-000000000001', 'Visa demo-grafen på krusgraph.com/explore', current_date + 2, '11111111-1111-1111-1111-000000000001'),
  ('44444444-4444-4444-4444-000000000002', '22222222-2222-2222-2222-000000000002', '33333333-3333-3333-3333-000000000003',
   'Avgränsad pilot: en arbetsyta', 'Pilot proposal', '11111111-1111-1111-1111-000000000002', 'Skicka pilotförslaget när Gustav granskat', current_date + 5, '11111111-1111-1111-1111-000000000002'),
  ('44444444-4444-4444-4444-000000000003', '22222222-2222-2222-2222-000000000003', '33333333-3333-3333-3333-000000000004',
   'Första samtal', 'New', '11111111-1111-1111-1111-000000000001', 'Boka 30 minuter', current_date + 7, '11111111-1111-1111-1111-000000000001'),
  ('44444444-4444-4444-4444-000000000004', '22222222-2222-2222-2222-000000000004', '33333333-3333-3333-3333-000000000005',
   'Partnerledd förstudie', 'Qualified', '11111111-1111-1111-1111-000000000003', 'Samla kundens frågor inför demo', current_date + 3, '11111111-1111-1111-1111-000000000003');

-- Partnern är uttryckligen tilldelad affär 1 (och ser bara 1 och sin egen 4).
insert into public.deal_members (deal_id, user_id, member_role, assigned_by) values
  ('44444444-4444-4444-4444-000000000001', '11111111-1111-1111-1111-000000000003', 'member', '11111111-1111-1111-1111-000000000001');

-- ---------------------------------------------------------------- aktiviteter och kundproblem (fiktiva)
insert into public.activities (deal_id, organisation_id, contact_id, kind, happened_at, summary, next_step, next_step_due, created_by) values
  ('44444444-4444-4444-4444-000000000001', '22222222-2222-2222-2222-000000000001', '33333333-3333-3333-3333-000000000001', 'meeting', now() - interval '3 days',
   'Första möte. Kunden beskrev att en försäljningsrapport visar för höga totaler när orderhuvud och orderrader slås ihop. Ingen vet vilken koppling som är fel.',
   'Demo på syntetisk data', current_date + 2, '11111111-1111-1111-1111-000000000001'),
  ('44444444-4444-4444-4444-000000000002', '22222222-2222-2222-2222-000000000002', '33333333-3333-3333-3333-000000000003', 'demo', now() - interval '10 days',
   'Demo av /explore. IT-chefen vill se vilka behörigheter appen ber om innan pilot; skickade länken krusgraph.com/it.',
   'Pilotförslag', current_date + 5, '11111111-1111-1111-1111-000000000002'),
  ('44444444-4444-4444-4444-000000000004', '22222222-2222-2222-2222-000000000004', '33333333-3333-3333-3333-000000000005', 'call', now() - interval '1 day',
   'Kort samtal. Kunden har nyligen flyttat till Fabric och saknar dokumentation av hur tabellerna hänger ihop.',
   'Demo', current_date + 3, '11111111-1111-1111-1111-000000000003');

-- ---------------------------------------------------------------- problemkort (utkast; Gustav godkänner i Administration)
insert into public.problem_cards (id, slug, title_sv, title_en, symptom_sv, symptom_en, how_krusgraph_helps_sv, how_krusgraph_helps_en, questions_sv, questions_en, example_sv, example_en, keywords, status, review_note) values
  ('55555555-5555-5555-5555-000000000001', 'total_doubles', 'Totalen som dubbleras', 'The total that doubles',
   'En rapport eller app visar för höga summor när ett huvud (order, faktura) slås ihop med sina rader: huvudets belopp räknas en gång per rad.',
   'A report or app shows totals that are too high when a header (order, invoice) is joined with its lines: the header amount is counted once per line.',
   'Krusgraph läser tabellnamn och kolumner, föreslår nycklar och relationer med regeln bakom varje, och kontrollräknar mot kundens egna rader: validate_plan säger om en nyckel är unik, om referenser pekar på ingenting, och amount_levels visar vilka huvudbelopp en join med raderna skulle upprepa. Bara det som påståendena nedan säger.',
   'Krusgraph reads table and column names, proposes keys and relationships with the rule behind each one, and counts against the customer''s own rows: validate_plan says whether a key is unique and whether references point at nothing, and amount_levels shows which header amounts a join with the line rows would repeat. Only what the claims below say.',
   array['Vilken rapport visar fel total, och sedan när?', 'Finns beloppet både på huvudet och på raderna?', 'Vem äger datamodellen i Fabric i dag?', 'Får vi se tabellnamnen (inte innehållet) i ett möte?'],
   array['Which report shows the wrong total, and since when?', 'Is the amount on both the header and the lines?', 'Who owns the data model in Fabric today?', 'May we see the table names (not the contents) in a meeting?'],
   'Den syntetiska butiken på krusgraph.com/explore: orders har ett totalbelopp och order_items radbelopp; en join som summerar orders.total per rad dubblerar. Demo utan konto, ingen kunddata.',
   'The synthetic shop on krusgraph.com/explore: orders carries a total and order_items the line amounts; a join that sums orders.total per line doubles it. A demo without an account, no customer data.',
   array['total', 'totalen', 'dubbel', 'dubblera', 'dubblerad', 'summa', 'belopp', 'för hög', 'join', 'orderrad', 'rader', 'huvud', 'faktura', 'doubles', 'amount', 'header', 'lines'],
   'draft', 'Skrivet 2026-11-01 utifrån README/home i fabric-backend; Gustav godkänner.'),
  ('55555555-5555-5555-5555-000000000002', 'keys_not_unique', 'Nycklar som inte är unika', 'Keys that are not unique',
   'Samma id förekommer på flera rader i en tabell som alla tror är en lista med unika poster; joins ger dubbletter och siffror som inte stämmer.',
   'The same id appears on several rows in a table everyone treats as a list of unique records; joins produce duplicates and numbers that do not add up.',
   'Krusgraph föreslår nycklar ur namn och struktur (K0–K5, regeln bakom varje) och validate_plan räknar mot kundens rader om varje föreslagen nyckel är unik. Kunden ser vilka tabeller som saknar nyckel. Bara det som påståendena nedan säger.',
   'Krusgraph proposes keys from names and structure (K0–K5, the rule behind each) and validate_plan counts against the customer''s rows whether each proposed key is unique. The customer sees which tables have no key. Only what the claims below say.',
   array['Vilka tabeller har en deklarerad primärnyckel i dag, och vilka inte?', 'Har ni sammansatta nycklar (två kolumner tillsammans)?', 'Finns en logg- eller händelsetabell utan nyckel?'],
   array['Which tables have a declared primary key today, and which do not?', 'Do you have composite keys (two columns together)?', 'Is there a log or event table without a key?'],
   'Den syntetiska butiken: order_items har nyckeln order_id + line_no (K5) och audit_log ingen nyckel; 6 av 6 nycklar unika i kontrollen 27 oktober 2026.',
   'The synthetic shop: order_items is keyed order_id + line_no (K5) and audit_log has no key; 6 of 6 keys unique in the check of 27 October 2026.',
   array['nyckel', 'nycklar', 'unik', 'unika', 'dubblett', 'dubbletter', 'primärnyckel', 'id', 'key', 'keys', 'unique', 'duplicate', 'duplicates'],
   'draft', 'Skrivet 2026-11-01 utifrån README/home i fabric-backend; Gustav godkänner.'),
  ('55555555-5555-5555-5555-000000000003', 'orphan_references', 'Referenser utan motsvarande rad', 'References with no matching row',
   'Rader pekar på en kund, produkt eller adress som inte finns; rapporter tappar rader eller visar tomma namn, och ingen vet hur många.',
   'Rows point at a customer, product or address that does not exist; reports lose rows or show blank names, and nobody knows how many.',
   'Krusgraph föreslår relationer ur namn (R0–R4) och validate_plan räknar hur många rader som pekar på ingenting; suggest_relationships hittar kolumner som ser ut som referenser men saknar relation och kontrollerar den bästa mot data. Bara det som påståendena nedan säger.',
   'Krusgraph proposes relationships from names (R0–R4) and validate_plan counts how many rows point at nothing; suggest_relationships finds columns that look like references but are in no relationship and checks the best one against the data. Only what the claims below say.',
   array['Vilken rapport tappar rader eller visar tomma namn?', 'Finns kolumner som ingen vet vart de pekar?', 'Får vi köra kontrollen på er egen kapacitet i en pilot?'],
   array['Which report loses rows or shows blank names?', 'Are there columns nobody knows the target of?', 'May we run the check on your own capacity in a pilot?'],
   'Den syntetiska butiken: orders.ship_to_id pekade på addresses.address_id utan deklarerad relation; suggest_relationships fann den och den höll för varje värde (27 oktober 2026).',
   'The synthetic shop: orders.ship_to_id pointed at addresses.address_id with no declared relationship; suggest_relationships found it and it held for every value (27 October 2026).',
   array['referens', 'referenser', 'pekar', 'saknas', 'tom', 'tomma', 'orphan', 'orphans', 'relation', 'relationer', 'koppling', 'kopplingar', 'reference', 'references', 'missing', 'blank', 'foreign key'],
   'draft', 'Skrivet 2026-11-01 utifrån README/home i fabric-backend; Gustav godkänner.');

-- Kundproblem kopplat till kort 1 (fiktivt)
insert into public.problems (deal_id, organisation_id, contact_id, title, description, problem_card_id, status, created_by) values
  ('44444444-4444-4444-4444-000000000001', '22222222-2222-2222-2222-000000000001', '33333333-3333-3333-3333-000000000001',
   'Försäljningsrapporten visar för höga totaler', 'Totalen blir för hög när order och orderrader slås ihop. Beskrivet med ord i mötet; inga tabellnamn eller siffror ur kundens data här.',
   '55555555-5555-5555-5555-000000000001', 'matched', '11111111-1111-1111-1111-000000000001'),
  ('44444444-4444-4444-4444-000000000004', '22222222-2222-2222-2222-000000000004', '33333333-3333-3333-3333-000000000005',
   'Ingen dokumentation av hur tabellerna hänger ihop', 'Nytt i Fabric; vill ha en bild av relationerna innan de bygger rapporter.', null, 'open', '11111111-1111-1111-1111-000000000003');

-- ---------------------------------------------------------------- påståenden (ORDAGRANT ur fabric-backend 7799ef7, 2026-11-01)
insert into public.claims (slug, text, scope, source, source_commit, source_date, captured_at, language, status, review_note) values
  ('live_run_summary', 'from Claude to a Fabric workspace with synthetic data: sign-in, plan, check, query, the drafts, three dry runs and an update in place of an existing API; no new item was created', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: LIVE_RUN_SUMMARY (the home page''s test line)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('test_status_sentence', 'Test status: on 27 October 2026 every tool but domain_draft, sap_pack_draft, create_report, create_ontology, create_silver_notebook, create_drift_monitor and create_gold_views ran from Claude against a Fabric workspace with synthetic data, read-only or as a draft, and create_views and create_data_agent as dry runs (compare_semantic_model only as far as the model lookup; create_backend only as an update in place of shop_api with confirmed); no new item was created that day. Since then create_silver_notebook, create_gold_views, create_drift_monitor, create_ontology, create_semantic_model and create_report have created items live against the same workspace (status per tool: /docs#test-status).', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: instructions_sentence() (the server''s instructions)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('create_api_status', 'Creating a new API is experimental; updating one in place was tested end to end on 27 October 2026', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: create_api_status()', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('connect_sentence', 'Experimental: VS Code, Cursor and Glama were tried here on 27 October 2026 and Lovable was tried here on 30 October 2026; they stay Experimental until a full sign-in with each is confirmed', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: connect_sentence() (/mcp/connect)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.plan_backend', 'plan_backend: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing (counting queries for rule R5).', 'fabric_backend/tool_status.py: label(''plan_backend'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.plan_backend', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''plan_backend'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.validate_plan', 'validate_plan: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing (counting queries).', 'fabric_backend/tool_status.py: label(''validate_plan'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.validate_plan', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''validate_plan'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.sample_rows', 'sample_rows: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''sample_rows'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.sample_rows', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''sample_rows'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.suggest_relationships', 'suggest_relationships: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing (counting queries).', 'fabric_backend/tool_status.py: label(''suggest_relationships'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.suggest_relationships', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''suggest_relationships'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.analyze_schema', 'analyze_schema: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''analyze_schema'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.analyze_schema', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''analyze_schema'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.join_path', 'join_path: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''join_path'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.join_path', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''join_path'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.query_graphql', 'query_graphql: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''query_graphql'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.query_graphql', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''query_graphql'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.semantic_model_draft', 'semantic_model_draft: Tested end to end (a draft; creates nothing)', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''semantic_model_draft'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.semantic_model_draft', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data as a draft; it creates nothing.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''semantic_model_draft'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.data_dictionary', 'data_dictionary: Tested end to end (a draft; creates nothing)', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''data_dictionary'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.data_dictionary', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data as a draft; it creates nothing.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''data_dictionary'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.review_plan', 'review_plan: Tested end to end; reading a file back is unit-tested', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing (counting queries with validate=true).', 'fabric_backend/tool_status.py: label(''review_plan'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.review_plan', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''review_plan'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.plan_drift', 'plan_drift: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''plan_drift'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.plan_drift', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''plan_drift'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.lineage', 'lineage: Tested end to end', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''lineage'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.lineage', 'Tested end to end on 27 October 2026 against a Fabric workspace with synthetic data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''lineage'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_backend', 'create_backend: Tested end to end (27 October 2026: update in place of shop_api with confirmed; updated in place again from Lovable on 30 October 2026; consumed live by a Lovable app on 30 October 2026)', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one item; never deletes.', 'fabric_backend/tool_status.py: label(''create_backend'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_backend', 'Run live on 27 October 2026 against a Fabric workspace with synthetic data only as an update in place of shop_api with confirmed; no new item was created; the rest is unit-tested.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_backend'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_semantic_model', 'create_semantic_model: Available when enabled by the operator; created live on 29 October 2026 (shop_model_live), refreshed and reviewed in the Fabric portal by Gustav the same day; shop_model updated in place from Lovable (experimental) on 30 October 2026', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one item; never deletes.', 'fabric_backend/tool_status.py: label(''create_semantic_model'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_semantic_model', 'On 29 October 2026 it created the semantic model shop_model_live live against a Fabric workspace with synthetic data (7 tables, 6 active and 1 inactive relationship, Direct Lake, 4 measures, the date table Calendar); the same day Gustav refreshed it and reviewed it in the Fabric portal. On 30 October 2026 shop_model was updated in place from Lovable (as an MCP client at /mcp/connect).', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_semantic_model'') (the note in the tool''s own answer)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_ontology', 'create_ontology: Available when enabled by the operator; created live on 28 October 2026 (shop_ontology), reviewed in the Fabric portal on 29 October 2026; first stopped by HTTP 403 FeatureNotAvailable while the ontology was turned off in that tenant''s settings', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one item; never deletes.', 'fabric_backend/tool_status.py: label(''create_ontology'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-29', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_ontology', 'On 28 October 2026 it created the ontology shop_ontology live against a Fabric workspace with synthetic data (7 entity types, 5 with a key; 7 relationship types). Before that, with the ontology (preview) turned off in the tenant''s settings, Fabric answered HTTP 403 FeatureNotAvailable. On 29 October 2026 Gustav reviewed the item in the Fabric portal.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_ontology'') (the note in the tool''s own answer)', '7799ef7', '2026-10-29', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_report', 'create_report: Experimental; created live on 30 October 2026 (shop_report_live, shop_report), opened and reviewed in the Fabric portal by Gustav the same day', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates one item; never updates or deletes.', 'fabric_backend/tool_status.py: label(''create_report'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_report', 'On 30 October 2026 it created the report shop_report_live live against a Fabric workspace with synthetic data (dry run first, then dry_run=false; one blank page bound to shop_model_live; status Succeeded, mode created). Later that day Lovable (as an MCP client at /mcp/connect) created shop_report on shop_model; Gustav opened shop_report in the Fabric portal, added a visualisation (Calendar) and saw data.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_report'') (the note in the tool''s own answer)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_views', 'create_views: Tested end to end as a dry run; creating them: Experimental', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/alters views in that schema only; never drops.', 'fabric_backend/tool_status.py: label(''create_views'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_views', 'The dry run was tested end to end on 27 October 2026 against a Fabric workspace with synthetic data; creating has not run against a live workspace.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_views'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_data_agent', 'create_data_agent: Available when enabled by the operator; tested end to end as a dry run', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one item and its staging config; never deletes.', 'fabric_backend/tool_status.py: label(''create_data_agent'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_data_agent', 'The dry run was tested end to end on 27 October 2026 against a Fabric workspace with synthetic data; creating has not run against a live workspace.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_data_agent'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_silver_notebook', 'create_silver_notebook: Experimental; created live on 28 October 2026 (silver_shop), not yet run in Fabric', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one item; never deletes.', 'fabric_backend/tool_status.py: label(''create_silver_notebook'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_silver_notebook', 'On 28 October 2026 it created the notebook silver_shop live against a Fabric workspace with synthetic data; the notebook has not been run in Fabric.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_silver_notebook'') (the note in the tool''s own answer)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_gold_views', 'create_gold_views: Experimental; created live on 28 October 2026 (gold_shop), not yet run in Fabric', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates one notebook; never deletes.', 'fabric_backend/tool_status.py: label(''create_gold_views'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_gold_views', 'On 28 October 2026 it created the notebook gold_shop live against a Fabric workspace with synthetic data; the notebook has not been run in Fabric.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_gold_views'') (the note in the tool''s own answer)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.create_drift_monitor', 'create_drift_monitor: Experimental; created live on 28 October 2026 with schedule=false (drift_shop, drift_shop_nightly), not yet run in Fabric; the schedule needs DataPipeline.Execute.All, which the app does not have', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: creates/updates two items and a schedule; never deletes.', 'fabric_backend/tool_status.py: label(''create_drift_monitor'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.create_drift_monitor', 'On 28 October 2026 it created drift_shop and drift_shop_nightly live with schedule=false against a Fabric workspace with synthetic data; neither has been run in Fabric, and the schedule needs DataPipeline.Execute.All.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''create_drift_monitor'') (the note in the tool''s own answer)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.sap_pack_draft', 'sap_pack_draft: Draft only', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''sap_pack_draft'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.sap_pack_draft', 'Not yet run against a live workspace.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''sap_pack_draft'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('status.domain_draft', 'domain_draft: Draft only', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Verktyget ändrar i Fabric: nothing.', 'fabric_backend/tool_status.py: label(''domain_draft'') (the docs'' tool table, /docs#test-status)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('note.domain_draft', 'Not yet run against a live workspace.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'fabric_backend/tool_status.py: answer_note(''domain_draft'') (the note in the tool''s own answer)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('function.validate_plan', 'validate_plan → amount_levels | Experimental | hosted, local demo, library | the total that doubles: header amounts a join with their line rows would repeat, with the line rows per header counted; unit-tested, and run on 28 October 2026 against SQL Server 2022 in a container with synthetic data', 'Gäller körningar lokalt eller i container med syntetisk data, inte det hostade Krusgraph och inte en kunds system.', 'fabric_backend/tool_status.py: FUNCTIONS (the overview table on /docs)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('function.plan_sql_server', 'plan_sql_server | Experimental | library | `from fabric_backend import plan_sql_server`: plan, validate, data dictionary and dbt schema over ODBC from your own Python; run on 28 October 2026 against SQL Server 2022 in a container, not yet on Windows', 'Gäller körningar lokalt eller i container med syntetisk data, inte det hostade Krusgraph och inte en kunds system.', 'fabric_backend/tool_status.py: FUNCTIONS (the overview table on /docs)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('function.fabric_backend_demo', 'fabric-backend demo | Experimental | local demo | the 20-minute demo on 127.0.0.1: SQL Server over ODBC, a folder of CSV / Excel files, a columns list (file or pasted), or the synthetic shop; step 1 ends with one of five answers; over ODBC run on 28 October 2026 against SQL Server 2022 in a container', 'Gäller körningar lokalt eller i container med syntetisk data, inte det hostade Krusgraph och inte en kunds system.', 'fabric_backend/tool_status.py: FUNCTIONS (the overview table on /docs)', '7799ef7', '2026-10-28', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('client.claude', 'Claude (client): Tested end to end (since 26 October 2026); the live runs of 26 and 27 October 2026 | hosted, via /mcp (the connector)', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: CLIENTS (the overview table on /docs)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('client.vs_code', 'VS Code (client): Experimental (works since 27 October 2026); client registration is switched on at krusgraph.com since 27 October 2026 | hosted, via /mcp/connect', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: CLIENTS (the overview table on /docs)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('client.cursor', 'Cursor (client): Experimental (works since 27 October 2026); client registration is switched on at krusgraph.com since 27 October 2026 | hosted, via /mcp/connect', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: CLIENTS (the overview table on /docs)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('client.lovable', 'Lovable (client): Experimental; Lovable''s own Microsoft Fabric connector reads the API; a Lovable app read shop_api live on 30 October 2026; the chain is in docs/LOVABLE-END-TO-END.md | via the GraphQL API that create_backend makes', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: CLIENTS (the overview table on /docs)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('client.lovable_mcp', 'Lovable (client): Experimental (works since 30 October 2026); signed in and ran plan, check and creates on 30 October 2026 (Entra sign-in through Krusgraph''s OAuth with dynamic client registration, from a phone: plan_backend, validate_plan, create_backend, create_semantic_model, create_report) | via MCP (/mcp/connect)', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'fabric_backend/tool_status.py: CLIENTS (the overview table on /docs)', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('sources', 'Lakehouse: tested end to end. Warehouse: experimental. SQL database: experimental.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Källor på det hostade Krusgraph, efter om en har lästs end to end.', 'fabric_backend/tool_status.py: SOURCES + source_word() (the start page''s hub)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.validate_plan_row6', '6 of 6 keys unique, 6 of 6 relationships hold without orphans', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 1, row 6 (validate_plan, Expected; passed 26 and 27 Oct)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.suggest_relationships_row27', '`orders.ship_to_id → addresses.address_id` first, holding for every value', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 1, row 27 (suggest_relationships, Expected; passed 26 and 27 Oct)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.sample_rows_masking', '5 rows; `name` shows `***` with a `personal_data` notice (rule P1) and the parameter `show_personal_data`', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 1, row 5 (sample_rows, Expected; passed 27 Oct masked)', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.ontology_verdict', 'On 29 October 2026 Gustav reviewed the item in the Fabric portal; his verdict: "ontology ser väldigt bra ut". No single part (entity types, keys, relationships, data bindings) was recorded as checked on its own, and no ontology agent or question has used it.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 6, create_ontology, 28 October 2026', '7799ef7', '2026-10-29', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.semantic_model_no_report', 'No report or query has used the model.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status. Avser shop_model_live.', 'docs/LIVE-TEST.md section 6, create_semantic_model, 29 October 2026', '7799ef7', '2026-10-29', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.create_backend_new_api', 'Creating a new API has still not run live.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 6, 30 October 2026, create_backend', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.lovable_app_reads_api', '`shop_api` was updated in place from Lovable on 30 October 2026, and a Lovable app reads the API live: orders, customers and the ship-to address through `ship_to_id → addresses`.', 'Gäller det hostade Krusgraph (krusgraph.com) mot demo-arbetsytan med syntetisk data (workspace demo, lakehouse demo_lh, schema shop). Säger inget om en kunds data eller arbetsyta. Statusordet är det som står på krusgraph.com/docs#test-status.', 'docs/LIVE-TEST.md section 6, 30 October 2026, create_backend', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.lovable_client', 'Lovable connected to `https://krusgraph.com/mcp/connect` with an Entra sign-in through Krusgraph''s OAuth (dynamic client registration), from a phone, and ran `plan_backend`, `validate_plan`, `create_backend`, `create_semantic_model` and `create_report`.', 'Gäller vilka MCP-klienter som provats mot det hostade Krusgraph, på vilket datum; inte en kunds klient eller tenant.', 'docs/LIVE-TEST.md section 6, 30 October 2026, Lovable as a client', '7799ef7', '2026-10-30', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.'),
  ('livetest.status_rule', 'A creating tool that answered `consent` stays **Available when enabled by the operator** until it has created something live.', 'Regeln för statusorden; gäller alla skapande verktyg.', 'docs/LIVE-TEST.md section 5, point 1', '7799ef7', '2026-10-27', '2026-11-01', 'en', 'imported', 'Ordagrant ur källan; Gustav bekräftar eller drar tillbaka i Administration.');

-- Problemkort → påståenden
insert into public.problem_card_claims (problem_card_id, claim_id)
select '55555555-5555-5555-5555-000000000001', id from public.claims where slug in
  ('function.validate_plan_amount_levels', 'status.validate_plan', 'note.validate_plan', 'status.plan_backend', 'livetest.validate_plan_row6', 'live_run_summary');
insert into public.problem_card_claims (problem_card_id, claim_id)
select '55555555-5555-5555-5555-000000000002', id from public.claims where slug in
  ('status.plan_backend', 'note.plan_backend', 'status.validate_plan', 'livetest.validate_plan_row6', 'status.data_dictionary', 'live_run_summary');
insert into public.problem_card_claims (problem_card_id, claim_id)
select '55555555-5555-5555-5555-000000000003', id from public.claims where slug in
  ('status.suggest_relationships', 'note.suggest_relationships', 'livetest.suggest_relationships_row27', 'status.validate_plan', 'livetest.validate_plan_row6', 'status.plan_drift');

-- ---------------------------------------------------------------- trust-svar (ORDAGRANT ur krusgraph.com/it: fabric_backend/page_templates/it.html)
insert into public.trust_answers (slug, question_sv, question_en, answer, source, source_commit, source_date, status, review_note) values
  ('where_data_goes', 'Vart tar vår data vägen?', 'Where does our data go?', 'Krusgraph stores no table contents. Names, counts and the sample rows you ask for pass through the service in memory and reach your AI client; the hosted service runs in the EU, and you can run it in your own Azure to keep everything in your tenant.', 'fabric_backend/page_templates/it.html: Where your data goes (lede)', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('hosted_where', 'Var körs den hostade tjänsten?', 'Where does the hosted service run?', 'Azure, Sweden Central. Answers pass through memory during the call; no table contents are saved.', 'fabric_backend/page_templates/it.html: Where your data goes, row Hosted (krusgraph.com). Villkorlig mening om loggars lagringstid utelämnad: beror på driftsinställningen KRUSGRAPH_LOG_RETENTION_DAYS.', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('own_azure', 'Kan vi köra det i vår egen Azure?', 'Can we run it in our own Azure?', 'The same open-source code and script (deploy/krusgraph.sh), in your tenant and your region. Nothing passes through Kruse Consulting.', 'fabric_backend/page_templates/it.html: Where your data goes, row In your own Azure', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('not_hosting', 'Hostar Krusgraph vår data eller våra appar?', 'Does Krusgraph host our data or apps?', 'Krusgraph does not host your data or apps. What it creates in Fabric is created in your workspace, with your permissions.', 'fabric_backend/page_templates/it.html: Where your data goes (note)', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('who_behind', 'Vem står bakom?', 'Who stands behind it?', 'Krusgraph is made and run by Kruse Consulting AB. Member of the Microsoft AI Cloud Partner Program Based in Uppsala, Sweden, and Bern, Switzerland Built for Microsoft Fabric Sign in with Microsoft Entra ID Hosted in Azure, Sweden Central', 'fabric_backend/page_templates/it.html: Who stands behind it (listan, radbrytningar ersatta med mellanslag; org.nr-parentesen är en driftsinställning och utelämnad)', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('permissions_delegated', 'Vilka behörigheter ber appen om, och varför?', 'What does the Entra app ask for, and why?', 'An administrator approves the Krusgraph app once (admin consent). All its permissions are delegated: every call runs as the signed-in person, with that person’s own Fabric rights, so Krusgraph can reach nothing that person cannot already reach. The app asks for no application permissions. Every creating tool except create_backend answers with what it would create until it is called with dry_run=false; create_backend has no dry run and creates or updates the one API for GraphQL named in the call.', 'fabric_backend/page_templates/it.html: What the Entra app asks for, and why', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('verified_publisher', 'Är utgivaren verifierad?', 'Is the publisher verified?', 'Verified publisher: Kruse Consulting AB (Microsoft Entra publisher verification). The publisher domain is krusgraph.com. Publisher verification confirms who publishes the app; it says nothing about its security. Your administrator can still require admin consent before anyone uses it.', 'fabric_backend/page_templates/it.html: verified-publisher', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('no_table_contents', 'Lagras något av våra tabeller?', 'Is anything of our tables stored?', 'No table contents. Metadata (workspace, item, table and column names and types), the counts from checks, sample rows and query results pass through Krusgraph to the person’s MCP client and are not kept after the request.', 'fabric_backend/page_templates/it.html: What is stored, where and for how long', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('tokens', 'Hur hanteras tokens?', 'How are tokens handled?', 'Tokens. From Claude, tokens are exchanged on the person’s behalf (OAuth 2.0 on-behalf-of) and held in memory only, never written to disk or logs.', 'fabric_backend/page_templates/it.html: What is stored (Tokens). Den villkorliga meningen om andra MCP-klienter (CLIENT_REGISTRATION) utelämnad; se /privacy.', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('usage_record', 'Vad loggas per anrop?', 'What is recorded per call?', 'A usage record per tool call: the tool’s name, the outcome, the duration and, for creating tools, whether it was a dry run. No user id, no table or column names.', 'fabric_backend/page_templates/it.html: What is stored (usage record). Villkorlig del om hash av tenant-id (USAGE_ORG) utelämnad.', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('revoke', 'Hur återkallar vi åtkomsten?', 'How do we revoke access?', 'An administrator can revoke the app at any time in Microsoft Entra ID, under Enterprise applications: removing the consent or the app ends every renewal of its tokens.', 'fabric_backend/page_templates/it.html: How to revoke access', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('if_gustav_unavailable', 'Vad händer om Gustav inte är tillgänglig?', 'What if Gustav is unavailable?', 'The code is open: your team can run Krusgraph in your own Azure with the same script (deploy/krusgraph.sh) and your own Entra app. No customer data is stored with us, so there is nothing of yours to retrieve. Access is revoked in your own tenant, as described under How to revoke access; it does not need us.', 'fabric_backend/page_templates/it.html: If Gustav is unavailable (tre listpunkter)', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('check_in_browser', 'Vad händer med filer vi släpper på /check?', 'What happens to files dropped on /check?', 'The page /check runs the same engine in the visitor’s browser (Python compiled to WebAssembly). Files dropped there are read in the browser and are not uploaded; the page’s content security policy does not let it send requests with them.', 'fabric_backend/page_templates/it.html: /check runs in the browser', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('security_issue', 'Hur rapporterar man en säkerhetsbrist?', 'How is a security issue reported?', 'Email gustav@krusgraph.com. The contact and the policy are also in /.well-known/security.txt (RFC 9116); the policy is SECURITY.md on GitHub.', 'fabric_backend/page_templates/it.html: Reporting a security issue', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('terms_preview', 'Vilka villkor gäller?', 'What terms apply?', 'The service is a preview: Preview terms. Pilots and team work: Pricing.', 'fabric_backend/page_templates/it.html: Terms (länkarna /terms och /pricing som text)', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.'),
  ('open_source', 'Är koden öppen?', 'Is the code open?', 'Krusgraph is open source under the MIT licence: the engine, the inference rules, the server and the deployment are on GitHub. Your team can read what each tool does, or host Krusgraph in your own Azure subscription with your own Entra app.', 'fabric_backend/page_templates/it.html: The code is open', '7799ef7', '2026-11-01', 'imported', 'Ordagrant ur /it-sidan (mallvariabler ifyllda: Krusgraph, krusgraph.com, create_backend); Gustav bekräftar. Svensk översättning tom tills godkänd.');

-- ---------------------------------------------------------------- mallar (utkast; Gustav godkänner i Administration innan de kan användas)
-- Platshållare: {{organisation}} {{contact}} {{seller}} {{date}}; priset är [PRIS] / [PRICE] och fylls ALDRIG i mallen (beslut 1).
insert into public.templates (id, slug, name_sv, name_en, body_sv, body_en, version, status) values
  ('66666666-6666-6666-6666-000000000001', 'data_review', 'Datagenomgång', 'Data review', '# Datagenomgång — {{organisation}}

Till: {{contact}}, {{organisation}}
Från: {{seller}}, Kruse Consulting AB
Datum: {{date}}

## Vad vi gör

En genomgång av **en** Fabric-arbetsyta, **en** källa (lakehouse, warehouse eller SQL database) och **ett** schema:
Krusgraph läser tabell- och kolumnnamn, föreslår nycklar och relationer med regeln bakom varje, och kontrollräknar
mot era egna rader (unika nycklar, referenser utan motsvarande rad, belopp som en join skulle upprepa). Inget skapas
i er arbetsyta. Inga radvärden lämnar er tenant; i mötet ser vi namn och antal.

## Vad ni får

- Planen som JSON och som ER-diagram, varje nyckel och relation märkt K0–K5 / R0–R4.
- Listan över oklara och okopplade kolumner, att besluta om tillsammans.
- En kort skriftlig sammanfattning: vad motorn hittade, vad den lämnade okopplat, vad ni fick bekräfta för hand.

## Vad vi behöver av er

- En person som kan er data och kan säga vilken av två tabeller en kolumn pekar på.
- Läsrättighet för den personen i arbetsytan, och ett engångsgodkännande av Krusgraph-appen (delegerade
  behörigheter; se krusgraph.com/it) eller den öppna koden körd i er egen Azure.
- Ett arbetsmöte.

## Vad som inte ingår

Att skapa något i Fabric, ändringar i er datamodell, flera arbetsytor eller källor, SAP-scheman.

## Pris

[PRIS]

## Påståenden om Krusgraph

Endast de som står i bilagan *Påståenden* (ordagrant ur fabric-backends statuskälla med datum).
', '# Data review — {{organisation}}

To: {{contact}}, {{organisation}}
From: {{seller}}, Kruse Consulting AB
Date: {{date}}

## What we do

A review of **one** Fabric workspace, **one** source (lakehouse, warehouse or SQL database) and **one** schema:
Krusgraph reads table and column names, proposes keys and relationships with the rule behind each one, and counts
against your own rows (unique keys, references with no matching row, amounts a join would repeat). Nothing is
created in your workspace. No row values leave your tenant; in the meeting we see names and counts.

## What you get

- The plan as JSON and as an ER diagram, every key and relationship labelled K0–K5 / R0–R4.
- The list of ambiguous and unlinked columns, to decide on together.
- A short written summary: what the engine found, what it left unlinked, what you had to confirm by hand.

## What we need from you

- One person who knows your data and can say which of two tables a column points at.
- Read access for that person in the workspace, and a one-time approval of the Krusgraph app (delegated
  permissions; see krusgraph.com/it), or the open-source code run in your own Azure.
- One working session.

## Not included

Creating anything in Fabric, changes to your data model, several workspaces or sources, SAP schemas.

## Price

[PRICE]

## Claims about Krusgraph

Only those in the appendix *Claims* (verbatim from fabric-backend''s status source, with dates).
', 1, 'draft'),
  ('66666666-6666-6666-6666-000000000002', 'bounded_pilot', 'Avgränsad pilot', 'Bounded pilot', '# Avgränsad pilot — {{organisation}}

Till: {{contact}}, {{organisation}}
Från: {{seller}}, Kruse Consulting AB
Datum: {{date}}

En avgränsad pilot: en kund, en Fabric-arbetsyta, ett överenskommet resultat. Omfattningen följer Krusgraphs
pilotpaket (fabric-backend, docs/PILOT.md).

## Mål

Inom piloten ser ni era egna tabeller som en förklarbar graf, går igenom de föreslagna nycklarna och relationerna med
regeln bakom varje, och avslutar med ett API for GraphQL-objekt i er arbetsyta som Claude (eller Lovable, Cursor,
Claude Code) kan fråga. Ni behåller en planfil som kan köras om, och en kort skrivelse om vad motorn fick rätt, vad
den lämnade okopplat och vad ni bekräftade för hand.

## Omfattning

| Ingår | Ingår inte |
| --- | --- |
| En arbetsyta, en källa, ett schema | Flera arbetsytor, joins över källor, SAP-scheman |
| Upp till cirka 60 tabeller | Radnivåsäkerhet, ändringar i datamodellen, prestandatrimning |
| Nycklar och relationer föreslagna och genomgångna tillsammans | Att skriva applikationskod |
| Ett API for GraphQL-objekt skapat eller uppdaterat på plats | Allt som raderar eller döper om objekt |
| Läsande frågor från Claude för att verifiera | Mutationer, skrivning tillbaka, ETL |
| De två manuella portalstegen (introspektion, objektbehörigheter) tillsammans med er | Tenant-administration utöver engångsgodkännandet |

## Leverabler

1. Planen (JSON och ER-diagram, K0–K5 / R0–R4, listan över oklara och okopplade kolumner).
2. Granskningsprotokoll: vad som godtogs, hoppades över eller ändrades, och varför; vad som kontrollerades mot data.
3. API for GraphQL-objektet i er arbetsyta, från den granskade planen.
4. Anslutningskort: endpoint, identitet, de tre exempelfrågorna som kördes.
5. Skrivelse (2–4 sidor): vad som fungerade, vad motorn missade, vad en bredare utrullning kräver. Bara namn och
   former på tabeller; inga raddata, inga kundidentifierare lämnar er tenant.

## Vad ni behöver ha

- En Fabric-kapacitet (prov räcker) och en arbetsyta pilotanvändarna kan öppna.
- En källa med tabeller som har *namn*; kodade kolumnnamn behöver en ordlista (ingår inte).
- En Entra-administratör som ger engångsgodkännandet, eller kör den öppna servern i er egen tenant.
- En person som kan er data. Två arbetsmöten om 90 minuter.

## Så går piloten

1. Anslut (möte 1, första halvan). 2. Utforska: planen över schemat. 3. Granska: varje osäker relation och kolumn,
beslut om nycklar och bekräftade relationer. 4. Bygg (möte 2): API:et, portalstegen, tre frågor från Claude.
Överlämning av planfil, protokoll och skrivelse en vecka senare.

## Risker vi nämner i förväg

Generiska kolumnnamn ger få länkar och piloten blir mest bekräftelsearbete; portalstegen kräver er administratör;
godkännandet av appen kan ta dagar i vissa organisationer (alternativet i egen tenant undviker det).

## Pris

[PRIS]

## Påståenden om Krusgraph

Endast de som står i bilagan *Påståenden* (ordagrant ur fabric-backends statuskälla med datum).
', '# Bounded pilot — {{organisation}}

To: {{contact}}, {{organisation}}
From: {{seller}}, Kruse Consulting AB
Date: {{date}}

A bounded pilot: one customer, one Fabric workspace, one agreed outcome. The scope follows Krusgraph''s pilot
package (fabric-backend, docs/PILOT.md).

## Goal

Within the pilot you see your own tables as an explainable graph, review the inferred keys and relationships with the
rule behind each one, and end with an API for GraphQL item in your workspace that Claude (or Lovable, Cursor, Claude
Code) can query. You keep a plan file you can re-run, and a short write-up of what the engine got right, what it left
unlinked, and what you had to confirm by hand.

## Scope

| In | Out |
| --- | --- |
| One workspace, one source, one schema | Several workspaces, cross-source joins, SAP schemas |
| Up to about 60 tables | Row-level security, data model changes, performance tuning |
| Keys and relationships inferred and reviewed together | Writing application code |
| One API for GraphQL item created or updated in place | Anything that deletes or renames items |
| Read-only queries from Claude to verify | Mutations, write-back, ETL |
| The two manual portal steps (introspection, item permissions) together with you | Tenant administration beyond the one-time consent |

## Deliverables

1. The plan (JSON and ER diagram, K0–K5 / R0–R4, the list of ambiguous and unlinked columns).
2. Review record: what was accepted, skipped or overruled, and why; what was checked against data.
3. The API for GraphQL item in your workspace, from the reviewed plan.
4. Connection card: endpoint, identity, the three example queries that were run.
5. Write-up (2–4 pages): what worked, what the engine missed, what a wider rollout would need. Names and shapes of
   tables only; no row data, no customer identifiers leave your tenant.

## What you need to have

- A Fabric capacity (trial is fine) and a workspace the pilot users can open.
- A source with tables that have *names*; coded column names need a dictionary (not included).
- An Entra administrator who grants the one-time consent, or runs the open-source server in your own tenant.
- One person who knows your data. Two 90-minute working sessions.

## How the pilot runs

1. Connect (session 1, first half). 2. Explore: the plan over the schema. 3. Review: every uncertain relationship
and column, decisions on keys and confirmed links. 4. Build (session 2): the API, the portal steps, three queries
from Claude. Hand-over of the plan file, the record and the write-up a week later.

## Risks named up front

Generic column names yield few links and the pilot becomes mostly confirmation work; the portal steps need your
administrator; approving the app can take days in some organisations (the in-house option avoids it).

## Price

[PRICE]

## Claims about Krusgraph

Only those in the appendix *Claims* (verbatim from fabric-backend''s status source, with dates).
', 1, 'draft'),
  ('66666666-6666-6666-6666-000000000003', 'continuation', 'Fortsättning', 'Continuation', '# Fortsättning efter pilot — {{organisation}}

Till: {{contact}}, {{organisation}}
Från: {{seller}}, Kruse Consulting AB
Datum: {{date}}

## Utgångsläge

Piloten är genomförd: planfilen, granskningsprotokollet och skrivelsen är överlämnade. Detta förslag beskriver
nästa avgränsade steg; det bygger på vad skrivelsen sade att en bredare utrullning kräver.

## Nästa steg (välj, stryk det som inte gäller)

- Ett till schema eller en till källa i samma arbetsyta, med samma arbetssätt som piloten.
- En Power BI-semantisk modell eller en Fabric IQ-ontologi från samma granskade plan (status per verktyg: bilagan
  *Påståenden*; ett verktyg som inte skapat något live beskrivs som utkast).
- Överlämning till ert eget team: dokumentation (data dictionary, dbt-schema) och genomgång av hur planen körs om.

## Vad som inte ingår

Drift, övervakning och löpande support.

## Pris

[PRIS]

## Påståenden om Krusgraph

Endast de som står i bilagan *Påståenden* (ordagrant ur fabric-backends statuskälla med datum).
', '# Continuation after the pilot — {{organisation}}

To: {{contact}}, {{organisation}}
From: {{seller}}, Kruse Consulting AB
Date: {{date}}

## Starting point

The pilot is done: the plan file, the review record and the write-up have been handed over. This proposal
describes the next bounded step, built on what the write-up said a wider rollout would need.

## Next step (choose; strike what does not apply)

- One more schema or source in the same workspace, with the same way of working as the pilot.
- A Power BI semantic model or a Fabric IQ ontology from the same reviewed plan (status per tool: the appendix
  *Claims*; a tool that has not created anything live is described as a draft).
- Hand-over to your own team: documentation (data dictionary, dbt schema) and a walk-through of re-running the plan.

## Not included

Operations, monitoring and ongoing support.

## Price

[PRICE]

## Claims about Krusgraph

Only those in the appendix *Claims* (verbatim from fabric-backend''s status source, with dates).
', 1, 'draft');

-- ---------------------------------------------------------------- ett fiktivt förslag från pilotmallen, pris tomt
-- (insatt som postgres: mallen är ännu draft; i gränssnittet kräver det en godkänd mall)
insert into public.proposals (id, deal_id, template_id, template_version, title, language, body, price, promises, status, created_by)
select '77777777-7777-7777-7777-000000000001', '44444444-4444-4444-4444-000000000002', t.id, t.version,
       'Avgränsad pilot — Testgrossisten Syd AB (fiktivt)', 'sv',
       replace(replace(replace(replace(t.body_sv, '{{organisation}}', 'Testgrossisten Syd AB (fiktivt)'), '{{contact}}', 'Fiktiv IT-chef'),
               '{{seller}}', 'Säljare Två Demo (fiktiv)'), '{{date}}', to_char(current_date, 'YYYY-MM-DD')),
       null, null, 'draft', '11111111-1111-1111-1111-000000000002'
from public.templates t where t.slug = 'bounded_pilot';

-- ett andra förslag med ett löfte utanför påståendena → needs_review (triggern), för Gustavs granskningsvy
insert into public.proposals (id, deal_id, template_id, template_version, title, language, body, price, promises, status, created_by)
select '77777777-7777-7777-7777-000000000002', '44444444-4444-4444-4444-000000000001', t.id, t.version,
       'Datagenomgång — Exempelbolaget Nord AB (fiktivt)', 'sv',
       replace(replace(replace(replace(t.body_sv, '{{organisation}}', 'Exempelbolaget Nord AB (fiktivt)'), '{{contact}}', 'Fiktiv Ekonomichef'),
               '{{seller}}', 'Säljare Demo (fiktiv)'), '{{date}}', to_char(current_date, 'YYYY-MM-DD')),
       null, 'Säljaren vill lova att genomgången även täcker ett andra schema. Står inte i mallen; Gustav avgör.', 'draft', '11111111-1111-1111-1111-000000000001'
from public.templates t where t.slug = 'data_review';

insert into public.proposal_claims (proposal_id, claim_id)
select '77777777-7777-7777-7777-000000000001', id from public.claims where slug in ('live_run_summary', 'status.create_backend', 'create_api_status', 'status.validate_plan');
