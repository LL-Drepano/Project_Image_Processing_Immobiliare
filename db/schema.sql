-- Photo Quality Lab
-- Supabase/PostgreSQL schema snapshot reconstructed from the final project metadata.
--
-- Objects:
--   11 tables
--   4 views
--
-- This file contains schema only: no benchmark rows, uploads, API keys, or service credentials.

-- ============================================================
-- Sequences used by non-identity bigint primary keys
-- ============================================================

CREATE SEQUENCE public.diagnosi_input_id_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1
    NO CYCLE;

CREATE SEQUENCE public.reference_qualita_umane_id_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1
    NO CYCLE;


-- ============================================================
-- Core data
-- ============================================================

CREATE TABLE public.foto (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    photo_id text NOT NULL,
    ambiente text,
    nome_file text NOT NULL,
    degradation_primary text,
    degradation_secondary text,
    severity text,
    synthetic boolean NOT NULL,
    has_original boolean NOT NULL,
    expected_outcome text,
    url_input text,
    id_cloudinary_input text,
    url_originale_pulito text,
    id_cloudinary_originale text,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT foto_pkey PRIMARY KEY (id),
    CONSTRAINT foto_photo_id_key UNIQUE (photo_id)
);


CREATE TABLE public.esecuzioni (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_foto uuid NOT NULL,
    livello text NOT NULL,
    fornitore text,
    operazione text,
    numero_replica integer NOT NULL DEFAULT 1,
    numero_tentativo integer NOT NULL DEFAULT 1,
    stato text NOT NULL DEFAULT 'in_attesa'::text,
    url_output text,
    id_cloudinary_output text,
    latenza_ms integer,
    costo_euro numeric,
    configurazione jsonb,
    messaggio_errore text,
    iniziata_il timestamptz,
    terminata_il timestamptz,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT esecuzioni_pkey PRIMARY KEY (id),
    CONSTRAINT esecuzioni_id_foto_fkey
        FOREIGN KEY (id_foto)
        REFERENCES public.foto(id)
        ON DELETE CASCADE,
    CONSTRAINT esecuzioni_livello_check
        CHECK (livello = ANY (ARRAY['L0'::text, 'L1'::text, 'L2'::text, 'L3'::text, 'L4'::text])),
    CONSTRAINT esecuzioni_stato_check
        CHECK (stato = ANY (ARRAY[
            'in_attesa'::text,
            'in_esecuzione'::text,
            'ok'::text,
            'errore'::text,
            'timeout'::text,
            'rifiuto'::text
        ]))
);


CREATE TABLE public.metriche (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_esecuzione uuid NOT NULL,
    luminosita_media numeric,
    percentuale_ombre_perse numeric,
    percentuale_luci_bruciate numeric,
    contrasto numeric,
    indice_nitidezza numeric,
    larghezza_pixel integer,
    altezza_pixel integer,
    ssim numeric,
    variazione_luminosita numeric,
    variazione_saturazione numeric,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT metriche_pkey PRIMARY KEY (id),
    CONSTRAINT metriche_id_esecuzione_fkey
        FOREIGN KEY (id_esecuzione)
        REFERENCES public.esecuzioni(id)
        ON DELETE CASCADE,
    -- Both UNIQUE constraints existed in the final Supabase schema.
    CONSTRAINT metriche_id_esecuzione_key UNIQUE (id_esecuzione),
    CONSTRAINT metriche_id_esecuzione_unique UNIQUE (id_esecuzione)
);


-- ============================================================
-- Benchmark and automated-evaluation tables
-- ============================================================

CREATE TABLE public.confronti_giudice (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_foto uuid NOT NULL,
    id_esecuzione_a uuid,
    id_esecuzione_b uuid,
    ordine_presentazione text,
    id_esecuzione_vincitrice uuid,
    motivazione text,
    risposta_completa jsonb,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT confronti_giudice_pkey PRIMARY KEY (id),
    CONSTRAINT confronti_giudice_id_foto_fkey
        FOREIGN KEY (id_foto)
        REFERENCES public.foto(id)
        ON DELETE CASCADE,
    CONSTRAINT confronti_giudice_id_esecuzione_a_fkey
        FOREIGN KEY (id_esecuzione_a)
        REFERENCES public.esecuzioni(id),
    CONSTRAINT confronti_giudice_id_esecuzione_b_fkey
        FOREIGN KEY (id_esecuzione_b)
        REFERENCES public.esecuzioni(id),
    CONSTRAINT confronti_giudice_id_esecuzione_vincitrice_fkey
        FOREIGN KEY (id_esecuzione_vincitrice)
        REFERENCES public.esecuzioni(id)
);


CREATE TABLE public.controlli_fedelta (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_esecuzione uuid NOT NULL,
    modifica_materiale_rilevata boolean,
    gravita_modifica text,
    differenze_rilevate jsonb,
    creato_il timestamptz DEFAULT now(),
    versione_checker text,

    CONSTRAINT controlli_fedelta_pkey PRIMARY KEY (id),
    CONSTRAINT controlli_fedelta_id_esecuzione_fkey
        FOREIGN KEY (id_esecuzione)
        REFERENCES public.esecuzioni(id)
        ON DELETE CASCADE,
    CONSTRAINT controlli_fedelta_gravita_modifica_check
        CHECK (gravita_modifica = ANY (ARRAY[
            'nessuna'::text,
            'minore'::text,
            'maggiore'::text
        ]))
);


CREATE TABLE public.controlli_fedelta_clean (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_esecuzione uuid NOT NULL,
    modifica_materiale_rilevata boolean,
    gravita_modifica text,
    differenze_rilevate jsonb,
    creato_il timestamptz DEFAULT now(),
    versione_checker text,
    reference_type text NOT NULL DEFAULT 'clean_original'::text,

    CONSTRAINT controlli_fedelta_clean_pkey PRIMARY KEY (id),
    CONSTRAINT controlli_fedelta_gravita_modifica_check
        CHECK (gravita_modifica = ANY (ARRAY[
            'nessuna'::text,
            'minore'::text,
            'maggiore'::text
        ])),
    CONSTRAINT controlli_fedelta_clean_reference_type_check
        CHECK (reference_type = 'clean_original'::text)
);


CREATE TABLE public.voti_umani (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_foto uuid NOT NULL,
    id_valutatore text,
    migliore_qualita_fotografica uuid,
    migliore_per_valutare_immobile uuid,
    output_con_alterazioni jsonb,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT voti_umani_pkey PRIMARY KEY (id),
    CONSTRAINT voti_umani_id_foto_fkey
        FOREIGN KEY (id_foto)
        REFERENCES public.foto(id)
        ON DELETE CASCADE,
    CONSTRAINT voti_umani_migliore_qualita_fotografica_fkey
        FOREIGN KEY (migliore_qualita_fotografica)
        REFERENCES public.esecuzioni(id),
    CONSTRAINT voti_umani_migliore_per_valutare_immobile_fkey
        FOREIGN KEY (migliore_per_valutare_immobile)
        REFERENCES public.esecuzioni(id)
);


CREATE TABLE public.reference_fedelta_umane (
    id bigint GENERATED ALWAYS AS IDENTITY,
    id_esecuzione uuid NOT NULL,
    photo_id text NOT NULL,
    livello text NOT NULL,
    alterazione_materiale boolean NOT NULL,
    tipo_alterazione text,
    nota text,
    origine_etichetta text NOT NULL DEFAULT 'human_manual_v1'::text,
    creato_il timestamptz NOT NULL DEFAULT now(),
    causa_alterazione text,

    CONSTRAINT reference_fedelta_umane_pkey PRIMARY KEY (id),
    CONSTRAINT reference_fedelta_umane_id_esecuzione_fkey
        FOREIGN KEY (id_esecuzione)
        REFERENCES public.esecuzioni(id),
    CONSTRAINT reference_fedelta_umane_id_esecuzione_key UNIQUE (id_esecuzione)
);


CREATE TABLE public.reference_qualita_umane (
    id bigint NOT NULL DEFAULT nextval('public.reference_qualita_umane_id_seq'::regclass),
    photo_id text NOT NULL,
    reviewer_label text NOT NULL DEFAULT 'self_v1'::text,
    winner_l1_vs_l0 text NOT NULL,
    winner_l4_vs_l0 text NOT NULL,
    reason_l1 text,
    reason_l4 text,
    nota text,
    origine_etichetta text DEFAULT 'single_reviewer_manual_ui'::text,
    creato_il timestamptz NOT NULL DEFAULT now(),
    aggiornato_il timestamptz NOT NULL DEFAULT now(),
    winner_l2_vs_l1 text,
    winner_l3_vs_l4 text,
    reason_l2 text,
    reason_l3 text,

    CONSTRAINT reference_qualita_umane_pkey PRIMARY KEY (id),
    CONSTRAINT reference_qualita_umane_photo_id_reviewer_label_key
        UNIQUE (photo_id, reviewer_label),
    CONSTRAINT reference_qualita_umane_winner_l1_vs_l0_check
        CHECK (winner_l1_vs_l0 = ANY (ARRAY['L0'::text, 'tie'::text, 'L1'::text])),
    CONSTRAINT reference_qualita_umane_winner_l4_vs_l0_check
        CHECK (winner_l4_vs_l0 = ANY (ARRAY['L0'::text, 'tie'::text, 'L4'::text])),
    CONSTRAINT reference_qualita_umane_winner_l2_vs_l1_check
        CHECK (winner_l2_vs_l1 = ANY (ARRAY['L1'::text, 'tie'::text, 'L2'::text])),
    CONSTRAINT reference_qualita_umane_winner_l3_vs_l4_check
        CHECK (winner_l3_vs_l4 = ANY (ARRAY['L3'::text, 'tie'::text, 'L4'::text]))
);


CREATE TABLE public.diagnosi_input (
    id bigint NOT NULL DEFAULT nextval('public.diagnosi_input_id_seq'::regclass),
    id_foto uuid NOT NULL,
    photo_id text NOT NULL,
    diagnosis_version text,
    technical_quality_ok boolean,
    deterministic_issue_detected boolean,
    blur text,
    noise text,
    compression text,
    underexposure text,
    overexposure text,
    resolution_risk text,
    quality_status text,
    verifiability_risk text,
    requires_extra_fidelity_caution boolean,
    blur_effect numeric,
    noise_sigma numeric,
    jpeg_blockiness numeric,
    jpeg_blockiness_ratio numeric,
    jpeg_boundary_mean numeric,
    jpeg_neighbor_mean numeric,
    mean_luminance numeric,
    median_luminance numeric,
    p05_luminance numeric,
    p95_luminance numeric,
    shadows_clipped_pct numeric,
    highlights_clipped_pct numeric,
    sharpness_raw numeric,
    sharpness_denoised numeric,
    high_frequency_ratio numeric,
    input_width integer,
    input_height integer,
    input_min_side integer,
    input_max_side integer,
    input_megapixels numeric,
    diagnosis_raw jsonb,
    creato_il timestamptz DEFAULT now(),

    CONSTRAINT diagnosi_input_pkey PRIMARY KEY (id),
    CONSTRAINT diagnosi_input_id_foto_fkey
        FOREIGN KEY (id_foto)
        REFERENCES public.foto(id)
);


-- ============================================================
-- Final routing / product decision table
-- ============================================================

CREATE TABLE public.decisioni_finali (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    id_foto uuid NOT NULL,
    id_esecuzione_consigliata uuid,
    livello_consigliato text,
    categoria_instradamento text,
    motivazione_decisione text,
    creato_il timestamptz DEFAULT now(),
    diagnosis_version text,
    routing_version text,
    final_output_url text,
    human_confirmation_required boolean,
    stato_finale text,
    human_confirmation_esito text,
    human_confirmation_il timestamptz,

    CONSTRAINT decisioni_finali_pkey PRIMARY KEY (id),
    CONSTRAINT decisioni_finali_id_foto_key UNIQUE (id_foto),
    CONSTRAINT decisioni_finali_id_foto_fkey
        FOREIGN KEY (id_foto)
        REFERENCES public.foto(id)
        ON DELETE CASCADE,
    CONSTRAINT decisioni_finali_id_esecuzione_consigliata_fkey
        FOREIGN KEY (id_esecuzione_consigliata)
        REFERENCES public.esecuzioni(id),
    CONSTRAINT decisioni_finali_livello_consigliato_check
        CHECK (
            livello_consigliato IS NULL
            OR livello_consigliato = ANY (
                ARRAY['L0'::text, 'L1'::text, 'L2'::text, 'L3'::text, 'L4'::text]
            )
        ),
    CONSTRAINT decisioni_finali_human_confirmation_esito_check
        CHECK (
            human_confirmation_esito IS NULL
            OR human_confirmation_esito = ANY (
                ARRAY['confirmed'::text, 'rejected'::text]
            )
        )
);


-- Tie non-identity sequences to their owning columns.
ALTER SEQUENCE public.diagnosi_input_id_seq
    OWNED BY public.diagnosi_input.id;

ALTER SEQUENCE public.reference_qualita_umane_id_seq
    OWNED BY public.reference_qualita_umane.id;


-- ============================================================
-- Analytical views
-- ============================================================

-- Supplies L0-L4 image URLs to the manual benchmark review UI.
CREATE VIEW public.review_qualita_images AS
SELECT
    f.photo_id,
    f.ambiente,
    f.degradation_primary,
    f.degradation_secondary,
    f.severity,
    f.url_input AS url_l0,
    l1.url_output AS url_l1,
    l4.url_output AS url_l4,
    l2.url_output AS url_l2,
    l3.url_output AS url_l3
FROM public.foto f
LEFT JOIN LATERAL (
    SELECT e.url_output
    FROM public.esecuzioni e
    WHERE e.id_foto = f.id
      AND e.livello = 'L1'::text
      AND e.stato = 'ok'::text
    ORDER BY e.creato_il
    LIMIT 1
) l1 ON true
LEFT JOIN LATERAL (
    SELECT e.url_output
    FROM public.esecuzioni e
    WHERE e.id_foto = f.id
      AND e.livello = 'L2'::text
      AND e.stato = 'ok'::text
    ORDER BY e.creato_il
    LIMIT 1
) l2 ON true
LEFT JOIN LATERAL (
    SELECT e.url_output
    FROM public.esecuzioni e
    WHERE e.id_foto = f.id
      AND e.livello = 'L3'::text
      AND e.stato = 'ok'::text
    ORDER BY e.creato_il
    LIMIT 1
) l3 ON true
LEFT JOIN LATERAL (
    SELECT e.url_output
    FROM public.esecuzioni e
    WHERE e.id_foto = f.id
      AND e.livello = 'L4'::text
      AND e.stato = 'ok'::text
    ORDER BY e.creato_il
    LIMIT 1
) l4 ON true
WHERE l1.url_output IS NOT NULL
  AND l2.url_output IS NOT NULL
  AND l3.url_output IS NOT NULL
  AND l4.url_output IS NOT NULL;


-- Compares the production-style fidelity checker against the clean-original
-- checker run for the same execution.
CREATE VIEW public.confronto_fedelta_checker AS
WITH prod_baseline AS (
    SELECT DISTINCT ON (cf.id_esecuzione)
        cf.id,
        cf.id_esecuzione,
        cf.modifica_materiale_rilevata,
        cf.gravita_modifica,
        cf.differenze_rilevate,
        cf.creato_il,
        cf.versione_checker
    FROM public.controlli_fedelta cf
    ORDER BY cf.id_esecuzione, cf.creato_il
)
SELECT
    c.id_esecuzione,
    f.photo_id,
    e.livello,
    p.modifica_materiale_rilevata AS prod_detected,
    c.modifica_materiale_rilevata AS clean_detected,
    p.gravita_modifica AS prod_severity,
    c.gravita_modifica AS clean_severity,
    p.differenze_rilevate AS prod_differences,
    c.differenze_rilevate AS clean_differences,
    p.modifica_materiale_rilevata = c.modifica_materiale_rilevata AS accordo
FROM prod_baseline p
JOIN public.controlli_fedelta_clean c
    ON c.id_esecuzione = p.id_esecuzione
JOIN public.esecuzioni e
    ON e.id = c.id_esecuzione
JOIN public.foto f
    ON f.id = e.id_foto;


-- Dataset used to inspect which L4 fidelity failures correlate with
-- properties of the degraded input.
CREATE VIEW public.recoverability_l4_basic AS
WITH l0_runs AS (
    SELECT DISTINCT ON (e.id_foto)
        e.id AS id_esecuzione_l0,
        e.id_foto
    FROM public.esecuzioni e
    WHERE e.livello = 'L0'::text
      AND e.stato = 'ok'::text
    ORDER BY e.id_foto, e.creato_il
),
l0_metrics AS (
    SELECT DISTINCT ON (m.id_esecuzione)
        m.id_esecuzione,
        m.luminosita_media,
        m.percentuale_ombre_perse,
        m.percentuale_luci_bruciate,
        m.contrasto,
        m.indice_nitidezza,
        m.larghezza_pixel,
        m.altezza_pixel
    FROM public.metriche m
    ORDER BY m.id_esecuzione, m.creato_il
)
SELECT
    f.id AS id_foto,
    f.photo_id,
    f.ambiente,
    f.degradation_primary,
    f.degradation_secondary,
    f.severity,
    f.synthetic,
    f.expected_outcome,
    h.id_esecuzione AS id_esecuzione_l4,
    h.alterazione_materiale,
    h.causa_alterazione,
    h.tipo_alterazione,
    h.nota,
    CASE
        WHEN h.alterazione_materiale = true
         AND h.causa_alterazione = 'input_ambiguity'::text
            THEN 'input_ambiguity'::text
        WHEN h.alterazione_materiale = true
         AND h.causa_alterazione = 'l4_direct'::text
            THEN 'l4_direct'::text
        ELSE 'no_alteration'::text
    END AS recoverability_group,
    m.luminosita_media,
    m.percentuale_ombre_perse,
    m.percentuale_luci_bruciate,
    m.contrasto,
    m.indice_nitidezza,
    m.larghezza_pixel,
    m.altezza_pixel,
    LEAST(m.larghezza_pixel, m.altezza_pixel) AS min_side
FROM public.reference_fedelta_umane h
JOIN public.esecuzioni e4
    ON e4.id = h.id_esecuzione
JOIN public.foto f
    ON f.id = e4.id_foto
LEFT JOIN l0_runs l0
    ON l0.id_foto = f.id
LEFT JOIN l0_metrics m
    ON m.id_esecuzione = l0.id_esecuzione_l0
WHERE h.livello = 'L4'::text;


-- Frozen candidate gate benchmark:
-- high verifiability risk + any non-none resolution risk => RETAKE.
CREATE VIEW public.recoverability_gate_result AS
SELECT
    h.photo_id,
    h.alterazione_materiale,
    h.causa_alterazione,
    d.verifiability_risk,
    d.resolution_risk,
    d.blur,
    d.compression,
    d.noise,
    d.input_min_side,
    d.verifiability_risk = 'high'::text
        AND d.resolution_risk <> 'none'::text AS retake_candidate,
    CASE
        WHEN d.verifiability_risk = 'high'::text
         AND d.resolution_risk <> 'none'::text
            THEN 'RETAKE'::text
        ELSE 'L4_ALLOWED'::text
    END AS recoverability_decision
FROM public.reference_fedelta_umane h
JOIN public.diagnosi_input d
    ON d.photo_id = h.photo_id
WHERE h.livello = 'L4'::text;


-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE public.foto ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.esecuzioni ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metriche ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.confronti_giudice ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.controlli_fedelta ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.controlli_fedelta_clean ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voti_umani ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reference_fedelta_umane ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reference_qualita_umane ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.diagnosi_input ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.decisioni_finali ENABLE ROW LEVEL SECURITY;


-- Only reference_qualita_umane had explicit anon/authenticated policies
-- in the captured final schema.

CREATE POLICY benchmark_review_insert
ON public.reference_qualita_umane
AS PERMISSIVE
FOR INSERT
TO anon, authenticated
WITH CHECK (reviewer_label = 'self_v1'::text);

CREATE POLICY benchmark_review_select
ON public.reference_qualita_umane
AS PERMISSIVE
FOR SELECT
TO anon, authenticated
USING (true);

CREATE POLICY benchmark_review_update
ON public.reference_qualita_umane
AS PERMISSIVE
FOR UPDATE
TO anon, authenticated
USING (reviewer_label = 'self_v1'::text)
WITH CHECK (reviewer_label = 'self_v1'::text);


-- No non-internal triggers or public enum types were present
-- in the captured final schema.
