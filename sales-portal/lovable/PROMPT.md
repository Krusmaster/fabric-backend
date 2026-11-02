# Lovable-prompt: Krusgraph säljportal (krusgraph-sales)

Klistra in hela denna fil som första meddelande i ett nytt Lovable-projekt som är kopplat till Supabase-projektet där
`supabase/schema.sql`, `supabase/policies.sql` och `supabase/seed.sql` redan körts. Prompten är skriven till Lovable.

---

Bygg en intern säljportal för Kruse Consulting AB som säljer produkten Krusgraph. Användarna är säljare och externa
säljpartner utan teknisk kunskap om Microsoft Fabric, plus en administratör (Gustav Kruse) som granskar. Appen ska vara
lugn, tydlig och mobilvänlig; en partner använder den på telefonen direkt efter ett kundmöte.

## Regler som inte får brytas

1. **Datamodellen finns redan i Supabase.** Skapa, ändra eller ta bort inga tabeller, kolumner, policyer, triggers,
   funktioner eller vyer. Skriv inga migrationer. Använd bara tabellerna, vyerna och funktionerna nedan. Om något
   saknas: säg det i chatten i stället för att lägga till det.
2. **Row Level Security avgör vad en användare ser.** Lita på den: fråga tabellerna direkt med den inloggade
   användarens session och visa det som kommer. Lägg ingen egen rollogik som ger mer än RLS ger. Rollen läses från
   `profiles.role` för den inloggade (`admin`, `reviewer`, `seller`, `partner`) och styr bara vilka vyer och knappar
   som visas.
3. **Inga fria påståenden om Krusgraph.** Allt som sägs om produkten i appen kommer från tabellerna `claims`,
   `problem_cards` och `trust_answers`. Ingen hårdkodad marknadstext, inga egna formuleringar om vad Krusgraph gör,
   inga siffror, priser, svarstider eller löften.
4. **Ingen LLM, ingen chatt.** Knappen *Hur kan Krusgraph hjälpa?* anropar databasfunktionen
   `search_meeting_support(q, lang)` och visar träffarna ur vyn `v_meeting_support`. Tomt resultat visas som
   *Otillräckligt underlag* / *Insufficient basis* med texten "Registret täcker inte den här frågan. Skriv ner kundens
   problem och be Gustav om ett underlag." Ingen AI-integration, ingen generering av text.
5. **Pris är ett tomt fält** i v1. Visa fältet `proposals.price` som valfritt och tomt; förifyll aldrig; lägg inga
   förslag på belopp. Mallarnas text innehåller `[PRIS]` / `[PRICE]` och det lämnas som det är.
6. **Personuppgifter.** Kontaktuppgifter är personuppgifter: visa en diskret text vid kontaktformuläret, "Bara
   uppgifter som behövs för affären. Inga privata nummer, inga anteckningar om personen." Visa aldrig en kontakts
   uppgifter i listor utanför den organisation den hör till. Aldrig kunders Fabric-data: fälten för
   problem och mötesanteckningar har hjälptexten "Beskriv med ord. Inga tabellnamn, siffror eller radvärden ur
   kundens data."
7. **Två språk**: svenska och engelska, växlas i profilen (`profiles.language`) och i sidhuvudet. Alla etiketter,
   knappar, tomma tillstånd och felmeddelanden finns på båda språken. Innehållet i registret visas på det språk raden
   har (`claims.language`, `problem_cards.title_sv/title_en`, `trust_answers.answer` på engelska och `answer_sv` när den
   finns).
8. **Inloggning** med Supabase Auth, e-post med magic link, inga lösenord. En användare med `profiles.active = false`
   ser en sida som säger att kontot väntar på aktivering av administratören, och inget annat.

## Tema

- Bakgrund varmvit `#FBF8F5`. Primär/knappar korall `#F2735C`. Sekundär/lyckade tillstånd salvia `#9DB8A0`.
  Accent/etiketter lavendel `#A99AD8`. Text mörk varmgrå (t.ex. `#2B2623`), aldrig ren svart. Kort i vitt med mjuk
  skugga och rundade hörn (12–16 px).
- Typsnitt: **Fredoka** för rubriker, **Nunito** för brödtext (Google Fonts). Rubriker får vara vänliga, inte
  skrikiga.
- Stadierna i affärer har egna färger i samma palett: New lavendel, Qualified lavendel mörkare, Demo korall ljus,
  Pilot proposal korall, Decision salvia ljus, Won salvia, Lost varmgrå.
- Mobil först: bottennavigation med fem ikoner på telefon (Min dag, Företag, Affärer, Mötesstöd, Material), sidonavigation
  på desktop; Administration bara för admin/reviewer. Alla formulär fungerar med en tumme; stora tryckytor; inga
  tabeller bredare än skärmen utan kort-vy.
- Tillgänglighet: kontrast enligt WCAG AA, fokusmarkering synlig, alla ikonknappar med text eller aria-label.

## Vyer

### 1. Min dag (`/`)
- Läser vyn `v_my_day` (RLS ger bara användarens affärer). Visar: nästa steg som förfaller i dag eller är försenade
  överst (korall), sedan kommande, varje rad med affärens titel, organisation, stadium och nästa steg.
- Snabbknappar: *Nytt möte* (öppnar aktivitetsformuläret), *Nytt företag*, *Hur kan Krusgraph hjälpa?* (går till
  Mötesstöd).
- För reviewer/admin dessutom en ruta *Att granska*: förslag med `status = needs_review` och påståenden, problemkort
  och mallar med `status in ('draft','imported')`, med antal och länk till Administration.
- Tomt tillstånd: "Inget planerat. Registrera ett möte eller ett företag."

### 2. Företag & kontakter (`/organisations`)
- Lista över `organisations` (sök på namn, filter på ägare och bransch), kort-vy på mobil. Klick öppnar företaget med
  flikarna *Kontakter*, *Affärer*, *Aktiviteter*, *Problem*.
- Formulär företag: name (obligatoriskt), org_number, country (standard SE), industry, website, size_band, notes.
  `created_by` och `owner_id` = inloggad användare.
- Formulär kontakt: full_name (obligatoriskt), title, email, phone, lawful_basis (standard business_contact; välj
  consent eller contract med consent_note). Visa texten om personuppgifter (regel 6). Visa `retain_until` om satt.
- Dubblettkoll: innan ett företag sparas, sök på namnet och visa "Finns redan?" med träffar (bara de användaren får se).

### 3. Affärer (`/deals`)
- Kanban på desktop med kolumnerna New, Qualified, Demo, Pilot proposal, Decision, Won, Lost; lista grupperad per
  stadium på mobil. Dra-och-släpp eller en stadium-väljare på kortet uppdaterar `deals.stage`. Lost kräver
  `lost_reason` (databasen avvisar annars; visa fel vänligt).
- Nytt: title, organisation (sök bland de företag användaren ser), primary_contact, stage, next_step, next_step_due,
  expected_decision. `owner_id` och `created_by` = inloggad.
- Affärssida: sidhuvud med stadium och nästa steg; flikar *Aktiviteter* (tidslinje, nytt möte/samtal/e-post/demo/
  anteckning med happened_at, summary, next_step, next_step_due), *Problem* (kundens problem med koppling till ett
  problemkort via `problems.problem_card_id`; knappen *Hur kan Krusgraph hjälpa?* med problemets text förifylld),
  *Förslag* (lista, skapa nytt från mall), *Medlemmar* (`deal_members`; en seller kan lägga till en kollega eller
  partner, en partner ser bara listan).
- Skapa förslag: välj mall (bara `templates` med status approved/imported, dvs. det RLS ger), språk, fyll i
  platshållarna `{{organisation}}` `{{contact}}` `{{seller}}` `{{date}}` från affären, visa den ifyllda texten
  redigerbar i ett enkelt Markdown-fält, pris tomt (regel 5), fältet *Löften utöver mallen* (`promises`) med
  hjälptexten "Allt här måste Gustav godkänna innan förslaget får skickas." Spara som `draft`; om pris eller löften
  fyllts i sätter databasen `needs_review`. Knappen *Skicka för granskning* sätter `needs_review`. Knappen *Markera som
  skickat* sätter `sent` (databasen vägrar om granskning krävs; visa felet). *Accepterat* / *Avböjt* bara från `sent`.
- Bilaga *Påståenden*: välj ur `claims` (bara approved/imported) som kopplas i `proposal_claims` och visas under
  förslagstexten med text, omfattning, källa och datum, ordagrant.
- Kundlänk (bara admin/seller, bara på approved/sent): skapa rad i `proposal_links` (requires_login förvalt true,
  recipient_email = kontaktens e-post), visa länken `/p/<token>`, utgångsdatum, antal öppningar, knapp *Återkalla*
  (sätter `revoked_at`). Sidan `/p/<token>` i v1: kräver inloggning och visar förslagets `body` och påståendena för
  en inloggad användare som får se affären; en kundinloggning är ett beslut för Gustav (visa inte sidan publikt).

### 4. Mötesstöd (`/support`)
- Ett stort textfält: "Vad sa kunden?" och knappen **Hur kan Krusgraph hjälpa?** (korall). Vid klick: anropa
  `search_meeting_support(q, lang)`. För varje träff visa ett kort från `v_meeting_support`: titel, symptom, *Så
  hjälper Krusgraph* (bara textfältet ur kortet), frågor att ställa, det fiktiva exemplet märkt *Exempel på syntetisk
  data*, och under det listan *Godkända påståenden* med text ordagrant, omfattning, källa och datum. Påståenden med
  `claim_status = 'imported'` märks *från publicerad källa, ej bekräftad i portalen*.
- Inga träffar: visa *Otillräckligt underlag* (regel 4) och knappen *Spara som kundproblem* som skapar en rad i
  `problems` med `status = 'no_match'` på vald affär.
- Bläddra: under sökfältet listas alla kort i `v_meeting_support` (tre i seeden) så att en säljare kan läsa in sig.
- Flik *Vanliga IT-frågor*: `trust_answers` (approved/imported) som fråga/svar; svaret visas ordagrant på engelska,
  med `answer_sv` ovanför när den finns, och källa + datum under. Knappen *Kopiera* kopierar svaret ordagrant.

### 5. Material (`/material`)
- Tre flikar: *Påståenden* (alla `claims` användaren får se, sök och filter på källa/datum, kopiera ordagrant),
  *Mallar* (`templates`, läs, förhandsvisa på båda språken), *Problemkort* (samma kort som i Mötesstöd).
- En seller kan föreslå ett nytt påstående: formulär text, scope, source, source_date; sparas med `status = 'draft'`
  och `owner_id` = inloggad; texten "Gustav granskar innan det syns för andra."

### 6. Administration (`/admin`, bara admin och reviewer)
- *Granskning*: listor över `claims`, `trust_answers`, `problem_cards` och `templates` med status draft/imported; per
  rad knapparna *Godkänn* (status approved) och *Dra tillbaka* (withdrawn) med `review_note`. Förslag med
  `needs_review`: visa texten, pris, löften och knapparna *Godkänn* / *Skicka tillbaka* (status draft med review_note).
- *Användare* (bara admin): `profiles` med roll, aktiv, partnerbolag; `role_invitations` för att bjuda in en e-post
  med roll i förväg; aktivera/inaktivera.
- *Gallring* (bara admin): resultatet av `contacts_due_for_erasure()` med knapparna *Radera* (delete) och *Förläng*
  (uppdatera `last_contact_at` till nu). Visa inställningen `contact_retention_months` ur `app_settings` och säg att
  den är tom tills beslut.
- *Inställningar* (bara admin): `app_settings` som nyckel/värde med beskrivning.
- *Logg* (bara admin): `audit_log`, senaste 200 raderna, filter på tabell.

## Databasen (använd exakt dessa namn)

Tabeller: `app_settings`, `profiles`, `role_invitations`, `organisations`, `contacts`, `deals`, `deal_members`,
`activities`, `problems`, `problem_cards`, `problem_card_claims`, `claims`, `trust_answers`, `templates`,
`proposals`, `proposal_claims`, `proposal_links`, `audit_log`.
Vyer: `v_my_day`, `v_meeting_support`. Funktioner: `search_meeting_support(q text, lang 'sv'|'en')`,
`contacts_due_for_erasure()`.
Enum-värden: stage `New | Qualified | Demo | Pilot proposal | Decision | Won | Lost`; activity kind
`meeting | call | email | demo | note`; status på register `draft | imported | approved | withdrawn`; proposal
status `draft | needs_review | approved | sent | accepted | declined | withdrawn`; roller
`admin | seller | partner | reviewer`.
Fel från databasen (RLS eller trigger) visas som vänliga meddelanden på valt språk, aldrig som råa feltexter.

## Leverans

Börja med inloggning, Min dag, Företag & kontakter och Affärer. Sedan Mötesstöd, Material, Administration. Visa en
förhandsvisning efter varje steg. Fråga om något i prompten är oklart i stället för att gissa.
