"""Command line: ibge-nomes basica | decadas | estados | ranking | enrich | probe."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .client import DECADES, IbgeNomes, fold, summarize

try:  # some government servers send incomplete certificate chains; the OS store usually fixes it
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


def enrich(client: IbgeNomes, source: Path, column: str, out: Path) -> None:
    """Add sex and decade columns to a CSV of names. Resumable: names already in `out` are skipped."""
    with open(source, encoding="utf-8", newline="") as f:
        names = list(dict.fromkeys(row[column] for row in csv.DictReader(f) if row.get(column)))
    done = set()
    if out.exists():
        with open(out, encoding="utf-8", newline="") as f:
            done = {row["name"] for row in csv.DictReader(f)}
    todo = [n for n in names if n not in done]
    fields = ["name", "female", "male", "share_female", "peak_decade"] + [f"born_{d}" for d in DECADES]
    new_file = not out.exists()
    with open(out, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            writer.writeheader()
        step = client.batch * 5
        for i in range(0, len(todo), step):
            chunk = todo[i:i + step]
            total = client.by_decade(chunk)
            female = client.by_decade(chunk, sex="F")
            male = client.by_decade(chunk, sex="M")
            for name in chunk:
                key = fold(name)
                writer.writerow({"name": name, **summarize(total.get(key), female.get(key), male.get(key))})
            f.flush()
            print(f"{min(i + step, len(todo)):,}/{len(todo):,} names, {client.calls:,} calls", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ibge-nomes", description="IBGE names API (Censo 2010)")
    ap.add_argument("--cache", type=Path, help="folder that keeps the raw answers (resume and offline rebuilds)")
    ap.add_argument("--wait", type=float, default=0.2, help="seconds between calls (default 0.2)")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("basica", help="rank, frequency, top state, related spellings")
    b.add_argument("name")
    b.add_argument("--sexo", choices=["F", "M"])
    d = sub.add_parser("decadas", help="frequency by decade of birth (several names allowed)")
    d.add_argument("names", nargs="+")
    d.add_argument("--sexo", choices=["F", "M"])
    d.add_argument("--localidade", help="IBGE code of a state or municipality")
    s = sub.add_parser("estados", help="frequency and proportion per state")
    s.add_argument("name")
    r = sub.add_parser("ranking", help="most common names")
    r.add_argument("--decada", type=int)
    r.add_argument("--sexo", choices=["F", "M"])
    r.add_argument("--localidade")
    e = sub.add_parser("enrich", help="add sex and decade columns to a CSV of names (resumable)")
    e.add_argument("csv", type=Path)
    e.add_argument("--column", default="name")
    e.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("probe", help="print the raw answers of every endpoint for one name")
    p.add_argument("name", nargs="?", default="caique")
    args = ap.parse_args(argv)

    client = IbgeNomes(cache=args.cache, wait=args.wait)
    show = lambda value: print(json.dumps(value, ensure_ascii=False, indent=2))  # noqa: E731
    if args.command == "basica":
        show(client.basic(args.name, sex=args.sexo))
    elif args.command == "decadas":
        show(client.by_decade(args.names, sex=args.sexo, locality=args.localidade))
    elif args.command == "estados":
        show(client.by_state(args.name))
    elif args.command == "ranking":
        show(client.ranking(decade=args.decada, sex=args.sexo, locality=args.localidade))
    elif args.command == "enrich":
        enrich(client, args.csv, args.column, args.out)
    elif args.command == "probe":
        name = fold(args.name).lower()
        for label, path, params in [
            ("v1 basica", "/v1/censos/nomes/basica", {"nome": name}),
            ("v1 basica sexo=F", "/v1/censos/nomes/basica", {"nome": name, "sexo": "F"}),
            ("v2 decadas", f"/v2/censos/nomes/{name}", {}),
            ("v2 decadas sexo=F", f"/v2/censos/nomes/{name}", {"sexo": "F"}),
            ("v2 dois nomes", f"/v2/censos/nomes/{name}|maria", {}),
            ("v2 groupBy=UF", f"/v2/censos/nomes/{name}", {"groupBy": "UF"}),
            ("v2 ranking 1990", "/v2/censos/nomes/ranking", {"decada": 1990}),
        ]:
            try:
                text = client.get_text(path, params)
            except Exception as error:  # noqa: BLE001 - probe reports everything
                text = f"ERRO: {error}"
            print(f"## {label}\n{text[:800]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
