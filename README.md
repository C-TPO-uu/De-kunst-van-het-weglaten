# De-kunst-van-het-weglaten: Rechtspraak.nl scraper met passage-gebaseerde uitsluiting

Dit Python-script is de technische operationalisering van de zoekstrategie voor systematische rechtspraakanalyse zoals beschreven in:
> C.M. Taylor Parkins-Ozephius, 'De kunst van het weglaten: uitspraken verzamelen voor systematische rechtspraakanalyse door contextuele uitsluiting op passageniveau met een Python-script', *Law and Method* 2026.

Het script lost het granulariteitsprobleem op dat, kort gezegd, ontstaat wanneer juridische databanken uitsluiting enkel op uitspraakniveau (ECLI) toestaan.

## ⚖️ Methodologische grondslag
Het script is ontworpen rondom de volgende wetenschappelijke uitgangspunten zoals beschreven in het bijbehorende artikel:

* **Uitsluiting op passageniveau:** In plaats van volledige uitspraken te verwijderen, filtert het script op individuele tekstsegmenten. Dit voorkomt dat een relevante uitspraak verloren gaat omdat er elders in de tekst een irrelevante context voorkomt.
* **Proximity-based filtering (Nabijheidszoeken):** De relevantie van een kernbegrip wordt beoordeeld aan de hand van de absolute woordafstand tot gedefinieerde uitsluitingstermen.
* **Asymmetrische filterlogica:** Het script is conservatief ingericht om *false negatives* (verlies van relevante data) te minimaliseren, waarbij een beperkte hoeveelheid *false positives* (ruis) wordt geaccepteerd voor handmatige screening.
* **Transparantie en repliceerbaarheid:** Door middel van een audit trail en configuratie-hashing (SHA-256) zijn alle selectiebeslissingen achteraf controleerbaar en reproduceerbaar.

## 🛠️ Werking van het script (Vier stappen)

Conform de structuur van het artikel doorloopt het script de volgende fasen:

1. **Stap 1: Ophalen van uitspraken**  
   Het script bevraagt de API van rechtspraak.nl op basis van metadata (datum, rechtsgebied, instantie). Bij instabiele verbindingen legt het script fouten vast in een apart bestand voor een latere `retry-modus` om volledigheid te bereiken.
2. **Stap 2: Zoeken naar kernbegrippen**  
   Met behulp van Reguliere Expressies (Regex) wordt gezocht naar de kernbegrippen en hun vervoegingen (bijv. `\b(on)?betrouw\w*`) op passageniveau.
3. **Stap 3: Contextuele uitsluiting**  
   Het script berekent de woordafstand tussen het kernbegrip en uitsluitingscriteria:
   * **Vaste termen:** Directe woordcombinaties die duiden op irrelevante context.
   * **Contextuele termen:** Termen die binnen een drempelwaarde (bijv. 20 woorden) van het kernbegrip staan.
4. **Stap 4: Rapportage & Audit Trail**  
   Het script genereert vier CSV-bestanden (Resultaten, Weggegooid, Overzicht, Fouten) en een JSON-metadatabestand. Elke run krijgt een unieke SHA-256 hash gebaseerd op de inhoudelijke configuratie; als de instellingen wijzigen, veranderen de hash en de bestandsnamen automatisch mee.

## 🚀 Gebruik & Configuratie
### 1. Installatie
Installeer de benodigde Python-bibliotheken via je terminal:

```bash
pip install requests xmltodict pandas
```

### 2. Configuratie (Instellen voor eigen onderzoek)
>Let op: Het script is standaard vooringevuld met de zoektermen, uitsluitingscriteria en afstanden die zijn gebruikt voor het onderzoek in het bijbehorende artikel. Dit dient als voorbeelddata, zodat notatie en werking direct helder zijn. Je hoeft in beginsel geen onderliggende Python-code aan te passen.

De configuratie is opgesplitst in twee logische delen: inhoudelijke instellingen (die de inhoudelijke selectie en de hash bepalen) en run-specifieke instellingen (die de technische uitvoering sturen).

In het kort: Pas de CONTENT_CONFIG in het script aan om je eigen uitsluitingscriteria te definiëren. Gebruik RUN_CONFIG om de instanties, datumbereik en rechtsgebied eventueel aan te passen. Zie hiervoor ook de waardelijsten die rechtspraak.nl deelt in het kader van Open Data. Via RUN_CONFIG is het eveneens mogelijk om test_mode in te schakelen voor iteratieve verfijning (trial-and-error) van de uitsluitingscriteria.

### 💡 Uitleg van de onderdelen in `CONTENT_CONFIG`
*Elke wijziging in deze sectie genereert een unieke SHA-256 hash in de bestandsnamen en metadata.*

* **`include_patterns` (Kernbegrippen):**  
  Hier definieer je de zoektermen. Door gebruik te maken van Reguliere Expressies (Regex) kun je met één patroon meerdere woordvarianten en vervoegingen opvangen.  
  * *Voorbeeld:* Met `r"\b(on)?betrouw\w*"` vang je in één keer woorden op als *betrouwbaar*, *onbetrouwbaar*, *betrouwbaarheid* en *onbetrouwbaarheid*.

* **`excluded_terms` (Vaste uitsluitingen):**  
  Woordcombinaties of zinnen die **altijd** tot uitsluiting van de passage dienen te leiden, ongeacht de afstand (bijv. de standaard overweging dat de rechter *"geen reden ziet om aan de juistheid en betrouwbaarheid"* te twijfelen).

* **Categorieën van contextuele termen (`analoog_bewijs`, `integriteit_context`, etc.):**  
  Hier groepeer je per inhoudelijke categorie uitsluitingstermen in een Regex-patroon met behulp van het `|`-teken (de OR-operator).  
  * *Voorbeeld:* `r"\bgetuige(n)?|\bslachtoffer(s)?|\baangifte(n|s)?"` zorgt ervoor dat zodra een van deze woorden voorkomt, de bijbehorende categorie wordt getriggerd.

* **`context_exclusions` (Proximity-regels / Nabijheidszoeken):**  
  Driedimensionale regels vastgelegd als een tuple: `(kernbegrip_regex, categorie_naam, maximale_woordafstand)`.  
  * *Voorbeeld:* `(r"\b(on)?betrouw\w*", "analoog_bewijs", 20)` betekent dat als een term uit de categorie `analoog_bewijs` (bijv. *"getuige"*) binnen **20 woorden** voor of na het kernbegrip (bijv. *"betrouwbaarheid"*) staat, deze passage automatisch wordt uitgesloten.

---

>### 🔤 Tussendoortje: Beknopte Regex-gids voor juristen en onderzoekers
>
>In de configuratie wordt gebruikgemaakt van Reguliere Expressies (Regex). Dit zijn patronen waarmee je flexibel naar tekstvariaties zoekt. De belangrijkste voor gebruik in dit script zijn (combinaties van) deze:
>
>1. **`\b` (Woordgrens / Word Boundary):**  
>   Zorgt ervoor dat je een **heel woord** of het **begin van een woord** zoekt, en niet een losse lettercombinatie middenin een ander woord.  
>   * *Voorbeeld:* `\bvalid` matcht wel op *validiteit*, maar niet op de letters 'valid' in het Engelse woord *in**valid**ate*.
>
>2. **`|` (OF-operator / Pipes):**  
>   Hiermee som je alternatieve termen op binnen een categorie. Het werkt als een "OF"-functie.  
>   * *Voorbeeld:* `aangifte|getuige|slachtoffer` zoekt naar *aangifte* OF *getuige* OF *slachtoffer*.
>
>3. **`\w*` (Snelkoppeling voor vervoegingen / Wildcard):**  
>   Matcht nul of meer letters/tekens achter een woordstam.  
>   * *Voorbeeld:* `betrouw\w*` matcht op *betrouw<b>baar</b>*, *betrouw<b>baarheid</b>*, *betrouw<b>bare</b>*, etc.
>
>4. **`( ... )?` (Optionele onderdelen / Enkelvoud & Meervoud):**  
>   Alles tussen de haakjes met een vraagteken erachter is optioneel. Dit is ideaal om enkelvoud én meervoud in één keer op te vangen.  
>   * *Voorbeeld 1:* `getuige(n)?` matcht op *getuige* én *getuigen*.  
>   * *Voorbeeld 2:* `(on)?betrouw` matcht op *betrouw* én *<b>on</b>betrouw*.  
>   * *Voorbeeld 3:* `aangifte(n|s)?` matcht op *aangifte*, *aangifte<b>n</b>* én *aangifte<b>s</b>*.

### 💡 Uitleg van de onderdelen in `RUN_CONFIG`
Wijzigingen hierin hebben betrekking op de reikwijdte van de run en veranderen de inhoudelijke unieke hash van de zoekstrategie niet.

* **`datumrange` & `rechtsgebied`:** Bepalen de zoekgrenzen voor het ophalen van uitspraken via de Rechtspraak.nl API.
> **Notatie datumbereik:** Gebruik `("YYYY-MM-DD", "YYYY-MM-DD")` met voorloopnullen (bijv. `("2024-01-01", "2025-12-31")`). De API accepteert geen Nederlandse datumnotaties (zoals `1-1-2024`).
* **`instanties`:** Een overzicht waarin per rechtsprekende instantie via `True` (wel meenemen) of `False` (uitsluiten) de selectie aan- of uitgezet kan worden.
* **`test_mode` & `test_batch_size`:** Maakt het mogelijk om snel een proefrun te draaien (bijv. op 100 uitspraken) om te controleren of de uitsluitingstermen niet te streng of te soepel zijn ingesteld.
* **`retry_mode`:** Wanneer een eerdere run is onderbroken door netwerkstoringen of API-blokkades, verzamelt het script alle gemiste ECLI's uit `uitspraken_fouten_[HASH].csv` en verwerkt met `"retry_mode": True` uitsluitend die ontbrekende bestanden.

## 📁 Output-structuur

Het script genereert bestanden met de unieke `[HASH]` (SHA-256) van je inhoudelijke configuratie in de bestandsnaam:

| Bestand | Inhoud |
| :--- | :--- |
| `uitspraken_resultaten_[HASH].csv` | Mogelijk relevante passages voor handmatige screening. |
| `uitspraken_weggegooid_[HASH].csv` | Uitgesloten passages inclusief de reden van uitsluiting en de berekende woordafstand. |
| `uitspraken_overzicht_[HASH].csv` | Overzicht van alle verwerkte ECLI’s, met het aantal relevante en uitgesloten passages. |
| `uitspraken_fouten_[HASH].csv` | Overzicht van niet-verwerkte ECLI’s t.b.v. een automatische of handmatige retry. (indien van toepassing)|
| `run_metadata_[HASH].json` | Volledige parameterset en audit trail voor maximale repliceerbaarheid. |

---

## ⚠️ Beperkingen
Hoewel het script is ontworpen met robuustheid en repliceerbaarheid als uitgangspunt, kent het enkele inherente beperkingen die voortkomen uit zowel technische als externe randvoorwaarden:

1. **Afhankelijkheid van de Rechtspraak.nl API:**  
   Het script is afhankelijk van de publieke API van rechtspraak.nl. Deze API kent geen formeel gedocumenteerde rate limits en kan bij intensief gebruik tijdelijke blokkades (bijv. HTTP 403 of 429) opleggen. Hoewel het script gebruikmaakt van automatische pauzes, kan niet worden gegarandeerd dat zeer grote zoekopdrachten altijd in één ononderbroken run worden afgerond.
2. **Server-side onderbrekingen & Retry-mechanisme:**  
   Netwerkfouten of server-side blokkades worden automatisch gedetecteerd en vastgelegd in `uitspraken_fouten_[HASH].csv`. Om te garanderen dat er geen gegevens verloren gaan, kan het script met `"retry_mode": True` opnieuw worden opgestart om enkel de gemiste ECLI's alsnog op te halen.
3. **Heuristische aannames bij contextuele nabijheid:**  
   De gekozen woordafstanden en uitsluitingscriteria zijn gebaseerd op methodologisch onderbouwde, maar uiteindelijk heuristische keuzes. Hoewel deze keuzes transparant zijn vastgelegd in de configuratie en audit trail, blijft menselijke interpretatie noodzakelijk bij de eindselectie van relevante passages.
4. **CSV-gebaseerde opslag als schaalbeperking:**  
   De keuze voor CSV-bestanden bevordert transparantie en laagdrempelige toegankelijkheid (bijv. via Excel of SPSS), maar is minder efficiënt bij extreem grote datasets (tienduizenden uitspraken).

---

## 📝 Citeerwijze & Contact

> C.M. Taylor Parkins-Ozephius, 'De kunst van het weglaten: uitspraken verzamelen voor systematische rechtspraakanalyse door contextuele uitsluiting op passageniveau met een Python-script', *Law and Method* 2026.

📧 **Contact:** [C.M.TaylorParkins-Ozephius@uu.nl](mailto:C.M.TaylorParkins-Ozephius@uu.nl)

