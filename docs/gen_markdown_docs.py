from pathlib import Path
import shutil

import mkdocs_gen_files
import requests


USER_GUIDE_SOURCE_API = "https://api.github.com/repos/NeutralAXIS/NeutralAXIS.github.io/contents/docs/3psLCCA"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DOCS_OUTPUT_DIR = SCRIPT_DIR / "docs"
USER_GUIDE_TMP_DIR = DOCS_OUTPUT_DIR / "_user-guide-src"
PYTHON_SOURCE_DIR = PROJECT_ROOT / "src"

DOCS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
USER_GUIDE_TMP_DIR.mkdir(parents=True, exist_ok=True)


def _write_generated_file(relative_path: Path, content: str) -> None:
    """Write generated files for MkDocs plugin runs and standalone script runs."""
    try:
        with mkdocs_gen_files.open(relative_path, "w") as fd:
            fd.write(content)
    except Exception:
        pass

    absolute_path = DOCS_OUTPUT_DIR / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_text(content, encoding="utf-8")


def _download_markdown_tree(api_url: str, destination: Path) -> None:
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Skipping guide download from {api_url}: {exc}")
        return

    for item in response.json():
        if item["type"] == "file" and item["name"].endswith(".md"):
            try:
                text = requests.get(item["download_url"], timeout=30).text
            except requests.RequestException as exc:
                print(f"Skipping file {item.get('name', '<unknown>')}: {exc}")
                continue
            output_file = destination / item["name"]
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(text, encoding="utf-8")
        elif item["type"] == "dir":
            subdir = destination / item["name"]
            subdir.mkdir(parents=True, exist_ok=True)
            _download_markdown_tree(item["url"], subdir)


def _strip_frontmatter(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("---"):
        return stripped
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return stripped
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:]).strip()
    return stripped


def _anchor_from_text(text: str) -> str:
    return text.lower().replace(".", "").replace("_", "-").replace(" ", "-")


def _normalize_title_from_stem(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").title()


def _write_section_pages(
    section_dir: str,
    section_title: str,
    description_line_1: str,
    description_line_2: str,
    entries: list[tuple[str, str]],
    include_markdownlint_header: bool,
) -> None:
    overview_lines = [
        f"# {section_title}",
        "",
        description_line_1,
        description_line_2,
        "",
        f"- [Combined {section_title.split()[-1]}](guide.md)",
        "",
        "## Source Pages",
        "",
    ]

    guide_lines: list[str] = []
    if include_markdownlint_header:
        guide_lines.extend([
            "<!-- markdownlint-disable MD024 MD033 -->",
            "<!-- prettier-ignore-file -->",
            "",
        ])

    guide_lines.extend(
        [
            f"# {section_title}",
            "",
            description_line_1,
            description_line_2,
            "",
        ]
    )

    if not entries:
        overview_lines.append(
            f"No {section_title.lower()} pages were generated.")
        guide_lines.append(f"No {section_title.lower()} pages were generated.")
    else:
        for idx, (title, body) in enumerate(entries):
            anchor = _anchor_from_text(title)
            overview_lines.append(f"- [{title}](guide.md#{anchor})")

            if idx > 0:
                guide_lines.extend(["", "---", ""])

            guide_lines.extend(
                [f"## {title}", "", body if body else "No content."])

    _write_generated_file(
        Path(section_dir, "index.md"),
        "\n".join(overview_lines).rstrip() + "\n",
    )
    _write_generated_file(
        Path(section_dir, "guide.md"),
        "\n".join(guide_lines).rstrip() + "\n",
    )


def _iter_python_modules() -> list[str]:
    module_names: list[str] = []
    for path in sorted(PYTHON_SOURCE_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel_path = path.relative_to(PYTHON_SOURCE_DIR).with_suffix("")
        parts = list(rel_path.parts)
        if parts[-1] == "__init__":
            continue
        module_names.append(".".join(parts))
    return module_names


def _title_from_module_name(module_name: str) -> str:
    return module_name.split(".")[-1].replace("_", " ").title()


def build_user_guide_pages() -> None:
    output_section_dir = DOCS_OUTPUT_DIR / "user-guide"
    if output_section_dir.exists():
        shutil.rmtree(output_section_dir)
    output_section_dir.mkdir(parents=True, exist_ok=True)

    if USER_GUIDE_TMP_DIR.exists():
        shutil.rmtree(USER_GUIDE_TMP_DIR)
    USER_GUIDE_TMP_DIR.mkdir(parents=True, exist_ok=True)

    _download_markdown_tree(USER_GUIDE_SOURCE_API, USER_GUIDE_TMP_DIR)

    entries: list[tuple[str, str]] = []
    for md_path in sorted(USER_GUIDE_TMP_DIR.rglob("*.md")):
        title = _normalize_title_from_stem(md_path.stem)
        content = _strip_frontmatter(md_path.read_text(encoding="utf-8"))
        entries.append((title, content))

    _write_section_pages(
        section_dir="user-guide",
        section_title="User Guide",
        description_line_1="Automatically generated from downloaded markdown sources.",
        description_line_2="",
        entries=entries,
        include_markdownlint_header=False,
    )

    if USER_GUIDE_TMP_DIR.exists():
        shutil.rmtree(USER_GUIDE_TMP_DIR)


def build_api_pages() -> None:
    modules_by_top_level: dict[str, list[str]] = {}
    for module_name in _iter_python_modules():
        top_level = module_name.split(".")[0]
        modules_by_top_level.setdefault(top_level, []).append(module_name)

    overview_titles: list[str] = []

    guide_lines: list[str] = [
        "<!-- markdownlint-disable MD024 MD033 -->",
        "<!-- prettier-ignore-file -->",
        "",
        "# API Reference",
        "",
        "Automatically generated from Python docstrings using",
        "[mkdocstrings](https://mkdocstrings.github.io/).",
        "",
    ]

    for top_level in sorted(modules_by_top_level):
        guide_lines.extend(["---", "", f"## {top_level.title()}", ""])
        for module_name in sorted(modules_by_top_level[top_level]):
            title = _title_from_module_name(module_name)
            overview_titles.append(title)
            guide_lines.extend(
                [
                    f"### {title}",
                    "",
                    f"::: {module_name}",
                    "    options:",
                    "      members_order: source",
                    "      show_root_heading: true",
                    "      show_source: false",
                    "      heading_level: 4",
                    "",
                ]
            )

    overview_lines = [
        "# API Reference",
        "",
        "Automatically generated from Python docstrings using",
        "[mkdocstrings](https://mkdocstrings.github.io/).",
        "",
        "- [Combined API](guide.md)",
        "",
        "## Source Pages",
        "",
    ]
    for title in overview_titles:
        overview_lines.append(f"- [{title}](guide.md#{_anchor_from_text(title)})")

    _write_generated_file(Path("api", "index.md"),
                          "\n".join(overview_lines).rstrip() + "\n")
    _write_generated_file(Path("api", "guide.md"),
                          "\n".join(guide_lines).rstrip() + "\n")


build_user_guide_pages()
build_api_pages()
