# Nota di accompagnamento

**Photo Quality Lab: Safe Enhancement / Recoverability Routing**
Case study *Product Builder, Agentic AI Products* · Immobiliare.it · settembre 2026

## 1. Perimetro

Il prototipo è pensato per chi carica foto da smartphone senza un fotografo, in particolare privati e piccole agenzie. Il requisito principale è mantenere fedele la rappresentazione dell'immobile.

Gli interventi ammessi riguardano la qualità fotografica: esposizione, bilanciamento del bianco, dominante, contrasto, rumore, artefatti di compressione e nitidezza recuperabile. Sono esclusi virtual staging, decluttering, aggiunta o rimozione di oggetti, cambio di cielo o vista, modifica di materiali, aperture e geometria, rimozione di crepe, umidità o altri difetti dell'immobile. Il raddrizzamento prospettico è fuori perimetro perché modifica la geometria percepita.

Il sistema può restituire **RETAKE** quando una recovery affidabile richiederebbe di ricostruire informazione non più verificabile nell'input.

## 2. Funzionamento del prototipo

Il percorso produttivo è:

```text
Upload UI
→ Cloudinary
→ webhook n8n
→ diagnosi deterministica FastAPI
→ prefiltro colore
→ eventuale triage Gemini
→ routing v3
→ KEEP | L1 | L4 | RETAKE
→ persistenza Supabase
→ risposta alla UI
```

I quattro esiti hanno ruoli distinti:

- **KEEP**: la foto viene mantenuta invariata.
- **L1 light polish**: Cloudinary `e_improve` corregge difetti fotografici leggeri.
- **L4 recovery**: GPT Image 2 interviene sui casi più compromessi. La UI mostra prima e dopo e richiede una conferma esplicita di fedeltà.
- **RETAKE**: nessun output migliorato viene proposto.

Per L4 la UI usa le azioni **“Conferma: rispecchia l'immobile”** e **“Rifiuta: non rispecchia l'immobile”**. Fino alla conferma, lo stato rimane `pending_human_confirmation`. L'esito viene salvato in `decisioni_finali`, insieme alle versioni di diagnosi e routing.

## 3. Workflow sperimentale

Il golden set contiene 30 fotografie distribuite tra bagno, cucina, soggiorno, camera da letto, corridoio e stanze vuote. Le degradazioni comprendono blur, compressione, esposizione, saturazione/temperatura, white blend, rumore e combinazioni. Sono disponibili 29 originali puliti come riferimento offline; `corridoio_04` è l'unica fotografia naturalmente molto degradata senza clean original.

Ogni input è stato elaborato su cinque livelli:

```text
L0 = input invariato
L1 = Cloudinary e_improve
L2 = Cloudinary e_enhance
L3 = Cloudinary e_gen_restore
L4 = GPT Image 2
```

Totale: 150 esecuzioni.

La review umana strutturata ha prodotto questi risultati:

- L1 vs L0: 14 vittorie, 9 pareggi, 7 sconfitte.
- L1 nel dominio luce/colore: 9 vittorie, 2 pareggi, 0 sconfitte.
- L4 vs L0: 28 vittorie, 1 pareggio, 1 sconfitta.
- L4 su blur + compressione: 16 vittorie su 16.
- L2 vs L1: 5 vittorie, 13 pareggi, 12 sconfitte → L2 escluso.
- L3 vs L4: 0 vittorie, 3 pareggi, 27 sconfitte → L3 escluso.

La review di fedeltà su tutti i 30 output L4 ha rilevato 8 alterazioni materiali: 6 associate ad ambiguità già presenti nell'input e 2 dovute a modifiche dirette dell'output. Questi risultati giustificano L4 solo con controlli di recoverability e conferma umana.

## 4. Parametri di valutazione

La decisione finale usa quattro dimensioni:

- **Qualità**: preferenza umana pairwise.
- **Fedeltà**: alterazioni materiali dell'immobile.
- **Recoverability**: possibilità di ottenere una recovery senza affidarsi a dettagli non verificabili.
- **Costo e latenza**: misure operative sui livelli rimasti.

Il candidate recoverability gate è:

```text
verifiability_risk = high
AND resolution_risk != none
→ RETAKE
```

Sulla reference composta da 6 failure da `input_ambiguity` e 22 output sicuri:

```text
TP = 5
FN = 1
FP = 1
TN = 21
```

Risultati: recall 83,3%, precision 83,3%, specificity 95,5%.

Il falso negativo `camera_da_letto_05` contiene un'ambiguità locale che le metriche globali non intercettano. Il falso positivo `corridoio_01` porta a un retake non necessario. Nel contesto del prototipo questo compromesso è accettabile perché una rappresentazione errata dell'immobile ha un costo di fiducia maggiore di un nuovo scatto.

Il benchmark operativo, n = 10 per livello, misura:

```text
L1: mediana 3,94 s · p95 4,90 s
L4: mediana 42,10 s · p95 45,63 s · costo medio ≈ $0,0526/immagine
```

L4 ha una latenza mediana circa 10,7 volte superiore a L1, quindi viene riservato ai casi che richiedono recovery.

## 5. Valutazione del qualitativo

La review è stata salvata in reference strutturate su Supabase:

1. **qualità**, tramite confronti pairwise tra livelli;
2. **fedeltà**, tramite ispezione dei 30 output L4;
3. **recoverability**, usando le failure di fedeltà come riferimento per valutare il candidate gate.

È stato anche benchmarkato un checker automatico VLM input→candidato. Sulla prima reference disponibile, 29 output L4 con 7 alterazioni umane, il checker ha restituito `material alteration = false` per tutti i casi: recall 0%. Per questo non viene usato come safety gate.

Un judge automatico pairwise per la qualità non è stato portato nel critical path. Con 30 fotografie la review umana strutturata era sufficiente per prendere la decisione sui livelli; un judge calibrato sugli umani resta una possibile estensione per benchmark più grandi.

## 6. Strumenti

- n8n in Docker per orchestrazione, webhook e branching;
- FastAPI, OpenCV, scikit-image e PyWavelets per la diagnosi;
- Cloudinary per storage, upload unsigned e trasformazioni da L1 a L3;
- OpenAI GPT Image 2 per L4;
- Gemini per il triage colore;
- Supabase/Postgres per foto, decisioni e reference umane;
- React/Vite per Upload UI e Lab UI;
- **ChatGPT (GPT-5.6 Sol) e Claude come assistenti di progettazione, sviluppo, debugging e documentazione.**

Gli assistenti AI sono stati usati durante il lavoro tecnico; benchmark, review, decisioni di prodotto e test end-to-end sono documentati nel repository.

## 7. Reale e simulato

**Implementato e testato:** golden set, benchmark, diagnosi, triage colore, review umane, checker automatico, candidate gate, workflow n8n con chiamate reali a Cloudinary/OpenAI/Gemini, persistenza Supabase, conferma L4, Upload UI, Lab UI, latenze e costi.

**Simulato o dichiarato:** integrazione con l'upload nativo di Immobiliare.it; degradazioni in gran parte sintetiche; singolo reviewer; esecuzione locale; testi UI senza revisione legale; nessuna misura di impatto business.

La distribuzione del golden set non viene usata come previsione del traffico reale: il set contiene intenzionalmente molti casi degradati per mettere sotto stress il sistema.

## 8. Limiti

Il campione è piccolo e prevalentemente sintetico. `corridoio_04`, l'unico caso naturalmente molto degradato, ha mostrato un failure mode che il sintetico non copriva bene: motion blur grave, assenza di colore e un output L4 visivamente pulito ma non sufficientemente fedele.

Il candidate gate è derivato da questo benchmark e richiede validazione su un dataset più ampio di foto reali. La diagnosi non distingue ancora bene il defocus recuperabile dal motion blur distruttivo. Le metriche globali possono perdere dettagli semanticamente ambigui in aree piccole. La review è stata eseguita da un singolo valutatore.

Gli asset Cloudinary del prototipo usano delivery pubblica con URL non facilmente indovinabile; un sistema reale richiederebbe hardening, policy di accesso e delivery firmata o autenticata.

## 9. Prossimi passi

- validazione su un dataset più ampio di fotografie reali da smartphone;
- review multi-rater;
- detector motion blur vs defocus;
- ricalibrazione periodica del gate usando gli esiti di conferma/rifiuto L4;
- hardening di storage e delivery;
- esperimento online su annunci reali, con metriche di contatto e indicatori trust & safety.

Le metriche offline servono a selezionare una policy iniziale. La validazione di prodotto richiede poi dati reali di utilizzo.
