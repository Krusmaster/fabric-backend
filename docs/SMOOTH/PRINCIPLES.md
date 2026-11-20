# Smooth principles (for every UI round, chat and editor)

Gustav, 19 November 2026: "Simple. Simple. Simple. Smooth!" A UI round checks its change against this list and says in
its PR which items it was measured on (`tools/smooth_measure.py`).

1. **One living card.** A tap continues in the same card. A new card appears only after typed text, and it continues
   from the shared state.
2. **The mascot says one sentence:** at most 15 words, what happens now. It never repeats the step's title, and it is
   never another step's sentence.
3. **At most 25 words per step besides the buttons.** Numbers that matter to the decision stay ("5 of 6 found");
   everything else goes under one Details fold.
4. **Two or three buttons, one of them primary.** Next counts as one. Never two primaries.
5. **Defaults are chosen for you.** One usable option is chosen, not asked. Read-only work runs on its own (the map, the
   check, the totals, the dry runs). The default build is pipeline + semantic model + data agent.
6. **Ask only what a rule cannot know:** meaning, ownership, names, and what to create. Every question comes with the
   count that supports the default.
7. **Never a dead end.** Every state has a forward button, including after Create, after an error and on the sample.
   An error says what to do in one sentence, with the button to do it.
8. **Every step is reversible.** Change, Back and Undo are always one tap. Nothing is written without a dry run and a
   second tap. A decision can be changed until Create.
9. **Evidence only on tap:** the map, the rules, the SQL, the full counts, the Turtle and TMDL. It is always there,
   never in the way.
10. **It fits the phone.** No step scrolls at 390 x 800 except an opened map. There is no blank space under a card, and
    light and dark mode both work.
11. **One numbering, one set of words,** the same in the chat and the editor (Step N of 5).
12. **Measured, not assumed.** Taps, words and seconds come from `smooth_measure`. The phone test confirms them before a
    round says "done".

In public text, never say "compliant", "secure" or "replaces data engineers". Say what was counted and checked, and when.
