# Krusgraph – figurer i rörelse
Datum: 2026-10-23

Fyra nya bildtavlor utvecklar de tre maskotarna i riktningen Little Connections. Allt är designförslag. Animationerna och hjälpfunktionerna är ännu inte implementerade.

## Börja här
1. images/01-onto-pointer-storyboard.jpg – korallfiguren och muspekaren.
2. images/02-sage-review-storyboard.jpg – den gröna hjälper användaren att granska ett förslag.
3. images/03-lavender-build-storyboard.jpg – den lila väntar, visar resultat och hjälper vid fel.
4. images/04-motion-language.jpg – figurernas olika sätt att vila, titta, peka och fira.

../mascots/01-family.jpg visar den tidigare valda familjen. Den gröna figurens ring i den äldre referensen ska inte vara en del av ansiktet eller följa med in i de nya modellerna.

HANDOFF-CLAUDE.md är en konkret brief för implementation.
CLAUDE-STARTPROMPT.md är en färdig första instruktion att ge Claude Code tillsammans med mappen.
motion-spec.json innehåller föreslagna mått och tider. Dessa är designvärden som ska justeras efter provning, inte uppmätta prestandalöften.
IMAGE-PROMPTS.md innehåller de fullständiga bildprompterna. Bilderna är skapade med den inbyggda bildgeneratorn.

Onto är ett arbetsnamn för korallfiguren. De andra heter tills vidare den gröna tänkaren och den lila byggaren. Noodies kan fortsatt utvärderas som familjenamn; inget namn är slutligt eller kontrollerat för tillgänglighet.

## Vad du lämnar över
Ge Claude Code hela den uppackade mappen och sökvägen till Krusgraph-repot. Börja med CLAUDE-STARTPROMPT.md. Målet för första steget är en separat lokal rörelseprototyp, som går att prova och ändra innan någon publicering.

