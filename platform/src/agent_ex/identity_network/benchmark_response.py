"""Replay saved transport and strict benchmark JSON; never print response text."""

import re

from ..domain import canonical_payload_hash
from .benchmark_adapter import reconstruct_request
from .dispatch import _strict_json
from .manipulation_evidence import bind_response, response_payload


def classify_benchmark_response(pack, ordinal, attempt_index, response):
    entry = pack.payload["entries"][ordinal]
    request = reconstruct_request(entry["attempt_requests"][attempt_index - 1])
    payload = response_payload(response)
    bind_response(
        payload,
        request=request,
        wire=entry["wire_body"].encode("utf-8"),
        adapter_binding={
            "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
            "served_model_name": pack.payload["served_model_name"],
        },
    )
    transport = response.transport_evidence
    parsed = None
    if transport.http_status == 429 and not transport.body_truncated:
        classification = "HTTP_429_REJECTED"
    elif transport.http_status is not None and transport.http_status >= 500:
        classification = "HTTP_5XX_AMBIGUOUS"
    elif response.outcome == "timeout":
        classification = "TIMEOUT_AMBIGUOUS"
    elif response.outcome != "response":
        classification = "TRANSPORT_AMBIGUOUS"
    else:
        try:
            envelope = _strict_json(response.raw_body.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            parsed = _strict_json(content)
            labels = _strict_json(request.rendered_messages[1]["content"])["allowed_stance_labels"]
            if (
                list(parsed) != ["stance", "confidence", "public_reason"]
                or type(parsed["stance"]) is not str
                or parsed["stance"] not in labels
                or type(parsed["confidence"]) is not int
                or not 1 <= parsed["confidence"] <= 5
                or type(parsed["public_reason"]) is not str
                or not re.search(r"[\u3400-\u9fff]", parsed["public_reason"])
                or response.finish_reason != "stop"
            ):
                raise ValueError("invalid benchmark JSON/finish")
            parsed = {
                "post_stance": labels.index(parsed["stance"]) + 1,
                "post_confidence": parsed["confidence"],
            }
            classification = "VALID"
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError):
            parsed = None
            classification = "PARSE_INVALID"
    return {
        "classification": classification,
        "response_record_hash": canonical_payload_hash(payload),
        "parsed": parsed,
    }
