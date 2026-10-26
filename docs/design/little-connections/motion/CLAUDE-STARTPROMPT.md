# Första instruktion till Claude Code

Jag vill utveckla en lokal interaktiv prototyp av tre maskotar för Krusgraph. Läs HANDOFF-CLAUDE.md, motion-spec.json och de fyra bildtavlorna i images/. Använd ../mascots/01-family.jpg för karaktärernas släktskap. Bilderna är statiska referenser, inte färdiga animationstillgångar.

Läs först repots anvisningar och undersök vilken webbteknik som redan används. Bygg sedan en separat lokal rörelseprototyp i den tekniken. Börja med lageruppdelad SVG och CSS/JavaScript: kropp, ögon, armar och skugga ska kunna röra sig separat. Målet är att testa personlighet och beteende; förklara att det är en förenklad 2,5D-tolkning av 3D-skisserna.

Korallfiguren Onto är en nyfiken guide, den gröna är en lugn granskare och den lila visar byggprocessens verkliga status. Behåll en vanlig muspekare och låt högst en liten figur följa den på avstånd inom grafområdet. Figuren ska parkera bredvid ett valt objekt, inte täcka det. Ingen automatisk acceptans av relationer eller start av API-skapande.

Gör tydligt märkta demokontroller för idle, explain, review_wait, working, success och error. Inga riktiga Fabric-anrop i prototypen. Lägg in reducerad rörelse, tangentbordsstöd, avstängning och en stillastående mobilvariant. Testa att figuren aldrig blockerar knappar och att misslyckade åtgärder aldrig visar framgång.

Öppna den färdiga lokala prototypen så att jag kan prova den. Beskriv vad som fungerar och vad som krävs för full 3D senare. Publicera inte prototypen i detta steg.

