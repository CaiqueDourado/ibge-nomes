"""Client for IBGE's names API (Censo 2010), standard library only.

Endpoints (https://servicodados.ibge.gov.br/api/docs/nomes):

    v1 /censos/nomes/basica?nome=X[&sexo=F|M][&regiao=<UF code>]
        rank, frequency, percentage, state where the name is most common, related spellings
    v2 /censos/nomes/<n1|n2|...>[?sexo=F|M][&localidade=<code>]
        frequency by decade of birth, for one or more names in one call
    v2 /censos/nomes/<nome>?groupBy=UF
        frequency and share per state
    v2 /censos/nomes/ranking[?decada=1990][&sexo=F|M][&localidade=<code>]
        the most common names

Every answer is JSON. The client keeps the raw text of each answer (optionally in a cache folder),
retries on network errors, waits between calls, and splits a batch when the server refuses it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

BASE = "https://servicodados.ibge.gov.br/api"
AGENT = "ibge-nomes (+https://github.com/CaiqueDourado/ibge-nomes)"
# Decades as the API labels them, in order, and the short names used in tables.
DECADES = ["before_1930", "1930s", "1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s"]


def fold(name: str) -> str:
    """Upper case without accents, as the API writes names: "Maria Júlia" -> "MARIA JULIA"."""
    text = unicodedata.normalize("NFD", name.strip())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").upper()


def decade_label(period: str) -> str | None:
    """Map the API's period ("1930[", "[1930,1940[") to "before_1930", "1930s"..."""
    years = [int(y) for y in re.findall(r"\d{4}", period or "")]
    if not years:
        return None
    if len(years) == 1:
        return "before_1930" if years[0] <= 1930 else f"{years[0]}s"
    return f"{years[0]}s"


def is_json(text: str) -> bool:
    if not text.strip():
        return True
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


class ApiError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str):
        super().__init__(f"{status or 'network'} on {url}: {message}")
        self.url, self.status = url, status


Transport = Callable[[str], tuple[int, bytes]]


def urllib_transport(timeout: float = 60) -> Transport:
    def get(url: str) -> tuple[int, bytes]:
        request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            return error.code, error.read() or b""
        return status, gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
    return get


@dataclass
class IbgeNomes:
    """Small client. `transport` can be replaced in tests; `cache` keeps raw answers on disk."""

    cache: Path | None = None
    wait: float = 0.2          # seconds between calls
    retries: int = 4
    batch: int = 20            # names per v2 call
    transport: Transport = field(default_factory=urllib_transport)
    calls: int = 0
    skipped: list = field(default_factory=list)
    _last: float = 0.0

    # ---- raw access -------------------------------------------------------------------------
    def get_text(self, path: str, params: dict | None = None) -> str:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
        url = f"{BASE}{path}" + (f"?{query}" if query else "")
        cached = self._cache_file(url)
        if cached and cached.exists():
            text = cached.read_text(encoding="utf-8")
            if is_json(text):
                return text
            cached.unlink()  # a bad answer cached by an older version: ask again
        for attempt in range(1, self.retries + 1):
            pause = self.wait - (time.monotonic() - self._last)
            if pause > 0:
                time.sleep(pause)
            self._last = time.monotonic()
            self.calls += 1
            try:
                status, body = self.transport(url)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
                if attempt == self.retries:
                    raise ApiError(url, None, str(error)) from error
                time.sleep(2 ** attempt)
                continue
            if status == 200:
                text = body.decode("utf-8", "replace")
                if not is_json(text):  # the server sometimes answers 200 with an HTML error page
                    if attempt < self.retries:
                        time.sleep(2 ** attempt)
                        continue
                    raise ApiError(url, 502, "answer is not JSON: " + text[:120])
                if cached:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(text, encoding="utf-8")
                return text
            if status in (429, 500, 502, 503, 504) and attempt < self.retries:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(url, status, body[:200].decode("utf-8", "replace"))
        raise ApiError(url, None, "no answer")

    def get_json(self, path: str, params: dict | None = None):
        text = self.get_text(path, params)
        return json.loads(text) if text.strip() else []

    def _cache_file(self, url: str) -> Path | None:
        if not self.cache:
            return None
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return Path(self.cache) / key[:2] / f"{key}.json"

    # ---- endpoints --------------------------------------------------------------------------
    def basic(self, name: str, sex: str | None = None, region: str | int | None = None) -> dict | None:
        """v1 basica: rank, freq, percentual, ufMax, ufMaxProp, nomes. None when IBGE has no data."""
        answer = self.get_json("/v1/censos/nomes/basica", {"nome": fold(name).lower(), "sexo": sex, "regiao": region})
        return answer[0] if answer else None

    def by_decade(self, names: Iterable[str], sex: str | None = None, locality: str | int | None = None) -> dict[str, dict[str, int]]:
        """v2 frequency by decade of birth: {"MARIA": {"before_1930": 336477, "1930s": 749053, ...}}.
        Names IBGE does not know are missing from the result. Batches of `self.batch` names per call;
        a batch the server refuses is retried one name at a time."""
        wanted = list(dict.fromkeys(fold(n) for n in names if n and n.strip()))
        result: dict[str, dict[str, int]] = {}
        for i in range(0, len(wanted), self.batch):
            chunk = wanted[i:i + self.batch]
            try:
                result.update(self._by_decade_call(chunk, sex, locality))
                continue
            except ApiError as error:
                if error.status not in (400, 404, 414, 500, 502):
                    raise
            for one in chunk:  # the server refused the batch: one name at a time, skip names it rejects
                try:
                    result.update(self._by_decade_call([one], sex, locality))
                except ApiError as error:
                    if error.status not in (400, 404, 500, 502):
                        raise
                    self.skipped.append(one)
                    print(f"skipped {one}: {error}", file=sys.stderr)
        return result

    def _by_decade_call(self, chunk: list[str], sex, locality) -> dict[str, dict[str, int]]:
        path = "/v2/censos/nomes/" + urllib.parse.quote("|".join(n.lower() for n in chunk), safe="|")
        out = {}
        for item in self.get_json(path, {"sexo": sex, "localidade": locality}):
            counts = {}
            for row in item.get("res") or []:
                label = decade_label(str(row.get("periodo", "")))
                if label:
                    counts[label] = counts.get(label, 0) + int(row.get("frequencia") or 0)
            if counts:
                out[fold(str(item.get("nome", "")))] = counts
        return out

    def by_state(self, name: str, sex: str | None = None) -> list[dict]:
        """v2 groupBy=UF: one row per state with frequency, population and proportion (per 100,000)."""
        path = "/v2/censos/nomes/" + urllib.parse.quote(fold(name).lower())
        answer = self.get_json(path, {"groupBy": "UF", "sexo": sex})
        rows = []
        for item in answer:
            for row in item.get("res") or []:
                rows.append({"state_code": str(item.get("localidade", row.get("localidade", ""))), **row})
        return rows

    def ranking(self, decade: int | None = None, sex: str | None = None, locality: str | int | None = None) -> list[dict]:
        """v2 ranking: [{"nome": "MARIA", "frequencia": ..., "ranking": 1}, ...].
        Note: `decada=1990` means people born in [1980, 1990[ (the year the decade ends)."""
        answer = self.get_json("/v2/censos/nomes/ranking", {"decada": decade, "sexo": sex, "localidade": locality})
        return answer[0].get("res", []) if answer else []


def summarize(total: dict[str, int] | None, female: dict[str, int] | None, male: dict[str, int] | None) -> dict:
    """Turn three by_decade answers for one name into flat columns."""
    total, female, male = total or {}, female or {}, male or {}
    f, m = sum(female.values()), sum(male.values())
    row = {
        "female": f or None,
        "male": m or None,
        "share_female": round(f / (f + m), 4) if f + m else None,
        "peak_decade": max(total, key=total.get) if total else None,
    }
    for decade in DECADES:
        row[f"born_{decade}"] = total.get(decade)
    return row
