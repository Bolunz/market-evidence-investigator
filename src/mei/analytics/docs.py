"""Product-document retrieval. Returns text so the agent can judge positioning itself;
the tool makes no judgement about whether a product 'addresses' a need."""
from __future__ import annotations

import re

from ..adapters.base import CAP_PRODUCT_DOCS


def _sentence_with(text: str, term: str) -> str:
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if term.lower() in sent.lower():
            return sent
    return text[:160]


def search_product_docs(md, terms: list[str], segment: str | None = None, max_results: int = 25) -> dict:
    md.require(CAP_PRODUCT_DOCS)
    docs = md.product_docs.merge(md.products[["product_id", "model", "oem", "segment"]], on="product_id")
    if segment:
        docs = docs[docs["segment"] == segment]
    hits = []
    for _, d in docs.iterrows():
        matched = [t for t in terms if t.lower() in d["text"].lower()]
        if matched:
            hits.append({"doc_id": d["doc_id"], "product_id": d["product_id"], "model": d["model"],
                         "segment": d["segment"], "doc_type": d["doc_type"],
                         "published_month": d["published_month"], "matched_terms": matched,
                         "snippet": _sentence_with(d["text"], matched[0])})
    # announcements first, then by number of matched terms
    hits.sort(key=lambda h: (h["doc_type"] != "announcement", -len(h["matched_terms"]), h["doc_id"]))
    total = len(hits)
    hits = hits[:max_results]
    return {"evidence_type": "product_doc_search",
            "values": {"terms": ",".join(terms), "segment": segment or "ALL", "n_hits": total,
                       "n_returned": len(hits)},
            "detail": {"hits": hits},
            "summary": f"{total} documents match {terms} (segment={segment or 'ALL'}); returned {len(hits)}."}


def get_product_doc(md, doc_id: str) -> dict:
    md.require(CAP_PRODUCT_DOCS)
    d = md.product_docs[md.product_docs["doc_id"] == doc_id]
    if d.empty:
        return {"evidence_type": "product_doc", "values": {"doc_id": doc_id, "status": "not_found"},
                "summary": f"{doc_id}: not found."}
    r = d.iloc[0]
    p = md.products.set_index("product_id").loc[r["product_id"]]
    return {"evidence_type": "product_doc",
            "values": {"doc_id": doc_id, "product_id": r["product_id"], "model": p["model"],
                       "segment": p["segment"], "doc_type": r["doc_type"], "published_month": r["published_month"]},
            "detail": {"text": r["text"]},
            "summary": f"{doc_id} ({r['doc_type']}, {r['published_month']}) for {p['model']}: {r['text']}"}


def product_info(md, product_id: str) -> dict:
    p = md.products.set_index("product_id")
    if product_id not in p.index:
        return {"evidence_type": "product_info", "values": {"product_id": product_id, "status": "not_found"},
                "summary": f"{product_id}: not found."}
    r = p.loc[product_id]
    values = {"product_id": product_id, "oem": r["oem"], "model": r["model"], "segment": r["segment"],
              "screen_size": r["screen_size"]}
    if md.sellout is not None:
        s = md.sellout[md.sellout["product_id"] == product_id]
        if not s.empty:
            bt = s.loc[s["battery_run_time"] != "N/A", "battery_run_time"]
            values["battery_run_time_mode"] = bt.mode().iloc[0] if not bt.empty else "N/A"
            values["total_units"] = int(s["units"].sum())
    return {"evidence_type": "product_info", "values": values,
            "summary": f"{product_id}: {values['model']} ({values['segment']})."}
