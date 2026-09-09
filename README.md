# Photo Quality Lab: Safe Enhancement / Recoverability Routing

Case study per la posizione **Product Builder, Agentic AI Products** · Immobiliare.it · settembre 2026

Prototipo end-to-end per valutare e migliorare fotografie immobiliari mantenendo come vincolo principale la fedeltà rispetto all'immobile reale.

Il sistema applica il livello minimo di intervento sufficiente. Quando l'immagine degradata non contiene abbastanza informazione verificabile per una recovery affidabile, richiede un nuovo scatto.

**Setup locale di sviluppo e demo.** n8n, il servizio di diagnosi e le due UI girano in locale; Supabase, Cloudinary, OpenAI e Gemini sono servizi cloud.

---

## Obiettivo

Il caso considera foto caricate da smartphone da privati o piccole agenzie, senza un fotografo professionista.

I problemi fotografici trattati includono:

* esposizione;
* dominante cromatica;
* blur;
* rumore;
* compressione;
* perdita di dettaglio;
* risoluzione insufficiente.

### Trattati parzialmente

Alcuni aspetti non vengono modificati direttamente dal sistema, ma sono stati trattati come vincoli di sicurezza e fedeltà:

* conservazione di oggetti e loro posizione;
* geometria della stanza e delle aperture;
* materiali, texture e finiture;
* difetti visibili dell'immobile;
* testo presente nella scena;
* vista esterna, framing e crop;
* attendibilità dei dettagli ricostruiti da L4.

Questi aspetti entrano nel progetto attraverso il prompt conservativo di L4, la review manuale di fedeltà, il benchmark del checker automatico, il recoverability gate e la conferma umana obbligatoria sugli output generativi.

Il sistema non può garantire automaticamente la correttezza semantica di ogni dettaglio. Per questo la decisione finale su L4 resta human-in-the-loop.

### Fuori perimetro

Non sono implementate trasformazioni intenzionali dell'immobile o della scena, tra cui:

* virtual staging;
* decluttering;
* redesign;
* aggiunta, rimozione o spostamento volontario di oggetti;
* sostituzione intenzionale di materiali o finiture;
* rimozione intenzionale di difetti reali dell'immobile.

---

## Scala sperimentale L0–L4

Il progetto è partito da cinque possibili livelli di intervento. Ogni foto del benchmark è stata processata con tutti i livelli.

| Livello | Implementazione                | Ruolo                                       |
| ------- | ------------------------------ | ------------------------------------------- |
| **L0**  | immagine invariata             | baseline                                    |
| **L1**  | Cloudinary `e_improve`         | light polish                                |
| **L2**  | Cloudinary `e_enhance`         | secondo candidato automatico di enhancement |
| **L3**  | Cloudinary `e_gen_restore`     | restoration generativa                      |
| **L4**  | OpenAI GPT Image 2, image edit | recovery generativa più forte               |

### L0

Nessuna trasformazione. Serve come baseline e diventa **KEEP** nel routing finale.

### L1

Correzione leggera tramite Cloudinary `e_improve`.

È pensata soprattutto per:

* piccoli problemi di esposizione;
* colore;
* white balance;
* miglioramento fotografico generale senza ricostruzione generativa.

### L2

Secondo candidato automatico basato su Cloudinary `e_enhance`.

È stato incluso nel benchmark per verificare se offrisse un vantaggio stabile rispetto a L1.

### L3

Restoration generativa tramite Cloudinary `e_gen_restore`.

È stato testato come livello intermedio tra enhancement automatico e recovery generativa L4.

### L4

Image edit con GPT Image 2.

Riceve l'immagine degradata e un prompt conservativo che permette interventi su:

* esposizione;
* white balance e color cast;
* contrasto;
* rumore;
* compressione;
* nitidezza recuperabile;
* qualità fotografica generale.

Il prompt chiede di preservare oggetti, geometria, materiali, texture, difetti, testo, vista, framing e crop.

L4 può recuperare immagini fortemente degradate, ma introduce un rischio specifico: quando l'input è ambiguo può ricostruire dettagli visivamente plausibili che non sono verificabili.

---

## Golden set e fan-out

Il benchmark usa **30 fotografie** distribuite su sei tipologie di ambiente:

* bagno;
* cucina;
* soggiorno;
* camera da letto;
* corridoio;
* stanze vuote.

Le degradazioni comprendono blur, compressione, rumore, esposizione e problemi di colore. La maggior parte delle degradazioni è sintetica e costruita per stressare il sistema.

Ogni foto è stata processata su tutti i livelli:

```text
30 immagini × 5 livelli = 150 esecuzioni
```

Sono stati mantenuti anche controlli `do no harm` su fotografie sane per verificare che l'enhancement non venisse applicato senza beneficio.

---

## Diagnosi deterministica

La diagnosi è separata dal routing.

`diagnosis-service/app/main.py` misura caratteristiche dell'immagine e produce segnali strutturati. La scelta KEEP/L1/L4/RETAKE avviene successivamente in n8n.

```text
immagine
   ↓
segnali raw
   ↓
classificazione del difetto
   ↓
routing prodotto
```

Questa separazione permette di modificare la policy di prodotto senza cambiare il significato delle metriche fotografiche.

### Metodo

La diagnosi non parte da un unico metodo di calibrazione.

Dove possibile utilizza metriche o principi già descritti in letteratura. Le regole operative trasformano poi questi segnali continui in categorie utilizzabili dal router.

Il golden set viene usato soprattutto per:

* verificare il comportamento sui difetti noti;
* controllare i falsi positivi sulle fotografie pulite;
* confrontare input degradati e originali quando disponibili;
* stressare le regole con degradazioni sintetiche controllate;
* verificare l'intera pipeline alle stesse condizioni del servizio reale.

Non tutte le soglie hanno quindi la stessa origine.

Per alcune misure esiste una base metodologica pubblicata; per altre il cutoff è una scelta operativa del prototipo, verificata sui dati disponibili. I segnali raw vengono mantenuti insieme alla classificazione per rendere queste decisioni ispezionabili.

### Blur

Il segnale principale è `blur_effect` di `scikit-image`, basato sulla metrica no-reference di Crété-Roffet et al.

La metrica restituisce un valore crescente con il blur.

Per rendere confrontabili le immagini, la diagnosi normalizza il lato massimo a 1280 px senza effettuare upscale.

Le soglie già utilizzate nella diagnosi sono:

```text
blur_effect >= 0.70  → high
blur_effect >= 0.55  → medium
blur_effect >= 0.40  → low
```

Le originali pulite disponibili restavano sotto circa `0.37`, quindi il benchmark ha anche fornito un controllo empirico sul margine della soglia `low`.

Se il detector del rumore è alto mentre `blur_effect` resta sotto soglia, il risultato può essere marcato `uncertain`, perché il rumore interferisce con le misure di alta frequenza.

#### Blur locale

Il limite pratico di una metrica globale è che una zona molto nitida può compensare aree significativamente sfocate.

L'uso di misure di blur a blocchi è già presente nella letteratura sulla stima no-reference della nitidezza. La v5 applica quindi la stessa metrica su una griglia 4×4.

Non viene introdotto un nuovo blur score: ogni tessera usa la stessa soglia `low` già presente nella diagnosi.

Le tessere quasi uniformi vengono escluse:

```text
std < 0.02
```

Una tessera informativa viene considerata sfocata con:

```text
blur_effect >= 0.40
```

Se più della metà delle tessere informative è sfocata, la classificazione globale viene portata almeno a `medium`.

Un primo test era stato eseguito usando `0.55` come soglia per tessera. Nel servizio finale è stata riutilizzata `0.40`, già esistente come soglia `low`, ottenendo una separazione più netta.

Sul golden set finale:

```text
clean / non-blur: massimo osservato ≈ 38% tessere sfocate
blur sintetico:   minimo osservato ≈ 73%
corridoio_04:     ≈ 81%
```

Il tile blur ha quindi corretto casi in cui la metrica globale sottostimava un degrado distribuito sull'immagine senza introdurre un nuovo cutoff di blur.

### Rumore

Come primo segnale è stato utilizzato `noise_sigma`, stimato tramite wavelet.

Nei test, però, fotografie pulite potevano presentare valori elevati anche senza degradazione sintetica. `noise_sigma` viene quindi conservato come informazione diagnostica, ma non è diventato il discriminante principale.

Il segnale risultato più utile nel prototipo è:

```text
high_frequency_ratio =
varianza Laplaciano raw
────────────────────────
varianza Laplaciano dopo smoothing
```

La regola corrente è:

```text
HF >= 80
OR
(HF >= 50 AND blur_effect >= 0.50)
→ noise = high
```

Sul golden set ha individuato i **3/3 casi di rumore sintetico** senza falsi positivi sulle 29 originali pulite disponibili.

Questa classificazione resta una euristica sperimentale del prototipo.

### Compressione JPEG

Il detector sfrutta una proprietà strutturale della compressione JPEG: il blocking tende a produrre discontinuità lungo la griglia 8×8.

`calculate_jpeg_blockiness()` confronta le differenze tra pixel sui confini dei blocchi con quelle presenti sulle linee immediatamente adiacenti.

La misura viene eseguita sull'immagine originale, senza resize, per non alterare la griglia JPEG.

```text
blockiness_ratio = boundary_mean / neighbor_mean
jpeg_blockiness  = blockiness_ratio - 1
```

La soglia si applica a `jpeg_blockiness`, non al ratio.

Le originali pulite arrivavano circa a `1.04`. La regola operativa del prototipo usa:

```text
jpeg_blockiness < 1.20
→ none

jpeg_blockiness >= 1.20 + blur presente
→ uncertain

jpeg_blockiness >= 1.20 senza blur
→ high
```

Il detector è orientato soprattutto al blocking forte. Compressioni più moderate possono non essere rilevate.

### Esposizione

L'esposizione usa statistiche derivate dalla distribuzione di luminanza:

* luminanza media e mediana;
* percentili `p05` e `p95`;
* percentuale di ombre prossime al nero;
* percentuale di alte luci prossime al bianco.

Per la sottoesposizione:

```text
mean_luminance < 35
OR shadows_clipped_pct >= 20
→ high

mean_luminance < 70
OR shadows_clipped_pct >= 10
→ medium

mean_luminance < 100
→ low
```

Questi cutoff servono a trasformare un segnale continuo in una severity utile al router.

Per la sovraesposizione il solo highlight clipping è risultato insufficiente: finestre, pareti o superfici realmente bianche possono produrre valori elevati senza rendere washed-out l'intera fotografia.

Il confronto paired tra input degradati e originali puliti ha quindi portato a combinare:

* luminanza media;
* `p95_luminance`;
* clipping delle alte luci;
* saturazione media.

La classificazione corrente è:

```text
mean >= 240
AND p95 >= 250
AND highlights clipped >= 20%
AND mean saturation < 50
→ high

mean >= 220
AND p95 >= 245
AND mean saturation < 50
→ medium

mean >= 205
AND p95 >= 245
AND mean saturation < 50
→ low
```

Nel golden set questa combinazione separa i casi di white blend osservati senza trattare come sovraesposta ogni scena contenente alte luci legittime.

### Risoluzione

La risoluzione è trattata come policy distinta dai detector fotografici.

```text
min_side <= 500  → high
min_side < 720   → medium
min_side < 1080  → low
altrimenti       → none
```

La misura esprime quanta informazione spaziale è disponibile per un'eventuale recovery. Non viene usata per inferire la compressione.

### Colore

I primi test consideravano statistiche globali RGB/HSV, tra cui:

* `color_cast_score`;
* `warm_cool_score`;
* saturazione media.

Il confronto con le originali pulite ha mostrato che queste misure non bastano a distinguere una dominante artificiale da contenuto realmente caldo o freddo.

Pareti beige, parquet, legno, illuminazione calda e luce naturale possono produrre segnali globali simili a un color cast.

È stato quindi introdotto `calculate_neutral_color_shift()`.

L'immagine viene convertita in CIELAB. Vengono considerati pixel con:

```text
20 <= L <= 95
```

e, tra questi, il 25% con croma più bassa.

La distanza del vettore medio nei canali `a,b` produce:

```text
neutral_chroma_shift
```

Il prefiltro usa:

```text
neutral_chroma_shift == null
OR neutral_chroma_shift >= 3
OR neutral_region_pct < 5
→ triage Gemini
```

La soglia `3` è una scelta empirica del prefiltro.

Gemini interviene solo nei casi ambigui e determina se la dominante osservata sia plausibile per il contenuto reale della stanza oppure sospetta.

Il router riceve soltanto l'esito normalizzato:

```text
normale
sospetto
incerto
```

### Fotografie monocromatiche

Un caso separato riguarda la perdita quasi completa dell'informazione cromatica.

Un'immagine in scala di grigi ideale ha saturazione pari a zero. Una fotografia JPEG memorizzata in RGB può però acquisire qualche unità di rumore cromatico dalla compressione.

Per evitare che questo rumore venga interpretato come colore reale, la diagnosi utilizza `p95_saturation` invece della sola media:

```text
p95_saturation < 8
→ RETAKE
```

Il significato è: anche il 5% dei pixel più saturi contiene una quantità trascurabile di colore.

Nel golden set:

```text
corridoio_04: p95_saturation = 0
altre 29 foto: p95_saturation >= 30
```

La soglia `8` resta quindi sopra il rumore cromatico atteso per un'immagine sostanzialmente grayscale e molto sotto il minimo osservato sulle fotografie a colori.

La regola copre il bianco e nero puro o quasi puro. Non identifica necessariamente immagini seppia o altri viraggi con saturazione non nulla.

### Verifiability risk

I singoli detector vengono infine combinati in `calculate_verifiability_risk()`.

Il segnale non misura quanto una fotografia sia esteticamente buona. Stima quanto sia difficile verificare la correttezza di un eventuale output ricostruttivo sulla base dell'informazione ancora presente nell'input.

Il risultato alimenta successivamente il recoverability gate.

Il codice e il razionale completo sono documentati in:

[`docs/diagnosi_e_routing.md`](docs/diagnosi_e_routing.md)

---

## Review umana

Per valutare gli output è stata costruita durante lo sviluppo una **mini UI di review collegata a Supabase**.

La view `review_qualita_images` esponeva per ogni fotografia gli URL degli output L0–L4. La UI li mostrava nello stesso contesto e salvava i confronti nella reference strutturata.

La prima fase ha raccolto:

```text
L1 vs L0
L4 vs L0
```

Successivamente la UI è stata estesa per mostrare tutti gli output **L0–L4** e raccogliere:

```text
L2 vs L1
L3 vs L4
```

Sono stati scelti i confronti necessari alle decisioni di prodotto, evitando tutte le dieci combinazioni pairwise possibili tra cinque livelli.

La reference finale è una **single-reviewer structured benchmark review**.

La mini UI usata per costruire la reference è distinta dalla **Lab UI finale**, che presenta in forma statica i risultati congelati del benchmark.

![UI comparativa usata per la review L0-L4](docs/assets/pic_comparation_ui_example.png)

---

## Risultati della selezione dei livelli

### L1 vs L0

| Risultato | Casi |
| --------- | ---: |
| L1 vince  |   14 |
| Pareggio  |    9 |
| L0 vince  |    7 |

Nel dominio previsto di luce, colore e white balance:

```text
9 vittorie L1
2 pareggi
0 sconfitte
```

L1 viene quindi mantenuto come light polish.

### L2 vs L1

```text
L2 vince: 5
Pareggi: 13
L1 vince: 12
```

Il vantaggio osservato nei pochi casi favorevoli a L2 era generalmente ridotto e non individuava un dominio abbastanza distinto da giustificare un ulteriore ramo produttivo.

**L2 viene escluso.**

### L3 vs L4

```text
L3 vince: 0
Pareggi: 3
L4 vince: 27
```

Sul golden set non emerge un caso in cui L3 sia preferibile a L4.

**L3 viene escluso.**

### L4 vs L0

```text
L4 vince: 28
Pareggio: 1
L0 vince: 1
```

Nei casi con blur e compressione:

```text
16/16 vittorie L4
```

L4 viene mantenuto come livello di recovery.

![Lab UI con i risultati del benchmark](docs/assets/ui_lab.png)

---

## Qualità e fedeltà

La qualità visiva da sola non è sufficiente per una fotografia immobiliare.

Tutti i 30 output L4 sono stati quindi sottoposti anche a review manuale di fedeltà.

Risultato:

```text
8/30 output L4 con alterazioni materiali
```

Le cause sono state classificate in:

```text
6 casi: ambiguità già presente nell'input
2 casi: alterazione diretta prodotta da L4
```

Il benchmark distingue quindi due domande:

1. l'immagine migliorata è fotograficamente migliore?
2. l'output rappresenta ancora in modo affidabile ciò che era verificabile nell'input?

L4 ottiene risultati molto forti sul primo punto. Il secondo richiede controlli aggiuntivi.

---

## Checker automatico di fedeltà

È stato testato un checker VLM per identificare automaticamente alterazioni materiali.

Il primo benchmark contro la reference umana ha prodotto:

```text
TP = 0
FN = 7
FP = 0
TN = 22
recall = 0%
```

Il checker non è quindi usato come hard gate nel prodotto finale.

La reference manuale resta il riferimento del benchmark di fedeltà.

---

## Recoverability

La fase successiva ha cercato di prevedere quando l'input contiene ancora abbastanza informazione verificabile per consentire una recovery L4.

Per calibrare il gate sono stati considerati:

```text
6 failure causate da input ambiguity
22 output L4 safe
```

I due casi di alterazione diretta prodotta da L4 sono stati esclusi da questa calibrazione: rappresentano un rischio diverso, che una misura della recoverability dell'input non può prevedere direttamente.

La diagnosi considera, tra gli altri segnali:

* blur;
* compressione;
* rumore;
* esposizione;
* risoluzione;
* `verifiability_risk`;
* `resolution_risk`.

La regola semplice risultata migliore sul benchmark è:

```text
verifiability_risk = high
AND resolution_risk != none
→ RETAKE
```

Risultato:

```text
TP = 5
FN = 1
FP = 1
TN = 21
```

| Metrica     | Valore |
| ----------- | -----: |
| Recall      |  83,3% |
| Precision   |  83,3% |
| Specificity |  95,5% |

Il falso negativo è `camera_da_letto_05`; il falso positivo è `corridoio_01`.

Non è stata aggiunta una regola ad hoc per correggere il singolo falso negativo.

Il gate resta quindi un **candidate recoverability gate derivato dal benchmark**, da validare su un dataset reale più ampio.

---

## Routing produttivo finale

La scala sperimentale L0–L4 viene ridotta a quattro esiti:

```text
KEEP / L0
L1
L4
RETAKE
```

`RETAKE` non è un sesto livello. È la decisione di non applicare enhancement quando la recovery richiederebbe una quantità eccessiva di ricostruzione non verificabile.

### KEEP

Foto già adeguata.

```text
output = input
human confirmation = false
```

### L1

Problema leggero di luce o colore.

```text
Cloudinary e_improve
human confirmation = false
```

### L4

Usato per:

* blur medio o alto;
* compressione seria o incerta;
* rumore alto;
* resolution risk alto;
* problemi significativi di esposizione.

Se il candidate recoverability gate segnala un rischio troppo alto, il router passa invece a RETAKE.

Ogni output L4 richiede conferma umana.

### RETAKE

La UI richiede un nuovo scatto e non produce un'immagine migliorata.

È usato anche quando l'input è sostanzialmente monocromatico:

```text
p95_saturation < 8
→ RETAKE
```

![Upload UI con output L4 e conferma umana](docs/assets/upload_ui_example.png)

---

## Architettura finale

```text
Upload UI (React)
      │
      ├─ upload unsigned ───────────────▶ Cloudinary
      │
      ▼
POST /webhook/photo_quality
      │
      ▼
n8n
 ├─ crea record `foto`
 ├─ diagnosis-service
 ├─ prefiltro colore
 ├─ [se necessario] Gemini
 ├─ routing v3
 │    ├─ KEEP
 │    ├─ L1 → Cloudinary e_improve
 │    ├─ L4 → GPT Image 2 → Cloudinary
 │    └─ RETAKE
 ├─ salva `decisioni_finali`
 └─ risposta alla Upload UI

L4
 └─ confronto prima/dopo
      │
      ▼
 POST /webhook/confirm_l4
      │
      ├─ confirmed
      └─ rejected
```

![Workflow n8n completo](docs/assets/PI_n8n_full_workflow_canvas.png)

Dettagli dei componenti e dei contratti:

[`docs/architettura.md`](docs/architettura.md)

---

## Benchmark operativo

| Cosa                | Risultato                     |
| ------------------- | ----------------------------- |
| L1, n = 10          | mediana 3,94 s · p95 4,90 s   |
| L4, n = 10          | mediana 42,10 s · p95 45,63 s |
| Costo L4            | ≈ $0,0526 / immagine          |
| Rapporto di latenza | L4 ≈ 10,7× L1                 |

Il golden set contiene volutamente molte immagini degradate. La distribuzione dei route osservata nel benchmark non rappresenta quella attesa in produzione, dove è ragionevole aspettarsi una quota maggiore di KEEP e L1.

Metodo e risultati completi:

[`docs/benchmark.md`](docs/benchmark.md)

---

## Persistenza e tracciabilità sperimentale

Supabase contiene **11 tabelle persistenti** e **4 view analitiche**.

Le strutture coprono sia il prototipo finale sia le diverse fasi del benchmark.

### Tabelle

| Tabella                   | Ruolo                                               |
| ------------------------- | --------------------------------------------------- |
| `foto`                    | metadati delle fotografie e del golden set          |
| `esecuzioni`              | fan-out L0–L4, provider, output, latenza e costo    |
| `metriche`                | metriche fotografiche calcolate sugli output        |
| `confronti_giudice`       | confronti pairwise del judge automatico             |
| `controlli_fedelta`       | controlli automatici input degradato → output       |
| `controlli_fedelta_clean` | controlli offline clean original → output           |
| `voti_umani`              | prima struttura di raccolta delle valutazioni umane |
| `reference_qualita_umane` | reference strutturata dei confronti di qualità      |
| `reference_fedelta_umane` | reference manuale delle alterazioni materiali       |
| `diagnosi_input`          | diagnosi persistita degli input degradati           |
| `decisioni_finali`        | risultato del routing produttivo e conferma L4      |

### View analitiche

| View                         | Ruolo                                             |
| ---------------------------- | ------------------------------------------------- |
| `review_qualita_images`      | espone gli URL L0–L4 alla mini UI di review       |
| `confronto_fedelta_checker`  | confronta i risultati del checker automatico      |
| `recoverability_l4_basic`    | unisce failure L4 e caratteristiche dell'input    |
| `recoverability_gate_result` | applica e valuta il candidate recoverability gate |

Il DDL completo è disponibile in:

[`db/schema.sql`](db/schema.sql)

---

## Struttura del repository

```text
├─ README.md
├─ docs/
│  ├─ assets/
│  │  ├─ upload_ui_example.png
│  │  ├─ ui_lab.png
│  │  ├─ pic_comparation_ui_example.png
│  │  └─ PI_n8n_full_workflow_canvas.png
│  ├─ nota_di_accompagnamento.md
│  ├─ architettura.md
│  ├─ benchmark.md
│  └─ diagnosi_e_routing.md
├─ n8n/
│  ├─ README.md
│  └─ photo_quality_workflow.json
├─ db/
│  └─ schema.sql
├─ diagnosis-service/
├─ upload-ui/
├─ lab-ui/
└─ .gitignore
```

---

## Avvio locale

### Requisiti

* Docker Desktop;
* Node.js e npm;
* container n8n già configurato;
* credenziali per Cloudinary, Supabase, OpenAI e Gemini;
* workflow importato da `n8n/`.

Ordine di avvio:

```text
Docker Desktop
→ n8n
→ diagnosis-service
→ upload-ui
→ lab-ui
```

### n8n

```powershell
docker start n8n
```

UI:

```text
http://localhost:5678
```

Endpoint:

```text
POST http://localhost:5678/webhook/photo_quality
POST http://localhost:5678/webhook/confirm_l4
```

Configurazione del workflow:

[`n8n/README.md`](n8n/README.md)

### diagnosis-service

Dalla root del repository:

```powershell
docker build -t diagnosis-service ./diagnosis-service
docker run --rm -p 8000:8000 --name diagnosis-service diagnosis-service
```

Servizio:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Da n8n il servizio viene raggiunto tramite:

```text
http://host.docker.internal:8000/diagnosi
```

### Upload UI

```powershell
cd upload-ui
npm install
npm run dev
```

UI:

```text
http://localhost:5173
```

### Lab UI

```powershell
cd lab-ui
npm install
npm run dev -- --port 5174
```

UI:

```text
http://localhost:5174
```

La Upload UI contiene il `cloud_name`, il nome del preset unsigned Cloudinary e gli URL dei webhook locali. Questi valori non sono segreti.

Le API key e le altre credenziali restano nell'istanza n8n e non sono incluse nel repository.

---

## Reale e simulato

### Implementato e testato

* golden set;
* degradazioni e fan-out L0–L4;
* 150 esecuzioni del benchmark principale;
* metriche fotografiche;
* diagnosi deterministica;
* blur globale e a tessere;
* detector di blockiness JPEG;
* segnali di esposizione, rumore, risoluzione e colore;
* mini UI di review;
* reference umana di qualità;
* reference umana di fedeltà;
* benchmark del checker automatico;
* analisi di recoverability;
* candidate recoverability gate;
* diagnosis-service;
* prefiltro colore;
* triage Gemini;
* routing finale;
* workflow n8n;
* Cloudinary;
* GPT Image;
* Supabase;
* conferma e rifiuto L4;
* Upload UI;
* Lab UI;
* benchmark di costo e latenza.

### Simulato o limitato al prototipo

* integrazione con l'upload nativo di Immobiliare.it, sostituita da un form;
* degradazioni prevalentemente sintetiche;
* review a singolo valutatore;
* esecuzione locale;
* testi UI senza revisione legale;
* nessuna misura di impatto business su traffico o conversione.

---

## Limiti

* Golden set di 30 fotografie.
* Degradazioni prevalentemente sintetiche.
* Review umana a singolo valutatore.
* Alcuni cutoff diagnostici sono scelte operative del prototipo e richiedono validazione su fotografie reali più numerose.
* Candidate gate derivato dallo stesso benchmark su cui è stato valutato.
* Diagnosi ancora debole nella distinzione tra defocus recuperabile e motion blur distruttivo.
* Le metriche globali possono perdere ambiguità semantiche locali.
* L4 richiede conferma umana per gestire il rischio residuo.
* Gli asset Cloudinary con delivery `upload` sono accessibili a chi conosce l'URL; un deployment reale richiederebbe hardening e delivery firmata o autenticata.

Ulteriori dettagli:

[`docs/nota_di_accompagnamento.md`](docs/nota_di_accompagnamento.md)

---

## Sviluppi successivi

### Adaptive L4 cost routing

Il prototipo usa GPT Image 2 con:

```text
quality = medium
size = auto
output = PNG
```

per tutti i casi L4.

Non è stato eseguito un benchmark tra `low` e `medium`, quindi il progetto non assume un vantaggio di fedeltà di `medium` rispetto a `low`.

Un'estensione prevista è scegliere la configurazione L4 in base al tipo di degradazione.

Per esempio:

```text
recovery prevalentemente fotometrica
→ valutare quality = low

blur / compressione / perdita di dettaglio
→ mantenere quality = medium
```

La scelta andrebbe validata misurando:

* qualità;
* fedeltà;
* costo;
* latenza.

Lo stesso benchmark potrebbe includere eventuali modelli image più economici disponibili come modelli API supportati.

### Diagnosi

Altri sviluppi:

* dataset più ampio con degradazioni reali;
* review multi-rater;
* calibrazione indipendente del recoverability gate;
* detector più affidabile per distinguere motion blur e defocus;
* hardening dell'upload e della delivery degli asset.

Un primo esperimento sulla direzionalità del blur è stato svolto durante il progetto, ma non è stato portato nel routing finale perché il set di casi reali era insufficiente per calibrare una soglia affidabile.

---

## Versioni di riferimento

| Componente           | Versione / regola                                                |
| -------------------- | ---------------------------------------------------------------- |
| Diagnosi             | `v5_tile_blur_2026-09-08`                                        |
| Routing              | `v3_2026-09-08`                                                  |
| Livelli sperimentali | L0 · L1 · L2 · L3 · L4                                           |
| Esiti produttivi     | KEEP/L0 · L1 · L4 · RETAKE                                       |
| Regola monocromatica | `p95_saturation < 8 → RETAKE`                                    |
| Candidate gate       | `verifiability_risk = high AND resolution_risk != none → RETAKE` |
| L4                   | conferma umana obbligatoria                                      |
| Modello L4           | `gpt-image-2-2026-04-21`                                         |
| Configurazione L4    | `quality=medium`, `size=auto`, PNG                               |

Ogni decisione finale salva `diagnosis_version` e `routing_version`, così i risultati restano associati alla logica che li ha prodotti.