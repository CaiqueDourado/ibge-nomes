import json
import urllib.parse

import pytest

from ibge_nomes import DECADES, ApiError, IbgeNomes, decade_label, fold, summarize
from ibge_nomes.cli import enrich

BASICA = [{"rank": 529, "nome": "CAIQUE", "freq": 50902, "percentual": 0.0278, "ufMax": "Bahia",
           "ufMaxProp": "68.3960", "regiao": 0, "sexo": "", "nomes": "CAYQUE,KAIQUE,KAYQUE"}]


def series(name, sex=None, scale=1):
    periods = ["1930[", "[1930,1940[", "[1940,1950[", "[1950,1960[", "[1960,1970[",
               "[1970,1980[", "[1980,1990[", "[1990,2000[", "[2000,2010["]
    return {"nome": name, "sexo": sex, "localidade": "BR",
            "res": [{"periodo": p, "frequencia": (i + 1) * scale} for i, p in enumerate(periods)]}


class Fake:
    """Answers like the API; records the URLs it was asked for."""

    def __init__(self, refuse_batches=False, unknown=()):
        self.urls, self.refuse_batches, self.unknown = [], refuse_batches, set(unknown)

    def __call__(self, url):
        self.urls.append(url)
        parsed = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        if parsed.path.endswith("/basica"):
            return 200, json.dumps(BASICA if query["nome"] == "caique" else []).encode()
        if parsed.path.endswith("/ranking"):
            return 200, json.dumps([{"localidade": "BR", "res": [{"nome": "MARIA", "frequencia": 1, "ranking": 1}]}]).encode()
        names = urllib.parse.unquote(parsed.path.rsplit("/", 1)[1]).split("|")
        if self.refuse_batches and len(names) > 1:
            return 500, b"error"
        if len(names) == 1 and names[0].upper() in self.unknown:
            return 404, b"[]"
        sex = query.get("sexo")
        scale = {"F": 3, "M": 1}.get(sex, 4)
        return 200, json.dumps([series(n.upper(), sex, scale) for n in names if n.upper() not in self.unknown]).encode()


def client(fake):
    return IbgeNomes(wait=0, retries=1, batch=2, transport=fake)


def test_fold():
    assert fold(" Maria Júlia ") == "MARIA JULIA"
    assert fold("João") == "JOAO"


@pytest.mark.parametrize("period,label", [("1930[", "before_1930"), ("[1930,1940[", "1930s"), ("[2000,2010[", "2000s"), ("", None)])
def test_decade_label(period, label):
    assert decade_label(period) == label


def test_basic():
    c = client(Fake())
    assert c.basic("Caique")["freq"] == 50902
    assert c.basic("Xyzw") is None


def test_by_decade_batches_and_folds():
    fake = Fake()
    out = client(fake).by_decade(["Maria", "João", "Ana", "maria"])
    assert set(out) == {"MARIA", "JOAO", "ANA"}
    assert out["MARIA"]["before_1930"] == 4 and out["MARIA"]["2000s"] == 36
    assert len(fake.urls) == 2  # batch of 2 + batch of 1
    assert "maria|joao" in urllib.parse.unquote(fake.urls[0])


def test_refused_batch_goes_one_by_one_and_skips_unknown():
    fake = Fake(refuse_batches=True, unknown={"ZZZ"})
    out = client(fake).by_decade(["Maria", "Zzz"])
    assert set(out) == {"MARIA"}


def test_error_is_raised():
    c = IbgeNomes(wait=0, retries=1, transport=lambda url: (403, b"forbidden"))
    with pytest.raises(ApiError):
        c.basic("Maria")


def test_cache(tmp_path):
    fake = Fake()
    c = IbgeNomes(wait=0, retries=1, transport=fake, cache=tmp_path)
    c.basic("Caique")
    c.basic("Caique")
    assert len(fake.urls) == 1


def test_summarize():
    row = summarize({"1990s": 10, "2000s": 30}, {"1990s": 3, "2000s": 27}, {"1990s": 7, "2000s": 3})
    assert row["female"] == 30 and row["male"] == 10 and row["share_female"] == 0.75
    assert row["peak_decade"] == "2000s" and row["born_1950s"] is None
    assert set(row) == {"female", "male", "share_female", "peak_decade", *[f"born_{d}" for d in DECADES]}
    assert summarize(None, None, None)["share_female"] is None


def test_ranking():
    assert client(Fake()).ranking(decade=1990)[0]["nome"] == "MARIA"


def test_enrich_resumes(tmp_path):
    src = tmp_path / "names.csv"
    src.write_text("name\nMaria\nJoão\nAna\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    fake = Fake()
    enrich(client(fake), src, "name", out)
    calls = len(fake.urls)
    enrich(client(fake), src, "name", out)
    assert len(fake.urls) == calls
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and lines[0].startswith("name,female,male,share_female")
    assert "0.75" in lines[1]
