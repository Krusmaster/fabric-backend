# Roadmap — det som inte är i v1

v1 är affärsdata med roller (README). Varje punkt nedan är **inte** byggd, inte påbörjad i schemat och tas inte in
utan att Gustav först fattat beslutet som står vid punkten (se docs/DECISIONS-FOR-GUSTAV.md). Ordningen är ingen
prioritering.

| Område | Vad det skulle vara | Beslut som krävs först | Varför det inte är i v1 |
| --- | --- | --- | --- |
| **Fakturering** | fakturaunderlag från ett vunnet förslag, koppling till bokföringssystem | priser och prismodell (beslut 1), bokföring (beslut 3) | inga priser finns; fabric-backends docs/PRICING-NOTES.md säger uttryckligen att inget fakturerar och att inget byggs innan ett första betalande samtal skett |
| **Bank** | betalningsavstämning mot bankkonto | bokföring (beslut 3), vilket system som är master | kräver bankdata i portalen; inget skäl i v1 |
| **Provision** | provision per partner och affär, utbetalningsunderlag | partneravtal och provisionssatser (beslut 2) | inga satser får finnas i repot; avtalet finns inte |
| **Kampanjer** | utskick, listor, spårning av öppningar | rättslig grund för marknadsföring mot kontakter, gallring (beslut 4) | kontaktuppgifter är personuppgifter; utskick är en annan behandling än affärskontakt |
| **Transkript** | inspelning/transkribering av kundmöten, sammanfattning | samtycke från kunden per möte, lagringstid, var transkriptet lagras | ett transkript innehåller personuppgifter och ofta kundens interna uppgifter; portalen ska aldrig hålla kunders Fabric-data |
| **Scanning** | fotografera visitkort/dokument och läsa in fält | samma som kampanjer och transkript: rättslig grund, gallring, var bilden lagras | bilder av visitkort är personuppgifter; OCR-tjänst är en tredje part |
| **Fri LLM-chatt i mötesstödet** | en modell som formulerar svar fritt | regeln i README: inga påståenden utanför `claims` | v1:s knapp söker bara i godkända kort och påståenden och svarar annars *otillräckligt underlag*; en fri chatt kan hitta på |
| **Kundportal utan inloggning** | förslagslänk som öppnas utan konto | inloggning för kundlänkar (beslut 6) | v1 kräver inloggning tills beslutet är taget |
| **Koppling till Krusgraph-tjänsten** | läsa användningsstatistik eller status direkt från krusgraph.com | om säljportalen alls ska tala med produkten | portalen ska inte ha tokens eller nycklar till Krusgraph, Fabric eller Entra |

Det som hör till v1 men saknas tills beslut tagits: ett prisfält med värde (tomt i v1), gallringstiden för kontakter,
standardspråk, inloggningskrav på kundlänkar.
