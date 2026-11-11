# n209: kort notis till grundaren (11 november 2026)

**Vad som ändrats** (inget av det är kört mot en riktig arbetsyta; testerna kör mot testdubblerna)

1. **Torrkörningen säger vad Create gör.** Ett och samma beslut för båda. Det som redan är byggt från samma plan, även av
   en annan Krusgraph Model, heter nu "already built from this plan, will be skipped", inte rött. Rött bara för ett objekt
   som någon annan har gjort (n207). "Would be updated" bara när Create verkligen skriver. Det mesta var redan rättat av
   n197 (4033655); kvar var rubriken och sammanfattningen för ett objekt från en annan plan, och dataproduktens lista.
2. **Gold upprepar inte nycklarna** (`orders_order_id`, `products_product_id`, `customers_customer_id` är borta). Regeln
   som tar bort rader som pekar på ingenting ligger nu i vyns WHERE och tar bort exakt samma rader som förut.
3. **Granskningen**: en länk som håller i raderna visar "This link holds in the rows: 0 of N rows point at nothing."
   vid Reject, och om du avvisar den står det att semantisk modell, API och ontologi får en relation färre.
4. **App-kortet** behåller valen och paketlänken när du öppnar objektet igen efter bygget. En App som byggdes före n209
   utan att någon ändrade valen har inget sparat; kortet säger det.
5. **Dataagenten** med Run once: exempelfrågorna kontrolleras (och agenten publiceras, om ikryssat) först när körningen
   lyckats. Anslutningsfel provas en gång till och visas sedan som "not checked yet", aldrig "invalid".
6. **n198, n200 och n201 tillsammans**: ett test går hela vägen (granskning, torrkörning, Create med Run once,
   dataproduktsidan med hälsoordet efter två körningar, Update- och Retire-torrkörning). Inget behövde rättas mellan dem.
7. **docs/GUEST-TRIAL.md** och ett avsnitt på /pilot/fabric: så bjuder du in gästerna som B2B-gäster i din tenant, med
   källor på Microsoft Learn. Det Learn inte säger är märkt Unverified, bl.a. att en B2B-gäst ser ett `Org.`-workload och
   att gästens egen Pro-licens räcker för att skapa semantiska modeller under F64. Tilldela hellre Pro/PPU i din tenant.

**Att göra**

1. **Driftsätt**: `bash deploy/krusgraph.sh --update` från `main` (sista kodändringen: `82505df`). Redigeraren serveras
   av containern, så den följer med.
2. **Inget nytt workload-paket behövs för n209**: manifestet är oförändrat, så versionen ska inte höjas. (Har du inte
   laddat upp paketet från n201 ännu, gäller det fortfarande.)

**Test på 10 minuter i en ny arbetsyta** (innan du bjuder in gästerna)

1. Skapa en ny arbetsyta med en lakehouse med schemas och shop-exemplet (syntetiska data), och ett Krusgraph Model-objekt.
2. Välj källan och `shop`, kör granskningen och sedan *Check against the rows*. Kolla att en länk med 0 orphans visar
   "This link holds in the rows" och att Reject på den visar "one relationship fewer". Ångra med Accept.
3. Välj alla utdata, kryssa Run once på pipelinen och App-valen. Torrkörning: alla "Create …", inget rött.
4. Create. När pipelinen har kört klart: dataagentens exempel ska stå som kontrollerade eller "not checked yet", inte
   "invalid" för ett anslutningsfel.
5. Öppna en gold-vy i SQL-endpointen: ingen `orders_order_id`, `products_product_id` eller `customers_customer_id`.
6. Stäng och öppna objektet igen: App-kortet visar dina val och paketlänken.
7. Kör torrkörningen igen: allt "already built from this plan, will be skipped", inget rött, inget "would be updated".
8. Dataproduktsidan: alla objekt "built" och ett hälsoord efter körningen; Retire → Delete from Fabric som torrkörning
   listar bara det Create gjorde. Radera inget.
