"""제품표 상세 "관련 문서" 목록 만들기 (change add-product-docs).

LS ELECTRIC 공식 사이트 자료실 API에서 제품 계열별 카탈로그·매뉴얼·시험 성적서·인증서를 골라
src/components/productDocs.json으로 쓴다. 파일은 받지 않고 공식 내려받기 주소만 적는다.
네트워크가 필요하다: python3 scripts/fetch-product-docs.py
"""

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KO = "https://www.ls-electric.com/ko/api/download.ashx"
EN = "https://www.ls-electric.com/api/"
SITE = "https://www.ls-electric.com"
OUT = Path(__file__).resolve().parent.parent / "src" / "components" / "productDocs.json"


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": SITE + "/ko/"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    return json.loads(text) if text.strip() else None


def ko_rows(c_code: str, p_code: str) -> list[dict]:
    rows, page = [], 1
    while page < 20:
        q = dict(t="list_by_product_page", certi_sr="", certi_type="", cur_lang="", d_c_code=c_code, d_dc_id="",
                 d_p_code=p_code, keyword="", page=page, rowsPerPage=100)
        data = (get(KO + "?" + urllib.parse.urlencode(q)) or {}).get("data") or []
        rows += data
        if len(data) < 100:
            break
        page += 1
    return [dict(r, _site="ko") for r in rows if (r["d_p_code"] == p_code if p_code else r["d_c_code"] == c_code)]


def en_rows(c_code: str, p_code: str) -> list[dict]:
    rows, page = [], 1
    while page < 20:
        q = dict(page=page, rows=100, keyword="", d_lang="en", d_dc_id="", d_c_code=c_code, d_p_code=p_code,
                 file_lang="", d_certi_type="", d_certi_sr="")
        data = get(EN + "products/download?" + urllib.parse.urlencode(q)) or []
        rows += data
        if len(data) < 100:
            break
        page += 1
    return [dict(r, _site="en") for r in rows if (r["d_p_code"] == p_code if p_code else r["d_c_code"] == c_code)]


def file_url(row: dict) -> str | None:
    if row["_site"] == "ko":
        files = (get(KO + "?t=file_list&d_id=%d" % row["d_id"]) or {}).get("data") or []
    else:
        files = get(EN + "downloads/files/%d" % row["d_id"]) or []
    return SITE + urllib.parse.quote(files[0]["df_path"]) if files else None


# 계열마다: 자료 출처(사이트, 분류 코드, 제품 코드), 고를 카탈로그·매뉴얼(제목 정규식), 시험 성적서·인증서(제목 정규식)
FAMILIES = {
    "susol-vcb": dict(src=[("ko", "AAA015001", "P01062")], page=SITE + "/ko/product/view/P01062",
                      catalog=r"^\[Susol VCB\]$", manual=r"^\[Susol VCB\] V[LH] Type$",
                      test=r"Susol VCB_TypeTest", cert=r"Susol VCB_(?!TypeTest)"),
    "susol-ul-vcb": dict(src=[("ko", "AAA015001", "P02216"), ("en", "AAA014001", "P01320")], page=SITE + "/ko/product/view/P02216",
                         catalog=r"^UL VCB$", manual=r"UVM_UVH-Type", test=None, cert=r"Susol UL VCB_UL"),
    "uspc-spd": dict(src=[("en", "AAA013005", "")], page="https://www.lselectricamerica.com/product/1670/ul-spd?category=577",
                     catalog=r"^\[SPD\] UL Type Catalog$", manual=r"USPC Series Manual", test=None, cert=r"^SPD_UL_"),
    "gis": dict(src=[("ko", "AAA009004", "")], page=SITE + "/products/category/Smart_Power_Solution/Power_Transmission/GIS",
                catalog=r"^\[GIS\] Total Solution$", manual=None, test=r"^GIS_TypeTest", cert=r"^GIS_공인검수"),
    "gis-170": dict(src=[("ko", "AAA009004", "")], page=SITE + "/products/category/Smart_Power_Solution/Power_Transmission/GIS",
                    catalog=r"^\[GIS\] 170kV$", manual=None, test=r"^GIS_TypeTest", cert=r"^GIS_공인검수"),
    "power-transformer": dict(src=[("ko", "AAA009005", ""), ("en", "AAA008005", "")],
                              page=SITE + "/products/category/Smart_Power_Solution/Power_Transmission/Power_Transformer",
                              catalog=r"^(초고압 변압기|\[Power Transformer\])$", manual=None,
                              test=r"^Power Transformer_TypeTest", cert=r"^Power Transformer_공인검수"),
    "swgr-24kv": dict(src=[("ko", "AAA010001", "P01098"), ("ko", "AAA010001", "")], page=SITE + "/ko/product/view/P01098",
                      catalog=r"^\[GSH-20V\]_국문$", manual=r"^\[배전반\] 설치 및 유지보수 설명서$", test=None, cert=None),
}
KIND = {"catalog": ("Catalog", "카탈로그"), "manual": ("Manual", "사용설명서"), "test": ("Certification", "인증서"),
        "cert": ("Certification", "인증서")}


def main() -> None:
    out = {}
    for key, f in FAMILIES.items():
        rows, seen = [], set()
        for site, cc, pc in f["src"]:
            for r in (ko_rows if site == "ko" else en_rows)(cc, pc):
                if r["d_id"] not in seen:
                    seen.add(r["d_id"])
                    rows.append(r)
        docs = []
        for kind, (en_name, ko_name) in KIND.items():
            pat = f[kind]
            if not pat:
                continue
            for r in rows:
                title = r["d_title"].strip()
                if r["d_dc_name"] in (en_name, ko_name) and re.search(pat, title):
                    url = file_url(r)
                    if url and all(d["url"] != url for d in docs):  # 국문·영문 자료실에 같은 파일이 있으면 한 번만
                        docs.append(dict(kind=kind, title=title, date=r["d_moddate"][:10].replace("/", "-"),
                                         lang=r["d_file_lang_name"], org=r.get("d_certi_orgname"), url=url))
        docs.sort(key=lambda d: d["date"], reverse=True)  # 새 문서 먼저
        docs.sort(key=lambda d: list(KIND).index(d["kind"]))
        out[key] = dict(page=f["page"], docs=docs)
        print(key, {k: sum(d["kind"] == k for d in docs) for k in KIND}, file=sys.stderr)
    OUT.write_text(json.dumps(dict(retrieved="2026-10-31", families=out), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
