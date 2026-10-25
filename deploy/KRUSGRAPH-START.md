# Starta och uppdatera Krusgraph i Azure

Det här paketet använder din befintliga appregistrering och de sex godkända API-behörigheterna. Startsidan, `/explore`, `/start`, `/support`, `/partners`, `/docs`, `/privacy` och `/mcp` körs tillsammans i en Azure Container App. Allt som behövs finns i GitHub-repot; inget zip-paket behövs.

## Första gången: hämta koden och lägg in din konfiguration

1. Öppna Azure Cloud Shell i rätt katalog (Krusgraphs Entra-katalog) och välj Bash.
2. Hämta koden:

   ```bash
   git clone https://github.com/Krusmaster/fabric-backend
   cd fabric-backend
   ```

3. Lägg din egen `deploy/krusgraph.json`. Utgå från `deploy/krusgraph.example.json`:

   ```bash
   cp deploy/krusgraph.example.json deploy/krusgraph.json
   nano deploy/krusgraph.json      # fyll i tenant_id, subscription_id, client_id, registry och company_orgnr
   ```

   Filen är tenant-specifik och ignoreras av git (`.gitignore`), så den checkas aldrig in. Spara en kopia i din lösenordshanterare eller hemkatalog (`~/krusgraph.json`) så att du kan lägga tillbaka den med `cp ~/krusgraph.json deploy/` när Cloud Shell har tömts.

   | Fält | Betydelse |
   | --- | --- |
   | `tenant_id`, `subscription_id`, `client_id` | katalogen, prenumerationen och den befintliga appregistreringen |
   | `domain`, `include_www` | `krusgraph.com`, och om `www` också ska bindas |
   | `location`, `resource_group`, `environment`, `app`, `registry`, `identity` | resursnamnen i Sweden Central |
   | `product_name`, `contact_email` | visas på sajten och i sekretesspolicyn |
   | `company_orgnr` | organisationsnummer; visas på `/privacy` och i sidfoten. Tom sträng döljer raden. Sätts som `COMPANY_ORGNR` på container-appen av både full körning och `--update`. |

## Kontrollera och kör

```bash
bash deploy/krusgraph.sh --check     # kontrollerar katalog, prenumeration, app och medgivanden; skapar inget
bash deploy/krusgraph.sh             # full körning: bygger bilden, skapar/återanvänder resurser, frågar efter hemligheten
```

När terminalen frågar efter klienthemlighetens **VÄRDE**, klistra in det från lösenordshanteraren och tryck Enter. Inmatningen visas inte. Hemligheten förs in i Container Apps hemlighetslager via en tillfällig fil med begränsad åtkomst som tas bort när Azure-anropet är klart. Den finns inte i repot, byggarkivet, kommandohistoriken eller resultatfilen.

Scriptet kontrollerar katalog, prenumeration, app och medgivanden. Sedan registrerar det nödvändiga Azure-resursleverantörer och skapar eller återanvänder dessa resurser i Sweden Central:

| Resurs | Inställning |
| --- | --- |
| Resursgrupp | `rg-krusgraph` |
| Container Apps-miljö | `cae-krusgraph`, Consumption, ingen loggdestination |
| Container App | `krusgraph`, 0–2 instanser, 0,25 CPU / 0,5 GiB |
| Container Registry | Basic, administratörsinloggning avstängd |
| Hanterad identitet | `krusgraph-pull`, endast AcrPull på registret |

Registret har en fast avgift: Microsofts publika pris för Sweden Central kontrollerat 2026-10-23 var 0,1666 USD/dygn, cirka 5 USD för 30 dagar. Byggtid, trafik och serveranvändning kan tillkomma. Faktisk kostnad beror på Azure-avtal, skatter och användning. Container Apps kan skala ned till noll vid inaktivitet. Inga Fabric-kapaciteter eller databaser skapas.

`bash deploy/krusgraph.sh --plan` visar konfigurationen utan Azure-anrop.

## Uppdatera en körande sajt: `--update`

När koden har ändrats (ny version hämtad med `git pull`, eller en annan branch utcheckad) räcker det med:

```bash
cd fabric-backend
git pull                              # eller: git checkout <branch>
cp ~/krusgraph.json deploy/           # om Cloud Shell har tömts
bash deploy/krusgraph.sh --check && bash deploy/krusgraph.sh --update
```

`--update` bygger en ny bild med `az acr build`, uppdaterar container-appen till den nya bilden (ny revision) och sätter de icke-hemliga miljövariablerna (`PRODUCT_NAME`, `CONTACT_EMAIL`, `COMPANY_ORGNR`, `MCP_PUBLIC_URL`, `ENTRA_CLIENT_ID`, `ENTRA_REQUIRED`) samt `KRUSGRAPH_BUILD` (bildens källmärke, `src-…`) från konfigurationen. Det rör inte Entra, hemligheter, domäner eller certifikat och frågar aldrig efter hemligheten; appens befintliga hemlighetsreferens behålls. Efteråt väntar scriptet tills `/healthz` svarar med just det bygget – en gammal revision som fortfarande svarar kan alltså inte passera – och kontrollerar sedan startsidan, `/explore`, `/start`, `/docs`, `/privacy`, demons plan-JSON, stilmallen, OAuth-metadatan och MCP-inloggningskravet på Azure-adressen. `azure-result.json` skrivs om (filen är git-ignorerad). Om appen inte finns ännu stoppar `--update` och hänvisar till den fulla körningen.

## Efter första körningen

När scriptet visar **START KLART** har startsidan och MCP-inloggningskravet kontrollerats på Azure-adressen. Kopiera det offentliga resultatet med `preview_url` och `dns` till chatten. Resultatet sparas också i `azure-result.json`.

I Namecheap ska den gamla URL-omdirigeringen på `@` ersättas med den utskrivna A-posten. `www` ska få det utskrivna CNAME-värdet i stället för parkeringssidan. Lägg till TXT-posterna `asuid` och `asuid.www`. Behåll Microsofts domänverifiering (TXT-posten som börjar med `MS=`) och e-postposterna.

När DNS-posterna är införda, kör:

```bash
bash deploy/krusgraph.sh --bind-domain
```

Det kopplar `krusgraph.com` och `www.krusgraph.com` till appen, beställer Azures hanterade HTTPS-certifikat och kontrollerar sidorna. Certifikatet för roten använder HTTP-validering; www använder CNAME-validering. Vid DNS-fördröjning kan detta steg köras igen.

Efter det återstår att ansluta MCP-klienten och testa en riktig Microsoft-inloggning mot ett Fabric-arbetsutrymme. Lokala tester använder signerade testtoken; de ersätter inte det testet.

## Om ett steg stannar

Kopiera felmeddelandet till chatten. Befintliga Azure-resurser finns kvar och kan fortfarande debiteras. Scriptet använder samma resursnamn när det körs igen. Det stoppar om ett namn redan används av en resurs som inte tillhör denna driftsättning.

För att få adress och DNS-värden igen:

```bash
bash deploy/krusgraph.sh --status
```

Cloud Shell-sessionen är tillfällig. Azure-resurser och sparade hemligheter i Container Apps finns kvar när sessionen stängs. Om klonen har försvunnit: klona igen och lägg tillbaka `deploy/krusgraph.json`. Din dator behöver inte vara på när servern väl körs i Azure.

## Loggar

Container Apps-miljön skapas med `--logs-destination none`. Serverns konsollogg (tid, metod, sökväg, HTTP-status, anslutningens IP-adress; aldrig headers, token eller frågetext) och plattformens systemlogg skickas inte till Log Analytics eller någon lagring; de kan bara följas som en direktström medan en container körs (`az containerapp logs show --follow`). Sekretesspolicyn på `/privacy` beskriver samma sak.

## Källor och kontroll

- [Azure Container Apps: egna domäner och hanterade certifikat](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [Hämta containerbilder med hanterad identitet](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Container Apps-fakturering](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Microsofts publika pris-API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Cloud Shell: filer och lagring](https://learn.microsoft.com/en-us/azure/cloud-shell/persisting-shell-storage)
