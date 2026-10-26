# Krusgraph: brief för maskoternas beteende
Datum: 2026-10-23
Status: designförslag och statiska skisser. Ingen animation, Rive-fil, lageruppdelad illustration eller 3D-modell följer med ännu.

## Avsikt
Krusgraph hjälper användaren att gå från Fabric-tabeller och förslag på relationer till en granskad GraphQL-API-plan. Figurerna ska göra nästa steg lättare att förstå och ge varumärket personlighet. De får inte ersätta tydliga etiketter, statusmeddelanden eller användarens beslut.

Vald riktning: Little Connections.
Rubrik för varumärket: “Good things happen when data connects.”

## Tre personligheter

| Figur | Roll | Rörelse | När den passar |
|---|---|---|---|
| Korall / Onto, arbetsnamn | Nyfiken guide | Blicken först, därefter en liten lutning och ett vänligt pekande | Startsida, grafutforskning, introduktion |
| Salviagrön / tänkaren | Lugn granskare | Stadig bas, långsam huvud-/kroppslutning, stilla väntan, liten nick | Förklaringar av relationsförslag och beslut |
| Lavendel / byggaren | Uppfinningsrik hjälpare | Lite mer energi i armar och kropp, ett litet hopp när en åtgärd faktiskt lyckas | Förhandsgranskning, väntan, resultat, återhämtning från fel |

Ansikten: två svarta pärlögon, ingen mun eller näsa. Kroppar: mjukt oregelbundna, matta, inga ben eller fingrar. Använd blick, lutning och korta armrörelser för uttryck. Behåll de tydliga skillnaderna i silhuett.
Kroppsformerna i referensbilderna är visuella mål, inte tillgängliga 3D-tillgångar.

## Fyra bildtavlor
- images/01-onto-pointer-storyboard.jpg: vila → uppmärksamma → följ → stanna → förklara → lämna plats.
- images/02-sage-review-storyboard.jpg: se ett förslag → överväg → förklara → vänta på användaren → accepterat ELLER överhoppat.
- images/03-lavender-build-storyboard.jpg: redo → användaren startar → pågår → lyckat ELLER fel → återgå till lugn.
- images/04-motion-language.jpg: det gemensamma rörelsespråket och skillnaderna mellan figurerna.

Tavlornas pilar och rörelseskuggor är instruktioner för animation, inte delar av den färdiga figuren.

## Rekommenderad första implementation
Bygg en separat lokal rörelseprototyp i projektets befintliga teknik. Läs repoanvisningarna först och utgå från befintliga filer; anta inte att projektet använder React. Krusgraphs tidigare webb låg i fabric_backend/page_templates/landing.html med samma server som /docs och /privacy.

Börja med lageruppdelad SVG och CSS/JavaScript:
- separata grupper för kropp, två ögon, två armar och skugga;
- mjuka toningar ger en förenklad 2,5D-känsla;
- håll positionering, känslotillstånd och ritning åtskilda;
- ögonen kan röra sig begränsat mot pekaren; kroppen har långsammare respons;
- använd transform och opacity där det går;
- en gemensam figurkomponent med tre varianter räcker.

Detta är en approximation av lerutseendet. Den första prototypen ska visa om beteendet känns rätt, inte utge sig för att exakt återskapa de renderade 3D-bilderna.

Claude Code kan skapa frontendkod från den visuella referensen och rörelsebriefen. Själva rörelserna körs lokalt i besökarens webbläsare, utan LLM-anrop per musrörelse. Det innebär ingen löpande AI-inferenskostnad för just de här animationerna. Vanlig hosting och utvecklingsverktyg är separata kostnader.

## Om vi vill ha den fulla 3D-känslan
Skapa eller beställ riktiga 3D-modeller med separata ögon och armar. Kroppens lutning och andning kan styras med transformering; mjukare deformation kan kräva rigg eller morph targets. Exportera exempelvis GLB med animationer för vila, blick, pekning, väntan, firande och hjälp vid fel.

Claude kan skriva integrationen med Three.js, växling mellan rörelser och respons på webbens händelser. Det finns ännu ingen sådan modell i paketet. En PNG blir inte automatiskt en redigerbar riggad figur. Claude kan även hjälpa till att skriva ett modelleringsskript för enkla former, men resultatet måste granskas visuellt.

Rive är ett alternativ om vi väljer en illustrerad 2D-stil. En animatör behöver skapa grafiken och rörelserna i en .riv-fil; Claude kan koppla webbens händelser till dess state machine. Rive ska inte beskrivas som en automatisk omvandling av de här bilderna till full 3D.

## Pekaren och figuren
- Vanlig muspekare behålls.
- Endast en aktiv guide åt gången.
- Följandet gäller grafens demo-/arbetsområde, efter att användaren aktiverat eller gått in i den guidade upplevelsen.
- På startsidan kan de stora figurerna titta mot pekaren utan att lämna sin plats.
- Föreslagen följarstorlek: 48 px på skrivbord; justera efter läsbarhet.
- Börja med ungefär 36 px horisontellt och 40 px vertikalt avstånd från pekaren.
- Föreslagen mjuk respons: 140 ms tidskonstant, med tidsbaserad utjämning så beteendet är jämnt vid olika bildfrekvenser. Detta är inte en fast händelsefördröjning.
- Vid en stilla pekare kan figuren parkera bredvid det aktuella objektet efter cirka 450 ms.
- När pekaren lämnar grafområdet återgår guiden till en bestämd viloplats.
- Begränsa placeringen till området och byt sida när figur/bubbla skulle skymma något.
- Figurlagret får inte fånga klick. Visa en separat riktig knapp för hjälp och en för att stänga guiden.
- Stängda hjälpbubblor ska förbli stängda tills användaren ber om hjälp igen eller byter relevant steg.

## Triggers och utfall

| Händelse | Figurens beteende | Text/produktregel |
|---|---|---|
| Pekaren går in i grafen | Onto tittar upp | Ingen bubbla på varje pixelrörelse |
| En tabell får fokus/pekas ut | Onto stannar bredvid | Beskriv tabellen utifrån tillgänglig metadata |
| Användaren väljer en föreslagen kant | Gröna figuren pekar och förklarar | Visa varför förslaget finns och vad som är osäkert |
| Beslut krävs | Gröna figuren väntar lugnt | Acceptera och Hoppa över är människans val |
| Förslag accepteras | En liten nick | Accepterat betyder inte oberoende verifierat |
| Förslag hoppas över | Lugn återgång | Ingen skuld eller besvikelse |
| Användaren bekräftar att skapa API | Lila figuren övergår till pågår | Åtgärden ska utlösas av användarens knapp |
| Servern bekräftar lyckat resultat | Lila figuren gör ett litet firande en gång | Visa verkligt resultat, inte en tidsstyrd gissning |
| Servern returnerar fel | Lila figuren lugnar sig och visar nästa steg | Visa begriplig feltext och relevant återförsök |
| Användaren döljer guiden | Figuren försvinner | Appens alla funktioner ska fortsatt fungera |

Föreslagna interna tillstånd: idle, attend, follow, explain, review_wait, working, success, error, dismissed.
Prioritera dismissed, sedan verkligt operationstillstånd/beslut, sedan fokus och pekarföljning. En pekarrörelse ska inte avbryta ett felmeddelande eller en pågående granskning. Undvik köade animationer som spelas långt efter händelsen.

## Tillgänglighet och komfort
- Vid prefers-reduced-motion: ingen pekarföljning, studs eller andningsloop. Stillastående figur och samma information i text.
- Tangentbordsfokus ska ge samma relevanta förklaring som pekning.
- På mobil: figuren står still vid panelen; tryck på hjälp eller ett objekt öppnar information. Ingen låtsasmuspekare.
- Hjälpknappar ska vara riktiga, namngivna knappar och fungera med tangentbord.
- Rent dekorativa figurer ska döljas från hjälpmedel. Status ges i vanlig text, och viktiga resultat kan meddelas med en diskret live-region.
- Utgå aldrig enbart från färg för att visa förslag, accepterat eller fel.
- Pausa dekorativa loopar när fliken är dold eller komponenten inte syns.
- Användaren kan stänga av figurerna, och valet sparas lokalt.
- Kort andning och blinkning är tillval. Prioritera lugn framför ständig aktivitet.

## Användning på andra sidor
- Startsidan: alla tre får synas i en samlad scen. De tittar mot pekaren och byter lugnt uppmärksamhet.
- Kom igång: Onto pekar på ett steg åt gången, med hjälptext som går att läsa utan figuren.
- Dokumentation: en stilla hjälpfigur vid en förklaring; inga karaktärer som jagar läsaren under scroll.
- Stöd/donation: ett litet tack efter ett faktiskt bekräftat stöd, eller en neutral hälsning före betalning. Inga manipulerande ledsna reaktioner om besökaren avstår.
- Partnersida: en diskret hälsning när riktig inloggning har lyckats. En skiss på inloggning är inte ett fungerande skydd för partnerinnehåll.

## Första leveransen från Claude
1. En separat lokal prototyp med alla tre figurerna och ett enkelt grafområde.
2. Synliga demokontroller för vila, granska, pågår, lyckat och fel. Märk dessa som simulerade tillstånd.
3. Fungerande mus, tangentbord, mobilvariant, avstängning och reducerad rörelse.
4. Ett kort dokument om vad som är approximation, vad som återstår och vilka filer som ändrats.
5. Skärmbilder av stilla lägen och en manuell genomgång av hela flödet.

Ingen publicering ingår i det första prototypsteget. Koppla inte demokontroller till riktiga Fabric-anrop.

## Granskningspunkter
- Kropp, ögon och armar ser ut att tillhöra samma figur.
- Figuren täcker aldrig den valda noden, knappen eller hjälptexten.
- En tangentbordsanvändare kan få samma hjälp och stänga den.
- Om en begäran misslyckas visas aldrig framgångsanimation.
- Upprepade snabba klick och växling av nod ger inte gamla bubblor eller dubbla följarfigurer.
- Noderna kunder och order i skissen är exempeldata; relationsförslagen är illustrativa.
- När guiden är avstängd fungerar hela huvudflödet ändå.

## Källor som kontrollerades 2026-10-23
- Anthropic, om design och prototyper med Claude Code: https://claude.com/resources/articles/how-anthropic-teams-use-claude-code
- Three.js animationssystem, GLB/glTF-import och animation clips: https://threejs.org/manual/pages/animation-system.html
- Rive, hur state machines kopplar animationer till övergångar: https://rive.app/docs/editor/state-machine/state-machine

Mått, rörelser, färger och produktbeteenden i denna brief är våra designförslag, inte påståenden från källorna.

