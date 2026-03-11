"""
Generic HTTP request with x402 (402 Payment Required) handling.
Mirrors agent0-ts src/core/x402-request.ts. Uses sync requests.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Callable, Dict, List, Optional, Union

from .x402_types import (
    X402Accept,
    X402Payment,
    X402RequiredResponse,
    RequestSnapshot,
    filter_evm_accepts,
    parse_402_from_header,
    parse_402_from_body,
    parse_402_from_www_authenticate,
    parse_402_settlement_from_header,
)


# Type: parse_response(response) -> T
# Type: build_payment(accept, snapshot) -> str
# Type: check_balance(accept) -> bool (optional)
# fetch callable: (url, method, headers, body, payment_header_name=None, payment_payload=None) -> response with .status_code, .headers, .text
class X402RequestDeps:
    """Dependencies for request_with_x402."""
    def __init__(
        self,
        fetch: Callable[..., Any],
        build_payment: Callable[[X402Accept, RequestSnapshot], str],
        check_balance: Optional[Callable[[X402Accept], bool]] = None,
    ):
        self.fetch = fetch
        self.build_payment = build_payment
        self.check_balance = check_balance


def _default_parse_response(response: Any) -> Any:
    """Default: parse response body as JSON."""
    return response.json()


def request_with_x402(
    options: Dict[str, Any],
    deps: X402RequestDeps,
) -> Any:
    """
    Perform a single HTTP request with built-in 402 handling.
    - 2xx: return parsed result (default JSON body).
    - 402: return X402RequiredResponse with x402Payment.pay() (uses first-with-balance when check_balance is set) or pay_first().
    - Other status: raise.
    """
    url = options["url"]
    method = options["method"]
    headers = dict(options.get("headers") or {})
    body = options.get("body")
    payment = options.get("payment")
    parse_response = options.get("parseResponse") or options.get("parse_response") or _default_parse_response

    snapshot = RequestSnapshot(url=url, method=method, headers=headers, body=body)

    def do_fetch(
        payment_payload: Optional[str] = None,
        payment_header_name: Optional[str] = None,
        request_url: Optional[str] = None,
    ) -> Any:
        target_url = request_url or url
        req_headers = dict(headers)
        if payment_payload is not None:
            hname = payment_header_name or "PAYMENT-SIGNATURE"
            req_headers[hname] = payment_payload
        return deps.fetch(target_url, method, req_headers, body, payment_header_name=payment_header_name, payment_payload=payment_payload)

    response = do_fetch(payment_payload=payment)

    status = getattr(response, "status_code", None) or getattr(response, "status", None) or 0

    if status == 402:
        resp_headers = getattr(response, "headers", {})
        if hasattr(resp_headers, "get"):
            def get_header(name: str) -> Optional[str]:
                v = resp_headers.get(name)
                if v is not None:
                    return v
                for k, v in (resp_headers.items() if hasattr(resp_headers, "items") else []):
                    if k.lower() == name.lower():
                        return v
                return None
        else:
            def get_header(name: str) -> Optional[str]:
                return getattr(resp_headers, "get", lambda x: None)(name) or (resp_headers.get(name) if hasattr(resp_headers, "get") else None)

        header_payload = get_header("payment-required") or get_header("PAYMENT-REQUIRED")
        parsed = parse_402_from_header(header_payload)
        accepts: List[X402Accept] = list(parsed.accepts)
        x402_version = parsed.x402Version
        resource = parsed.resource
        error = parsed.error
        response_from_www_authenticate = False

        if not accepts:
            www_auth = get_header("www-authenticate") or get_header("WWW-Authenticate")
            parsed_www = parse_402_from_www_authenticate(www_auth)
            accepts = list(parsed_www.accepts)
            if accepts:
                response_from_www_authenticate = True
            if x402_version is None and parsed_www.x402Version is not None:
                x402_version = parsed_www.x402Version

        if not accepts:
            body_text = getattr(response, "text", None) or (response.content.decode("utf-8") if getattr(response, "content", None) else "")
            parsed_body = parse_402_from_body(body_text)
            accepts = list(parsed_body.accepts)
            if x402_version is None and parsed_body.x402Version is not None:
                x402_version = parsed_body.x402Version
            if resource is None and parsed_body.resource is not None:
                resource = parsed_body.resource
            if error is None and parsed_body.error is not None:
                error = parsed_body.error

        accepts = filter_evm_accepts(accepts)
        single_accept = accepts[0] if len(accepts) == 1 else None

        def pay_fn(accept_arg: Optional[Union[X402Accept, int]] = None) -> Any:
            chosen: Optional[X402Accept] = None
            if accept_arg is None:
                if deps.check_balance:
                    for i, acc in enumerate(accepts):
                        if acc and deps.check_balance(acc):
                            chosen = accepts[i]
                            break
                    if chosen is None:
                        raise ValueError("x402: no accept with sufficient balance")
                if chosen is None:
                    chosen = single_accept or (accepts[0] if accepts else None)
            elif isinstance(accept_arg, int):
                if 0 <= accept_arg < len(accepts):
                    chosen = accepts[accept_arg]
            else:
                chosen = accept_arg
            if not chosen:
                raise ValueError("x402: no payment option selected (empty accepts or invalid index)")
            snap_with_402 = RequestSnapshot(
                url=snapshot.url,
                method=snapshot.method,
                headers=dict(snapshot.headers),
                body=snapshot.body,
                x402Version=x402_version,
                resource=resource,
                error=error,
            )
            payload = deps.build_payment(chosen, snap_with_402)
            payment_header_name = "Authorization" if response_from_www_authenticate else ("X-PAYMENT" if x402_version == 1 else "PAYMENT-SIGNATURE")
            payment_header_value = f"x402 {payload}" if response_from_www_authenticate else payload

            if os.environ.get("X402_DEBUG"):
                print("[X402_DEBUG] accept: network=%r token=%r destination=%r price=%r x402Version=%s" % (
                    getattr(chosen, "network", None), getattr(chosen, "token", None),
                    getattr(chosen, "destination", None), getattr(chosen, "price", None), x402_version))
                print("[X402_DEBUG] payment header name: %s" % (payment_header_name,))
                try:
                    decoded = base64.b64decode(payload).decode("utf-8")
                    obj = json.loads(decoded)
                    print("[X402_DEBUG] payload (decoded JSON):")
                    print(json.dumps(obj, indent=2))
                except Exception as e:
                    print("[X402_DEBUG] payload decode failed: %s" % (e,))

            def try_url(request_url: str, use_auth_header: bool = True) -> Any:
                if response_from_www_authenticate and not use_auth_header:
                    return do_fetch(payment_payload=payload, payment_header_name="PAYMENT-SIGNATURE", request_url=request_url)
                return do_fetch(payment_payload=payment_header_value, payment_header_name=payment_header_name, request_url=request_url)

            retry_response = try_url(snapshot.url)
            retry_status = getattr(retry_response, "status_code", getattr(retry_response, "status", 0))
            if response_from_www_authenticate and retry_status == 402:
                retry_response = try_url(snapshot.url, False)
                retry_status = getattr(retry_response, "status_code", getattr(retry_response, "status", 0))

            if retry_status != 200 and retry_status != 201 and not (200 <= retry_status < 300):
                try:
                    err_body = getattr(retry_response, "text", "") or (retry_response.content.decode("utf-8") if getattr(retry_response, "content", None) else "(failed to read body)")
                except Exception:
                    err_body = "(failed to read body)"
                if os.environ.get("X402_DEBUG"):
                    print("[X402_DEBUG] retry response status: %s" % (retry_status,))
                    print("[X402_DEBUG] retry response body: %s" % (err_body[:2000] if err_body else "(empty)"))
                msg = "x402: payment rejected or insufficient (server returned 402 again)" if retry_status == 402 else f"x402: retry failed with HTTP {retry_status}"
                err = RuntimeError(msg)
                err.status = retry_status  # type: ignore
                err.body = err_body  # type: ignore
                err.url = snapshot.url  # type: ignore
                err.method = snapshot.method  # type: ignore
                raise err

            result = parse_response(retry_response)
            resp_headers_retry = getattr(retry_response, "headers", {})
            pay_resp_header = None
            if hasattr(resp_headers_retry, "get"):
                pay_resp_header = resp_headers_retry.get("payment-response") or resp_headers_retry.get("PAYMENT-RESPONSE")
            if pay_resp_header:
                settlement = parse_402_settlement_from_header(pay_resp_header)
                if settlement and isinstance(result, dict) and not isinstance(result, (list, type(None))):
                    result["x402Settlement"] = settlement
            return result

        pay_first_fn: Optional[Callable[[], Any]] = None
        if deps.check_balance:
            pay_first_fn = lambda: pay_fn()  # pay() with no arg now uses first-with-balance

        x402_payment = X402Payment(
            accepts=accepts,
            pay=pay_fn,
            x402Version=x402_version,
            error=error,
            resource=resource,
            price=single_accept.price if single_accept else None,
            token=single_accept.token if single_accept else None,
            network=single_accept.network if single_accept else None,
            pay_first=pay_first_fn,
        )
        return X402RequiredResponse(x402Required=True, x402Payment=x402_payment)

    if 200 <= status < 300:
        return parse_response(response)

    raise RuntimeError(f"HTTP {status}: {getattr(response, 'reason', getattr(response, 'text', ''))}")
