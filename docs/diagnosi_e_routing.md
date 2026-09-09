# Diagnosi e routing

La diagnosi e il routing sono versionati separatamente. Il servizio FastAPI calcola segnali osservabili sull'immagine; n8n usa quei segnali per applicare la policy di prodotto.

## Diagnosi: `v5_tile_blur_2026-09-08`

Servizio:

```text
diagnosis-service/app/main.py
```

Endpoint:

```text
POST /diagnosi
```

Stack: FastAPI, Uvicorn, httpx, NumPy, OpenCV, scikit-image, PyWavelets.

Da n8n:

```text
http://host.docker.internal:8000/diagnosi
```

### Segnali principali

| Campo | Significato |
| --- | --- |
| `underexposure`, `overexposure` | livello `none/low/medium/high` del problema di esposizione |
| `blur` | livello di sfocatura, con eventuale override tile-based |
| `compression` | livello degli artefatti JPEG; può valere `uncertain` |
| `noise` | livello di rumore |
| `resolution_risk` | rischio legato alla risoluzione effettiva dell'input |
| `verifiability_risk` | difficoltà di verificare dettagli dell'immobile a partire dall'input |
| `p95_saturation`, `mean_saturation` | statistiche usate anche dalla regola monocromatica |
| `jpeg_blockiness`, `jpeg_blockiness_ratio` | segnali di blockiness JPEG |
| `blur_tiles_n`, `blur_tiles_median`, `blur_tiles_blurred_frac`, `blur_tiles_override` | dettaglio del tile blur |
| `reconstruction_risk`, `reconstruction_risk_reasons` | segnali descrittivi, esclusi dal routing |

`verifiability_risk` viene calcolato nel `diagnosis-service` e restituito nel JSON della diagnosi.

### Compressione

Il servizio espone:

```text
jpeg_blockiness = jpeg_blockiness_ratio - 1
```

La soglia `1.20` si applica a `jpeg_blockiness`.

```text
jpeg_blockiness >= 1.20
```

Applicare la stessa soglia al ratio cambierebbe la scala e produrrebbe falsi positivi sulle immagini pulite.

### Tile blur

La diagnosi usa una versione ridimensionata con lato massimo 1280 e una griglia 4×4.

Procedura:

- scarta tile piatte con `std < 0.02`;
- considera sfocata una tile con `blur_effect >= 0.40`;
- se più della metà delle tile informative è sfocata, porta `blur` almeno a `medium`.

Sul golden set:

```text
foto pulite/non-blur: blurred tile fraction max ≈ 38%
blur sintetico:       blurred tile fraction min ≈ 73%
corridoio_04:         ≈ 81%
```

Questa modifica nasce dal caso `corridoio_04`, che la metrica globale sottostimava a causa di un centro parzialmente nitido.

Il detector attuale misura bene la presenza diffusa di blur nel dominio osservato. La separazione tra defocus e motion blur direzionale richiede un detector dedicato e resta fuori dalla v5.

### Regola monocromatica

```text
p95_saturation < 8 → RETAKE
```

La regola intercetta immagini sostanzialmente in bianco e nero e impedisce una colorizzazione generativa priva di riferimento nell'input.

Limite noto: seppia e altri monocromi tonalizzati possono avere saturazione sufficiente a non attivare la regola.

### `reconstruction_risk`

`reconstruction_risk` e `reconstruction_risk_reasons` restano nell'output per debug e analisi.

Confronto sulla reference di recoverability:

| Regola | Ambiguità intercettate (su 6) | Sicuri bloccati (su 22) |
| --- | ---: | ---: |
| Candidate gate | 5 | 1 |
| `reconstruction_risk` high/medium | 5 | 5 |
| `reconstruction_risk` high | 2 | 0 |

Nel benchmark il candidate gate intercetta 5/6 ambiguità e blocca 1/22 casi sicuri. `reconstruction_risk` non viene quindi letto dal router.

## Prefiltro colore e triage Gemini

Versione del prefiltro:

```text
v3_neutral_color_prefilter_2026-09-07
```

Gemini viene chiamato quando:

```text
neutral_chroma_shift == null
OR neutral_chroma_shift >= 3
OR neutral_region_pct < 5
```

Risultati osservati:

| Set | Chiamate Gemini | Esito |
| --- | ---: | --- |
| Originali puliti, n = 29 | 9 | 7 normale · 2 sospetto |
| Degradati paired | 14 | 9 normale · 5 sospetto |

Il router legge:

```text
esito_colore ∈ {normale, sospetto, incerto}
```

## Routing: `v3_2026-09-08`

La prima policy mandava a L1 tutti i problemi di esposizione. Durante i test end-to-end con la Upload UI, i casi `medium/high` hanno mostrato un beneficio visivo maggiore con L4. La v3 sposta quindi questi casi su L4 con conferma umana.

L'aggiornamento riguarda la policy applicativa. I confronti tra i livelli del benchmark restano invariati.

### Priorità

| # | Condizione | Esito |
| ---: | --- | --- |
| 0 | `p95_saturation < 8` | **RETAKE** |
| 1 | `blur` medium/high, oppure `compression` high/uncertain, oppure `noise` high, oppure `resolution_risk` high | candidate gate → **RETAKE** oppure **L4** |
| 2 | `underexposure` o `overexposure` medium/high | **L4 + conferma umana** |
| 3 | esposizione low oppure `esito_colore` sospetto/incerto | **L1** |
| 4 | nessuna condizione precedente | **KEEP** |

Candidate gate:

```text
verifiability_risk = high
AND resolution_risk != none
→ RETAKE
```

### Codice del nodo `Classifica Route`

```javascript
const d = $json;

const ROUTING_VERSION = 'v3_2026-09-08';

// Guardrail: senza colore nell'input non tentiamo di ricostruirlo.
if (d.p95_saturation !== null && d.p95_saturation < 8) {
  return {
    json: {
      ...d,
      route: 'RETAKE',
      route_motivo:
        'foto monocromatica: il colore non può essere ricostruito senza inventarlo',
      routing_version: ROUTING_VERSION
    }
  };
}

const serio =
  ['medium', 'high'].includes(d.blur) ||
  ['high', 'uncertain'].includes(d.compression) ||
  d.noise === 'high' ||
  d.resolution_risk === 'high';

// Exposure medium/high: recovery. Low: percorso economico.
const esposizioneDaRecovery =
  ['medium', 'high'].includes(d.underexposure) ||
  ['medium', 'high'].includes(d.overexposure);

const luceColore =
  d.underexposure === 'low' ||
  d.overexposure === 'low' ||
  ['sospetto', 'incerto'].includes(d.esito_colore);

let route;
let route_motivo;

if (serio) {
  const retake =
    d.verifiability_risk === 'high' &&
    d.resolution_risk !== 'none';

  route = retake ? 'RETAKE' : 'L4';

  route_motivo = retake
    ? 'perdita di informazione con risoluzione insufficiente (candidate gate)'
    : 'perdita di informazione recuperabile: L4 con conferma umana';

} else if (esposizioneDaRecovery) {
  route = 'L4';
  route_motivo =
    'problema significativo di esposizione: recovery L4 con conferma umana';

} else if (luceColore) {
  route = 'L1';
  route_motivo = 'problema leggero di luce o colore';

} else {
  route = 'KEEP';
  route_motivo = 'nessun problema rilevato';
}

return {
  json: {
    ...d,
    route,
    route_motivo,
    routing_version: ROUTING_VERSION
  }
};
```

## Distribuzione delle route

Il repository non riporta conteggi KEEP/L1/L4/RETAKE sul golden set.

I conteggi calcolati con la policy precedente non descrivono la v3 e il golden set è volutamente ricco di casi degradati. I risultati confrontabili restano quelli del benchmark per livello e delle reference di fedeltà/recoverability.

Vedi [`benchmark.md`](benchmark.md).
