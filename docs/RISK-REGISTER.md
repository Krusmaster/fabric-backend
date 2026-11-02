# Riskregister (internt)

Åtta riskhypoteser för Krusgraph, skrivna 2 november 2026 (runda n76) från vad repot innehåller, och en nionde (R9)
tillagd samma dag i runda n83 med överlappsfönstret i refresh-rotationen. Varje "befintlig
kontroll" pekar på en fil eller funktion i repot som belägg; en kontroll som bara finns i huvudet på någon står inte
här. Sannolikhet och konsekvensgrad är **ej bedömt** överallt där inget underlag finns i repot (ingen incident, ingen
kund, ingen mätning), och de fylls inte i för att en rad ska se grön ut. Ägare för allt är Gustav. Nästa granskning är
ett förslag, inte en bokad tid.

Två sorters rader: **produktrisk** (något i koden eller tjänsten ger fel resultat eller rör fel sak) och
**affärshinder** (något utanför koden stoppar eller förvränger affären). En rad kan bara vara det ena.

Vad registret inte är: ingen riskbedömning enligt någon standard, ingen poäng. `docs/ISO27001-SELF-ASSESSMENT.md`
listar kontrollerna; `docs/TRUST.md` är det som får sägas utåt; `docs/MISSING-EVIDENCE.md` är listan över bevis som
saknas.

## R1 Fel relation eller summeringsnivå accepteras

| Fält | Innehåll |
| --- | --- |
| Typ | Produktrisk |
| Orsak | Motorn föreslår nycklar och relationer från namn (K0–K5, R0–R5) och en person godtar förslaget utan att läsa regeln eller räkna mot raderna; eller en header-summa (orders.order_amount) summeras över radnivån. |
| Händelse | En API för GraphQL, en semantisk modell eller en ontologi skapas med en relation som inte stämmer, eller en rapport räknar en total två gånger. |
| Konsekvens | Fel siffror i det kunden bygger; förtroendet för "beviset bakom varje länk" skadas. |
| Område | Engine (`infer.py`, `evidence.py`, `graphs.py`, `amounts.py`), MCP tools (`validate_plan`, `suggest_relationships`, `create_*`). |
| Sannolikhet | Ej bedömt. Benchmarken (`examples/benchmark/README.md`, `docs/INFERENCE.md`) mäter på syntetiska scheman med facit skrivet av samma projekt; ingen extern körning finns (`docs/MISSING-EVIDENCE.md` rad 8). |
| Konsekvensgrad | Ej bedömt (ingen kund har byggt på ett resultat ännu). |
| Befintliga kontroller | Regeln bakom varje nyckel och relation i svaret (`fabric_backend/infer.py`, `Plan.summary()`); `validate_plan` räknar dubbletter, NULL och föräldralösa referenser mot raderna (`fabric_backend/evidence.py`); `suggest_relationships` kontrollerar kandidater mot data (`fabric_backend/graphs.py`); "summan som dubbleras" pekas ut från namn och räknas per header (`fabric_backend/amounts.py`); `review_plan` håller beslut och kontroller åtskilda och markerar kontroller på ändrade tabeller som gamla (`fabric_backend/review.py`); demon säger uttryckligen att "accepterad" inte är "verifierad" (`fabric_backend/demo_app.py`); ärendeformuläret "A wrong relationship" (`.github/ISSUE_TEMPLATE/`); de skapande verktygen är dry run som standard (R3). |
| Åtgärd | Få en person utanför projektet att köra `/check` på egna tabeller och skriva ner rätt och fel (MISSING-EVIDENCE rad 8); läs om Power BI-autodetektens regler på Learn innan benchmarkens approximation citeras (`examples/benchmark/README.md`). Ingen kodändring föreslås här; Engine-området äger motorn. |
| Ägare | Gustav |
| Nästa granskning | Efter den första externa körningen av `/check`, eller senast vid nästa versionstagg. |

## R2 Kunddata når en AI-klient kunden inte godkänt

| Fält | Innehåll |
| --- | --- |
| Typ | Produktrisk |
| Orsak | En anställd kopplar Krusgraph till en MCP-klient (Claude, VS Code, Cursor, Glama, Lovable) som organisationen inte har godkänt; verktygens svar (namn, antal, exempelrader, frågeresultat) går då till den klientens leverantör. |
| Händelse | Tabellnamn, exempelrader eller frågeresultat lämnar organisationen till en leverantör utan avtal. |
| Konsekvens | Ett brott mot kundens egna regler; Krusgraph pekas ut som vägen dit. |
| Område | MCP tools and errors (`entra.py`, `server.py`), klientregistreringen (`registration.py`, `registration_flow.py`), Docs (`docs/SCOPES.md`, `docs/CLIENT-REGISTRATION.md`, `docs/TRUST.md`). |
| Sannolikhet | Ej bedömt. |
| Konsekvensgrad | Ej bedömt; beror på kundens tabeller. |
| Befintliga kontroller | Varje anrop sker med den inloggade personens egna Fabric-behörigheter och delegerade scopes; appen har inga applikationsbehörigheter (`docs/SCOPES.md`, `deploy/azure_containerapp.py` `REQUIRED_SCOPES`); en administratör måste ge admin consent en gång, och kan dra tillbaka appen under Enterprise applications (`fabric_backend/page_templates/it.html`); tokens valideras mot appens audience, utgivare och scope (`fabric_backend/entra.py`, `tests/test_security.py`); valfri tenant-lista `ENTRA_ALLOWED_TENANTS` (`entra.py`); för andra klienter än Claude visar Krusgraph en egen samtyckessida per klient med namn, domän och återkopplingsadress (`fabric_backend/registration_flow.py`, `docs/CLIENT-REGISTRATION.md`); kolumner som ser ut som personuppgifter maskas i exempelrader och lämnas utanför utkast till frågor (`fabric_backend/privacy.py`); inget tabellinnehåll lagras på servern (`SECURITY.md`). Vad Krusgraph inte styr: vilken AI-klient en person använder, och vad kundens avtal med den leverantören säger. |
| Åtgärd | Säg det rakt ut i `docs/TRUST.md` och på /it: AI-klienten är kundens egen leverantör och underbiträde, inte Krusgraphs; hänvisa administratörer till att styra samtycke per app i Entra. Ingen kodändring föreslås här. |
| Ägare | Gustav |
| Nästa granskning | När en kund med egen MCP-klientpolicy ansluter, eller vid nästa versionstagg. |

## R3 Ett skapande verktyg ändrar fel objekt

| Fält | Innehåll |
| --- | --- |
| Typ | Produktrisk |
| Orsak | Ett namn i anropet pekar på ett befintligt objekt i arbetsytan som inte är det personen menade; eller en uppdatering ersätter en definition som någon ändrat i portalen. |
| Händelse | En API, modell, ontologi, rapport, notebook eller pipeline uppdateras på plats och förlorar något som fanns. |
| Konsekvens | Arbete i kundens arbetsyta går förlorat eller måste återställas från portalens historik. |
| Område | MCP tools and errors (`server.py`, de nio `create_*`-verktygen), Engine (`deploy.py`). |
| Sannolikhet | Ej bedömt. De skapande anropen som körts live gäller den syntetiska demo-arbetsytan (`fabric_backend/tool_status.py` `LATER_LIVE`, `docs/LIVE-TEST.md`). |
| Konsekvensgrad | Ej bedömt. |
| Befintliga kontroller | Åtta av nio skapande verktyg är dry run som standard och svarar med vad de skulle skapa tills `dry_run=false` (`fabric_backend/server.py`, `tool_params.DryRun`; `tool_status.NO_DRY_RUN`); inget verktyg raderar något (`fabric_backend/deploy.py` `create_or_update_api`, docstrings i `server.py`, annoteringarna `WRITE`); `create_backend` skriver ingenting när uppdateringen skulle ta bort relationer som API:et har (`server.py`, `_dropped_relationships`); `create_report` lämnar en rapport med samma namn orörd (`server.py`); `plan_drift` och `lineage` visar vad en omkörning skulle röra (`fabric_backend/drift.py`, `fabric_backend/lineage.py`); skapande kräver personens egen Contributor-roll i arbetsytan (`docs/SCOPES.md`); tester för avvisningar (`tests/test_create_refusals.py`, `tests/test_creating_tools.py`). Lucka: `create_backend` har ingen dry run (`tool_status.NO_DRY_RUN`), och en uppdatering av en modell eller ontologi ersätter definitionen så att tillägg gjorda utanför planen försvinner (sagt i verktygens egna texter). |
| Åtgärd | Beslut för Engine/MCP tools-området: en dry run för `create_backend`, eller en varning i svaret när objektet redan finns. Till dess säger /docs, /it och verktygstexterna vad som ersätts. |
| Ägare | Gustav |
| Nästa granskning | Vid nästa liveprotokoll (`docs/LIVE-TEST.md`). |

## R4 Fel person läser en affär i säljportalen

| Fält | Innehåll |
| --- | --- |
| Typ | Affärshinder |
| Orsak | Säljportalen (partnerarbetsytan) ligger **utanför detta repo**. Här finns bara den publika sidan /partners utan inloggning och ett designkoncept för en partnerarbetsyta där inloggningen uttryckligen inte är kopplad (`docs/design/little-connections/`, "Sign-in is not connected"). |
| Händelse | En partner eller en anställd ser en annan parts affär, pris eller kontakt. |
| Konsekvens | Avtalsbrott mot partnern; skada för kundens upphandling. |
| Område | Utanför repot. Hänvisning: portalens eget repo och dess ägare bedömer behörighetsmodell, loggning och radering. |
| Sannolikhet | Ej bedömt (inget underlag här). |
| Konsekvensgrad | Ej bedömt. |
| Befintliga kontroller | Inga i detta repo. Det som finns här rör inte affärer: /partners är en informationssida, och inga kundnamn eller affärsuppgifter får finnas i repot (`CONTRIBUTING.md`, "What never goes into the repository"; `tests/test_site.py`). |
| Åtgärd | Föra in raden i portalens eget riskregister med samma kolumner; tills portalen har en behörighetsmodell som går att peka på hålls affärer utanför den. |
| Ägare | Gustav |
| Nästa granskning | När säljportalen får sin första riktiga användare. |

## R5 Inaktuellt säljmaterial överdriver

| Fält | Innehåll |
| --- | --- |
| Typ | Affärshinder |
| Orsak | Ett deck, ett e-postutkast eller en portalanmälan skrivs av från sajten vid en tidpunkt och lever vidare när statusorden ändras; eller ett ord smyger in som produkten inte kan backa upp. |
| Händelse | En köpare läser "testad" om något som är ett utkast, eller en siffra som inte finns. |
| Konsekvens | Förtroendet går förlorat i första mötet; i värsta fall ett avtal på fel premiss. |
| Område | Docs and submission (`README.md`, `docs/`, `deploy/SUBMISSION.md`), Website (statusord), och materialet utanför repot. |
| Sannolikhet | Ej bedömt. |
| Konsekvensgrad | Ej bedömt. |
| Befintliga kontroller | En statuskälla per verktyg som sajt, docs, llms.txt och verktygens egna svar renderas från (`fabric_backend/tool_status.py`); tester som stoppar säljord och statusord som inte stämmer (`tests/test_site.py`, `SALES`, `test_status_words_on_the_site_match_tool_status`, `_CREATE_CLAIMS` över `README.md` och alla `docs/*.md`); `tests/test_submission.py` håller portalanmälans siffror lika med servern; regeln mot påståenden produkten inte kan backa (`CONTRIBUTING.md`); listan över bevis som saknas (`docs/MISSING-EVIDENCE.md`); FAQ:ns regler om källor och "overifierat" (`docs/FAQ-COMPETITION.md`). Lucka: material utanför repot (deck, mejl) testas inte. |
| Åtgärd | Datera allt säljmaterial och skriv statusord ur `tool_status` på datumet; när ett verktyg ändrar status, uppdatera eller dra in decket. `docs/TRUST.md` är underlaget för vad som får sägas om säkerhet. |
| Ägare | Gustav |
| Nästa granskning | Före varje kundmöte där ett deck visas; senast vid nästa versionstagg. |

## R6 Grundaren otillgänglig

| Fält | Innehåll |
| --- | --- |
| Typ | Affärshinder |
| Orsak | En person driver tjänsten, äger Azure-prenumerationen, Entra-appen, GitHub-organisationen och domänen. |
| Händelse | Klienthemligheten går ut, certifikatet förnyas inte, en säkerhetsrapport blir obesvarad, eller en kund behöver hjälp, och ingen kan agera. |
| Konsekvens | Tjänsten slutar ta emot inloggningar; kundens egna objekt i Fabric påverkas inte (de ligger i kundens arbetsyta med kundens behörigheter). |
| Område | Deployment (`deploy/`), Docs (`docs/OPERATIONS.md`), Website (/it). |
| Sannolikhet | Ej bedömt. |
| Konsekvensgrad | Ej bedömt; `docs/OPERATIONS.md` §9 punkt 5 namnger det som inte kan vänta. |
| Befintliga kontroller | Överlämningen i `docs/OPERATIONS.md` §9 (åtkomst, konfiguration, var hemligheterna ligger med namn, drift, det som inte kan vänta); deploy-skriptet som kod (`deploy/krusgraph.sh`, `deploy/azure_containerapp.py`) med `--from-azure` som återskapar konfigurationen, `--doctor` som visar tjänstens tillstånd inklusive hemlighetens och certifikatets datum, och `--backup` för registreringstabellen (`docs/OPERATIONS.md` §8; `tests/test_deploy_doctor.py`); en helt ny driftsättning från början i `deploy/KRUSGRAPH-START.md`; sidan /it, "If Gustav is unavailable" (`fabric_backend/page_templates/it.html`); MIT-licensen gör att en kund kan köra koden i egen Azure (`LICENSE`); inget kunddata finns att lämna tillbaka (`SECURITY.md`). Luckor: §8 har inte körts mot Azure (sagt i §8); listan över vem som har åtkomst förs utanför repot (§9 punkt 1), och om någon annan faktiskt har den framgår inte här. |
| Åtgärd | Namnge en andra person med Contributor på resursgruppen, ägarskap på Entra-appen, GitHub-organisationen och registraren; kör `--doctor` en gång mot den riktiga prenumerationen och skriv datumet i §8. |
| Ägare | Gustav |
| Nästa granskning | Vid klienthemlighetens utgångsdatum (raden i `--doctor`), och senast vid nästa versionstagg. |

## R7 Preview-beroenden ändras

| Fält | Innehåll |
| --- | --- |
| Typ | Produktrisk |
| Orsak | Krusgraph bygger på Fabric-ytor som är preview eller nya: ontologi-objektet i Fabric IQ, Fabric IQ MCP, speglade databaser (Snowflake, Azure SQL, Cosmos DB, SAP) och Business Central-spegling via de speglade källorna, Rayfin. Microsoft kan ändra format, behörighet eller tenant-inställning. |
| Händelse | `create_ontology` eller `ontology_draft` skriver ett format Fabric inte längre tar emot; en speglad källa svarar annorlunda; en tenant-inställning stänger av objektet. |
| Konsekvens | Verktyget faller, med ett fel som kan se ut som Krusgraphs eget. |
| Område | Engine (`ontology.py`, `platforms/fabric.py`), MCP tools (`create_ontology`, `list_sources`), Docs (`docs/FAQ-COMPETITION.md`, `docs/ECOSYSTEM-WATCHLIST.md`). |
| Sannolikhet | Ej bedömt; har hänt en gång i annan form: Fabric svarade 403 `FeatureNotAvailable` tills "Users can create Ontology (preview) items" slogs på (`fabric_backend/tool_status.py` `LATER_LIVE["create_ontology"]`). |
| Konsekvensgrad | Ej bedömt. |
| Befintliga kontroller | Ontologiformatet är verifierat mot inspelade definitioner, inte mot ett löfte (`fabric_backend/ontology.py`); Fabrics egen felkod skickas vidare i svaret (`fabric_backend/errors.py`, `kind`); goldenfiler låser motorns svar så att ett formatbyte syns i diffen (`tests/test_golden.py`); källor utöver lakehouse är märkta Experimental tills en livekörning (`fabric_backend/tool_status.py`); varje Learn-läsning dateras med `ms.date` och commit (`docs/FAQ-COMPETITION.md`, `docs/FET-PLAN.md`); `docs/ECOSYSTEM-WATCHLIST.md` håller datum för närliggande servrar. |
| Åtgärd | Läs om de preview-sidor Krusgraph lutar sig mot före varje versionstagg och skriv datum; håll ontologi-skapandet bakom `ontology_write`/operatörsflaggan tills objektet lämnar preview (`deploy/krusgraph.example.json`). |
| Ägare | Gustav |
| Nästa granskning | Vid nästa versionstagg, eller när Microsoft meddelar GA för ontologi-objektet. |

## R8 För många speciallösningar säljs

| Fält | Innehåll |
| --- | --- |
| Typ | Affärshinder |
| Orsak | Varje pilot vill ha sitt system (SAP, Younium + Salesforce, nordiska ERP), sin dialekt och sitt undantag; en enmansverksamhet lovar det för att få affären. |
| Händelse | Motorn får kundspecifika grenar, eller löften ges om pack som inte finns. |
| Konsekvens | Underhållet växer snabbare än intäkten; produkten blir konsulttimmar. |
| Område | SAP pack (`fabric_backend/packs/`), Engine (`platforms/`), Docs (`docs/PILOT.md`, `docs/PRICING-NOTES.md`). |
| Sannolikhet | Ej bedömt. |
| Konsekvensgrad | Ej bedömt. |
| Befintliga kontroller | Systemkunskap ligger som data i pack, inte som kod (`fabric_backend/packs/*/*.json`, `fabric_backend/sap_pack.py`), med källa och "unverified" per rad där källan inte kunnat öppnas (`docs/YOUNIUM-SALESFORCE.md`, `docs/NORDIC-PACK-SPIKE.md`); plattformskod bakom en adaptergräns som ett test bevakar (`docs/ARCHITECTURE.md`, `tests/test_architecture.py`); pilotens in- och ut-lista (`docs/PILOT.md`, "Scope"); fri och betald nivå följer produktens egen form (`docs/PRICING-NOTES.md`). |
| Åtgärd | Regel för säljsamtal: ett nytt system blir ett pack (data) eller sägs nej till; ingen kundgren i motorn. Skriv regeln i `docs/PILOT.md` när nästa pilot tar form. |
| Ägare | Gustav |
| Nästa granskning | Efter den första piloten. |

## R9 En stulen gammal refresh-token används inom överlappsfönstret

| Fält | Innehåll |
| --- | --- |
| Typ | Produktrisk |
| Orsak | Sedan n83 får den refresh-token som just ersattes samma svar igen i 60 sekunder, från samma klient-id, så att ett omförsök efter ett förlorat svar inte loggar ut användaren (`docs/REFRESH-ROTATION.md`). Klient-id:n är publika (VS Codes är en URL), så kravet på samma klient-id stoppar inte en tjuv. |
| Händelse | Någon som har kommit över en refresh-token (en logg hos klienten, en kopierad konfigurationsfil, en angripare på användarens dator) använder den inom 60 sekunder efter ägarens förnyelse och får samma access-token (giltig ungefär en timme) och den aktuella refresh-token. **Det upptäcks inte**: linjen avslutas inte och ingen `refresh_reused` loggas, bara `refresh_replayed`, som ser ut som ett vanligt omförsök. |
| Konsekvens | Tjuven kan anropa Fabric som användaren, med användarens behörigheter, och förnya vidare. Upptäckten kommer först när någon av dem visar en token mer än 60 sekunder efter att den ersattes; då avslutas linjen som förut. |
| Område | MCP tools and errors (klientregistreringen, `registration_flow.py` `Layer._refresh`), Docs (`docs/CLIENT-REGISTRATION.md`, `docs/TRUST.md`, `docs/REFRESH-ROTATION.md`, /privacy). |
| Sannolikhet | Ej bedömt. Ingen incident; fönstret är bara provat mot ett falskt Entra och en falsk lagring (`tests/test_refresh_rotation.py`). |
| Konsekvensgrad | Ej bedömt; samma som en stulen refresh-token utan fönster, men utan upptäckt de första 60 sekunderna. |
| Befintliga kontroller | Rotationen är kvar och återanvändning efter fönstret, eller mer än en rotation bakåt, avslutar linjen (`tests/test_refresh_rotation.py`, `test_after_the_window_the_old_token_ends_the_line_as_before`, `test_the_window_reaches_one_rotation_back_only`); fel klient-id får aldrig det sparade svaret och avslutar linjen (`test_another_client_id_never_gets_the_stored_answer_and_still_ends_the_line`); det sparade svaret är krypterat både med serverns nyckel och med en nyckel härledd ur den ersatta token, som tabellen inte har, och fönstrets slut ingår i det som förseglingen skyddar, så det öppnas aldrig efter fönstret (`test_after_the_window_the_stored_answer_is_never_opened_and_the_next_rotation_replaces_it`); ingen token i klartext i tabell eller logg (`test_no_token_in_clear_in_the_table_or_the_log`); en administratör kan dra tillbaka appen i Entra, vilket stoppar varje förnyelse. Claudes väg via `/mcp` berörs inte (`test_claude_s_path_through_mcp_is_unchanged_by_the_window`). |
| Åtgärd | Läs loggarna efter driftsättning: `refresh_replayed` med `when` (`retry`, `conflict`, `entra_refused`) per klient. Många omspelningar från en klient som inte borde göra omförsök är ett skäl att korta fönstret eller ta bort det. |
| Ägare | Gustav |
| Nästa granskning | När Log Analytics behåller konsolraderna och en vecka av `refresh_replayed` kan läsas, eller vid nästa versionstagg. |

## Hur registret hålls levande

En rad ändras i samma commit som den kontroll den pekar på, och "Nästa granskning" flyttas när granskningen är gjord.
Sannolikhet och konsekvensgrad får ett värde först när något i repot kan bära det: en incident, en mätning, ett
protokoll i `docs/LIVE-TEST.md` eller en kund. Fram till dess står det ej bedömt.
