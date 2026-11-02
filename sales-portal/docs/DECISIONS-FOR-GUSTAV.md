# Beslut för Gustav

Öppna beslut som v1 inte kan ta själv. Inget nedan är föreslaget som färdigt svar; där det finns ett underlag i
fabric-backend står det vilket. Inga priser, provisionssatser eller svarstider står i detta repo.

## 1. Priser och prismodell

- Förslagets prisfält (`proposals.price`) är tomt i v1 och mallen *Avgränsad pilot* har `[PRIS]` som platshållare.
- Underlag: `docs/PILOT.md` i fabric-backend har tre prisnivåer markerade *proposals to test, not a price list*, och
  `docs/PRICING-NOTES.md` är en gräns mellan gratis (läsande verktyg) och betalt (skapande, drift) utan belopp.
- Att besluta: finns det ett listpris alls i v1, eller är varje ifyllt pris ett specialpris som Gustav granskar?
  v1 antar det senare: en trigger kräver granskning innan ett förslag med ifyllt pris eller löften får status `sent`.

## 2. Partneravtal och provision

- Vad en partner får lova, i vilket namn förslaget skickas (Kruse Consulting eller partnern), och om partnern alls
  får se pris.
- Provisionssatser: inga i repot. Provision är roadmap (docs/ROADMAP.md) och byggs inte före ett avtal.
- Att besluta: krävs ett påskrivet partneravtal innan rollen `partner` aktiveras? v1 antar ja (`profiles.active`
  sätts av admin).

## 3. Bokföring

- Vilket system är master för kund, faktura och betalning, och ska portalen någonsin skriva dit?
- v1 lagrar vunna affärer (`stage = Won`, `won_at`) men inget belopp som bokförs.

## 4. Gallring och rättslig grund för kontakter

- `app_settings.contact_retention_months` är tom i seeden; tills den sätts får nya kontakter inget `retain_until`
  och gallringslistan är tom.
- Att besluta: antal månader efter senaste aktivitet (`last_contact_at`) innan en kontakt gallras; om förlorade
  affärers kontakter gallras tidigare; om `lawful_basis = business_contact` (intresseavvägning) räcker eller om
  samtycke ska samlas in för partnerregistrerade kontakter.
- Också: vem svarar på en registrerads begäran om utdrag eller radering, och inom vilken tid (står inte här).

## 5. Språk

- Gränssnittet är sv + en. Påståenden och trust-svar är ordagrant på engelska (källans språk); problemkort och
  mallar finns på båda språken.
- Att besluta: standardspråk för nya användare, och om ett förslag till en svensk kund får innehålla ett engelskt
  påstående ordagrant eller om Gustav godkänner svenska översättningar som egna påståenden (v1: översättningar är egna
  rader i `claims` med `language = 'sv'` och `status = draft` tills de godkänts).

## 6. Inloggning för kundlänkar

- `proposal_links.requires_login` är `true` som standard: kunden måste logga in (magic link till kontaktens e-post)
  för att öppna förslaget. Alternativet är en hemlig länk med utgångsdatum utan inloggning.
- Att besluta: vilket, och hur länge en länk gäller (standard i seeden: 30 dagar, ändras i `app_settings`).

## 7. Importerade påståenden

- Seeden importerar påståenden ordagrant från `fabric_backend/tool_status.py` och `docs/LIVE-TEST.md` (commit
  7799ef7, 2026-11-01) med `status = imported`. Gustav bekräftar eller drar tillbaka varje rad i Administration.
- Att besluta: hur ofta registret uppdateras mot fabric-backend (varje release?), och vem som är ansvarig
  (`claims.owner_id`) för att ett påstående fortfarande stämmer.
