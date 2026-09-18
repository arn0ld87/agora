Das Projektregal zeigt wieder den Projektnamen statt der rohen `project_id`.
`useShelf` las das Feld `project_name`, das Backend liefert `name` — die
Bedingung fiel deshalb immer auf die Kennung zurück.

Unentdeckt blieb das, weil die Antwortform von Hand als Interface deklariert war
(mit `[key: string]: unknown`, wodurch der Zugriff auf ein nicht existierendes
Feld gültiges TypeScript blieb) und die Testfixture das Feld erfand. Beides ist
durch einen Zod-Spiegel `contracts/projectContract.ts` ersetzt, der die Antwort
`.strict()` prüft. Der strikte Typ hat direkt einen zweiten toten Zweig
aufgedeckt: `useGraphBuildPipeline` verglich den Projektstatus mit `completed`,
den es nur für Tasks gibt — für ein Projekt heißt der Wert `graph_completed`.
