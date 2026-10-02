#!/usr/bin/env python3
"""Beyond Publishing 0.1: local, deterministic helpers; no network or AI calls.

These helpers validate supplied records. They do not independently verify a
source, prove legal clearance, estimate competitor sales, or publish books.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

VERSION = "0.4.0"
SYNTHETIC_WARNING = "SYNTHETIC TEST ONLY — not market evidence; excluded from real recommendations."
INTEGRATIONS = ('research.search', 'research.capture_book', 'evidence.verify_claim', 'rules.refresh',
                'book.plan', 'book.draft', 'book.revise', 'book.review', 'art.generate', 'cover.compose',
                'edition.export', 'edition.validate', 'publishing.prepare', 'publishing.submit',
                'sales.import', 'sales.analyze', 'mcp.server')
FORMATS = {"ebook", "paperback", "hardcover", "audiobook"}
EVIDENCE_BASES = {"user_supplied", "authorized_browser", "licensed_feed", "official_docs", "fixture"}
REQUIRED_CHECKS = (
    "format_validation", "visual_review", "metadata_consistency", "source_review",
    "rights_review", "ai_disclosure_review", "channel_eligibility",
    "distribution_conflicts", "policy_freshness",
)


class CoreError(ValueError):
    """A validation failure safe to display to the caller."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def text(value: Any, field: str, max_length: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise CoreError(f"{field} must be a nonempty string of at most {max_length} characters")
    if "\x00" in value:
        raise CoreError(f"{field} contains a null character")
    return value.strip()


def number(value: Any, field: str, *, nonnegative: bool = True) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise CoreError(f"{field} must be an integer or decimal string, not a float")
    raw = str(value)
    if len(raw) > 80 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", raw):
        raise CoreError(f"{field} must be a plain, finite decimal")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise CoreError(f"Invalid {field}") from exc
    if not result.is_finite() or (nonnegative and result < 0):
        raise CoreError(f"{field} must be finite" + (" and nonnegative" if nonnegative else ""))
    if abs(result) > Decimal("1000000000000") or result.as_tuple().exponent < -8:
        raise CoreError(f"{field} exceeds supported magnitude or precision")
    return result


def currency_code(value: Any) -> str:
    value = text(value, "currency", 3)
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise CoreError("currency must be three uppercase letters; this is a syntax check, not an ISO registry check")
    return value


def timestamp(value: Any, field: str) -> datetime:
    value = text(value, field, 80)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CoreError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CoreError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def positive_hours(value: Any) -> Decimal:
    result = number(value, "max_age_hours")
    if result <= 0:
        raise CoreError("max_age_hours must be positive")
    return result


def age_status(observed_at: str, max_age_hours: Any, as_of: datetime | None = None) -> dict[str, Any]:
    observed = timestamp(observed_at, "observed_at")
    current = as_of or now_utc()
    if current.tzinfo is None:
        raise CoreError("as_of must include a timezone")
    age_seconds = (current - observed).total_seconds()
    if age_seconds < 0:
        raise CoreError("observed_at is in the future relative to as_of")
    limit = positive_hours(max_age_hours)
    return {"status": "fresh" if age_seconds <= float(limit * 3600) else "stale",
            "age_hours": round(age_seconds / 3600, 6), "max_age_hours": str(limit)}


def validate_evidence(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise CoreError("evidence must be an object")
    result = dict(record)
    for key in ("evidence_id", "source_url", "title", "captured_at", "access_basis", "permission_reference", "excerpt"):
        result[key] = text(record.get(key), key, 12000 if key == "excerpt" else 4000)
    if result["access_basis"] not in EVIDENCE_BASES:
        raise CoreError("unsupported access_basis")
    parts = urlsplit(result["source_url"])
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
        raise CoreError("source_url must be an HTTP(S) URL without embedded credentials")
    if any(c.isspace() for c in result["source_url"]):
        raise CoreError("source_url must not contain whitespace")
    timestamp(result["captured_at"], "captured_at")
    # Permission references are declarations; this helper cannot establish access rights.
    result["capture_sha256"] = hashlib.sha256(result["excerpt"].encode("utf-8")).hexdigest()
    result["verification"] = "record_shape_checked_source_not_independently_verified"
    result["synthetic"] = is_synthetic(record)
    result["warnings"] = [SYNTHETIC_WARNING] if result["synthetic"] else []
    return result


def is_synthetic(record: dict[str, Any]) -> bool:
    return (record.get("synthetic") is True or record.get("access_basis") == "fixture"
            or bool(record.get("fixture_warning")))


def validate_bsr(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise CoreError("BSR observation must be an object")
    result = dict(record)
    for key in ("observation_id", "product_id", "marketplace", "store", "format", "rank_scope", "ranking_list", "observed_at", "evidence_id"):
        result[key] = text(record.get(key), key)
    if result["format"] not in FORMATS:
        raise CoreError("unsupported format")
    if result["rank_scope"] not in {"store", "category"}:
        raise CoreError("rank_scope must be store or category")
    if result["ranking_list"] not in {"paid", "free"}:
        raise CoreError("ranking_list must be paid or free")
    if not isinstance(record.get("edition_verified"), bool):
        raise CoreError("edition_verified must be true or false")
    if result["rank_scope"] == "category":
        result["category"] = text(record.get("category"), "category")
    elif record.get("category") is not None:
        raise CoreError("store-level observation must have category null or absent")
    rank = record.get("rank")
    if rank is None:
        result["missing_reason"] = text(record.get("missing_reason"), "missing_reason")
    elif type(rank) is not int or rank < 1:
        raise CoreError("rank must be a positive integer, or null with missing_reason")
    result["rank"] = rank
    timestamp(result["observed_at"], "observed_at")
    if record.get("price") is not None:
        result["price"] = str(number(record["price"], "price"))
        result["currency"] = currency_code(record.get("currency"))
    if any(key in record for key in ("estimated_sales", "estimated_royalties", "guaranteed_income")):
        raise CoreError("sales and royalty estimates do not belong in an observed BSR record")
    result["synthetic"] = is_synthetic(record)
    result["warnings"] = [SYNTHETIC_WARNING] if result["synthetic"] else []
    return result


def compare_bsr(left: Any, right: Any, max_age_hours: Any, as_of: datetime | None = None) -> dict[str, Any]:
    a, b = validate_bsr(left), validate_bsr(right)
    issues: list[str] = []
    if a["synthetic"] != b["synthetic"]:
        issues.append("different_evidence_mode")
    keys = ("marketplace", "store", "format", "rank_scope", "ranking_list", "category")
    for key in keys:
        if a.get(key) != b.get(key):
            issues.append(f"different_{key}")
    for name, record in (("left", a), ("right", b)):
        if record["rank"] is None:
            issues.append(f"{name}_rank_missing")
        if not record["edition_verified"]:
            issues.append(f"{name}_edition_unverified")
        if age_status(record["observed_at"], max_age_hours, as_of)["status"] == "stale":
            issues.append(f"{name}_observation_stale")
    return {
        "status": "not_comparable" if issues else "comparable_snapshots_only",
        "issues": issues,
        "left_rank": a["rank"], "right_rank": b["rank"],
        "evidence_ids": [a["evidence_id"], b["evidence_id"]],
        "sales_estimate": None,
        "synthetic": a["synthetic"] or b["synthetic"],
        "warnings": [SYNTHETIC_WARNING] if a["synthetic"] or b["synthetic"] else [],
        "limitation": "Relative snapshots, not sales, earnings, or a forecast. Record authenticity is not independently verified.",
    }


def economics(*, receipts_per_copy: Any, variable_cost_per_copy: Any, fixed_cost: Any,
              currency: str, assumptions: str) -> dict[str, Any]:
    """Use author receipts/royalties, not the retail list price.

Do not subtract printing/retailer fees twice if receipts are already net of them.
All inputs must be in the same stated currency; no FX is inferred.
"""
    receipts = number(receipts_per_copy, "receipts_per_copy")
    variable = number(variable_cost_per_copy, "variable_cost_per_copy")
    fixed = number(fixed_cost, "fixed_cost")
    code = currency_code(currency)
    assumptions = text(assumptions, "assumptions")
    with localcontext() as ctx:
        ctx.prec = 50
        contribution = receipts - variable
        copies = int((fixed / contribution).to_integral_value(rounding=ROUND_CEILING)) if contribution > 0 else None
    return {"currency": code, "contribution_per_copy": str(contribution), "break_even_copies": copies,
            "status": "scenario_only" if contribution > 0 else "nonpositive_contribution",
            "assumptions": assumptions,
            "limitation": "No demand forecast. Taxes, returns, advertising and fees must be explicitly included where applicable."}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preflight(payload: Any) -> dict[str, Any]:
    """Aggregate supplied reports; never claim to have performed their checks."""
    if not isinstance(payload, dict) or not isinstance(payload.get("checks"), list):
        raise CoreError("preflight input must include a checks array")
    expected = text(payload.get("artifact_sha256"), "artifact_sha256", 64)
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise CoreError("artifact_sha256 must be a lowercase SHA-256 hash")
    by_name: dict[str, dict[str, Any]] = {}
    for item in payload["checks"]:
        if not isinstance(item, dict):
            raise CoreError("each check must be an object")
        name = text(item.get("check"), "check")
        if name not in REQUIRED_CHECKS or name in by_name:
            raise CoreError("unknown or duplicate check")
        state = item.get("status")
        if state not in {"pass", "fail", "needs_review", "not_run"}:
            raise CoreError("invalid check status")
        normalized = dict(item)
        if state == "pass":
            text(item.get("report_ref"), "report_ref")
            timestamp(item.get("checked_at"), "checked_at")
            if item.get("artifact_sha256") != expected:
                normalized["status"] = "needs_review"
                normalized["reason"] = "artifact_changed_or_hash_missing"
        by_name[name] = normalized
    blockers = []
    for name in REQUIRED_CHECKS:
        row = by_name.get(name, {"check": name, "status": "not_run"})
        if row["status"] != "pass":
            blockers.append(row)
    return {"status": "not_clear_to_submit" if blockers else "ready_for_human_review",
            "blockers": blockers,
            "checked_against_artifact_sha256": expected,
            "publication_authorized": False,
            "limitation": "Aggregates supplied reports only. Does not verify their authenticity, perform the reviews, or authorize publication."}


def action_policy(action: str) -> dict[str, str]:
    rules = {
        "read_public": ("allowed_in_permitted_scope", "Verify source access and retrieval policy."),
        "edit_local": ("allowed_in_project_scope", "Preserve approved versions and enforce filesystem scope."),
        "upload_manuscript": ("requires_human_confirmation", "Confirm exact files, destination and sharing before upload."),
        "publish": ("requires_human_confirmation", "Final publication requires fresh, artifact-bound approval."),
        "spend": ("requires_human_confirmation", "Confirm price, currency, payee and budget."),
        "enter_identity": ("manual_only", "Account owner supplies identity information directly."),
        "enter_tax": ("manual_only", "Account owner completes and attests tax declarations."),
        "enter_bank": ("manual_only", "Account owner enters banking information directly."),
        "captcha": ("manual_only", "Stop for user handoff; no bypass."),
        "bypass_access_control": ("denied", "Do not bypass access controls or automation restrictions."),
    }
    if action not in rules:
        return {"decision": "denied", "reason": "Unknown actions are denied by default."}
    decision, reason = rules[action]
    return {"decision": decision, "reason": reason}


def scoped_path(workspace: Path) -> Path:
    candidate = workspace.absolute()
    if '..' in candidate.parts:
        raise CoreError("parent traversal is not supported in workspace paths")
    for part in (candidate, *candidate.parents):
        # macOS system aliases are not user-controlled project aliases.
        if sys.platform == 'darwin' and str(part) in {'/var', '/tmp'} and part.resolve() == Path('/private') / part.name:
            continue
        if part.is_symlink():
            raise CoreError("workspace paths must not contain symlinks")
    return candidate.resolve()


def connect(workspace: Path) -> sqlite3.Connection:
    db = scoped_path(workspace) / "evidence.sqlite3"
    if not db.is_file() or db.is_symlink():
        raise CoreError("Initialize the selected workspace first; symlinked databases are not supported")
    connection = sqlite3.connect(f"{db.as_uri()}?mode=rw", uri=True, timeout=10)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_project(workspace: Path, title: str, country: str, language: str, budget: Any, currency: str) -> dict[str, Any]:
    metadata = {"schema_version": 1, "project_id": str(uuid4()), "title": text(title, "title"),
                "country": text(country, "country"), "language": text(language, "language"),
                "budget": str(number(budget, "budget")), "currency": currency_code(currency),
                "stage": "intake", "created_at": iso_now(), "policy_status": "unverified"}
    if workspace.is_symlink():
        raise CoreError("workspace must not be a symlink")
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise CoreError("workspace must be a new or empty directory; nothing was overwritten")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("research", "brief", "manuscript", "assets", "reviews", "exports", "publishing", "marketing"):
        (workspace / name).mkdir(mode=0o700)
    (workspace / "project.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    db = workspace / "evidence.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE evidence (id TEXT PRIMARY KEY, payload TEXT NOT NULL, added_at TEXT NOT NULL);
        CREATE TABLE observations (id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(id),
                                   payload TEXT NOT NULL, added_at TEXT NOT NULL);
        """)
    if os.name != "nt":
        db.chmod(0o600)
        (workspace / "project.json").chmod(0o600)
    return {"workspace": str(workspace.resolve()), "project": metadata}


def add_record(workspace: Path, kind: str, record: Any) -> dict[str, Any]:
    if kind == "evidence":
        value = validate_evidence(record)
        sql = "INSERT INTO evidence(id,payload,added_at) VALUES (?,?,?)"
        params = (value["evidence_id"], json.dumps(value, ensure_ascii=False), iso_now())
    elif kind == "bsr":
        value = validate_bsr(record)
        sql = "INSERT INTO observations(id,evidence_id,payload,added_at) VALUES (?,?,?,?)"
        params = (value["observation_id"], value["evidence_id"], json.dumps(value, ensure_ascii=False), iso_now())
    else:
        raise CoreError("unsupported record kind")
    conn = connect(workspace)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_revisions'").fetchone():
                raise CoreError("Versioned project: use the project API with project ID and expected revision")
            if kind == 'bsr':
                source = conn.execute('SELECT payload FROM evidence WHERE id=?', (value['evidence_id'],)).fetchone()
                if source and is_synthetic(json.loads(source[0])):
                    value['synthetic'] = True
                    value['warnings'] = [SYNTHETIC_WARNING]
                    params = (value['observation_id'], value['evidence_id'], json.dumps(value, ensure_ascii=False), iso_now())
            conn.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        raise CoreError("Duplicate record ID or missing referenced evidence; existing records were not changed") from exc
    finally:
        conn.close()
    return {"status": "stored_record", "record": value}


def list_records(workspace: Path) -> dict[str, Any]:
    conn = connect(workspace)
    try:
        return {"evidence": [json.loads(row[0]) for row in conn.execute("SELECT payload FROM evidence ORDER BY rowid")],
                "bsr_observations": [json.loads(row[0]) for row in conn.execute("SELECT payload FROM observations ORDER BY rowid")]}
    finally:
        conn.close()


def capabilities() -> dict[str, Any]:
    runtime = {'project.local': {'installed': True, 'configured': True, 'reachable': True,
                                'authorized': None, 'status': 'OK',
                                'authorization_scope': 'selected local project; ID/revision checked per operation'}}
    for name in INTEGRATIONS:
        runtime[name] = {'installed': False, 'configured': False, 'reachable': False,
                         'authorized': False, 'status': 'UNAVAILABLE', 'reason': 'Legacy proposed interface is not callable; use the explicit Beyondwords connect adapter where supported'}
    runtime['research.local'] = {'installed': True, 'configured': True, 'reachable': True, 'authorized': None, 'status': 'OK', 'reason': 'BP-002 CLI/API; source permissions checked per action'}
    runtime['book.local'] = {'installed': True, 'configured': True, 'reachable': True, 'authorized': None, 'status': 'OK', 'reason': 'Versioned plans, supplied drafts, claims, reviews, reports and owner packages; host supplies AI drafting'}
    runtime['browser.read_only'] = {'installed': importlib.util.find_spec('playwright') is not None, 'configured': None, 'reachable': None, 'authorized': None, 'status': 'UNVERIFIED', 'reason': 'Run publishing_browser.doctor for browser installation; source authorization remains separate'}
    runtime['connect.amazon_ads'] = {'installed': True, 'configured': None, 'reachable': None, 'authorized': None, 'status': 'UNVERIFIED', 'reason': 'Actual connect adapter; inspect configuration then authenticate/select profile before account actions'}
    runtime['connect.kdp_attended'] = {'installed': importlib.util.find_spec('playwright') is not None, 'configured': None, 'reachable': None, 'authorized': None, 'status': 'UNVERIFIED', 'reason': 'Observed browser controls; owner login and exact scoped action review required'}
    runtime['transport.mcp_stdio'] = {'installed': importlib.util.find_spec('mcp') is not None, 'configured': None, 'reachable': None, 'authorized': None, 'status': 'UNVERIFIED', 'reason': 'Optional official SDK; configure and test a real host connection'}
    return {'runtime': runtime,
            'host': {name: {'installed': None, 'configured': None, 'reachable': None, 'authorized': None,
                            'status': 'UNVERIFIED', 'reason': 'No host-side probe performed'}
                     for name in ('model', 'search', 'browser', 'images')},
            'network': 'offline core; optional permission-scoped research and explicit account connectors',
            'limitation': 'Capability detection is not authorization. Host capability is separate from the bundled runtime.'}


def doctor() -> dict[str, Any]:
    return {"version": VERSION, "python": sys.version.split()[0],
            "local_helpers": "available", "network_calls": "doctor performs no source requests",
            "capabilities": capabilities(),
            "detection_only": {"codex_command_found": bool(shutil.which("codex")),
                               "java_command_found": bool(shutil.which("java")),
                               "playwright_module_found": importlib.util.find_spec("playwright") is not None,
                               "mcp_module_found": importlib.util.find_spec("mcp") is not None},
            "integrations": {"live_research":"BP002_permission_scoped", "browser_control":"optional_read_only_playwright", "mcp_server":"UNAVAILABLE", "image_generation":"host_tool_required", "epub_export":"local_text_route_epubcheck_separate", "pdf_export":"local_text_route_optional_dependencies", "publisher_upload":"UNAVAILABLE", "ad_execution":"UNAVAILABLE", "report_import":"local_csv_with_explicit_mapping"},
            "limitation": "Module detection does not prove configured or working integrations. Host capabilities require a host-side probe."}


def read_json(path: str) -> Any:
    candidate = Path(path)
    if candidate.stat().st_size > 5 * 1024 * 1024:
        raise CoreError("JSON input exceeds the 5 MiB helper limit")
    with candidate.open(encoding="utf-8") as stream:
        return json.load(stream)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == 'research':
        from publishing_research import main as research_main
        return research_main(argv[1:])
    if argv and argv[0] == 'project':
        from publishing_project import main as project_main
        return project_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("doctor")
    init = subs.add_parser("init")
    for flag in ("workspace", "title", "country", "language", "budget", "currency"):
        init.add_argument(f"--{flag}", required=True)
    for name in ("add-evidence", "add-bsr"):
        sub = subs.add_parser(name)
        sub.add_argument("--workspace", required=True)
        sub.add_argument("--input", required=True)
    records = subs.add_parser("records")
    records.add_argument("--workspace", required=True)
    compare = subs.add_parser("compare-bsr")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.add_argument("--max-age-hours", required=True)
    compare.add_argument("--as-of")
    calc = subs.add_parser("economics")
    for flag in ("receipts-per-copy", "variable-cost-per-copy", "fixed-cost", "currency", "assumptions"):
        calc.add_argument(f"--{flag}", required=True)
    fresh = subs.add_parser("freshness")
    fresh.add_argument("--observed-at", required=True)
    fresh.add_argument("--max-age-hours", required=True)
    fresh.add_argument("--as-of")
    pre = subs.add_parser("preflight")
    pre.add_argument("--input", required=True)
    action = subs.add_parser("action-policy")
    action.add_argument("--action", required=True)
    checksum = subs.add_parser("hash")
    checksum.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "init":
            result = init_project(Path(args.workspace), args.title, args.country, args.language, args.budget, args.currency)
        elif args.command in {"add-evidence", "add-bsr"}:
            result = add_record(Path(args.workspace), "evidence" if args.command == "add-evidence" else "bsr", read_json(args.input))
        elif args.command == "records":
            result = list_records(Path(args.workspace))
        elif args.command == "compare-bsr":
            result = compare_bsr(read_json(args.left), read_json(args.right), args.max_age_hours,
                                 timestamp(args.as_of, "as_of") if args.as_of else None)
        elif args.command == "economics":
            result = economics(receipts_per_copy=args.receipts_per_copy, variable_cost_per_copy=args.variable_cost_per_copy,
                               fixed_cost=args.fixed_cost, currency=args.currency, assumptions=args.assumptions)
        elif args.command == "freshness":
            result = age_status(args.observed_at, args.max_age_hours, timestamp(args.as_of, "as_of") if args.as_of else None)
        elif args.command == "preflight":
            result = preflight(read_json(args.input))
        elif args.command == "action-policy":
            result = action_policy(args.action)
        else:
            result = {"sha256": sha256_file(Path(args.file))}
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (CoreError, OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
