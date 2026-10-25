# Starta Krusgraph i Azure

Det här paketet använder din befintliga appregistrering och de sex godkända API-behörigheterna. Hemsidan, `/docs`, `/privacy` och `/mcp` körs tillsammans i Azure Container Apps.

## Kör paketet

1. Öppna Azure Cloud Shell i rätt katalog och välj Bash.
2. Ladda upp `krusgraph-azure.zip` med **Hantera filer / Manage files → Ladda upp / Upload**. Filen hamnar i din hemkatalog.
3. Kör följande:

```bash
unzip -o ~/krusgraph-azure.zip -d ~/krusgraph-azure
cd ~/krusgraph-azure/krusgraph
bash deploy/krusgraph.sh
```

När terminalen frågar efter klienthemlighetens **VÄRDE**, klistra in det från lösenordshanteraren och tryck Enter. Inmatningen visas inte. Hemligheten förs in i Container Apps hemlighetslager via en tillfällig fil med begränsad åtkomst som tas bort när Azure-anropet är klart. Den finns inte i paketet, byggarkivet, kommandohistoriken eller resultatfilen.

Scriptet kontrollerar katalog, prenumeration, app och medgivanden. Sedan registrerar det nödvändiga Azure-resursleverantörer och skapar eller återanvänder dessa resurser i Sweden Central:

| Resurs | Inställning |
| --- | --- |
| Resursgrupp | `rg-krusgraph` |
| Container Apps-miljö | `cae-krusgraph`, Consumption |
| Container App | `krusgraph`, 0–2 instanser, 0,25 CPU / 0,5 GiB |
| Container Registry | Basic, administratörsinloggning avstängd |
| Hanterad identitet | `krusgraph-pull`, endast AcrPull på registret |

Registret har en fast avgift: Microsofts publika pris för Sweden Central kontrollerat 2026-10-23 var 0,1666 USD/dygn, cirka 5 USD för 30 dagar. Byggtid, trafik och serveranvändning kan tillkomma. Faktisk kostnad beror på Azure-avtal, skatter och användning. Container Apps kan skala ned till noll vid inaktivitet. Inga Fabric-kapaciteter eller databaser skapas.

Kör `bash deploy/krusgraph.sh --plan` för att visa konfigurationen utan Azure-anrop, eller `bash deploy/krusgraph.sh --check` för att kontrollera inloggningen och behörigheterna utan att skapa resurser.

## Efter första körningen

När scriptet visar **START KLART** har startsidan och MCP-inloggningskravet kontrollerats på Azure-adressen. Kopiera det offentliga resultatet med `preview_url` och `dns` till chatten. Resultatet sparas också i `azure-result.json`.

I Namecheap ska den gamla URL-omdirigeringen på `@` ersättas med den utskrivna A-posten. `www` ska få det utskrivna CNAME-värdet i stället för parkeringssidan. Lägg till TXT-posterna `asuid` och `asuid.www`. Behåll domänverifieringen `MS=ms61673308` och e-postposterna.

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

Cloud Shell-sessionen är tillfällig. Azure-resurser och sparade hemligheter i Container Apps finns kvar när sessionen stängs. Ladda upp paketet igen om filerna har försvunnit. Din dator behöver inte vara på när servern väl körs i Azure.

## Källor och kontroll

- [Azure Container Apps: egna domäner och hanterade certifikat](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [Hämta containerbilder med hanterad identitet](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Container Apps-fakturering](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Microsofts publika pris-API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Ladda upp filer i Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/use-the-shell-window#manage-files-menu)

Källkodens utgångspunkt är GitHub-commit `1fbd071e156f273076ac740d4050fa6b7e807e2a`. Paketet innehåller lokala rättningar av OAuth-rutter, delegerad behörighetskontroll, GraphQL-läsverktyget, Dockerkonfigurationen och driftsättningen. Dessa rättningar har inte publicerats till GitHub från denna session.
