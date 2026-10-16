"""Lossless, checksummed evidence bundles for large raw provider responses.

The readable JSON retains all derived samples and validation results. Its gzip
companion preserves the exact original evidence bytes, including full histories.
This is packaging only: it never changes a source timestamp or frozen sample.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys


def load_evidence(path):
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    bundle = document.get("raw_evidence_archive")
    if not bundle:
        return document
    archived = (path.parent / bundle["filename"]).read_bytes()
    if hashlib.sha256(archived).hexdigest() != bundle["gzip_sha256"]:
        raise ValueError("raw_evidence_gzip_checksum_mismatch")
    original = gzip.decompress(archived)
    if hashlib.sha256(original).hexdigest() != bundle["original_sha256"]:
        raise ValueError("raw_evidence_original_checksum_mismatch")
    if len(original) != bundle["original_bytes"]:
        raise ValueError("raw_evidence_original_length_mismatch")
    full = json.loads(original)
    for key, value in document.items():
        if key != "raw_evidence_archive" and full.get(key) != value:
            raise ValueError("readable_evidence_differs_from_original:" + key)
    return full


def pack_evidence(path):
    path = Path(path)
    original = path.read_bytes()
    full = json.loads(original)
    if "raw_evidence_archive" in full:
        load_evidence(path)
        return
    archived = gzip.compress(original, compresslevel=9, mtime=0)
    companion = path.with_suffix(path.suffix + ".gz")
    companion.write_bytes(archived)
    bulky = ("raw_daily_histories", "qfq_daily_histories", "minute_price_paths")
    readable = {key: value for key, value in full.items() if key not in bulky}
    readable["raw_evidence_archive"] = {
        "filename": companion.name,
        "format": "gzip_of_exact_original_json_bytes",
        "gzip_sha256": hashlib.sha256(archived).hexdigest(),
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "original_bytes": len(original),
        "preserved_field_counts": {key: len(full[key]) for key in bulky},
        "note": "完整原始JSON无损保留于同目录gzip；此文件保留全部派生样本、验证及来源。解压校验后可复算，不改变冻结时间或原始条件。",
    }
    path.write_text(json.dumps(readable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert load_evidence(path) == full
    print(json.dumps({"readable": str(path), "raw": str(companion),
                      "raw_bytes": len(original), "gzip_bytes": len(archived),
                      "original_sha256": readable["raw_evidence_archive"]["original_sha256"]}))


if __name__ == "__main__":
    pack_evidence(sys.argv[1])
