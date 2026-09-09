# Benchmark

I numeri di questo documento sono congelati. La Lab UI li espone come dati statici, senza dipendenze da Supabase o API.

## 1. Golden set

Il golden set contiene 30 fotografie in sei ambienti:

- bagno;
- cucina;
- soggiorno;
- camera da letto;
- corridoio;
- stanze vuote.

Degradazioni:

- blur;
- compressione;
- esposizione;
- saturazione/temperatura;
- white blend;
- rumore;
- combinazioni.

Sono disponibili 29 originali puliti. `corridoio_04` è l'unica fotografia naturalmente degradata senza clean original.

Casi healthy usati come controllo `do no harm`:

```text
cucina_05
stanze_vuote_05
corridoio_05
```

Metadati principali:

```text
photo_id
ambiente
degradation_primary
degradation_secondary
severity
synthetic
expected_outcome
url_input
url_originale_pulito
```

Gli originali puliti vengono usati offline per benchmark e calibrazione. La pipeline produttiva non ne dipende.

Il set contiene intenzionalmente molti difetti: serve a stressare il sistema e non a stimare la distribuzione del traffico reale.

## 2. Fan-out da L0 a L4

Ogni fotografia è stata elaborata su cinque livelli:

| Livello | Trasformazione | Natura |
| --- | --- | --- |
| L0 | input invariato | controllo |
| L1 | Cloudinary `e_improve` | trasformazione classica |
| L2 | Cloudinary `e_enhance` | AI |
| L3 | Cloudinary `e_gen_restore` | generativa |
| L4 | OpenAI GPT Image 2 edit | generativa |

Totale:

```text
30 × 5 = 150 esecuzioni
```

Configurazione L4:

```text
model = gpt-image-2-2026-04-21
quality = medium
size = auto
output_format = png
```

Il prompt chiede di migliorare esposizione, white balance, dominante, contrasto, rumore, compressione e nitidezza recuperabile, preservando contenuto, geometria, materiali, texture, difetti e inquadratura. Vieta staging, decluttering, repair, redesign e modifiche agli oggetti.

La review successiva mostra che il prompt riduce il rischio ma non può recuperare informazione assente dall'input.

## 3. Review umana della qualità

Metodo: review strutturata a singolo valutatore con confronti pairwise per fotografia. Reference: `reference_qualita_umane`.

| Confronto | Vince il primo | Pareggi | Vince il secondo |
| --- | ---: | ---: | ---: |
| L1 vs L0 | 14 | 9 | 7 |
| L4 vs L0 | 28 | 1 | 1 |
| L2 vs L1 | 5 | 13 | 12 |
| L3 vs L4 | 0 | 3 | 27 |

Nel dominio previsto per L1 (luce, saturazione/temperatura e white blend) il risultato è:

```text
9 vittorie
2 pareggi
0 sconfitte
```

Su blur + compressione, L4 ottiene:

```text
16 vittorie su 16 contro L0
```

Decisioni:

- **L1 mantenuto** per interventi fotografici leggeri.
- **L2 escluso**: non offre un vantaggio sufficientemente consistente rispetto a L1.
- **L3 escluso**: nel golden set L4 è almeno pari in 30/30 casi e migliore in 27/30.
- **L4 mantenuto** per recovery, con controlli di fedeltà specifici.

## 4. Review umana di fedeltà L4

Tutti i 30 output L4 sono stati confrontati manualmente con l'input.

Reference: `reference_fedelta_umane`.

Risultato:

```text
8/30 alterazioni materiali
22/30 output giudicati safe
```

| Causa | n | Foto |
| --- | ---: | --- |
| `input_ambiguity` | 6 | `bagno_04`, `camera_da_letto_01`, `camera_da_letto_03`, `camera_da_letto_04`, `camera_da_letto_05`, `stanze_vuote_01` |
| `l4_direct` | 2 | `bagno_01`, `corridoio_04` |

Nei casi `input_ambiguity`, il modello ricostruisce dettagli che l'input non rende sufficientemente leggibili. I due casi `l4_direct` riguardano una lampada modificata lievemente e una porta rimossa.

### `corridoio_04`

Caratteristiche dell'input:

- motion blur grave;
- centro parzialmente nitido;
- parete sovraesposta;
- immagine in bianco e nero;
- `mean_saturation = 0`;
- `p95_saturation = 0`.

L'output L4 rende l'immagine più leggibile, ma introduce colori e dettagli non verificabili e modifica una porta. Questo caso ha portato a due modifiche della diagnosi: regola monocromatica e tile blur.

## 5. Checker automatico di fedeltà

Un checker VLM input→candidato è stato confrontato con la prima reference umana disponibile:

```text
29 output L4
7 positivi umani
22 negativi
```

Il checker ha restituito `material alteration = false` per tutti i casi.

| | Alterazione umana | Nessuna alterazione umana |
| --- | ---: | ---: |
| Checker: alterazione | TP = 0 | FP = 0 |
| Checker: nessuna alterazione | FN = 7 | TN = 22 |

Recall:

```text
0%
```

Il checker non viene usato come safety gate.

Il judge automatico pairwise per la qualità è rimasto fuori dal critical path. Con 30 fotografie, la review umana strutturata era sufficiente per selezionare i livelli produttivi.

## 6. Recoverability e candidate gate

Reference di calibrazione:

```text
6 failure da input_ambiguity
22 output L4 safe
```

I due casi `l4_direct` sono esclusi dalla calibrazione primaria perché non dipendono dalla recoverability dell'input.

Candidate gate:

```text
verifiability_risk = high
AND resolution_risk != none
→ RETAKE
```

Confusion matrix:

| | Ambiguità, n = 6 | Safe, n = 22 |
| --- | ---: | ---: |
| Gate: RETAKE | TP = 5 | FP = 1 |
| Gate: passa | FN = 1 | TN = 21 |

Metriche:

```text
recall      = 83,3%
precision   = 83,3%
specificity = 95,5%
```

Falso negativo:

```text
camera_da_letto_05
```

L'ambiguità è locale e semantica; le metriche globali non la evidenziano.

Falso positivo:

```text
corridoio_01
```

Il gate richiede un retake anche se l'output L4 è stato giudicato safe.

Non è stata aggiunta una regola ad hoc per correggere il falso negativo: con sei positivi avrebbe aumentato il rischio di overfitting.

## 7. `reconstruction_risk`

Confronto sulla stessa reference:

| Regola | Ambiguità intercettate | Safe bloccati |
| --- | ---: | ---: |
| Candidate gate | 5/6 | 1/22 |
| `reconstruction_risk` high/medium | 5/6 | 5/22 |
| `reconstruction_risk` high | 2/6 | 0/22 |

`reconstruction_risk` resta un campo descrittivo della diagnosi.

## 8. Prefiltro colore e triage Gemini

Versione:

```text
v3_neutral_color_prefilter_2026-09-07
```

Gemini viene chiamato se:

```text
neutral_chroma_shift == null
OR neutral_chroma_shift >= 3
OR neutral_region_pct < 5
```

Risultati:

| Set | Chiamate Gemini | Esito |
| --- | ---: | --- |
| Originali puliti, n = 29 | 9 | 7 normale · 2 sospetto |
| Degradati paired | 14 | 9 normale · 5 sospetto |

Il router usa `esito_colore ∈ {normale, sospetto, incerto}`.

## 9. Benchmark operativo

Micro-benchmark sui livelli produttivi L1 e L4, n = 10 ciascuno.

| Livello | Mediana | p95 | Costo medio per immagine |
| --- | ---: | ---: | ---: |
| L1, Cloudinary `e_improve` | 3,94 s | 4,90 s | non dichiarato |
| L4, GPT Image 2 medium | 42,10 s | 45,63 s | ≈ $0,0526 |

Per L1 il benchmark misura la latenza su asset Cloudinary freschi, evitando di misurare una derivata già presente in cache. Il costo monetario marginale non viene stimato perché dipende dal piano Cloudinary.

Rapporto tra mediane:

```text
L4 ≈ 10,7× L1
```

## 10. Distribuzione delle route

Non vengono riportati conteggi KEEP/L1/L4/RETAKE sul golden set.

La policy produttiva attuale è `v3_2026-09-08`, mentre alcuni conteggi intermedi erano stati calcolati con una versione precedente. Inoltre il set è deliberatamente degradato. I numeri utili e confrontabili restano quelli del benchmark per livello e delle reference di fedeltà/recoverability.

La policy finale è descritta in [`diagnosi_e_routing.md`](diagnosi_e_routing.md).
