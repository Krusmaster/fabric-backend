# krusgraph-sales — Kruse Consultings interna säljportal för Krusgraph

Status: specifikation och byggfiler, version 1 (v1). Ingenting här är driftsatt. Repot innehåller bara filer:
inget körs, inget anropar Supabase, Lovable, Azure, Entra eller Fabric. Gustav kör SQL-filerna i Supabase och klistrar
in prompten i Lovable (avsnittet *Så sätter Gustav upp det*).

**Var det ligger.** Uppdraget bad om det privata repot `Krusmaster/krusgraph-sales`. Sessionen som skrev filerna
saknade behörighet att skapa repot (GitHub-tokenen gällde bara `fabric-backend`), så allt ligger under
`sales-portal/` på branchen `sales-portal-spec` i `fabric-backend`. **Gustav skapar repot** `Krusmaster/krusgraph-sales`
(privat) och flyttar innehållet i `sales-portal/` till dess rot; ingen fil här refererar till sökvägen `sales-portal/`.

## Syfte

En säljpartner utan Fabric-kunskap ska kunna:

1. registrera ett **företag**, en **kontakt**, ett **möte** och de **kundproblem** som kom upp,
2. få **godkända säljargument** (påståenden ur registret `claims`) och **exempel** (ur `problem_cards`) som svar på
   frågan *Hur kan Krusgraph hjälpa?*, eller svaret *otillräckligt underlag* när registret inte täcker frågan,
3. skapa ett **förslag** från en av tre mallar (Datagenomgång, Avgränsad pilot, Fortsättning) och
4. **följa affären** genom stadierna New → Qualified → Demo → Pilot proposal → Decision → Won / Lost.

Gustav Kruse (admin) **granskar specialpris och löften** innan ett förslag får skickas, och godkänner påståenden
innan de visas för säljare och partner.

v1 är affärsdata med roller. **Inte i v1**: fakturering, bank, provision, kampanjer, mötestranskript och
dokumentscanning. De ligger i [docs/ROADMAP.md](docs/ROADMAP.md) och kräver Gustavs beslut först
([docs/DECISIONS-FOR-GUSTAV.md](docs/DECISIONS-FOR-GUSTAV.md)).

## Teknik

- **Supabase**: Postgres (schemat i `supabase/schema.sql`), Auth (inloggning), Row Level Security
  (`supabase/policies.sql`, negativa tester i `supabase/tests/rls_negative.sql`), seed med uppenbart fiktiva data
  (`supabase/seed.sql`).
- **Lovable**: gränssnittet, byggt från `lovable/PROMPT.md` mot Supabase-projektet. Lovable skriver ingen egen
  datamodell; schemat och policyerna är de i detta repo.
- Ingen egen server, inga edge functions i v1, ingen LLM-chatt. Knappen *Hur kan Krusgraph hjälpa?* söker i
  `problem_cards` och `claims` med vanlig textsökning och visar bara det som finns där.

## Roller

| Roll | Vem | Ser | Får göra |
| --- | --- | --- | --- |
| `admin` | Gustav Kruse | allt, inklusive `audit_log` | allt: roller, godkänna påståenden, mallar, förslag, gallring |
| `reviewer` | den Gustav utser (i v1 Gustav själv) | alla affärer, förslag, påståenden och problemkort, läsande | godkänna/avslå påståenden, problemkort, trust-svar och förslag med specialpris eller löften |
| `seller` | anställd säljare hos Kruse Consulting | hela registret av företag och kontakter; **de affärer hen är tilldelad** (medlem i `deal_members`, vilket den som skapar affären blir automatiskt) | registrera företag, kontakter, aktiviteter, problem; skapa och ändra sina affärer och förslag; dela en förslagslänk när förslaget är godkänt |
| `partner` | extern säljpartner | **bara det hen uttryckligen är tilldelad**: affärer med en rad i `deal_members`, och de företag och kontakter som hör till dem eller som hen själv registrerat | samma som säljare, men inom sina affärer; inget annat i registret |

En ny inloggning utan inbjudan (`role_invitations`) blir `partner` med `active = false` och ser ingenting förrän
Gustav aktiverar kontot i Administration. Gustavs e-post är inbjuden som `admin` i seeden.

## Dataskydd

- **Kontaktuppgifter är personuppgifter.** Tabellen `contacts` (namn, titel, e-post, telefon) innehåller
  personuppgifter om kundernas anställda. Varje kontakt bär `lawful_basis` (i v1 `business_contact`, dvs. intresseavvägning
  för affärskontakt) och `retain_until`. Lagra bara det som behövs för affären: inga privata telefonnummer, inga
  anteckningar om personen som inte rör affären. Fritextfält (`notes`, `summary`) får inte innehålla känsliga uppgifter.
- **Gallring.** `retain_until` sätts vid registrering från inställningen `contact_retention_months` i `app_settings`
  (tom tills Gustav beslutat; se docs/DECISIONS-FOR-GUSTAV.md). Funktionen `contacts_due_for_erasure()` listar kontakter
  som passerat datumet; Administration visar listan och admin raderar eller förlänger. `erase_requested_at` markerar
  en begäran om radering, som hanteras i samma vy. Raderingar loggas i `audit_log` utan personuppgifterna (bara id).
- **Aldrig kunders Fabric-data eller tokens.** Portalen rör aldrig en kunds Fabric-arbetsyta, tabeller, radvärden,
  Entra-tokens, tenant-id eller arbetsyte-id. Fälten `problems.description` och `activities.summary` beskriver problem
  med ord, inte med kundens tabellnamn eller siffror ur deras data. Seeden innehåller bara fiktiva företag med
  `example.com`-adresser; inga riktiga personer, inga riktiga kunder.
- **Förslagslänkar** (`proposal_links`) har utgångsdatum, kan återkallas och kräver inloggning tills Gustav beslutat
  annat (öppen fråga i docs/DECISIONS-FOR-GUSTAV.md).
- **Loggning.** `audit_log` skriver vem som ändrade vad i affärer, förslag, påståenden, kontakter och roller; bara
  admin läser den. Inga lösenord, inga tokens: Supabase Auth hanterar inloggningen.

## Påståenden om Krusgraph

Portalen får bara påstå det som står i registret `claims`. Seeden fyller registret **ordagrant** (på engelska, som
källan) från `fabric_backend/tool_status.py` och `docs/LIVE-TEST.md` i fabric-backend, med källa, datum och commit.
Trust-svaren (`trust_answers`) är ordagrant från sidan krusgraph.com/it (`fabric_backend/page_templates/it.html`).
Ett påstående som inte finns där får inte skrivas in i ett förslag eller sägas i ett möte; vill en säljare ha ett
nytt, läggs det som `draft` och Gustav godkänner. Inga priser, provisionssatser eller svarstider finns i repot.

## Filerna

| Fil | Innehåll |
| --- | --- |
| `README.md` | denna fil |
| `LICENSE` | All rights reserved, Kruse Consulting AB |
| `supabase/schema.sql` | tabeller, enum-typer, triggers (updated_at, audit, medlemskap, granskningsregler), hjälpfunktioner för RLS, vyn för *Min dag* |
| `supabase/policies.sql` | RLS: alla tabeller låsta, policyer per roll |
| `supabase/tests/rls_negative.sql` | negativa tester som SQL: vad en partner, säljare och anonym **inte** ska se eller få göra; körs efter seed och rullas tillbaka |
| `supabase/seed.sql` | inställningar, inbjudan för Gustav, fiktiva demoanvändare, fiktiva företag/kontakter/affärer, de tre problemkorten, påståenden, trust-svar, de tre mallarna |
| `lovable/PROMPT.md` | prompten för Lovable: vyer, tema, språk, mobil, reglerna för knappen *Hur kan Krusgraph hjälpa?* |
| `docs/ROADMAP.md` | det som inte är i v1, och beslutet som krävs före varje punkt |
| `docs/DECISIONS-FOR-GUSTAV.md` | öppna beslut: priser, partneravtal, bokföring, gallring, språk, inloggning för kundlänkar |

## Så sätter Gustav upp det

1. **Supabase**: nytt projekt (region EU). I *SQL Editor*, kör i ordning:
   `supabase/schema.sql` → `supabase/policies.sql` → `supabase/seed.sql` → `supabase/tests/rls_negative.sql`.
   Testfilen skriver `PASS` per test i *Messages* och rullar tillbaka allt den gjorde; ett `FAIL` stoppar med
   felmeddelande och då ska inget byggas förrän det är löst.
2. **Auth**: slå på e-postinloggning (magic link). Logga in med `fagerstagustav@gmail.com`; profilen får rollen
   `admin` från `role_invitations`. Demoanvändarna i seeden kan inte logga in (tomt lösenord) och raderas före skarp
   drift (block *Demoanvändare* i `seed.sql`).
3. **Lovable**: nytt projekt, koppla Supabase-projektet (Lovables Supabase-integration), klistra in hela
   `lovable/PROMPT.md` som första meddelande. Lovable ska **inte** skapa eller ändra tabeller; prompten säger det.
4. Gå igenom *Administration → Påståenden*: alla importerade påståenden (`status = imported`) bekräftas eller dras
   tillbaka av Gustav. Till dess visas de i mötesstödet märkta *från publicerad källa, ej bekräftad i portalen*.
5. Besluten i `docs/DECISIONS-FOR-GUSTAV.md` tas innan en partner bjuds in.

## Regler för repot

- Inga riktiga personnamn utöver Gustav Kruse (admin). Inga priser, provisionssatser eller svarstider.
- Inga påståenden om Krusgraph utanför `fabric_backend/tool_status.py` och `docs/LIVE-TEST.md`.
- Ingen kund-, Fabric- eller tokendata, inte heller i seed eller tester.
- Commits som Gustav Kruse <fagerstagustav@gmail.com>, utan co-author-, session- eller "generated with"-rader.
