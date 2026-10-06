import hashlib
import hmac
import time


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    try:
        request_time = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(time.time() - request_time) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body.decode()}"
    computed = "v0=" + hmac.new(
        signing_secret.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)
