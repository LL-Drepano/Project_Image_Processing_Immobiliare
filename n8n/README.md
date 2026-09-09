# Workflow n8n

Questa cartella contiene l'export del workflow n8n usato dal prototipo.

## File

```text
n8n/
├─ README.md
└─ photo_quality_workflow.json
```

Il workflow gestisce:

* intake della foto;
* chiamata al `diagnosis-service`;
* prefiltro colore;
* triage Gemini quando necessario;
* routing KEEP / L1 / L4 / RETAKE;
* trasformazioni Cloudinary;
* recovery L4 con GPT Image;
* persistenza su Supabase;
* risposta alla Upload UI;
* conferma o rifiuto umano degli output L4.

## Endpoint

| Endpoint                      | Ruolo                                             |
| ----------------------------- | ------------------------------------------------- |
| `POST /webhook/photo_quality` | esegue diagnosi, routing ed eventuale enhancement |
| `POST /webhook/confirm_l4`    | registra conferma o rifiuto di un risultato L4    |

## Import

1. Avviare n8n.
2. Importare `photo_quality_workflow.json`.
3. Ricollegare le credenziali richieste dai nodi.
4. Verificare che il servizio di diagnosi punti a:

```text
http://host.docker.internal:8000/diagnosi
```

5. Attivare il workflow.

La Upload UI usa gli endpoint `/webhook/...`, quindi il workflow deve essere attivo. Gli endpoint `/webhook-test/...` servono solo durante il test manuale in n8n.

## Credenziali richieste

Il workflow utilizza credenziali n8n per:

* OpenAI;
* Gemini;
* Supabase;
* Cloudinary.

L'export incluso nel repository non contiene API key o secret. Le credenziali devono essere configurate separatamente nell'istanza n8n.

## Versioni

```text
diagnosis_version = v5_tile_blur_2026-09-08
routing_version   = v3_2026-09-08
```

La logica della diagnosi e del routing è documentata in:

* [`../docs/diagnosi_e_routing.md`](../docs/diagnosi_e_routing.md)
* [`../docs/architettura.md`](../docs/architettura.md)
