# n201: kort notis till grundaren (11 november 2026)

**Vad som ändrats**

- **Krusgraph Model läser speglade databaser** (mirrored databases: Azure SQL, SQL Server, Snowflake, open mirroring,
  och SAP speglat via SAP Datasphere), samt warehouses och SQL-databaser. Källväljaren erbjuder alla fyra; granskning
  och kontroll läser källans SQL analytics endpoint, bara läsning.
- **Mållakehouse.** En speglad databas är skrivskyddad, så silver, gold, pipelinen och dess kontroll skrivs till en
  lakehouse du väljer under *Target lakehouse* (standard: den första lakehousen i samma arbetsyta; torrkörningen säger
  vilken). Silveranteckningsboken läser de speglade tabellerna där Fabric har dem i OneLake (`oneLakeTablesPath`, Get
  Mirrored Database på Learn): ingen kopia utanför Fabric, ingen genväg skapas.
- **SAP.** När tabellerna ser ut som SAP:s (VBAK, VBAP, KNA1, MARA, EKKO, EKPO …) visar granskningen SAP-paketets
  nycklar (med MANDT) och länkar, var och en märkt "from the SAP pack" med paketets publika källa, bredvid de härledda.
  Du godkänner eller avvisar dem som vanligt. En notis säger vad spegling levererar (Initial and Delta, Parquet) och
  att SAP Datasphere Premium Outbound Integration är kundens licensfråga med SAP.
- **Detaljsidan i Fabric**: "Compatible with" listar nu Lakehouse, MirroredDatabase, Warehouse och SQLDatabase i båda
  paketen (Org.Krusgraph och Krusgraph.Modeler), texten säger "Works with data mirrored into Fabric", och din
  översiktsfilm (https://youtu.be/69oikujqZDI, som `https://www.youtube.com/embed/69oikujqZDI`) är första bilden i
  "En snabbtitt", med den gamla bilden efter. Video är dokumenterat på Learn (mediaType 1, YouTube-embed).
- **"Certification"-länken** pekar i båda paketen på attesteringssidan, som börjar med "Draft.". Learn dokumenterar
  ingen etikett för länken, så den kan inte döpas om.

**Att göra**

1. **Driftsätt motorn igen:** `bash deploy/krusgraph.sh --update`.
2. **Bygg och ladda upp ett nytt workload-paket** (redigeraren och manifestet har ändrats): i Cloud Shell,
   `workload/scripts/build-package --frontend-app-id <workload-appens id>` (och `--name Krusgraph.Modeler` för det
   publicerade namnet). Versionen blir som alltid `1.0.<antal commits>`, nu 1.0.990 eller högre (skriptet skriver ut
   den), alltså högre än 1.0.937. Ladda upp i Fabric: OneLake catalog → Govern → Workloads → Upload workload, och
   aktivera versionen.

**Prova utan SAP: en Azure SQL-spegling av mill-exemplet**

1. Lägg mill-tabellerna (docs/SAMPLE-MILL.md, sexton syntetiska tabeller) i en Azure SQL Database.
2. Spegla den in i Fabric (Learn: "Tutorial: Configure Microsoft Fabric mirrored databases from Azure SQL Database").
3. Se till att arbetsytan har en lakehouse (med Lakehouse schemas om du vill ha gold-vyerna).
4. + New item → Krusgraph Model → Choose a source → den speglade databasen, schema `dbo`; låt *Target lakehouse* stå
   på standard eller välj en.
5. Find keys and relationships → Check against the rows → välj utdata → läs torrkörningen (den namnger
   mållakehousen) → Create.

**Vad ett riktigt SAP-test kräver**

- Ett SAP-system (S/4HANA, ECC eller BW) och SAP Datasphere med Premium Outbound Integration (kundens licens).
- Ett replikeringsflöde till ADLS Gen2 (Group Delta None, File Type Parquet, Initial and Delta), en lakehouse-genväg
  till containern och New item → Mirrored SAP i Fabric, enligt Learns tutorial.
- Sedan samma steg 4–5 som ovan. Vi har ingen SAP Datasphere: inget av detta är provat mot SAP-data, och
  docs/SAP-MIRRORING.md säger det.

**Overifierat**

- Workloaden "SAP mirroring" i Workload Hub gick inte att identifiera från publika sidor (community-sidan nåddes inte,
  ingen Learn-sida nämner den). Skapar den en speglad databas eller lakehouse-tabeller fungerar den redan; är det en
  egen objekttyp beskriver docs/SAP-MIRRORING.md vad som skulle behövas. Open mirroring-verktygen för SAP som Learn
  listar skapar speglade databaser och fungerar.
- Hur Fabric visar de nya "Compatible with"-namnen, och vilka typnamn källväljaren tar för en speglad databas, syns
  först när paketet är uppladdat.
- Webbplatsen listar fortfarande inte speglade databaser bland källorna (n206 tog bort dem i väntan på n201); det är
  en ändring för en Website-runda.
