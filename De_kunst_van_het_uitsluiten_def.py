import requests
import xmltodict
import re
import pandas as pd
import csv
import os
import time
import json
import hashlib
from datetime import datetime, timezone

# ============================================================
# 1️⃣ INHOUDELIJKE CONFIG (Veranderingen hierin genereren een nieuwe RUN_ID)
# ============================================================

CONTENT_CONFIG = {
    # 🔍 Kernbegrippen (Inclusie-criteria, ondersteunt regex)
    "include_patterns": [
        r"\b(on)?betrouw\w*",
        r"\bintegriteit\w*",
        r"\bauthenti\w*",
        r"\bvalid\w*"
    ],
    # ⛔ Vaste uitsluitingen (Zinnen of woordcombinaties die altijd worden uitgesloten)
    "excluded_terms": [
        "geen reden om aan de juistheid en betrouwbaarheid",
        "twijfelt niet aan de juistheid en betrouwbaarheid",
        "betrouwbaarheid van het proces-verbaal",
        "authentieke akte",
        "authentiek afschrift",
        "validation",
        "validity",
        "objectieve, betrouwbare, nauwkeurige en naar behoren bijgewerkte"
    ],
    #🏷️ Contextuele uitsluitingstermen per categorie (Regexen voor specifieke termen)
    # hier groepeer je de uitsluitingstermen in categorieen door "categorie": en dan met behulp van regex een opsomming van de verschillende uitsluitingstermen te geven.
    "analoog_bewijs": r"\w*verklaring(en)?|\w*herkenning(en)?|\bwaarneming(en)?|\baangifte(n|s)?|\bgetuige(n)?|\baangever(s)?|\bslachtoffer(s)?|\bbetrokkene|\b(mede)?verdachte(n|s)?|\baangeefster|\buitlating(en)?|\bPBC-rapport|\bverkoper(s)?|\bter beschikking gestelde|\breclasseringsadvies|\bbenadeelde|\bbkroongetuige",
    "integriteit_context": r"\blichamelijk(e)?|\bseksu(e|ee)?l(e)?|\bjeugdige leeftijd|\bfysiek(e)?|\bgeestelijk(e)?|\bpsychisch(e)?|\bpersoonlijk(e)?|algemene eerbaarheid|\bfinanci\w*|\beconomisch(e)?|\bhandelsverkeer",
    "eab_context": r"\bjudgement(s)?|\bconsented|\bfinal|\blaw|\bassurance|\bstatement|\blegally|\bverdict|\bcase|\benforceable|\brequested|\bEuropean arrest warrant|\bEAB|\bcourt|\bvisits|\bcase",
    # 📏 Proximity-uitsluitingen: (kernbegrip, contextuele uitsluitingsterm, max_woordafstand)
    "context_exclusions": [
        (r"\b(on)?betrouw\w*", "analoog_bewijs", 20),
        (r"\bauthenti\w*", "analoog_bewijs", 10),
        (r"\bintegriteit", "integriteit_context", 10),
        (r"\bvalid\w*", "analoog_bewijs", 10),
        (r"\bvalid\w*", "eab_context", 15)
    ]
}

# ============================================================
# 2️⃣ RUN-SPECIFIEKE CONFIG (NIET HASHED)
# ============================================================

RUN_CONFIG = {
    "datumrange": ("2024-01-01", "2025-12-31"), # opmaak: "jjjj-mm-dd", "jjjj-mm-dd"
    "rechtsgebied": "strafrecht",
    "instanties": {
        "Rechtbank_Amsterdam": True, #True neemt de instantie mee, False sluit de instantie uit 
        "Rechtbank_Den_Haag": True,
        "Rechtbank_Gelderland": True,
        "Rechtbank_Limburg": True,
        "Rechtbank_Midden-Nederland": True,
        "Rechtbank_Noord-Holland": True,
        "Rechtbank_Noord-Nederland": True,
        "Rechtbank_Oost-Brabant": True,
        "Rechtbank_Overijssel": True,
        "Rechtbank_Rotterdam": True,
        "Rechtbank_Zeeland-West-Brabant": True,
        "Gerechtshof_Amsterdam": True,
        "Gerechtshof_'s-Hertogenbosch": True,
        "Gerechtshof_Arnhem-Leeuwarden": True,
        "Gerechtshof_Den_Haag": True,
        "Parket_bij_de_Hoge_Raad": False,
        "Hoge_Raad_der_Nederlanden": False
    },
    "test_mode": True, # True = beperkte batch draaien om te testen, False = hele script draaien
    "retry_mode": False,  # Handmatig retry enkel op True zetten bij alleen mislukte ECLI's opnieuw proberen
    "test_batch_size": 100, # Aantal uitspraken tijdens test_mode
    "save_every": 50
}

# ============================================================
# 🌐 API CONSTANTEN 🛑 HIERONDER NIETS AANPASSEN (PYTHON LOGICA & VERWERKING)
# ============================================================

BASE_URL = "https://data.rechtspraak.nl/uitspraken"
SEARCH_URL = f"{BASE_URL}/zoeken"
CONTENT_URL = f"{BASE_URL}/content"
LINK_URL = "https://uitspraken.rechtspraak.nl/details"

# ============================================================
# 🔹 HASH & BESTANDEN
# ============================================================

CONFIG_HASH = hashlib.sha256(json.dumps(CONTENT_CONFIG, sort_keys=True).encode("utf-8")).hexdigest()
RUN_ID = f"{CONFIG_HASH[:8]}"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

OUT_RELEVANT = f"uitspraken_resultaten_{RUN_ID}.csv"
OUT_WEG = f"uitspraken_weggegooid_{RUN_ID}.csv"
OUT_SUMMARY = f"uitspraken_overzicht_{RUN_ID}.csv"
OUT_ERRORS = f"uitspraken_fouten_{RUN_ID}.csv"
OUT_META = f"run_metadata_{RUN_ID}_{TIMESTAMP}.json"

# ============================================================
# 🧾 HULPFUNCTIES
# ============================================================

def save_csv(filename, rows, append=True):
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_csv(
        filename,
        sep=";",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
        mode="a" if append and os.path.exists(filename) else "w",
        header=not os.path.exists(filename) or not append
    )

def load_existing_eclis(filename):
    if not os.path.exists(filename):
        return set()
    return set(pd.read_csv(filename, sep=";")["ECLI"].unique())

def safe_text(text):
    if not isinstance(text, str):
        return text
    return text.replace('"', '""').replace("\n", " ").replace("\r", " ")

# ============================================================
# 🔍 CONTEXTUELE UITSUITSLINGEN EN HITS
# ============================================================

include_patterns_compiled = [re.compile(p, re.IGNORECASE) for p in CONTENT_CONFIG["include_patterns"]]

context_exclusions_compiled = []
for pat1, pat2_key, max_words in CONTENT_CONFIG["context_exclusions"]:
    pat2_regex = re.compile(CONTENT_CONFIG[pat2_key], re.IGNORECASE)
    context_exclusions_compiled.append((re.compile(pat1, re.IGNORECASE), pat2_regex, max_words))

def is_context_excluded(text, match_span):
    words = text.split()
    start_word = len(text[:match_span[0]].split())
    
    best_match = None
    min_dist = float('inf')

    for pat1, pat2, max_words in context_exclusions_compiled:
        if not pat1.search(text[match_span[0]:match_span[1]]):
            continue
        
        for m in pat2.finditer(text):
            context_word = len(text[:m.start()].split())
            dist = abs(context_word - start_word)
            
            if dist <= max_words and dist < min_dist:
                min_dist = dist
                best_match = (True, pat1.pattern, m.group(), dist)
    
    if best_match:
        return best_match
    return False, None, None, None

def zoek_hits(paras):
    relevante, weggegooid = [], []
    for idx, p in enumerate(paras, 1):
        p_lower = p.lower()
        matches_excl = [t for t in CONTENT_CONFIG["excluded_terms"] if t.lower() in p_lower]
        hits = []
        excl_reasons = []
        for pat in include_patterns_compiled:
            for m in pat.finditer(p):
                overlap = False
                for excl in matches_excl:
                    if excl in p_lower:
                        overlap = True
                        excl_reasons.append(f"Vaste uitsluiting: {excl}")
                if not overlap:
                    excluded, kern, ctx, dist = is_context_excluded(p, m.span())
                    if excluded:
                        overlap = True
                        excl_reasons.append(f"Context: {kern} ↔ {ctx} ({dist})")
                if not overlap:
                    hits.append(m.group())
        if hits:
            relevante.append((idx, p, list(set(hits))))
        elif excl_reasons:
            weggegooid.append((idx, p, excl_reasons))
    return relevante, weggegooid

# ============================================================
# 🔍 API FUNCTIES
# ============================================================

def query_api(max_results=100, start_from=0):
    params = [
        ("max", max_results),
        ("from", start_from),
        ("return", "DOC"),
        ("date", RUN_CONFIG["datumrange"][0]),
        ("date", RUN_CONFIG["datumrange"][1]),
        ("subject", f"http://psi.rechtspraak.nl/rechtsgebied#{RUN_CONFIG['rechtsgebied']}"),
        ("sort", "DESC")
    ]
    for inst, active in RUN_CONFIG["instanties"].items():
        if active:
            params.append(("creator", f"http://standaarden.overheid.nl/owms/terms/{inst}"))
    r = requests.get(SEARCH_URL, params=params, headers={"Accept": "application/atom+xml"})
    r.raise_for_status()
    data = xmltodict.parse(r.text)
    eclis = []
    for entry in data.get("feed", {}).get("entry", []):
        ecli = entry.get("id")
        title_dict = entry.get("title", {})
        title = title_dict.get("#text") if isinstance(title_dict, dict) else title_dict
        date = entry.get("updated", "")
        if ecli:
            eclis.append({"ECLI": ecli, "Titel": title, "Datum": date})
    return eclis

def extract_paras(node):
    paras = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("para"):
                if isinstance(v, list):
                    for p in v:
                        paras.extend(extract_paras(p))
                else:
                    paras.extend(extract_paras(v))
            else:
                paras.extend(extract_paras(v))
    elif isinstance(node, list):
        for i in node:
            paras.extend(extract_paras(i))
    elif isinstance(node, str):
        paras.append(node)
    return paras

def get_full_text_with_regex_search(ecli):
    r = requests.get(f"{CONTENT_URL}?id={ecli}", headers={"Accept": "application/xml"})
    r.raise_for_status()
    data = xmltodict.parse(r.text)
    uitspraak = None
    for key in data.get("open-rechtspraak", {}):
        if key.lower().endswith("uitspraak"):
            uitspraak = data["open-rechtspraak"][key]
            break
    if not uitspraak:
        return []
    paras = extract_paras(uitspraak)
    clean = [re.sub(r"\s+", " ", p).strip() for p in paras if isinstance(p, str) and p.strip()]
    combined = re.compile("|".join(CONTENT_CONFIG["include_patterns"]), re.IGNORECASE)
    return [p for p in clean if combined.search(p)]

# ============================================================
# 🔄 RETRY FUNCTIE
# ============================================================

def retry_errors(rows_errors, rows_r, rows_w, rows_s, max_retries=2):
    for attempt in range(1, max_retries + 1):
        if not rows_errors:
            print(f"🔄 Geen errors om te retryen (poging {attempt})", flush=True)
            break
        print(f"🔄 Retry poging {attempt} voor {len(rows_errors)} fouten", flush=True)
        new_errors = []
        for err in rows_errors:
            ecli = err["ECLI"]
            link = err["Link"]
            try:
                paras = get_full_text_with_regex_search(ecli)
                relevante, weggegooid = zoek_hits(paras)

                totaal_relevante = len(relevante)
                totaal_weggegooid = len(weggegooid)
                totaal_hits = totaal_relevante + totaal_weggegooid

                for _, txt, terms in relevante:
                    rows_r.append({
                        "ECLI": ecli,
                        "Link": link,
                        "Datum": err.get("Datum",""),
                        "Tekst": safe_text(txt),
                        "Gevonden termen": ", ".join(terms),
                        "Totaal relevante alinea's": totaal_relevante,
                        "Handmatig relevant": ""
                    })
                for _, txt, excl in weggegooid:
                    rows_w.append({
                        "ECLI": ecli,
                        "Link": link,
                        "Datum": err.get("Datum",""),
                        "Tekst": safe_text(txt),
                        "Reden uitsluiting": "; ".join(excl),
                        "Totaal weggegooide alinea's": totaal_weggegooid
                    })
                rows_s.append({
                    "ECLI": ecli,
                    "Link": link,
                    "Datum": err.get("Datum",""),
                    "Relevante hits": len(relevante),
                    "Niet relevante hits": len(weggegooid),
                    "Totaal hits": totaal_hits
                })
            except Exception as ex:
                new_errors.append({"ECLI": ecli, "Link": link, "Datum": err.get("Datum",""), "Fout": str(ex)})
        rows_errors = new_errors
    return rows_errors

# ============================================================
# 🚀 MAIN LOOP
# ============================================================

if __name__ == "__main__":

    # Metadata JSON
    meta_data = {
        "run_id": RUN_ID,
        "timestamp": TIMESTAMP,
        "content_hash": CONFIG_HASH,
        "content_config": CONTENT_CONFIG,
        "run_config": RUN_CONFIG,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2, ensure_ascii=False)

    # Laad reeds verwerkte ECLI's
    processed_eclis = load_existing_eclis(OUT_SUMMARY)
    print(f"📄 Reeds verwerkt: {len(processed_eclis)} ECLI’s", flush=True)

    rows_r, rows_w, rows_s, rows_e = [], [], [], []

    start_time = time.time()

    # === Handmatige retry modus ===
    if RUN_CONFIG["retry_mode"]:
        if os.path.exists(OUT_ERRORS):
            all_errors = pd.read_csv(OUT_ERRORS, sep=";").to_dict(orient="records")
            if all_errors:
                print(f"🔄 Handmatige retry voor {len(all_errors)} fouten")
                rows_r, rows_w, rows_s = [], [], []
                remaining_errors = retry_errors(all_errors, rows_r, rows_w, rows_s, max_retries=2)
                save_csv(OUT_RELEVANT, rows_r)
                save_csv(OUT_WEG, rows_w)
                save_csv(OUT_SUMMARY, rows_s)
                save_csv(OUT_ERRORS, remaining_errors, append=False)
                print("✅ Handmatige retry afgerond", flush=True)
        exit(0)  # Mainloop wordt niet uitgevoerd

    # === Normale mainloop ===
    all_eclis = []
    start_from = 0
    api_batch_size = 100
    batch_counter = 0
    max_to_fetch = RUN_CONFIG["test_batch_size"] if RUN_CONFIG["test_mode"] else None

    while True:
        batch = query_api(api_batch_size, start_from)
        if not batch:
            break
        all_eclis.extend(batch)
        start_from += api_batch_size
        batch_counter += 1
        print(f"🔎 Batch opgehaald: {len(batch)} ECLI's, totaal nu {len(all_eclis)}", flush=True)
        time.sleep(0.5)
        if batch_counter % 10 == 0:
                    print("⏳ Kleine koffiepauze voor de server (10s)...")
                    time.sleep(10)
        if max_to_fetch and len(all_eclis) >= max_to_fetch:
            all_eclis = all_eclis[:max_to_fetch]
            break

    print(f"📌 Totaal op te halen ECLI's: {len(all_eclis)}", flush=True)

    for count, item in enumerate(all_eclis, 1):
        ecli = item["ECLI"]
        if ecli in processed_eclis:
            continue
        link = f"{LINK_URL}?id={ecli}"
        try:
            paras = get_full_text_with_regex_search(ecli)
        except Exception as ex:
            rows_e.append({"ECLI": ecli, "Link": link, "Datum": item["Datum"], "Fout": str(ex)})
            print(f"❌ {count}/{len(all_eclis)} {ecli} → Fout: {ex}", flush=True)
            continue

        relevante, weggegooid = zoek_hits(paras)
        print(f"✅ {count}/{len(all_eclis)} {ecli} → Relevante: {len(relevante)}, Niet relevant: {len(weggegooid)}", flush=True)

        totaal_relevante = len(relevante)
        totaal_weggegooid = len(weggegooid)
        totaal_hits = totaal_relevante + totaal_weggegooid

        for _, txt, terms in relevante:
            rows_r.append({
                "ECLI": ecli,
                "Link": link,
                "Datum": item["Datum"],
                "Tekst": safe_text(txt),
                "Gevonden termen": ", ".join(terms),
                "Totaal relevante alinea's": totaal_relevante,
                "Handmatig relevant": ""
            })
        for _, txt, excl in weggegooid:
            rows_w.append({
                "ECLI": ecli,
                "Link": link,
                "Datum": item["Datum"],
                "Tekst": safe_text(txt),
                "Reden uitsluiting": "; ".join(excl),
                "Totaal weggegooide alinea's": totaal_weggegooid,
            })
        rows_s.append({
            "ECLI": ecli,
            "Link": link,
            "Datum": item["Datum"],
            "Relevante hits": len(relevante),
            "Niet relevante hits": len(weggegooid),
            "Totaal hits": totaal_hits
        })

        if count % RUN_CONFIG["save_every"] == 0:
            save_csv(OUT_RELEVANT, rows_r)
            save_csv(OUT_WEG, rows_w)
            save_csv(OUT_SUMMARY, rows_s)
            save_csv(OUT_ERRORS, rows_e)
            rows_r, rows_w, rows_s, rows_e = [], [], [], []
            print(f"💾 {count} zaken verwerkt", flush=True)
        time.sleep(0.5)

    # Opslaan laatste batch
    save_csv(OUT_RELEVANT, rows_r)
    save_csv(OUT_WEG, rows_w)
    save_csv(OUT_SUMMARY, rows_s)
    save_csv(OUT_ERRORS, rows_e)

    # === Automatische retry na mainloop ===
    if os.path.exists(OUT_ERRORS):
        all_errors = pd.read_csv(OUT_ERRORS, sep=";").to_dict(orient="records")
        if all_errors:
            print(f"🔄 Automatische retry voor {len(all_errors)} fouten")
            rows_r, rows_w, rows_s = [], [], []
            remaining_errors = retry_errors(all_errors, rows_r, rows_w, rows_s, max_retries=2)
            save_csv(OUT_RELEVANT, rows_r)
            save_csv(OUT_WEG, rows_w)
            save_csv(OUT_SUMMARY, rows_s)
            
            if remaining_errors:
                save_csv(OUT_ERRORS, remaining_errors, append=False)
            else:
                pd.DataFrame(columns=["ECLI", "Link", "Datum", "Fout"]).to_csv(OUT_ERRORS,sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
                print("🧹 Alle fouten succesvol hersteld, foutenbestand opgeschoond", flush=True)
           
           
    elapsed = time.time() - start_time
    print(f"✅ Klaar in {elapsed/60:.1f} minuten", flush=True)
