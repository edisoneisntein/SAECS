import os
import ast
import re
from html.parser import HTMLParser


WEB_EXTENSIONS = (".html", ".css", ".js", ".mjs")
CRITICAL_ACTION_PATTERN = (
    r"approve|reject|execute|submit|commit|deploy|publish|transfer|"
    r"delete|remove|cancel|disable|enable|kill|shutdown|gate|"
    r"aprobar|rechazar|ejecutar|eliminar|cancelar|desactivar|activar"
)
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".saecs",
    "__pycache__",
    "node_modules",
    "venv",
    "env",
    ".venv",
    "dist",
    "build",
    "coverage",
    "tests",
    "BACKUP_CCC_ESTABLE",
}


class _HTMLUXParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: dict[str, int] = {}
        self.buttons: list[dict] = []
        self.inputs: list[dict] = []
        self.forms = 0
        self.images = 0
        self.images_missing_alt = 0
        self.links = 0
        self.links_missing_text = 0
        self.inline_handlers = 0
        self.aria_labels = 0
        self.landmarks = 0
        self.headings: list[str] = []
        self._current_button: dict | None = None
        self._current_link: dict | None = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        self.tags[tag] = self.tags.get(tag, 0) + 1
        self.inline_handlers += sum(1 for k in attrs_dict if k.startswith("on"))
        if attrs_dict.get("aria-label") or attrs_dict.get("aria-labelledby"):
            self.aria_labels += 1
        if tag in ("main", "nav", "header", "footer", "aside", "section"):
            self.landmarks += 1
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(tag)
        if tag == "form":
            self.forms += 1
        elif tag == "img":
            self.images += 1
            if not attrs_dict.get("alt"):
                self.images_missing_alt += 1
        elif tag == "button":
            button = {"attrs": attrs_dict, "text": ""}
            self.buttons.append(button)
            self._current_button = button
        elif tag == "input":
            self.inputs.append({"attrs": attrs_dict})
        elif tag == "a":
            self.links += 1
            link = {"attrs": attrs_dict, "text": ""}
            self._current_link = link

    def handle_endtag(self, tag):
        if tag == "button":
            self._current_button = None
        elif tag == "a":
            if self._current_link and not _has_accessible_name(
                self._current_link["text"],
                self._current_link["attrs"],
            ):
                self.links_missing_text += 1
            self._current_link = None

    def handle_data(self, data):
        if self._current_button is not None:
            self._current_button["text"] += data.strip()
        if self._current_link is not None:
            self._current_link["text"] += data.strip()


def scan_project(
    project_path: str,
    include_code: bool = True,
    include_web: bool = True,
) -> tuple[list[dict], dict[str, float], float, bool]:
    modules: dict[str, dict] = {}
    web_files: dict[str, dict] = {}
    ux_findings: list[dict] = []
    total_lines = 0
    total_complexity = 0.0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".opencode")]
        if any(part in SKIP_DIRS for part in root.split(os.sep)):
            continue
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, project_path)
            if include_code and f.endswith(".py"):
                info = _analyze_python(path)
                if info:
                    modules[rel] = info
                    total_lines += info["lines"]
                    total_complexity += info["complexity"]
            elif include_web and f.endswith(WEB_EXTENSIONS):
                info, findings = _analyze_web_file(path, rel)
                if info:
                    web_files[rel] = info
                    total_lines += info["lines"]
                    ux_findings.extend(findings)

    metrics = {
        "modules": len(modules),
        "web_files": len(web_files),
        "html_files": sum(1 for f in web_files if f.endswith(".html")),
        "css_files": sum(1 for f in web_files if f.endswith(".css")),
        "js_files": sum(1 for f in web_files if f.endswith((".js", ".mjs"))),
        "lines": total_lines,
        "avg_complexity": round(total_complexity / max(len(modules), 1), 2),
    }
    metrics.update(_summarize_ux(web_files, ux_findings))

    components = [
        {"name": m, "kind": "python", "lines": v["lines"], "complexity": v["complexity"]}
        for m, v in modules.items()
    ]
    components.extend(
        {"name": m, "kind": v["kind"], **v}
        for m, v in web_files.items()
    )
    components.extend(
        {"name": f["id"], "kind": "ui_finding", **f}
        for f in ux_findings
    )

    uncertainty = _calculate_uncertainty(modules, web_files, metrics, ux_findings)
    changes = True

    return components, metrics, uncertainty, changes


def _analyze_python(path: str) -> dict | None:
    try:
        with open(path) as f:
            source = f.read()
    except (IOError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    complexity = 1.0
    functions = 0
    classes = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions += 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                    complexity += 1.0
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
        elif isinstance(node, ast.ClassDef):
            classes += 1

    return {
        "lines": len(source.splitlines()),
        "complexity": complexity,
        "functions": functions,
        "classes": classes,
    }


def _analyze_web_file(path: str, rel: str) -> tuple[dict | None, list[dict]]:
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except (IOError, UnicodeDecodeError):
        return None, []

    if path.endswith(".html"):
        return _analyze_html(source, rel)
    if path.endswith(".css"):
        return _analyze_css(source, rel), []
    return _analyze_js(source, rel), _find_js_ux_risks(source, rel)


def _analyze_html(source: str, rel: str) -> tuple[dict, list[dict]]:
    parser = _HTMLUXParser()
    parser.feed(source)
    unlabeled_buttons = [
        b for b in parser.buttons
        if not _has_accessible_name(b["text"], b["attrs"])
    ]
    unlabeled_inputs = [
        i for i in parser.inputs
        if not _input_has_label(source, i["attrs"])
    ]
    danger_controls = _count_danger_controls(parser.buttons)
    findings = []

    if unlabeled_buttons:
        findings.append(_finding(
            rel, "accessibility", "high",
            "Interactive buttons need accessible names.",
            "Buttons without text, aria-label, or title increase operator error.",
        ))
    if unlabeled_inputs:
        findings.append(_finding(
            rel, "accessibility", "medium",
            "Inputs need labels or aria labels.",
            "Unlabeled inputs reduce form clarity and screen-reader usability.",
        ))
    if parser.images_missing_alt:
        findings.append(_finding(
            rel, "accessibility", "medium",
            "Images need alt text.",
            "Missing alt text leaves visual context unavailable to assistive tech.",
        ))
    if danger_controls and not _has_confirmation_copy(source):
        findings.append(_finding(
            rel, "operational_safety", "critical",
            "Critical controls need explicit confirmation UX.",
            "High-impact actions should prevent accidental activation and make consequences clear before execution.",
        ))
    if not _has_viewport_meta(source):
        findings.append(_finding(
            rel, "responsive", "high",
            "HTML is missing a viewport meta tag.",
            "Mobile review and emergency operation can break without responsive scaling.",
        ))
    if parser.headings and parser.headings[0] != "h1":
        findings.append(_finding(
            rel, "information_architecture", "low",
            "Heading hierarchy does not start with h1.",
            "A clear heading hierarchy improves scanning in high-pressure workflows.",
        ))

    info = {
        "kind": "html",
        "lines": len(source.splitlines()),
        "buttons": len(parser.buttons),
        "inputs": len(parser.inputs),
        "forms": parser.forms,
        "images": parser.images,
        "images_missing_alt": parser.images_missing_alt,
        "links": parser.links,
        "links_missing_text": parser.links_missing_text,
        "inline_event_handlers": parser.inline_handlers,
        "aria_labels": parser.aria_labels,
        "landmarks": parser.landmarks,
        "headings": len(parser.headings),
        "unlabeled_controls": len(unlabeled_buttons) + len(unlabeled_inputs),
        "danger_controls": danger_controls,
        "has_viewport": _has_viewport_meta(source),
        "has_dialog": bool(re.search(r"\b(dialog|modal|confirm|confirmation)\b", source, re.I)),
    }
    return info, findings


def _analyze_css(source: str, rel: str) -> dict:
    return {
        "kind": "css",
        "lines": len(source.splitlines()),
        "media_queries": len(re.findall(r"@media\b", source)),
        "focus_styles": len(re.findall(r":focus|:focus-visible", source)),
        "css_variables": len(re.findall(r"--[a-zA-Z0-9_-]+\s*:", source)),
        "important_rules": len(re.findall(r"!important\b", source)),
        "fixed_position": len(re.findall(r"position\s*:\s*fixed", source)),
    }


def _analyze_js(source: str, rel: str) -> dict:
    return {
        "kind": "javascript",
        "lines": len(source.splitlines()),
        "event_listeners": len(re.findall(r"\.addEventListener\s*\(", source)),
        "fetch_calls": len(re.findall(r"\bfetch\s*\(", source)),
        "local_storage": len(re.findall(r"\blocalStorage\b", source)),
        "confirm_calls": len(re.findall(r"\bconfirm\s*\(", source)),
        "alert_calls": len(re.findall(r"\balert\s*\(", source)),
        "dom_queries": len(re.findall(r"\b(querySelector|getElementById)\s*\(", source)),
        "loading_states": len(re.findall(r"loading|spinner|skeleton|pending", source, re.I)),
        "error_states": len(re.findall(r"catch\s*\(|error|toast|notify", source, re.I)),
    }


def _find_js_ux_risks(source: str, rel: str) -> list[dict]:
    findings = []
    if not _is_ui_javascript(rel, source):
        return findings
    has_danger_action = re.search(
        CRITICAL_ACTION_PATTERN,
        source,
        re.I,
    )
    if has_danger_action and "confirm(" not in source and "modal" not in source.lower():
        findings.append(_finding(
            rel, "operational_safety", "high",
            "Critical JS actions appear to lack confirmation handling.",
            "High-impact actions should include clear review, confirmation, and recovery states.",
        ))
    if "fetch(" in source and not re.search(r"\.catch\s*\(|try\s*{", source):
        findings.append(_finding(
            rel, "resilience", "medium",
            "Network calls need visible error handling.",
            "Users need clear feedback when data loading or action requests fail.",
        ))
    if re.search(r"\balert\s*\(", source):
        findings.append(_finding(
            rel, "interaction_design", "low",
            "Alert dialogs are a weak feedback pattern.",
            "Inline status, toasts, or modal review flows give better context than browser alerts.",
        ))
    return findings


def _is_ui_javascript(rel: str, source: str) -> bool:
    normalized = rel.replace(os.sep, "/")
    if normalized == "js/main.js" or normalized.startswith("js/ui/"):
        return True
    return bool(re.search(r"\b(document|window)\b|\.addEventListener\s*\(|\b(querySelector|getElementById)\s*\(", source))


def _summarize_ux(web_files: dict[str, dict], findings: list[dict]) -> dict[str, float]:
    html = [v for v in web_files.values() if v["kind"] == "html"]
    css = [v for v in web_files.values() if v["kind"] == "css"]
    js = [v for v in web_files.values() if v["kind"] == "javascript"]
    interactive_controls = sum(v.get("buttons", 0) + v.get("inputs", 0) for v in html)
    unlabeled_controls = sum(v.get("unlabeled_controls", 0) for v in html)
    danger_controls = sum(v.get("danger_controls", 0) for v in html)
    confirmation_gaps = sum(
        1 for f in findings
        if f["category"] == "operational_safety"
    )
    responsive_signals = sum(v.get("media_queries", 0) for v in css) + sum(
        1 for v in html if v.get("has_viewport")
    )
    focus_styles = sum(v.get("focus_styles", 0) for v in css)
    error_states = sum(v.get("error_states", 0) for v in js)
    loading_states = sum(v.get("loading_states", 0) for v in js)
    risk_points = sum(_severity_weight(f["severity"]) for f in findings)
    accessibility_score = 1.0
    if interactive_controls:
        accessibility_score -= min(unlabeled_controls / interactive_controls, 1.0) * 0.5
    if html:
        missing_alt = sum(v.get("images_missing_alt", 0) for v in html)
        images = max(sum(v.get("images", 0) for v in html), 1)
        accessibility_score -= min(missing_alt / images, 1.0) * 0.2
    if not focus_styles and interactive_controls:
        accessibility_score -= 0.2

    return {
        "interactive_controls": interactive_controls,
        "unlabeled_controls": unlabeled_controls,
        "danger_controls": danger_controls,
        "ui_findings": len(findings),
        "critical_ui_findings": sum(1 for f in findings if f["severity"] == "critical"),
        "high_ui_findings": sum(1 for f in findings if f["severity"] == "high"),
        "confirmation_gaps": confirmation_gaps,
        "responsive_signals": responsive_signals,
        "focus_styles": focus_styles,
        "error_states": error_states,
        "loading_states": loading_states,
        "accessibility_score": round(max(accessibility_score, 0.0), 2),
        "ux_risk_score": round(min(risk_points / 20.0, 1.0), 2),
    }


def _calculate_uncertainty(
    modules: dict, web_files: dict, metrics: dict, findings: list[dict]
) -> float:
    if not modules and not web_files:
        return 1.0
    sources = 0
    test_files = [m for m in modules if "test" in m.lower()]
    if modules and len(test_files) < len(modules) * 0.1:
        sources += 1
    if metrics.get("avg_complexity", 0) > 10:
        sources += 1
    if web_files and not metrics.get("responsive_signals", 0):
        sources += 1
    if metrics.get("confirmation_gaps", 0):
        sources += 1
    if metrics.get("accessibility_score", 1.0) < 0.7:
        sources += 1
    if any(f["severity"] == "critical" for f in findings):
        sources += 1
    return min(sources * 0.2, 0.9)


def _has_accessible_name(text: str, attrs: dict) -> bool:
    return bool(
        text.strip()
        or attrs.get("aria-label")
        or attrs.get("aria-labelledby")
        or attrs.get("title")
        or attrs.get("value")
    )


def _input_has_label(source: str, attrs: dict) -> bool:
    input_type = attrs.get("type", "text").lower()
    if input_type in ("hidden", "submit", "button"):
        return True
    if attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("title"):
        return True
    input_id = attrs.get("id")
    if input_id and re.search(rf"<label[^>]+for=[\"']{re.escape(input_id)}[\"']", source, re.I):
        return True
    return False


def _count_danger_controls(buttons: list[dict]) -> int:
    danger = re.compile(CRITICAL_ACTION_PATTERN, re.I)
    count = 0
    for button in buttons:
        attrs = button.get("attrs", {})
        haystack = " ".join([
            button.get("text", ""),
            attrs.get("id", ""),
            attrs.get("class", ""),
            attrs.get("aria-label", ""),
            attrs.get("data-action", ""),
        ])
        if danger.search(haystack):
            count += 1
    return count


def _has_confirmation_copy(source: str) -> bool:
    return bool(re.search(r"confirm|confirmation|modal|pin|revis|segur|confirmar", source, re.I))


def _has_viewport_meta(source: str) -> bool:
    return bool(re.search(r"<meta[^>]+name=[\"']viewport[\"']", source, re.I))


def _finding(path: str, category: str, severity: str, problem: str, impact: str) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{path}-{category}-{problem}".lower()).strip("-")
    return {
        "id": f"ui-{slug[:80]}",
        "path": path,
        "category": category,
        "severity": severity,
        "problem": problem,
        "impact": impact,
    }


def _severity_weight(severity: str) -> int:
    return {
        "critical": 5,
        "high": 3,
        "medium": 2,
        "low": 1,
    }.get(severity, 1)
