# Køreplan for det automatiske tjek

Instruktionen bag Relocation Watch for ruten **Brisbane → Sydney**. Den automatiske del
kører som GitHub Action fire gange i døgnet (`scripts/refresh.py`). Resten er den
manuelle opdagelsesrunde, som en agent følger når Karsten beder om en fuld gennemgang.

## Opgaven

Find relocation-tilbud på ruten **Brisbane → Sydney** der passer i Karstens vindue,
verificér at de faktisk er ledige, og opdatér `data.json`.

## Hårde krav

| Krav | Værdi |
|---|---|
| Afhentning | Brisbane (by eller lufthavn). Gold Coast og Sunshine Coast må gerne vises, men kun som «tæt på». |
| Afhentningsdato | **30. september, 1., 2. eller 3. oktober 2026.** Én af de fire dage, ikke før, ikke efter. |
| Aflevering | Sydney (by eller lufthavn). Turens længde er fri, så længe udbyderen tillader den. |
| **Maks pris** | **50 AUD pr. dag for selve bilen.** Bookinggebyr, depositum og brændstof må gerne komme oveni, men skal stå tydeligt. |
| Personer | 2 |
| Køretøj | Alt tages med: biler, SUV'er, varevogne, minibusser, lastbiler, campere. |

## Præference

Det er et **plus hvis man kan sove i bilen** (campervan, motorhome, sleepervan, hi-top). Ikke et
krav. Kortet viser «Kan sove i» øverst på fotoet, og listerne sorterer campere først ved samme pris.

## Vurderingen (`fit`)

Beregnes af `scripts/common.py → assess()`, så alle kilder vurderes ens:

- `passer`: en afhentningsdato i 30. sep – 3. okt ligger inden for udbyderens vindue, afhentning i
  Brisbane, og dagsprisen er højst 50 AUD.
- `naesten`: prisen passer, men enten (a) lukker udbyderens vindue op til 7 dage før dit eller åbner
  op til 7 dage efter (de forlænger ofte), eller (b) afhentningen er i Gold Coast / Sunshine Coast.
- `nej`: alt andet. Vises stadig, så man kan se hvad ruten plejer at byde på.

`availability.state`: `ledig` (mindst to mulige afhentningsdage), `ledig-snaevert` (præcis én dag),
`ikke-i-vindue`, `udsolgt` eller `ukendt`. Skriv aldrig `ledig` uden at have set en dato.

## Automatiske kilder

| Kilde | Hvordan | Fil |
|---|---|---|
| Imoova | GraphQL-API (`api.imoova.com/graphql`), samme kald som deres side laver. Henter Brisbane, Gold Coast og Sunshine Coast → Sydney med alle sider. | `scripts/sources/imoova.py` |
| Coseats | JSON-API bag app.coseats.com (`coseats-au.herokuapp.com/trips/search/findRelocations`). Filtreres på ruten. | `scripts/sources/coseats.py` |

Fejler en kilde, beholdes dens gamle opslag, og fejlen står i loggen og på kildekortet («FEJLEDE»).
Nye kilder tilføjes som en fil i `scripts/sources/` med `SOURCE`, `LABEL` og `fetch_deals(window, now)`,
og navnet skrives ind i `SOURCES` i `scripts/refresh.py` plus `autoKey` på kilden i `data.json`.

## Billeder

Hvert tilbud skal have et rigtigt foto af køretøjet i `img/` og en `imageCredit`. De automatiske
kilder henter selv. Til manuelle tilbud: hent udbyderens side, træk `og:image`, `src`, `data-src` og
`srcset` ud, vælg et eksteriørfoto (ikke logo eller landskab), hent med `curl` og en almindelig
browser-signatur plus `-e <sidens URL>`, og sæt `imageUrl` til den lokale sti. Findes intet foto,
lad `imageUrl` være `null`, så tegner siden en illustration ud fra `vehicleType`
(`campervan`, `sedan`, `suv`, `van`, `truck`, `minibus`).

## Manuel opdagelsesrunde (når Karsten beder om fuld gennemgang)

**Alle kilder i `data.json` under `sources` tjekkes, uanset prioritet.** Kunne en side ikke læses,
skal det stå i loggen med navn og årsag.

Kendte adgangsforhold:

- **transfercar.com.au**: Cloudflare afviser almindelige `curl`-kald (403), men svarer 200 når man
  sender fulde browser-headers (`Accept: text/html…`, `Sec-Fetch-Mode: navigate`, `Sec-Fetch-Dest: document`,
  `Upgrade-Insecure-Requests: 1`) over HTTP/1.1. Søgesiden er en Next.js-app, hvor opslagene hentes
  af browseren. Bliver det ikke automatiseret, så brug WebSearch med `allowed_domains: ["transfercar.com.au"]`.
- **drivenow.com.au**: samme Cloudflare-mønster. `onewayrentals.jspc` svarer 200 med fulde headers.
- **gumtree.com.au**, **backpackerjobboard.com.au**: 403 på alt. Brug WebSearch begrænset til domænet.
- **cheapacampa.com**: 403 på hele domænet. Apollo-koncernens (Apollo, Cheapa, Hippie, Star RV)
  flytninger sælges typisk via Imoova og DriveNow.

Søgninger der køres hver gang:

- `relocation Brisbane Sydney campervan $1 day`
- `relocation car Brisbane to Sydney october 2026`
- `campervan relocation australia facebook group` (udlejere poster dér før platformene)
- `one way relocation Gold Coast to Sydney`

Finder du en udbyder der ikke står i `sources`, så tilføj den med navn, URL, type, prioritet,
`access` og en kort note, også selvom den ikke har noget lige nu.

## Sådan opdaterer du

1. Læs `data.json`.
2. Kør `python3 scripts/refresh.py` (automatiske kilder), tjek derefter de manuelle kilder.
3. Opdatér hvert manuelt tilbuds `availability`, priser og datoer, og sæt `fit` efter reglerne ovenfor.
4. Opdatér eksisterende poster frem for at duplikere. Forsvundne tilbud fjernes og noteres i loggen.
5. Sæt `updated` til nuværende Brisbane-tid i ISO 8601 med `+10:00`.
6. Tilføj **én** post i `log`. Behold højst 40.
7. Commit og push til `main` med beskeden `tjek: <kort opsummering>`.

## Vigtigt

- Opfind aldrig et tilbud, en dato eller en inklusion. Karsten booker på det her.
  Kunne en side ikke læses, så skriv det. Det er langt bedre end et gæt.
- Starter et nyt tilbud med `fit: "passer"`, så begynd logteksten med `NYT:`.
- Ret ikke i `index.html` ved et tjek, kun `data.json` og `img/`.
