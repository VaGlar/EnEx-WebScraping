# EnEx DAM MCP Collector

Αυτοματοποιημένη συλλογή, καταγραφή και έλεγχος πληρότητας των ωριαίων τιμών
MCP (Marginal Clearing Price) από τα ημερήσια DAM (Day-Ahead Market) αρχεία
της EnEx Group.

Το project ξεκίνησε ως σύνολο Google Colab notebooks και έχει μετατραπεί σε
ένα κανονικό Python πακέτο (`enex_dam`) που τρέχει είτε τοπικά είτε μέσω
GitHub Actions, χωρίς εξάρτηση από Google Colab/Drive.

## 📁 Δομή

```
enex_dam/
  config.py        # URL template, paths, retry/backoff, γνωστές εξαιρέσεις (DST)
  dam.py            # download + parse ενός ημερήσιου DAM αρχείου
  storage.py        # load/merge/save του dataset ως CSV
  completeness.py   # εντοπισμός ελλιπών/λειπόντων ημερομηνιών
  economics.py       # υπολογισμός μηνιαίων κερδών μηχανής (βλ. παρακάτω)
  dashboard.py        # παραγωγή του στατικού HTML dashboard (βλ. παρακάτω)
  logging_config.py # κοινή ρύθμιση logging (αρχείο + κονσόλα)
  scripts/
    bulk_download.py  # μαζική λήψη για εύρος ημερομηνιών
    daily_update.py   # λήψη μίας ημέρας (default: σήμερα)
    check_missing.py  # έλεγχος πληρότητας dataset
    manual_insert.py  # διαδραστική εισαγωγή συγκεκριμένων ημερομηνιών
    compute_profit.py # υπολογισμός & εκτύπωση μηνιαίων κερδών
    build_dashboard.py # παράγει το docs/index.html
data/
  mcp_full.csv       # το dataset (date, hour, mcp), ενημερώνεται αυτόματα
  monthly_prices.csv # μηνιαίες τιμές ΤΑ/ΕΤΑ/TTF (χειροκίνητη ενημέρωση)
docs/
  index.html          # το dashboard, ενημερώνεται αυτόματα, σερβίρεται από GitHub Pages
tests/               # pytest unit tests (χωρίς πραγματικά network calls)
.github/workflows/
  daily_update.yml   # καθημερινό cron που τρέχει το daily_update + commit
  backfill.yml       # χειροκίνητο (workflow_dispatch) backfill για εύρος ημερομηνιών
```

## ▶️ Χρήση

```bash
pip install -r requirements.txt

# Μαζική αρχική λήψη (backfill) — προεπιλογή: DATA_START_DATE έως σήμερα
python -m enex_dam.scripts.bulk_download --start 2026-01-01 --end 2026-08-19

# Καθημερινή ενημέρωση (σημερινή ημερομηνία)
python -m enex_dam.scripts.daily_update

# Έλεγχος πληρότητας
python -m enex_dam.scripts.check_missing

# Χειροκίνητη εισαγωγή συγκεκριμένων ημερομηνιών
python -m enex_dam.scripts.manual_insert

# Υπολογισμός μηνιαίων κερδών μηχανής
python -m enex_dam.scripts.compute_profit

# Παραγωγή/ενημέρωση του dashboard (docs/index.html)
python -m enex_dam.scripts.build_dashboard
```

Για development/tests:

```bash
pip install -r requirements-dev.txt
pytest
```

## 🤖 Αυτοματοποίηση

Το workflow `.github/workflows/daily_update.yml` τρέχει καθημερινά (cron,
ώρα UTC — βλ. σχόλιο στο αρχείο για τη μετατροπή σε ώρα Ελλάδας), κατεβάζει
τις τιμές της ημέρας, ελέγχει πληρότητα, και κάνει commit το ενημερωμένο
`data/mcp_full.csv` πίσω στο repo. Μπορεί επίσης να τρέξει χειροκίνητα από
το tab **Actions** (`workflow_dispatch`).

Για το αρχικό ιστορικό backfill (πριν ενεργοποιηθεί το daily cron) υπάρχει
ξεχωριστό workflow `backfill.yml`: **Actions → Backfill DAM MCP data → Run
workflow**, με προαιρετικά πεδία `start`/`end` (προεπιλογή: `2026-01-01` έως
σήμερα). Τρέχει στο runner του GitHub, οπότε δεν χρειάζεται τίποτα τοπικά.

## 📄 Logging

Τα logs γράφονται τοπικά στο `logs/mcp_log.txt` (δεν γίνονται commit στο
repo — βλέπε ιστορικό εκτελέσεων στο GitHub Actions run log).

## 💶 Μηνιαία κέρδη μηχανής

Η εγκατάσταση είναι μονάδα φυσικού αερίου 1 MW, βαθμού απόδοσης 43%
(`PLANT_CAPACITY_MW`, `PLANT_EFFICIENCY` στο `enex_dam/config.py`). Ανά ώρα:

```
margin (€/MWh ρεύματος) = MCP + ΤΑ - ΕΤΑ - (TTF / 0,43)
```

όπου ΤΑ (Τιμή Αναφοράς), ΕΤΑ (Ειδικό Τέλος Ανανεώσιμων) και TTF (τιμή φυσικού
αερίου, €/MWh αερίου) είναι μηνιαίες σταθερές — συμπληρώνονται χειροκίνητα στο
`data/monthly_prices.csv` (στήλες `month,ta,eta,ttf,mtfa`). Το TTF διαιρείται με
την απόδοση ώστε να ανάγεται σε κόστος καυσίμου ανά MWh ρεύματος. Η στήλη
`mtfa` (Μέση Τιμή Φυσικού Αερίου) δεν μπαίνει στον τύπο — κρατιέται μόνο για
σύγκριση/συσχέτιση με το TTF στο dashboard (βλ. παρακάτω· είναι σχεδόν
ταυτόσημη με το TTF, r ≈ 1).

Το μηνιαίο κέρδος πολλαπλασιάζει τον μέσο όρο του margin επί τις ώρες του
μήνα, την ισχύ (1 MW) και έναν συντελεστή διαθεσιμότητας 350/365 (η μηχανή
προϋπολογίζεται να λειτουργεί 24ω/ημέρα, 350 μέρες/έτος — `AVAILABILITY_FACTOR`
στο config.py). Δεν αφαιρείται άλλο λειτουργικό κόστος (OPEX) προς το παρόν,
άρα «κέρδη μηχανής» = τα έσοδα από αυτό το spread.

`python -m enex_dam.scripts.compute_profit` τυπώνει τον πίνακα μηνιαίων
κερδών (ώρες, μέσο margin €/MWh, κέρδος €) και προαιρετικά τον αποθηκεύει με
`--out FILE.csv`. Αν λείπει κάποιος μήνας από το `monthly_prices.csv`, το
script σταματά με σαφές μήνυμα σφάλματος αντί να υπολογίσει λάθος νούμερο.

## 📊 Dashboard

`python -m enex_dam.scripts.build_dashboard` παράγει ένα αυτόνομο στατικό HTML
(`docs/index.html`, χωρίς εξωτερικά assets/CDN) με:
- στατιστικά tiles (τελευταία μέση MCP, συνολικό κέρδος, μέσο margin, ελλιπείς μέρες)
- γράφημα ημερήσιας μέσης τιμής MCP (line chart, hover tooltip + crosshair)
- γράφημα μηνιαίου κέρδους μηχανής (bar chart, hover tooltip)
- ενότητα **Ανάλυση**: γράφημα τάσεων MCP/ΤΑ/ΕΤΑ/TTF/Κέρδους (δείκτης 100 =
  πρώτος μήνας, ώστε να συγκρίνονται μεγέθη διαφορετικής κλίμακας σε ένα
  chart χωρίς δεύτερο άξονα), scatter TTF↔Κέρδος με γραμμή τάσης και
  συντελεστή συσχέτισης r, και πίνακας μέσων όρων/συσχετίσεων (`enex_dam/analysis.py`)
- εναλλαγή γράφημα/πίνακας σε κάθε κάρτα, dark mode (`prefers-color-scheme`)

Ενημερώνεται αυτόματα σε κάθε τρέξιμο του `daily_update.yml` και του
`backfill.yml`, οπότε το `docs/index.html` μένει πάντα συγχρονισμένο με το
`data/mcp_full.csv`.

**Ενεργοποίηση GitHub Pages (μία φορά, χειροκίνητα):** στο repo, **Settings →
Pages → Build and deployment → Source: "Deploy from a branch"**, branch
`main`, folder `/docs`, **Save**. Μετά το πρώτο deploy, το dashboard είναι
διαθέσιμο στο `https://vaglar.github.io/EnEx-WebScraping/`.

## 🗓️ Πληρότητα δεδομένων

Κάθε ημερομηνία αναμένεται να έχει 24 ωριαίες εγγραφές, με γνωστές εξαιρέσεις
τις ημέρες αλλαγής ώρας (23 εγγραφές την ημέρα εαρινής αλλαγής, 25 την
ημέρα φθινοπωρινής) — ορίζονται στο `enex_dam/config.py`
(`EXPECTED_HOURLY_RECORD_EXCEPTIONS`).

## ✅ Δυνατότητες / πιθανές επεκτάσεις

- [x] Ενιαία, επαναχρησιμοποιήσιμη λογική download/parse (χωρίς duplication)
- [x] Retry με backoff + timeout σε κάθε HTTP αίτημα
- [x] Πλήρες logging (επιτυχία/σφάλμα, όχι hardcoded μηνύματα)
- [x] Tests χωρίς πραγματικά network calls (mocked HTTP)
- [x] Αυτοματοποίηση μέσω GitHub Actions (χωρίς Google Drive)
- [x] Υπολογισμός μηνιαίων κερδών μηχανής (MCP+ΤΑ-ΕΤΑ-TTF/απόδοση)
- [x] Οπτικοποίηση δεδομένων MCP + μηνιαίου κέρδους (static dashboard, GitHub Pages)
- [ ] Ανάλυση στατιστικών (μέσος όρος/διακύμανση ανά μήνα, peak/off-peak)
- [ ] Ειδοποιήσεις (π.χ. Slack/email) σε περίπτωση σφάλματος ή ελλείψεων
- [ ] Αρχειοθέτηση των ωμών DAM xlsx αρχείων (όχι μόνο των ωριαίων μέσων όρων)
