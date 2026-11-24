"""Estimate a meal's calories and nutrition with Google's Gemini, from a photo or a description.

Needs a Gemini API key in the GEMINI_API_KEY environment variable (free from
https://aistudio.google.com/apikey). The key never goes in this code.

    >>> from food import estimate
    >>> estimate(text="two eggs on toast and an orange juice")
"""
import os

from pydantic import BaseModel, Field

import re

# Google retires model names often, so the app asks which ones your key can use and picks the
# newest plain "flash" one (set GEMINI_MODEL to force a particular model instead).
_chosen = []


def pick_models(client):
    if _chosen:
        return _chosen
    if os.environ.get("GEMINI_MODEL"):
        _chosen.append(os.environ["GEMINI_MODEL"])
        return _chosen
    found = []
    for m in client.models.list():
        name = m.name.removeprefix("models/")
        match = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", name)  # e.g. gemini-3.8-flash, not -lite/-image
        if match and "generateContent" in (getattr(m, "supported_actions", None) or []):
            found.append((float(match.group(1)), name))
    _chosen.extend(name for _, name in sorted(found, reverse=True)[:3])
    return _chosen or ["gemini-flash-latest"]

PROMPT = """You are a sports dietitian estimating what's in a meal for a calorie tracker.
List each food you can see (or that is described) with a realistic portion, then total the meal.
Assume typical portions unless the photo or note shows otherwise. If something is unclear,
make your best estimate rather than refusing, and say what you assumed in `notes`.
Use kcal and grams. Round calories to the nearest 10 and grams to whole numbers."""


class Item(BaseModel):
    name: str = Field(description="Food, with portion, e.g. '1 cup white rice'")
    calories: float


class Meal(BaseModel):
    name: str = Field(description="Short name for the whole meal, e.g. 'Chicken burrito bowl'")
    items: list[Item]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fibre_g: float
    sugar_g: float
    notes: str = Field(description="One short sentence on assumptions, or empty")


class FoodError(Exception):
    """Something went wrong that the app should explain in plain words."""


def api_key():
    """The Gemini key: from this program's environment, or else straight from your Windows
    user settings (where `setx` saves it), so a newly set key works without restarting."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                key = winreg.QueryValueEx(reg, "GEMINI_API_KEY")[0]
        except OSError:
            key = None
    return key or None


def has_key():
    return bool(api_key())


MANY_PHOTOS = """There are several photos. They may show the same food from different angles, or
different dishes from one meal. Count each food once: don't add up the same plate seen twice."""


MAX_SIDE = 1024  # pixels: plenty to recognise food, and ~40x smaller than a phone photo to upload


def shrink(data, mime):
    """Phone photos are 3-12 MB; uploading that is most of the wait. Resize to MAX_SIDE as a JPEG.
    Anything Pillow can't open (e.g. HEIC) is sent as it is."""
    import io
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))  # keep phone photos upright
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=85)
        return (out.getvalue(), "image/jpeg") if out.tell() < len(data) else (data, mime)
    except Exception:
        return data, mime


# The model that answered last time. Tried first next time, so a busy newer model isn't asked first
# on every estimate. (The app passes it back in, because the app reloads this file on each run.)
last_model = None


def estimate(images=(), text="", progress=None, prefer=None):
    """Ask Gemini what's in a meal. `images` is a list of (photo bytes, mime type), e.g.
    [(open("lunch.jpg", "rb").read(), "image/jpeg")]; `text` is a description or note.
    `progress(step, detail)` is called as it goes: step is "shrink", "send", "read" (with the
    answer so far) or "retry". Returns a Meal. Raises FoodError with a plain-language message."""
    global last_model
    say = progress or (lambda step, detail="": None)
    if not has_key():
        raise FoodError("No Gemini API key found. Set GEMINI_API_KEY, then restart the app.")
    if not images and not text.strip():
        raise FoodError("Add a photo or describe the meal first.")

    from google import genai  # imported here so the rest of the app works without it
    from google.genai import errors, types

    if images:
        say("shrink")
        images = [shrink(data, mime) for data, mime in images]
    client = genai.Client(api_key=api_key())
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
    parts.append(PROMPT + (f"\n\n{MANY_PHOTOS}" if len(images) > 1 else "")
                 + (f"\n\nThe person says: {text.strip()}" if text.strip() else ""))
    # Low thinking: about twice as fast as the default, with the same estimates in testing
    fast = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Meal,
                                       temperature=0.2,
                                       thinking_config=types.ThinkingConfig(thinking_level="LOW"))
    plain = types.GenerateContentConfig(response_mime_type="application/json", response_schema=Meal,
                                        temperature=0.2)
    try:
        models = list(pick_models(client))
    except errors.ClientError as e:
        if e.code in (400, 401, 403):
            raise FoodError("Gemini didn't accept the API key. Check GEMINI_API_KEY.")
        raise FoodError(f"Couldn't reach Gemini ({e.code}). Try again in a minute.")
    if prefer in models:
        models.remove(prefer)
        models.insert(0, prefer)

    def ask(model, config):
        """Stream the answer, so the app can show it arriving. Returns the whole JSON text."""
        say("send")
        text = ""
        for chunk in client.models.generate_content_stream(model=model, contents=parts, config=config):
            text += chunk.text or ""
            say("read", text)
        return text

    last = None
    for i, model in enumerate(models):
        if i:
            say("retry")
        try:
            try:
                answer = ask(model, fast)
            except errors.ClientError as e:
                if e.code == 400 and "thinking" in str(e).lower():  # this model can't do low thinking
                    answer = ask(model, plain)
                else:
                    raise
        except errors.ClientError as e:
            last = e
            if e.code in (404, 429):  # not available, or this model's free limit is used: try the next
                continue
            if e.code in (400, 401, 403) and "key" in str(e).lower():
                raise FoodError("Gemini didn't accept the API key. Check GEMINI_API_KEY.")
            raise FoodError(f"Gemini couldn't read that ({e.code}). Try another photo or add a description.")
        except errors.ServerError as e:  # that model is busy: try the next one
            last = e
            continue
        try:
            meal = Meal.model_validate_json(answer)
        except ValueError:
            raise FoodError("Gemini's answer didn't make sense. Try again, or describe the meal in words.")
        last_model = model
        return meal
    if isinstance(last, errors.ServerError):
        raise FoodError("Gemini is busy right now. Try again in a minute.")
    if getattr(last, "code", None) == 429:
        raise FoodError("Gemini's free limit is used up for now. Try again in a minute, or tomorrow.")
    raise FoodError(f"None of the Gemini models are available to this key ({last}).")
