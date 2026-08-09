# Køreplan for det automatiske tjek

Instruktionen den planlagte cloud-agent følger fire gange dagligt.

## Opgaven

Find relocation-tilbud på ruten **Christchurch → Auckland** der passer i Karstens vindue,
verificér at de faktisk er ledige, og opdatér `data.json`.

## Hårde krav

| Krav | Værdi |
|---|---|
| Afhentning | Christchurch (by eller lufthavn). **Ikke** Queenstown, Dunedin eller andre byer. |
| Tidligste afhentning | 21. august 2026 |
| Aflevering | Auckland |
| Afleveringsvindue | 28. august – 8. september 2026, begge inkl. |
| **Maks pris** | **20 NZD pr. dag.** Alt derover er uinteressant, uanset hvor godt det ellers ser ud. |
| Færge | Cook Strait-overfarten skal være **betalt af udlejeren** for bil + fører |
| Passagerer | 1 — ekstra passagerbilletter er irrelevante |

Et tilbud passer kun hvis `afhentningsdato + antal dage` kan lande i afleveringsvinduet.
Afhentning behøver ikke være den 21. — blot den 21. eller senere. En 5-dages deal hentet
24. august afleveres 29. august og **passer**. Samme deal hentet 21. august afleveres
26. august og **passer ikke**.

## Præference

Karsten vil helst køre en **sportsvogn eller anden sjov bil**. Ikke et krav, men fremhæv det
tydeligt hvis noget mere spændende end en økonomibil dukker op.

## Tilgængelighed — skal altid tjekkes

For hvert tilbud skal `availability` udfyldes ved hver kørsel:

- `state`: `ledig` · `ledig-snaevert` (vinduet lukker snart) · `ikke-i-vindue` · `udsolgt` · `ukendt`
- `from` / `to`: de faktiske datoer udbyderen tillader afhentning og aflevering
- `spaces`: antal ledige køretøjer hvis det står nogen steder
- `detail`: én sætning om hvad datoerne betyder for Karsten
- `confidence`: `direkte` hvis du læste det på udbyderens side, `indirekte` hvis via søgeindeks
- `checkedAt`: tidspunktet for dette tjek

Skriv aldrig `ledig` uden at have set en dato. Er du i tvivl, brug `ukendt`.

## Billeder

Hvert tilbud skal have et rigtigt foto af køretøjet i `img/` og en `imageCredit`.
Sådan finder du dem: hent udbyderens side og træk `og:image`, `src`, `data-src` og `srcset`
ud. Vælg et eksteriørfoto af køretøjet — ikke logoer, landskabsbilleder eller partnerbannere.
Hent filen ned i `img/` med `curl` og en almindelig browser-signatur plus `-e <sidens URL>`
som referer, skalér til maks 900 px bredde, og sæt `imageUrl` til den lokale sti.
Findes der intet brugbart foto, så lad `imageUrl` være `null` — så tegner siden selv en
illustration ud fra `vehicleType` (`campervan`, `sedan`, `sports`).

## Kilder

**Alle kilder i `data.json` under `sources` tjekkes ved hver eneste kørsel — uden undtagelse,
uanset prioritet.** Prioritetstallet styrer kun rækkefølgen. Kunne en side ikke læses, skal
det stå i loggen med navn og årsag.

Kendte adgangsproblemer, som allerede er undersøgt til bunds:

- **transfercar.co.nz** — HTTP 403 på alt. Testet uden held med browser-signatur, mobilsignatur,
  support-subdomænet og en ekstern læseproxy. Kan **kun** læses via websøgning begrænset til
  domænet: brug WebSearch med `allowed_domains: ["transfercar.co.nz"]`. Det virker og har
  allerede afsløret et rigtigt opslag. Gør det hver gang, med mindst to forskellige søgninger.
- **apollocamper.co.nz** (også Cheapa og Hippie) — HTTP 403 på hele domænet. Brug websøgning.
- **easycarrelo.co.nz** — ren JavaScript-app, intet indhold i svaret. Kan ikke læses.
- **britz.com** — offentliggør ingen relocations; kræver tilmelding til deres database.

Disse fire skal blive stående i `manualCheck` med en ærlig forklaring, så Karsten ved
præcis hvad han selv skal åbne.

### Opdagelsesrunde — hver gang

Led efter udbydere og opslag vi ikke kender. Kør mindst disse søgninger:

- `relocation Christchurch Auckland campervan $1 day`
- `relocation car Christchurch to Auckland ferry included august september 2026`
- `campervan relocation NZ Facebook group` — udlejere poster ledige biler dér før platformene
- `motorhome relocation south island to north island deal`

Gennemgå også branchekataloget **rentalcarrelocation.co.nz**, som lister stort set alle
NZ-udbydere med relocations — det er den bedste enkeltkilde til at opdage nye.

Finder du en udbyder der ikke står i `sources`, så tilføj den med navn, URL, type, prioritet,
`access` og en kort note — også selvom den ikke har noget lige nu.

### Sportsvognsrunde — hver gang

Tjek specials-siderne hos rentaclassic.co.nz, touchdowncarrental.co.nz,
luxurycarrentalsnewzealand.co.nz, sportscarrental.co.nz, smartcarrental.co.nz og sixt.nz for
envejstilbud CHC→AKL, og søg på
`sports car OR convertible one way rental Christchurch Auckland relocation special`.
Rapportér ethvert fund, også hvis det ikke er gratis.

## Sådan opdaterer du

1. Læs `data.json`.
2. Tjek alle kilder, kør opdagelses- og sportsvognsrunden.
3. Opdatér hvert tilbuds `availability`, priser og datoer. Sæt `fit`:
   - `passer` — alle hårde krav opfyldt, inkl. bekræftet betalt færge og maks 20 NZD/dag
   - `naesten` — datoer og pris passer, men færgen er ubekræftet eller der er et forbehold
   - `nej` — opfylder ikke kravene, men er værd at kende som nødløsning
4. Opdatér eksisterende poster frem for at duplikere. Forsvundne tilbud fjernes og noteres i loggen.
5. Sæt `updated` til nuværende Pacific/Auckland-tid i ISO 8601 med `+12:00`.
6. Tilføj **én** post i `log`. Behold højst 40 — slet de ældste.
7. Commit og push til `main` med beskeden `tjek: <kort opsummering>`.

## Vigtigt

- Opfind aldrig et tilbud, en dato eller en færgeinklusion. Karsten booker på det her, og han
  tjekker ikke selv. Kunne en side ikke læses, så skriv det — det er langt bedre end et gæt.
- Starter et nyt tilbud med `fit: "passer"`, så begynd logteksten med `NYT:`.
- Ret ikke i `index.html` — kun `data.json` og `img/`.
