from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from urllib.parse import urlparse, parse_qs, unquote
import re

app = FastAPI()

class RequestBody(BaseModel):
    url: str


@app.post("/getIherbItems")
def get_iherb_items(body: RequestBody):
    url = body.url
    if not url:
        raise HTTPException(status_code=400, detail='Missing "url" parameter.')

    try:
        # ===============================
        # STEP 1: GET URL + FOLLOW REDIRECTS
        # ===============================
        get_resp = requests.get(url, allow_redirects=True, timeout=20)

        final_url = get_resp.url if get_resp.url else None
        header_location = (
            get_resp.headers.get("location")
            or get_resp.headers.get("Location")
        )

        location_to_parse = final_url or header_location

        if not location_to_parse:
            # fallback: search in response body
            txt = get_resp.text
            m = re.search(r'https?://[^\s"\'<>]*pcodes=[^"\'<>]*', txt, re.I)
            if m:
                location_to_parse = m.group(0)

        if not location_to_parse:
            return {
                "success": False,
                "message": "no_location_header_or_final_url"
            }

        # ===============================
        # STEP 2: EXTRACT pcodes
        # ===============================
        try:
            location_to_parse = unquote(location_to_parse)
        except Exception:
            pass

        pcodes = None

        try:
            parsed = urlparse(location_to_parse)
            qs = parse_qs(parsed.query)
            pcodes = qs.get("pcodes", [None])[0]
        except Exception:
            pass

        if not pcodes:
            m2 = re.search(r'pcodes=([^&"\'<>#\s]+)', location_to_parse, re.I)
            if m2:
                pcodes = unquote(m2.group(1))

        if not pcodes:
            return {
                "success": False,
                "message": "no_pcodes_param",
                "debug": {
                    "finalUrl": final_url,
                    "headerLocation": header_location
                }
            }

        # ===============================
        # STEP 3: POST TO IHERB API
        # ===============================
        post_url = "https://checkout14-api.iherb.biz/v3/ec/share/showItems"
        headers = {
            "ih-pref": "lc=ar-SA;cc=SAR;ctc=SA;wp=kilograms",
            "Content-Type": "application/json; charset=UTF-8"
        }

        post_resp = requests.post(
            post_url,
            headers=headers,
            json={"data": pcodes},
            timeout=20
        )

        try:
            body_json = post_resp.json()
        except Exception:
            return {
                "success": False,
                "message": "invalid_json_from_post",
                "rawResponse": post_resp.text
            }

        # ===============================
        # STEP 4: FILTER DATA
        # ===============================
        prod_list = (
            body_json.get("cart", {}).get("prodList", [])
            if isinstance(body_json, dict)
            else []
        )

        filtered = []

        for p in prod_list:
            # quantity
            quantity = None
            if p.get("prodQty") is not None:
                q = re.sub(r"\D+", "", str(p["prodQty"]))
                quantity = int(q) if q.isdigit() else p["prodQty"]

            # weight
            weight = None
            if p.get("shipWeightLbs") is not None:
                w = str(p["shipWeightLbs"]).replace(",", "")
                try:
                    weight = float(w)
                except Exception:
                    weight = p["shipWeightLbs"]

            filtered.append({
                "img": p.get("frontImg"),
                "name": p.get("displayName") or p.get("prodName"),
                "sku": p.get("pid"),
                "retailPrice": (
                    p.get("listPriceRawAmount")
                    if p.get("listPriceRawAmount") is not None
                    else p.get("retailPriceRawAmount")
                ),
                "salePrice": p.get("listPricePostDiscountRawAmount"),
                "skucode": p.get("pn"),
                "quantity": quantity,
                "weight": weight
            })

        return {
            "success": True,
            "items": filtered
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
