"""Image captioning — free path via HF Inference API (BLIP) or local transformers.

If no HF token and no local model available, degrades to a placeholder caption so
the pipeline keeps running (images are stored in MinIO either way).
"""
import io

from rag_kro_shared import get_settings


def caption_image(raw: bytes) -> str:
    settings = get_settings()
    model = "Salesforce/blip-image-captioning-base"

    if settings.hf_token:
        try:
            import httpx

            resp = httpx.post(
                f"{settings.hf_api_url}/models/{model}",
                headers={"Authorization": f"Bearer {settings.hf_token}"},
                content=raw,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data[0].get("generated_text", "") if isinstance(data, list) else str(data)
        except Exception:
            pass

    try:
        from PIL import Image
        from transformers import BlipForConditionalGeneration, BlipProcessor

        processor = BlipProcessor.from_pretrained(model)
        model_ = BlipForConditionalGeneration.from_pretrained(model)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        inputs = processor(image, return_tensors="pt")
        out = model_.generate(**inputs)
        return processor.decode(out[0], skip_special_tokens=True)
    except Exception:
        return "[image uploaded] awaiting caption model"