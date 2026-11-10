# n205: kort notis till grundaren (10 november 2026)

**Vad som ändrats**

- **/trust ("Security and data")**, med Markdown-tvilling /trust.md, skriven ur docs/TRUST-PACK.md: vad som passerar
  tjänsten, att inga tabellinnehåll lagras, region (Sweden Central), underbiträden, delegerade behörigheter, hur man
  återkallar, statustabellen (ingen certifiering, attesteringen är ett utkast, inget penetrationstest) och svaren på ett
  säkerhetsformulär. Länkad från sidfoten, /pricing och /choose; finns i sitemap och llms.txt.
- **Ärliga etiketter**: fem verktyg får "(experimental)" sist i titeln i Claudes verktygslista, från samma statuspost som
  webbplatsen: domain_draft, sap_pack_draft, create_views, create_data_agent och compare_semantic_model. create_pipeline
  räknas nu som "created live" (pipeline_shop skapades och kördes 7 november).
- **README**: första raden säger vad Krusgraph gör för Microsoft Fabric och att repot är källkoden; en statustabell per
  verktyg genereras ur tool_status (testad); ett avsnitt "Roadmap" med fem planerade punkter.
- **/choose**: tabellen "Why not just Microsoft's tools?" (fem rader, inga logotyper), länkad från /docs.
- **/pricing**: ett stycke om vad som är gratis i dag, att koden förblir MIT och att en betald teamplan via Microsoft
  Marketplace är planerad (inget pris än). Raden om personuppgiftsbiträdesavtal säger nu att det finns ett utkast och
  att den juridiska texten skrivs med jurist.

**Att observera**: briefen sa att create_backend "skapades live 26–27 okt". Protokollet (docs/LIVE-TEST.md och
tool_status) säger att shop_api *uppdaterades på plats* 27 okt (och från Lovable 30 okt), och att ett *nytt* API ännu
inte skapats live. README och verktygslistan följer protokollet. Har du ett skapande live som inte är protokollfört,
lägg till det i docs/LIVE-TEST.md och tool_status, så följer allt annat med.

**GitHub-inställningar att klicka i** (detaljer i docs/FOUNDER-TODO.md):

1. Description: `Krusgraph: keys and relationships for Microsoft Fabric tables, checked against the rows`
2. Website: `https://krusgraph.com`
3. Topics: microsoft-fabric, mcp, graphql, data-modeling, power-bi, krusgraph
4. Skapa en GitHub Release `v0.8.0` på main med anteckningar ur CHANGELOG.md.

**Driftsätt**: `bash deploy/krusgraph.sh --update`, så att /trust, sidfoten, /pricing, /choose och de nya titlarna syns
på krusgraph.com före LinkedIn-inlägget 08:30 och demon 15:00.
