from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from urllib.parse import urlparse, parse_qs, unquote
import re

app = FastAPI()

# ===============================
# CORS CONFIG (الحل الحقيقي)
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lavendersales.flutterflow.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestBody(BaseModel):
    url: str

@app.post("/getIherbItems")
def get_iherb_items(body: RequestBody):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail='Missing "url" parameter.')

    try:
        # STEP 1
        get_resp = requests.get(url, allow_redirects=True, timeout=20)

        final_url = get_resp.url
        header_location = get_resp.headers.get("location") or get_resp.headers.get("Location")
        location_to_parse = final_url or header_location

        if not location_to_parse:
            m = re.search(r'https?://[^\s"\'<>]*pcodes=[^"\'<>]*', get_resp.text, re.I)
            if m:
                location_to_parse = m.group(0)

        if not location_to_parse:
            return {"success": False, "message": "no_location_header_or_final_url"}

        try:
            location_to_parse = unquote(location_to_parse)
        except:
            pass

        pcodes = None
        parsed = urlparse(location_to_parse)
        qs = parse_qs(parsed.query)
        pcodes = qs.get("pcodes", [None])[0]

        if not pcodes:
            m2 = re.search(r'pcodes=([^&"\'<>#\s]+)', location_to_parse, re.I)
            if m2:
                pcodes = unquote(m2.group(1))

        if not pcodes:
            return {
                "success": False,
                "message": "no_pcodes_param",
                "debug": {"finalUrl": final_url, "headerLocation": header_location}
            }

        # STEP 3
        post_resp = requests.post(
            "https://checkout14-api.iherb.biz/v3/ec/share/showItems",
            headers={
                "ih-pref": "lc=ar-SA;cc=SAR;ctc=SA;wp=kilograms",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"data": pcodes},
            timeout=20
        )

        body_json = post_resp.json()
        prod_list = body_json.get("cart", {}).get("prodList", [])

        items = []
        for p in prod_list:
            items.append({
                "img": p.get("frontImg"),
                "name": p.get("displayName") or p.get("prodName"),
                "sku": p.get("pid"),
                "retailPrice": p.get("listPriceRawAmount") or p.get("retailPriceRawAmount"),
                "salePrice": p.get("listPricePostDiscountRawAmount"),
                "skucode": p.get("pn"),
                "quantity": int(re.sub(r"\D+", "", str(p.get("prodQty")))) if p.get("prodQty") else None,
                "weight": float(str(p.get("shipWeightLbs")).replace(",", "")) if p.get("shipWeightLbs") else None
            })

        return {"success": True, "items": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
