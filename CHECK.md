# Køreplan for det automatiske tjek

Dette er instruktionen den planlagte cloud-agent følger fire gange dagligt.

## Opgaven

Find relocation-tilbud (gratis eller næsten gratis biler/campervans der skal flyttes) på ruten
**Christchurch → Auckland**, der passer i Karstens rejsevindue, og opdatér `data.json`.

## Hårde krav

| Krav | Værdi |
|---|---|
| Afhentning | Christchurch (by eller lufthavn). **Ikke** Queenstown, Dunedin eller andre byer. |
| Tidligste afhentning | 21. august 2026 |
| Aflevering | Auckland |
| Afleveringsvindue | 28. august – 8. september 2026, begge inkl. |
| Færge | Cook Strait-overfarten skal være **betalt af udlejeren** for bil + fører |
| Passagerer | 1 (kun Karsten) — ekstra passagerbilletter er irrelevante |

Et tilbud passer kun hvis `afhentningsdato + antal dage` kan lande inden for
28. aug – 8. sep. Eksempel: en 5-dages deal hentet 24. aug afleveres 29. aug → **passer**.
En 5-dages deal hentet 21. aug afleveres 26. aug → **passer ikke** (for tidligt).
Regn altid efter, i stedet for at antage at afhentning sker 21. august.

## Præference

Karsten vil helst køre en **sportsvogn eller på anden måde sjov bil**. Det er ikke et krav,
men rapportér altid tydeligt hvis noget mere spændende end en økonomibil dukker op.
Rapportér alt der passer — også campervans og kedelige biler.

## Kilder der skal tjekkes hver gang

**Alle kilder i `data.json` under `sources` skal tjekkes ved hver eneste kørsel — uden
undtagelse, uanset prioritet.** Prioritetstallet styrer kun rækkefølgen, ikke om noget må
springes over. Karsten må ikke gå glip af en mulighed fordi en side blev sprunget over.
Hvis en side ikke kunne læses, skal det stå i loggen med navn og årsag.

Bemærk: **Transfercar blokerer automatisk aflæsning** (Cloudflare 403). Forsøg alligevel via
WebSearch efter nye Transfercar-opslag på ruten, og skriv i loggen hvis siden ikke kunne læses.
Karsten har en e-mailalarm slået til der.

### Opdagelsesrunde — hver gang

Ud over den kendte liste skal du hver gang lede efter udbydere og opslag vi endnu ikke kender.
Kør mindst disse søgninger og se på resultater fra de seneste dage:

- `relocation Christchurch Auckland campervan $1 day` (og varianten med "car")
- `"relocation" OR "transfer car" New Zealand new deals august september 2026`
- `campervan relocation NZ Facebook group Christchurch Auckland` — der findes aktive
  Facebook-grupper (bl.a. "Campervan Relocations NZ", "NZ Relocation Deals") hvor udlejere
  poster ledige biler før de rammer platformene
- `motorhome relocation south island to north island deal` 
- søg på navnene på nye udlejere du støder på, og find deres deals-/specials-side

Finder du en udbyder eller platform der ikke allerede står i `sources`, så **tilføj den** med
navn, URL, type, prioritet og en kort note — også selvom den ikke har noget lige nu. Listen
skal vokse over tid, så dækningen bliver bedre for hver dag.

### Sportsvogn — særskilt runde hver gang

Relocation-platformene har aldrig sportsvogne. Tjek derfor også specials-/deals-siderne hos
sports- og luksusudlejerne i `outreach`-listen for envejstilbud CHC→AKL, og søg efter
`sports car OR convertible one way rental Christchurch Auckland relocation special`.
Rapportér ethvert fund, også hvis det ikke er gratis.

## Sådan opdaterer du

1. Læs `data.json`.
2. Tjek hver kilde. For hvert tilbud på CHC→AKL: notér køretøj, antal dage, pris, færge, brændstof, gyldighedsperiode, min. alder, depositum.
3. Sæt `fit`:
   - `"passer"` — alle hårde krav opfyldt, inkl. bekræftet betalt færge
   - `"naesten"` — passer på datoer, men færge er ubekræftet eller der er et væsentligt forbehold
   - `"nej"` — opfylder ikke kravene, men er værd at kende som backup
4. Opdatér eksisterende poster i stedet for at duplikere. Fjern tilbud der ikke længere findes, og skriv det i loggen.
5. Sæt `updated` til nuværende NZ-tid (Pacific/Auckland, ISO 8601 med +12:00).
6. Tilføj **én** post i `log` med hvad der er nyt siden sidst. Behold højst 40 log-poster — slet de ældste.
7. Commit og push til `main`. Commit-besked: `tjek: <kort opsummering>`.

## Vigtigt

- Opfind aldrig et tilbud. Hvis en side ikke kunne læses, skriv det i loggen — det er
  bedre end et gæt. Karsten træffer beslutninger på det her.
- Hvis et helt nyt tilbud opfylder alle krav (`fit: "passer"`), så start loggens tekst med
  `NYT:` så det er let at få øje på.
- Ret ikke i `index.html` — kun `data.json`.
