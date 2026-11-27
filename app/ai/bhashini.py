"""Bhashini (Government of India, free) text-to-speech. Natural for Kannada and Hindi.
Needs BHASHINI_USER_ID and BHASHINI_API_KEY (bhashini.gov.in -> Profile -> generate API key)."""
import base64
import os
import time

import requests

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
PIPELINE_ID = os.environ.get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")   # MeitY public pipeline
_CACHE: dict[str, tuple] = {}     # lang -> (url, auth header, serviceId, time)


def available() -> bool:
    return bool(os.environ.get("BHASHINI_USER_ID") and os.environ.get("BHASHINI_API_KEY"))


def _service(lang: str):
    c = _CACHE.get(lang)
    if c and time.time() - c[3] < 6 * 3600:
        return c
    r = requests.post(CONFIG_URL, timeout=20,
                      headers={"userID": os.environ["BHASHINI_USER_ID"], "ulcaApiKey": os.environ["BHASHINI_API_KEY"]},
                      json={"pipelineTasks": [{"taskType": "tts", "config": {"language": {"sourceLanguage": lang}}}],
                            "pipelineRequestConfig": {"pipelineId": PIPELINE_ID}})
    r.raise_for_status()
    d = r.json()
    ep = d["pipelineInferenceAPIEndPoint"]
    header = {ep["inferenceApiKey"]["name"]: ep["inferenceApiKey"]["value"]}
    sid = d["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    _CACHE[lang] = (ep["callbackUrl"], header, sid, time.time())
    return _CACHE[lang]


def speak(text: str, lang: str, gender: str = "female") -> bytes:
    """Returns WAV bytes."""
    url, header, sid, _ = _service(lang)
    r = requests.post(url, headers=header, timeout=30, json={
        "pipelineTasks": [{"taskType": "tts", "config": {"language": {"sourceLanguage": lang}, "serviceId": sid,
                                                         "gender": gender, "samplingRate": 22050}}],
        "inputData": {"input": [{"source": text[:1500]}]}})
    r.raise_for_status()
    return base64.b64decode(r.json()["pipelineResponse"][0]["audio"][0]["audioContent"])
