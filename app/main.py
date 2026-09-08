from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import httpx
import cv2
import numpy as np

from skimage.metrics import structural_similarity
from skimage.measure import blur_effect
from skimage.restoration import estimate_sigma
from skimage.color import rgb2lab


app = FastAPI(title="Photo Quality Metrics Service — Calibrated Diagnosis v4")


# ============================================================
# REQUEST MODELS
# ============================================================

class MetricsRequest(BaseModel):
    id_esecuzione: str
    url_input: HttpUrl
    url_output: HttpUrl


class DiagnosiRequest(BaseModel):
    url_input: HttpUrl


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

async def download_image(url: str, tipo: str) -> np.ndarray:
    try:
        async with httpx.AsyncClient(
            timeout=90.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        cloudinary_error = exc.response.headers.get("x-cld-error")

        raise HTTPException(
            status_code=502,
            detail={
                "errore": "download_http",
                "tipo": tipo,
                "url": url,
                "status_cloudinary": status,
                "x_cld_error": cloudinary_error,
            },
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "errore": "download_connessione",
                "tipo": tipo,
                "url": url,
                "dettaglio": str(exc),
            },
        )

    data = np.frombuffer(response.content, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(
            status_code=502,
            detail={
                "errore": "immagine_non_valida",
                "tipo": tipo,
                "url": url,
                "content_type": response.headers.get("content-type"),
                "bytes": len(response.content),
            },
        )

    return image


# ============================================================
# IMAGE RESIZING
# ============================================================

def resize_to_reference(
    candidate: np.ndarray,
    reference: np.ndarray,
) -> np.ndarray:
    ref_h, ref_w = reference.shape[:2]
    cand_h, cand_w = candidate.shape[:2]

    if (cand_w, cand_h) == (ref_w, ref_h):
        return candidate

    if cand_w > ref_w or cand_h > ref_h:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_CUBIC

    return cv2.resize(
        candidate,
        (ref_w, ref_h),
        interpolation=interpolation,
    )


def resize_for_diagnosis(
    image: np.ndarray,
    max_side: int = 1280,
) -> np.ndarray:
    """
    Normalizza la dimensione dell'immagine prima della diagnosi.

    Non effettua upscale.
    Manteniamo max_side costante perché le metriche devono
    essere confrontabili tra immagini.
    """

    height, width = image.shape[:2]

    current_max = max(height, width)

    if current_max <= max_side:
        return image

    scale = max_side / current_max

    new_width = int(width * scale)
    new_height = int(height * scale)

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_AREA,
    )


# ============================================================
# PHOTO METRICS
# ============================================================

def mean_saturation(image: np.ndarray) -> float:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(np.mean(hsv[:, :, 1]))


def calculate_photo_metrics(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    height, width = image.shape[:2]

    return {
        "luminosita_media": float(np.mean(gray)),
        "percentuale_ombre_perse": float(
            np.mean(gray <= 5) * 100
        ),
        "percentuale_luci_bruciate": float(
            np.mean(gray >= 250) * 100
        ),
        "contrasto": float(np.std(gray)),
        "indice_nitidezza": float(
            cv2.Laplacian(gray, cv2.CV_64F).var()
        ),
        "larghezza_pixel": int(width),
        "altezza_pixel": int(height),
    }


# ============================================================
# DIAGNOSIS SIGNALS
# ============================================================

def calculate_diagnosis_signals(
    image: np.ndarray,
) -> dict:
    """
    Calcola i segnali no-reference usati per la diagnosi.

    Produce i segnali raw usati dalle regole calibrate.
    Le classificazioni vengono applicate separatamente sotto.
    """

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    # Float normalizzato 0-1.
    # Utile soprattutto per avere noise_sigma
    # su una scala coerente.
    gray_float = (
        gray.astype(np.float32) / 255.0
    )

    # --------------------------------------------------------
    # 1. BLUR EFFECT
    #
    # Implementazione scikit-image:
    # circa 0 = poco blur
    # circa 1 = molto blur
    # --------------------------------------------------------

    perceptual_blur = float(
        blur_effect(
            gray_float,
            h_size=11,
            channel_axis=None,
        )
    )

    # --------------------------------------------------------
    # 2. NOISE SIGMA
    #
    # Estimatore wavelet robusto di scikit-image.
    # Dato che gray_float è 0-1, anche sigma è espresso
    # rispetto a questa scala.
    # --------------------------------------------------------

    noise_sigma = float(
        estimate_sigma(
            gray_float,
            average_sigmas=True,
            channel_axis=None,
        )
    )

    # --------------------------------------------------------
    # 3. LAPLACIAN RAW
    #
    # Lo conserviamo come segnale diagnostico.
    # È sensibile sia al dettaglio reale sia al rumore.
    # --------------------------------------------------------

    laplacian_raw = cv2.Laplacian(
        gray,
        cv2.CV_64F,
    )

    sharpness_raw = float(
        laplacian_raw.var()
    )

    # --------------------------------------------------------
    # 4. LAPLACIAN DOPO SMOOTHING
    #
    # Non viene usato direttamente per classificare il blur.
    # Ci serve principalmente per studiare la quantità
    # di alta frequenza eliminata dallo smoothing.
    # --------------------------------------------------------

    gray_denoised = cv2.GaussianBlur(
        gray,
        (5, 5),
        0,
    )

    laplacian_denoised = cv2.Laplacian(
        gray_denoised,
        cv2.CV_64F,
    )

    sharpness_denoised = float(
        laplacian_denoised.var()
    )

    # --------------------------------------------------------
    # 5. HIGH FREQUENCY RATIO
    #
    # Nei primi test:
    #
    # good  ≈ 8
    # noise ≈ 206
    #
    # Non è ancora un detector.
    # Lo conserviamo per la calibrazione.
    # --------------------------------------------------------

    high_frequency_ratio = (
        sharpness_raw
        / max(sharpness_denoised, 0.001)
    )

    return {
        "blur_effect": perceptual_blur,
        "noise_sigma": noise_sigma,
        "sharpness_raw": sharpness_raw,
        "sharpness_denoised": sharpness_denoised,
        "high_frequency_ratio": high_frequency_ratio,
    }


def calculate_jpeg_blockiness(
    image: np.ndarray,
) -> dict:
    """
    Stima la presenza di blockiness JPEG confrontando
    le discontinuità ai bordi dei blocchi 8x8 con quelle
    immediatamente adiacenti.

    Score più alto = maggiore evidenza di blocking 8x8.

    blockiness_ratio = bordo / vicini  (1.0 = nessun blocking)
    blockiness_score = ratio - 1, con minimo 0

    La soglia 1.20 del detector si applica a blockiness_score
    (campo JSON "jpeg_blockiness"), NON al ratio.
    """

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    ).astype(np.float32)

    height, width = gray.shape

    if height < 24 or width < 24:
        return {
            "blockiness_score": 0.0,
            "block_boundary_mean": 0.0,
            "block_neighbor_mean": 0.0,
            "blockiness_ratio": 1.0,
        }

    # Differenze tra pixel adiacenti.
    vertical_diff = np.abs(
        gray[:, 1:] - gray[:, :-1]
    )

    horizontal_diff = np.abs(
        gray[1:, :] - gray[:-1, :]
    )

    # Nei JPEG i confini dei blocchi cadono
    # tra pixel 7/8, 15/16, 23/24, ...
    vertical_boundaries = np.arange(
        7,
        vertical_diff.shape[1],
        8,
    )

    horizontal_boundaries = np.arange(
        7,
        horizontal_diff.shape[0],
        8,
    )

    vertical_boundary_values = vertical_diff[
        :,
        vertical_boundaries,
    ].ravel()

    horizontal_boundary_values = horizontal_diff[
        horizontal_boundaries,
        :,
    ].ravel()

    boundary_values = np.concatenate([
        vertical_boundary_values,
        horizontal_boundary_values,
    ])

    # Confrontiamo i boundary 8x8 con le linee
    # immediatamente adiacenti.
    vertical_neighbors = np.concatenate([
        vertical_boundaries - 1,
        vertical_boundaries + 1,
    ])

    vertical_neighbors = vertical_neighbors[
        (vertical_neighbors >= 0)
        & (
            vertical_neighbors
            < vertical_diff.shape[1]
        )
    ]

    horizontal_neighbors = np.concatenate([
        horizontal_boundaries - 1,
        horizontal_boundaries + 1,
    ])

    horizontal_neighbors = horizontal_neighbors[
        (horizontal_neighbors >= 0)
        & (
            horizontal_neighbors
            < horizontal_diff.shape[0]
        )
    ]

    vertical_neighbor_values = vertical_diff[
        :,
        vertical_neighbors,
    ].ravel()

    horizontal_neighbor_values = horizontal_diff[
        horizontal_neighbors,
        :,
    ].ravel()

    neighbor_values = np.concatenate([
        vertical_neighbor_values,
        horizontal_neighbor_values,
    ])

    boundary_mean = float(
        np.mean(boundary_values)
    )

    neighbor_mean = float(
        np.mean(neighbor_values)
    )

    blockiness_ratio = (
        boundary_mean
        / max(neighbor_mean, 0.001)
    )

    blockiness_score = max(
        0.0,
        (
            boundary_mean
            - neighbor_mean
        )
        / max(neighbor_mean, 0.001),
    )

    return {
        "blockiness_score": blockiness_score,
        "block_boundary_mean": boundary_mean,
        "block_neighbor_mean": neighbor_mean,
        "blockiness_ratio": blockiness_ratio,
    }


def calculate_exposure_signals(
    image: np.ndarray,
) -> dict:
    """
    Segnali no-reference per esposizione.

    Restituisce i segnali raw usati dalle regole calibrate
    di under/over exposure.
    """

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    return {
        "mean_luminance": float(np.mean(gray)),
        "median_luminance": float(np.median(gray)),
        "p05_luminance": float(np.percentile(gray, 5)),
        "p95_luminance": float(np.percentile(gray, 95)),
        "shadows_clipped_pct": float(
            np.mean(gray <= 5) * 100
        ),
        "highlights_clipped_pct": float(
            np.mean(gray >= 250) * 100
        ),
    }


def calculate_color_signals(
    image: np.ndarray,
) -> dict:
    """
    Segnali globali per dominante colore / white balance
    e saturazione.

    Sono volutamente descrittivi: il confronto con le
    originali pulite ha confermato che scene reali possono
    avere valori estremi senza essere cromaticamente errate.
    """

    # OpenCV usa BGR.
    b_mean = float(np.mean(image[:, :, 0]))
    g_mean = float(np.mean(image[:, :, 1]))
    r_mean = float(np.mean(image[:, :, 2]))

    rgb_mean = max(
        (r_mean + g_mean + b_mean) / 3.0,
        0.001,
    )

    # Magnitudine dello sbilanciamento globale tra canali.
    channel_spread = (
        max(r_mean, g_mean, b_mean)
        - min(r_mean, g_mean, b_mean)
    )

    color_cast_score = float(
        channel_spread / rgb_mean
    )

    # Segnale caldo/freddo:
    # positivo = tendenza più calda/rossa
    # negativo = tendenza più fredda/blu
    warm_cool_score = float(
        (r_mean - b_mean) / rgb_mean
    )

    hsv = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2HSV,
    )

    saturation = hsv[:, :, 1].astype(np.float32)

    return {
        "red_mean": r_mean,
        "green_mean": g_mean,
        "blue_mean": b_mean,
        "color_cast_score": color_cast_score,
        "warm_cool_score": warm_cool_score,
        "mean_saturation": float(
            np.mean(saturation)
        ),
        "p95_saturation": float(
            np.percentile(saturation, 95)
        ),
        "high_saturation_pct": float(
            np.mean(saturation >= 240) * 100
        ),
        "low_saturation_pct": float(
            np.mean(saturation <= 15) * 100
        ),
    }


def calculate_neutral_color_shift(
    image: np.ndarray,
) -> dict:
    """
    Stima una dominante cromatica comune nelle regioni
    più vicine al neutro dell'immagine.

    Procedura:
    - input OpenCV BGR -> RGB;
    - RGB float [0,1] -> CIELAB con skimage.color.rgb2lab;
    - tiene solo 20 <= L <= 95;
    - tra i validi seleziona esattamente il 25% con croma
      C = sqrt(a^2 + b^2) più bassa;
    - misura la lunghezza del vettore medio (mean_a, mean_b).

    neutral_chroma_shift misura quindi una tinta comune,
    non la croma media dei singoli pixel.

    Se i pixel con luminanza valida sono meno dell'1% del
    totale, il segnale non è considerato verificabile:
    shift/mean_a/mean_b vengono restituiti come null.
    """

    height, width = image.shape[:2]
    total_pixels = int(height * width)

    if total_pixels == 0:
        return {
            "neutral_chroma_shift": None,
            "neutral_shift_direction": "none",
            "neutral_region_pct": 0.0,
            "neutral_mean_a": None,
            "neutral_mean_b": None,
        }

    # OpenCV legge BGR; rgb2lab richiede RGB.
    rgb = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB,
    ).astype(np.float32) / 255.0

    lab = rgb2lab(rgb)

    l_channel = lab[:, :, 0]
    a_channel = lab[:, :, 1]
    b_channel = lab[:, :, 2]

    valid_mask = (
        (l_channel >= 20.0)
        & (l_channel <= 95.0)
    )

    valid_count = int(
        np.count_nonzero(valid_mask)
    )

    valid_pct = (
        valid_count / total_pixels
    ) * 100.0

    if valid_count == 0:
        return {
            "neutral_chroma_shift": None,
            "neutral_shift_direction": "none",
            "neutral_region_pct": 0.0,
            "neutral_mean_a": None,
            "neutral_mean_b": None,
        }

    valid_a = a_channel[valid_mask]
    valid_b = b_channel[valid_mask]

    valid_chroma = np.sqrt(
        valid_a ** 2
        + valid_b ** 2
    )

    # Percentile richiesto dalla specifica.
    # In immagini uniformi molti pixel possono avere esattamente
    # la stessa croma del percentile: usare semplicemente
    # C <= percentile_25 selezionerebbe anche il 100% dei pixel.
    # Manteniamo quindi il concetto del percentile, ma limitiamo
    # la selezione a esattamente il 25% dei validi.
    percentile_25 = float(
        np.percentile(valid_chroma, 25)
    )

    target_count = max(
        1,
        int(np.ceil(valid_count * 0.25)),
    )

    # Tolleranza puramente numerica per il tie handling.
    # 0.05 CIELAB è molto più piccola di una differenza
    # cromatica visivamente significativa, ma evita che
    # quantizzazione/round-trip RGB facciano scegliere tutta
    # una metà di una regione che ha croma sostanzialmente uguale.
    tie_tolerance = 0.05

    below_idx = np.flatnonzero(
        valid_chroma
        < (percentile_25 - tie_tolerance)
    )

    tie_idx = np.flatnonzero(
        np.abs(
            valid_chroma - percentile_25
        ) <= tie_tolerance
    )

    if below_idx.size >= target_count:
        # Caso raro: se già i valori nettamente sotto il
        # percentile superano il target, prendiamo i più bassi.
        local_order = np.argpartition(
            valid_chroma[below_idx],
            target_count - 1,
        )[:target_count]

        selected_idx = below_idx[
            local_order
        ]

    else:
        remaining = (
            target_count - below_idx.size
        )

        if tie_idx.size > remaining:
            # Campionamento deterministico e distribuito lungo
            # l'array per non introdurre bias spaziale nelle
            # grandi regioni piatte / a croma uguale.
            positions = np.linspace(
                0,
                tie_idx.size - 1,
                num=remaining,
                dtype=np.int64,
            )

            tie_selected = tie_idx[
                positions
            ]
        else:
            tie_selected = tie_idx

        selected_idx = np.concatenate([
            below_idx,
            tie_selected,
        ])

        # Fallback robusto se il pool entro tolleranza non basta.
        if selected_idx.size < target_count:
            selected_idx = np.argpartition(
                valid_chroma,
                target_count - 1,
            )[:target_count]

    selected_a = valid_a[selected_idx]
    selected_b = valid_b[selected_idx]

    selected_count = int(
        selected_idx.size
    )

    neutral_region_pct = (
        selected_count / total_pixels
    ) * 100.0

    # Se la regione con luminanza informativa è troppo piccola,
    # non forziamo una stima cromatica.
    if valid_pct < 1.0:
        return {
            "neutral_chroma_shift": None,
            "neutral_shift_direction": "none",
            "neutral_region_pct": float(
                neutral_region_pct
            ),
            "neutral_mean_a": None,
            "neutral_mean_b": None,
        }

    mean_a = float(
        np.mean(selected_a)
    )

    mean_b = float(
        np.mean(selected_b)
    )

    shift = float(
        np.sqrt(
            mean_a ** 2
            + mean_b ** 2
        )
    )

    if shift < 1.0:
        direction = "none"

    elif abs(mean_b) >= abs(mean_a):
        direction = (
            "warm"
            if mean_b > 0.0
            else "cool"
        )

    else:
        direction = (
            "magenta"
            if mean_a > 0.0
            else "green"
        )

    return {
        "neutral_chroma_shift": shift,
        "neutral_shift_direction": direction,
        "neutral_region_pct": float(
            neutral_region_pct
        ),
        "neutral_mean_a": mean_a,
        "neutral_mean_b": mean_b,
    }


def calculate_resolution_signals(
    image: np.ndarray,
) -> dict:
    """
    Segnali geometrici per valutare la sufficienza
    della risoluzione dell'input.

    La policy di resolution risk è separata dai detector
    fotografici e non viene usata per inferire compressione.
    """

    height, width = image.shape[:2]

    megapixels = (
        width * height
    ) / 1_000_000.0

    return {
        "width": int(width),
        "height": int(height),
        "min_side": int(min(width, height)),
        "max_side": int(max(width, height)),
        "megapixels": float(megapixels),
    }


# ============================================================
# CALIBRATED DIAGNOSIS
# ============================================================

DIAGNOSIS_VERSION = "v4_reconstruction_risk_2026-09-08"


def classify_blur(
    blur_score: float,
    noise_level: str,
) -> str:
    """
    Soglie calibrate sul golden set e validate contro
    le originali pulite disponibili.

    Le originali pulite osservate restano sotto ~0.37.
    Quando il detector noise segnala rumore forte e il
    blur_effect resta sotto soglia, non concludiamo "no blur":
    il rumore può sabotare il detector di blur.
    """

    if blur_score >= 0.70:
        return "high"

    if blur_score >= 0.55:
        return "medium"

    if blur_score >= 0.40:
        return "low"

    if noise_level == "high":
        return "uncertain"

    return "none"


def classify_noise(
    high_frequency_ratio: float,
    blur_score: float,
) -> str:
    """
    Euristica sperimentale calibrata su 3 esempi noti di noise.

    NON usa noise_sigma come soglia primaria perché sulle
    originali pulite sono stati osservati valori elevati anche
    senza degradazione sintetica.

    high_frequency_ratio è risultato molto più discriminante.
    """

    if high_frequency_ratio >= 80.0:
        return "high"

    if (
        high_frequency_ratio >= 50.0
        and blur_score >= 0.50
    ):
        return "high"

    return "none_detected"


def classify_compression(
    blockiness_score: float,
    blur_level: str,
) -> str:
    """
    Il detector 8x8 è affidabile soprattutto per blocking forte.

    Si applica a blockiness_score (= ratio - 1).
    Le originali pulite arrivano circa a 1.04 di score, quindi
    usiamo una soglia conservativa >= 1.20.

    Se contemporaneamente c'è blur evidente, il blocking può
    essere un falso segnale e viene marcato uncertain.

    Limite noto: compressioni medie (score 0.5-1.0) non vengono
    rilevate, es. corridoio_01 (0.87).
    """

    if blockiness_score < 1.20:
        return "none_detected"

    if blur_level in {"low", "medium", "high", "uncertain"}:
        return "uncertain"

    return "high"


def classify_underexposure(
    mean_luminance: float,
    shadows_clipped_pct: float,
) -> str:
    if (
        mean_luminance < 35.0
        or shadows_clipped_pct >= 20.0
    ):
        return "high"

    if (
        mean_luminance < 70.0
        or shadows_clipped_pct >= 10.0
    ):
        return "medium"

    if mean_luminance < 100.0:
        return "low"

    return "none"


def classify_overexposure(
    mean_luminance: float,
    p95_luminance: float,
    highlights_clipped_pct: float,
    mean_saturation: float,
) -> str:
    """
    Rileva soprattutto white-blend / washed-out forte.

    La calibrazione paired input-vs-clean ha mostrato che il solo
    highlight clipping è troppo permissivo: una foto può avere
    aree bianche bruciate senza essere globalmente sovraesposta.

    Per questo richiediamo una combinazione di:
    - luminanza globale alta;
    - percentile alto vicino al bianco;
    - saturazione globale bassa.

    Le soglie separano i tre casi white-blend osservati senza
    marcare camera_da_letto_04 come overexposed.
    """

    if (
        mean_luminance >= 240.0
        and p95_luminance >= 250.0
        and highlights_clipped_pct >= 20.0
        and mean_saturation < 50.0
    ):
        return "high"

    if (
        mean_luminance >= 220.0
        and p95_luminance >= 245.0
        and mean_saturation < 50.0
    ):
        return "medium"

    if (
        mean_luminance >= 205.0
        and p95_luminance >= 245.0
        and mean_saturation < 50.0
    ):
        return "low"

    return "none"


def classify_resolution_risk(
    min_side: int,
) -> str:
    """
    Policy di prodotto, non detector fotografico.

    Manteniamo la risoluzione separata dalla compressione per
    evitare benchmark leakage.
    """

    if min_side <= 500:
        return "high"

    if min_side < 720:
        return "medium"

    if min_side < 1080:
        return "low"

    return "none"


def calculate_verifiability_risk(
    blur_level: str,
    noise_level: str,
    compression_level: str,
    underexposure_level: str,
    overexposure_level: str,
    resolution_risk: str,
) -> str:
    """
    Quanto è difficile verificare la fedeltà di un output
    ricostruttivo partendo dall'input.

    Non misura la qualità estetica: misura quanta informazione
    affidabile resta disponibile per il fidelity checker.

    NON è il gate di routing: per quello vedi
    calculate_reconstruction_risk.
    """

    if (
        blur_level == "high"
        or noise_level == "high"
        or underexposure_level == "high"
        or overexposure_level == "high"
        or resolution_risk == "high"
    ):
        return "high"

    if (
        blur_level in {"medium", "uncertain"}
        or compression_level in {"high", "uncertain"}
        or underexposure_level == "medium"
        or overexposure_level == "medium"
        or resolution_risk == "medium"
    ):
        return "medium"

    return "low"


def calculate_reconstruction_risk(
    blur_level: str,
    noise_level: str,
    compression_level: str,
    resolution_risk: str,
) -> dict:
    """
    Rischio che un livello ricostruttivo (L4) inventi o alteri
    contenuto reale dell'immobile.

    Derivato dall'incrocio tra i flag di input e le 29 etichette
    umane di fedeltà su L4 (8 settembre 2026, 7 alterazioni):

    - compressione (blockiness_score >= 1.20, cioè compression
      high o uncertain): 3 foto, 3 alterazioni, tutte gravi
      -> high
    - risoluzione (lato corto <= 500): 4 foto, 3 alterazioni
    - blur high: 4 foto, 2 alterazioni
    - noise high: 3 foto, 1 alterazione
      -> medium
    - esposizione (under/over, qualsiasi livello): 8 foto,
      0 alterazioni -> ESCLUSA dal rischio

    È un'ipotesi calibrata su 7 casi positivi.
    Non decide il routing: n8n decide cosa fare con
    high / medium / none. Il caso camera_da_letto_05
    (prese elettriche) non viene intercettato da nessun
    segnale di input: per questo la conferma umana dopo L4
    resta necessaria.
    """

    reasons = []

    if compression_level in {"high", "uncertain"}:
        reasons.append("compression")

    if resolution_risk == "high":
        reasons.append("resolution")

    if blur_level == "high":
        reasons.append("blur")

    if noise_level == "high":
        reasons.append("noise")

    if "compression" in reasons:
        level = "high"
    elif reasons:
        level = "medium"
    else:
        level = "none"

    return {
        "reconstruction_risk": level,
        "reconstruction_risk_reasons": reasons,
    }


def build_calibrated_diagnosis(
    signals: dict,
    compression_signals: dict,
    exposure_signals: dict,
    color_signals: dict,
    resolution_signals: dict,
) -> dict:
    """
    Costruisce la parte deterministica della diagnosi.

    IMPORTANTE SUL COLORE:
    i confronti con le originali pulite hanno dimostrato che
    color_cast_score, warm_cool_score e saturation globali non
    possono stabilire in modo affidabile se i colori siano
    sbagliati rispetto alla realtà.

    Di conseguenza FastAPI:
    - conserva i segnali colore raw;
    - NON decide color_cast/saturation_issue;
    - NON decide autonomamente se chiedere conferma umana;
    - dichiara invece che serve un color triage semantico
      (es. VLM in n8n), che potrà poi escalare all'umano.

    La quality finale viene quindi risolta dopo quel triage.
    """

    noise_level = classify_noise(
        signals["high_frequency_ratio"],
        signals["blur_effect"],
    )

    blur_level = classify_blur(
        signals["blur_effect"],
        noise_level,
    )

    compression_level = classify_compression(
        compression_signals["blockiness_score"],
        blur_level,
    )

    underexposure_level = classify_underexposure(
        exposure_signals["mean_luminance"],
        exposure_signals["shadows_clipped_pct"],
    )

    overexposure_level = classify_overexposure(
        exposure_signals["mean_luminance"],
        exposure_signals["p95_luminance"],
        exposure_signals["highlights_clipped_pct"],
        color_signals["mean_saturation"],
    )

    resolution_risk = classify_resolution_risk(
        resolution_signals["min_side"]
    )

    verifiability_risk = calculate_verifiability_risk(
        blur_level,
        noise_level,
        compression_level,
        underexposure_level,
        overexposure_level,
        resolution_risk,
    )

    reconstruction = calculate_reconstruction_risk(
        blur_level,
        noise_level,
        compression_level,
        resolution_risk,
    )

    deterministic_issue_detected = bool(
        blur_level in {"low", "medium", "high", "uncertain"}
        or noise_level == "high"
        or compression_level in {"high", "uncertain"}
        or underexposure_level in {"low", "medium", "high"}
        or overexposure_level in {"low", "medium", "high"}
        or resolution_risk in {"medium", "high"}
    )

    technical_quality_ok = not deterministic_issue_detected

    return {
        "diagnosis_version": DIAGNOSIS_VERSION,

        # Esito della sola parte deterministica.
        # Non è ancora la quality finale perché il colore resta
        # da valutare semanticamente.
        "technical_quality_ok": technical_quality_ok,
        "deterministic_issue_detected": deterministic_issue_detected,

        "blur": blur_level,
        "noise": noise_level,
        "compression": compression_level,
        "underexposure": underexposure_level,
        "overexposure": overexposure_level,
        "resolution_risk": resolution_risk,

        # Colore / temperatura:
        # le metriche raw sono restituite sotto, ma la decisione
        # viene volutamente delegata al prossimo layer n8n.
        "color_status": "unresolved_no_reference",
        "color_decision_deferred_to_n8n": True,
        "color_triage_strategy": "n8n_triage_then_human_confirmation",

        # quality_ok finale verrà calcolato nel layer di decisione
        # dopo il color triage / eventuale conferma umana.
        "quality_status": (
            "technical_issue_detected"
            if deterministic_issue_detected
            else "pending_color_triage"
        ),

        # Quanto il fidelity checker può verificare (invariato).
        "verifiability_risk": verifiability_risk,
        "requires_extra_fidelity_caution": (
            verifiability_risk in {"medium", "high"}
        ),

        # Rischio che L4 inventi contenuto: segnale per il routing.
        "reconstruction_risk": reconstruction["reconstruction_risk"],
        "reconstruction_risk_reasons": reconstruction[
            "reconstruction_risk_reasons"
        ],
    }


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.post("/metriche")
async def calculate_metrics(
    payload: MetricsRequest,
):
    input_image = await download_image(
        str(payload.url_input),
        "input",
    )

    output_image = await download_image(
        str(payload.url_output),
        "output",
    )

    # Metriche fotografiche dell'output
    metrics = calculate_photo_metrics(
        output_image
    )

    # Per i confronti allineiamo l'output
    # alla stessa dimensione dell'input
    output_aligned = resize_to_reference(
        output_image,
        input_image,
    )

    input_gray = cv2.cvtColor(
        input_image,
        cv2.COLOR_BGR2GRAY,
    )

    output_gray = cv2.cvtColor(
        output_aligned,
        cv2.COLOR_BGR2GRAY,
    )

    ssim_value = structural_similarity(
        input_gray,
        output_gray,
        data_range=255,
    )

    input_brightness = float(
        np.mean(input_gray)
    )

    output_brightness = float(
        np.mean(output_gray)
    )

    input_saturation = mean_saturation(
        input_image
    )

    output_saturation = mean_saturation(
        output_aligned
    )

    return {
        "id_esecuzione": payload.id_esecuzione,
        **metrics,
        "ssim": float(ssim_value),
        "variazione_luminosita": (
            output_brightness
            - input_brightness
        ),
        "variazione_saturazione": (
            output_saturation
            - input_saturation
        ),
    }


@app.post("/diagnosi")
async def diagnose_image(
    payload: DiagnosiRequest,
):
    """
    Diagnosi automatica calibrata v4.

    Restituisce:
    - segnali numerici raw per audit/debug;
    - classificazioni calibrate per blur, noise, compressione,
      esposizione e resolution risk;
    - technical_quality_ok e verifiability_risk;
    - reconstruction_risk + reasons (segnale per il routing);
    - stato colore volutamente unresolved_no_reference.

    Il triage colore e l'eventuale conferma umana appartengono
    al layer n8n successivo. Il routing (KEEP / L1 / L4 / RETAKE)
    resta in n8n.
    """

    input_image = await download_image(
        str(payload.url_input),
        "input_diagnosi",
    )

    original_height, original_width = (
        input_image.shape[:2]
    )

    diagnosis_image = resize_for_diagnosis(
        input_image,
        max_side=1280,
    )

    diagnosis_height, diagnosis_width = (
        diagnosis_image.shape[:2]
    )

    signals = calculate_diagnosis_signals(
        diagnosis_image
    )

    # La blockiness JPEG va misurata sull'immagine originale,
    # non su quella ridimensionata per la diagnosi: il resize
    # può alterare la griglia 8x8 che vogliamo osservare.
    compression_signals = calculate_jpeg_blockiness(
        input_image
    )

    exposure_signals = calculate_exposure_signals(
        input_image
    )

    color_signals = calculate_color_signals(
        input_image
    )

    # La metrica sulle regioni neutre usa una copia separata
    # ridotta a max 1024 px. Non tocchiamo diagnosis_image (1280),
    # perché le metriche già calibrate, soprattutto blur,
    # devono restare invarianti.
    neutral_color_image = resize_for_diagnosis(
        input_image,
        max_side=1024,
    )

    neutral_color_signals = calculate_neutral_color_shift(
        neutral_color_image
    )

    resolution_signals = calculate_resolution_signals(
        input_image
    )

    calibrated = build_calibrated_diagnosis(
        signals,
        compression_signals,
        exposure_signals,
        color_signals,
        resolution_signals,
    )

    return {
        # Diagnosi strutturata calibrata
        **calibrated,

        # Segnali raw conservati per audit / debug
        "blur_effect": round(
            signals["blur_effect"],
            4,
        ),
        "noise_sigma": round(
            signals["noise_sigma"],
            6,
        ),

        # Segnali raw di compressione JPEG / blockiness.
        # jpeg_blockiness = score (ratio - 1): è il campo su cui
        # si applica la soglia 1.20.
        "jpeg_blockiness": round(
            compression_signals["blockiness_score"],
            4,
        ),
        "jpeg_blockiness_ratio": round(
            compression_signals["blockiness_ratio"],
            4,
        ),
        "jpeg_boundary_mean": round(
            compression_signals["block_boundary_mean"],
            4,
        ),
        "jpeg_neighbor_mean": round(
            compression_signals["block_neighbor_mean"],
            4,
        ),

        # Esposizione
        "mean_luminance": round(
            exposure_signals["mean_luminance"],
            2,
        ),
        "median_luminance": round(
            exposure_signals["median_luminance"],
            2,
        ),
        "p05_luminance": round(
            exposure_signals["p05_luminance"],
            2,
        ),
        "p95_luminance": round(
            exposure_signals["p95_luminance"],
            2,
        ),
        "shadows_clipped_pct": round(
            exposure_signals["shadows_clipped_pct"],
            4,
        ),
        "highlights_clipped_pct": round(
            exposure_signals["highlights_clipped_pct"],
            4,
        ),

        # Colore / white balance / saturazione
        "red_mean": round(
            color_signals["red_mean"],
            2,
        ),
        "green_mean": round(
            color_signals["green_mean"],
            2,
        ),
        "blue_mean": round(
            color_signals["blue_mean"],
            2,
        ),
        "color_cast_score": round(
            color_signals["color_cast_score"],
            4,
        ),
        "warm_cool_score": round(
            color_signals["warm_cool_score"],
            4,
        ),
        "mean_saturation": round(
            color_signals["mean_saturation"],
            2,
        ),
        "p95_saturation": round(
            color_signals["p95_saturation"],
            2,
        ),
        "high_saturation_pct": round(
            color_signals["high_saturation_pct"],
            4,
        ),
        "low_saturation_pct": round(
            color_signals["low_saturation_pct"],
            4,
        ),

        # Dominante cromatica sulle regioni più vicine al neutro
        "neutral_chroma_shift": (
            round(
                neutral_color_signals[
                    "neutral_chroma_shift"
                ],
                4,
            )
            if neutral_color_signals[
                "neutral_chroma_shift"
            ] is not None
            else None
        ),
        "neutral_shift_direction": (
            neutral_color_signals[
                "neutral_shift_direction"
            ]
        ),
        "neutral_region_pct": round(
            neutral_color_signals[
                "neutral_region_pct"
            ],
            4,
        ),
        "neutral_mean_a": (
            round(
                neutral_color_signals[
                    "neutral_mean_a"
                ],
                4,
            )
            if neutral_color_signals[
                "neutral_mean_a"
            ] is not None
            else None
        ),
        "neutral_mean_b": (
            round(
                neutral_color_signals[
                    "neutral_mean_b"
                ],
                4,
            )
            if neutral_color_signals[
                "neutral_mean_b"
            ] is not None
            else None
        ),

        # Risoluzione
        "input_width": (
            resolution_signals["width"]
        ),
        "input_height": (
            resolution_signals["height"]
        ),
        "input_min_side": (
            resolution_signals["min_side"]
        ),
        "input_max_side": (
            resolution_signals["max_side"]
        ),
        "input_megapixels": round(
            resolution_signals["megapixels"],
            4,
        ),

        # Metriche diagnostiche secondarie
        "sharpness_raw": round(
            signals["sharpness_raw"],
            2,
        ),
        "sharpness_denoised": round(
            signals["sharpness_denoised"],
            2,
        ),
        "high_frequency_ratio": round(
            signals["high_frequency_ratio"],
            2,
        ),

        # Informazioni dimensionali
        "original_width": int(
            original_width
        ),
        "original_height": int(
            original_height
        ),
        "diagnosis_width": int(
            diagnosis_width
        ),
        "diagnosis_height": int(
            diagnosis_height
        ),
    }