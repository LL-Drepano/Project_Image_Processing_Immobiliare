# Architettura

## 1. Obiettivo

Il prototipo riceve una fotografia, misura i principali problemi tecnici, applica una policy di routing e restituisce uno dei quattro esiti produttivi:

```text
KEEP
L1
L4
RETAKE
```

La diagnosi e il routing sono versionati separatamente. Il servizio FastAPI produce segnali deterministici; n8n applica la policy di prodotto e orchestra i provider esterni.

## 2. Componenti

| Componente | Ruolo | Esecuzione |
| --- | --- | --- |
| Upload UI | upload, preview, risultato, conferma L4 | React/Vite locale |
| Cloudinary | storage input/output e trasformazione L1 | cloud |
| n8n | orchestrazione, webhook, branching e persistenza | Docker locale |
| diagnosis-service | diagnosi deterministica dell'input | FastAPI in Docker locale |
| Gemini | triage colore quando richiesto dal prefiltro | cloud |
| GPT Image 2 | recovery L4 | cloud |
| Supabase | foto, decisioni e reference del benchmark | cloud |
| Lab UI | visualizzazione dei risultati congelati del benchmark | React/Vite locale |

## 3. Flusso principale

```text
Upload UI
│
├─ upload unsigned → Cloudinary
│
└─ POST /webhook/photo_quality
   │
   ▼
n8n
│
├─ Crea Foto → Supabase `foto`
├─ POST diagnosis-service /diagnosi
├─ Merge dati foto + diagnosi
├─ Prefiltro Colore
│   ├─ skip → esito_colore = normale
│   └─ triage → Gemini → esito_colore
├─ Classifica Route (routing v3)
├─ Switch
│   ├─ KEEP
│   ├─ L1
│   ├─ L4
│   └─ RETAKE
├─ Prepara Risposta
├─ Salva Decisione Finale
└─ Respond to Webhook
```

Il Merge dopo la diagnosi è **by position**. Durante lo sviluppo ha sostituito un nodo Code che dipendeva da riferimenti `.item`/`.first()` fragili con più trigger.

## 4. Contratto di intake

Endpoint:

```text
POST http://localhost:5678/webhook/photo_quality
```

Payload:

```json
{
  "photo_id": "ui_<uuid>",
  "nome_file": "foto.jpg",
  "url_input": "https://...",
  "id_cloudinary_input": "<public_id>"
}
```

La Upload UI genera `photo_id` con `crypto.randomUUID()`.

`ambiente` non è richiesto per gli upload reali: il router non lo usa e il vincolo `NOT NULL` è stato rimosso dalla tabella `foto`.

## 5. Diagnosi

Endpoint interno:

```text
POST http://host.docker.internal:8000/diagnosi
```

Versione:

```text
v5_tile_blur_2026-09-08
```

Il servizio restituisce, tra gli altri:

```text
underexposure
overexposure
blur
compression
noise
resolution_risk
verifiability_risk
p95_saturation
neutral_chroma_shift
neutral_region_pct
reconstruction_risk
```

`reconstruction_risk` è descrittivo e non entra nel routing.

## 6. Colore

Il prefiltro evita una chiamata VLM quando i segnali deterministici sono sufficientemente tranquilli.

Gemini viene chiamato se:

```text
neutral_chroma_shift == null
OR neutral_chroma_shift >= 3
OR neutral_region_pct < 5
```

Output usato dal router:

```text
esito_colore ∈ {normale, sospetto, incerto}
```

## 7. Routing

Versione:

```text
v3_2026-09-08
```

Ordine:

1. `p95_saturation < 8` → RETAKE.
2. Perdita seria di informazione → candidate gate → RETAKE oppure L4.
3. Esposizione medium/high → L4.
4. Esposizione low o colore sospetto/incerto → L1.
5. Altrimenti KEEP.

Dettagli e codice in [`diagnosi_e_routing.md`](diagnosi_e_routing.md).

## 8. Rami

### KEEP

```text
final_output_url = url_input
human_confirmation_required = false
stato_finale = completed
livello_consigliato = L0
```

### L1

Trasformazione:

```text
c_limit,w_4500,h_4500/e_improve
```

Output:

```text
final_output_url = url_l1
human_confirmation_required = false
stato_finale = completed
livello_consigliato = L1
```

### L4

Flusso:

```text
timer
→ GPT Image 2
→ parser
→ upload output su Cloudinary
→ finalizzazione
```

Configurazione:

```text
model = gpt-image-2-2026-04-21
quality = medium
size = auto
output_format = png
```

Il parser preserva i campi dell'item e rimuove dal JSON solo il base64 dell'immagine prima dei passaggi successivi.

Output:

```text
human_confirmation_required = true
stato_finale = pending_human_confirmation
livello_consigliato = L4
```

Per L4 la risposta al frontend include anche `decision_id`.

### RETAKE

```text
output_url = null
human_confirmation_required = false
stato_finale = retake_required
livello_consigliato = null
```

## 9. Risposta al frontend

KEEP/L1:

```json
{
  "photo_id": "...",
  "route": "KEEP",
  "status": "completed",
  "output_url": "...",
  "human_confirmation_required": false,
  "motivo": "..."
}
```

L4:

```json
{
  "photo_id": "...",
  "route": "L4",
  "status": "pending_human_confirmation",
  "output_url": "...",
  "human_confirmation_required": true,
  "motivo": "...",
  "decision_id": "..."
}
```

RETAKE:

```json
{
  "photo_id": "...",
  "route": "RETAKE",
  "status": "retake_required",
  "output_url": null,
  "human_confirmation_required": false,
  "motivo": "..."
}
```

## 10. Conferma L4

Endpoint:

```text
POST http://localhost:5678/webhook/confirm_l4
```

Payload:

```json
{
  "decision_id": "...",
  "esito": "confirmed"
}
```

oppure:

```json
{
  "decision_id": "...",
  "esito": "rejected"
}
```

Aggiornamenti:

```text
confirmed → stato_finale = completed
rejected  → stato_finale = rejected
```

In entrambi i casi vengono salvati:

```text
human_confirmation_esito
human_confirmation_il
```

Il workflow registra la decisione dell'utente e mantiene invariati output e livello applicato.

## 11. Persistenza

Le tabelle rilevanti per il flusso finale sono `foto` e `decisioni_finali`. Il DDL completo va esportato in [`../db/schema.sql`](../db/schema.sql).

`decisioni_finali` conserva almeno:

```text
id
id_foto
livello_consigliato
categoria_instradamento
motivazione_decisione
diagnosis_version
routing_version
final_output_url
human_confirmation_required
stato_finale
human_confirmation_esito
human_confirmation_il
creato_il
```

Mapping del livello:

```text
KEEP   → L0
L1     → L1
L4     → L4
RETAKE → null
```

## 12. UI

### Upload UI

Responsabilità:

- selezione o drag & drop;
- preview;
- upload Cloudinary;
- invio al webhook;
- stato di elaborazione;
- visualizzazione prima/dopo per L1 e L4;
- messaggio RETAKE;
- conferma/rifiuto per L4.

### Lab UI

Mostra dati statici del benchmark:

- architettura finale;
- confronti tra i livelli;
- fidelity/recoverability;
- latenza e costo;
- routing v3.

La Lab UI non interroga Supabase: i numeri sono congelati e versionati con il repo.

## 13. Sicurezza e configurazione

Il prototipo è local-first e non è esposto pubblicamente.

Da non inserire nel repository:

```text
OpenAI API key
Gemini API key
Cloudinary API secret
Supabase service_role
credenziali n8n
```

Il `cloud_name` Cloudinary e il nome del preset unsigned non sono segreti.

Il preset di upload usa un public ID generato dal provider. Gli asset restano comunque accessibili a chi conosce l'URL; un deployment reale richiederebbe una policy di delivery più restrittiva.

## 14. Esecuzione locale

```text
Docker Desktop
→ docker start n8n
→ diagnosis-service su :8000
→ upload-ui su :5173
→ lab-ui su :5174
```

Il setup è pensato per demo e sviluppo locale, senza esposizione Internet.
