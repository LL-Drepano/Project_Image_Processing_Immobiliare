from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import httpx
import cv2
import numpy as np
from skimage.metrics import structural_similarity


app = FastAPI(title="Photo Quality Metrics Service")


class MetricsRequest(BaseModel):
    id_esecuzione: str
    url_input: HttpUrl
    url_output: HttpUrl


async def download_image(url: str) -> np.ndarray:
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Errore download immagine: {exc}",
        )

    data = np.frombuffer(response.content, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(
            status_code=400,
            detail="Il file ricevuto non è un'immagine valida",
        )

    return image


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/metriche")
async def calculate_metrics(payload: MetricsRequest):
    input_image = await download_image(str(payload.url_input))
    output_image = await download_image(str(payload.url_output))

    # Metriche fotografiche dell'output
    metrics = calculate_photo_metrics(output_image)

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

    input_brightness = float(np.mean(input_gray))
    output_brightness = float(np.mean(output_gray))

    input_saturation = mean_saturation(input_image)
    output_saturation = mean_saturation(output_aligned)

    return {
        "id_esecuzione": payload.id_esecuzione,
        **metrics,
        "ssim": float(ssim_value),
        "variazione_luminosita": (
            output_brightness - input_brightness
        ),
        "variazione_saturazione": (
            output_saturation - input_saturation
        ),
    }