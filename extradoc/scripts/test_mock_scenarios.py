#!/usr/bin/env python3
"""Test mock API against real API with diverse batchUpdate scenarios.

Pulls a document, then sends individual batchUpdate requests through the
CompositeTransport to compare real vs mock behavior. Each scenario is
independent - we re-pull between scenarios to reset state.

Usage:
    cd extradoc
    uv run python scripts/test_mock_scenarios.py <doc_url>
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "client" / "src"))

from extrasuite.client import CredentialsManager

from extradoc.composite_transport import CompositeTransport, MismatchLogger
from extradoc.transport import GoogleDocsTransport


def extract_document_id(url: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError(f"Invalid Google Docs URL: {url}")
    return match.group(1)


def get_doc_info(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract useful info from a document for building test requests."""
    body = doc["tabs"][0]["documentTab"]["body"]
    content = body["content"]
    last_index = content[-1].get("endIndex", 1)

    # Find paragraphs with text
    paragraphs = []
    for elem in content:
        if "paragraph" in elem:
            p = elem["paragraph"]
            text = ""
            for el in p.get("elements", []):
                tr = el.get("textRun", {})
                text += tr.get("content", "")
            paragraphs.append(
                {
                    "start": elem.get("startIndex", 0),
                    "end": elem.get("endIndex", 0),
                    "text": text,
                    "style": p.get("paragraphStyle", {}).get("namedStyleType", ""),
                    "has_bullet": "bullet" in p,
                }
            )

    # Find tables
    tables = []
    for elem in content:
        if "table" in elem:
            tables.append(
                {
                    "start": elem.get("startIndex", 0),
                    "end": elem.get("endIndex", 0),
                    "rows": elem["table"].get("rows", 0),
                    "cols": elem["table"].get("columns", 0),
                }
            )

    return {
        "last_index": last_index,
        "paragraphs": paragraphs,
        "tables": tables,
        "tab_id": doc["tabs"][0]["tabProperties"]["tabId"],
    }


def build_scenarios(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Build diverse test scenarios based on document structure."""
    tab_id = info["tab_id"]
    last_idx = info["last_index"]
    paragraphs = info["paragraphs"]
    # Insert point: just before the final newline of the last paragraph
    insert_idx = last_idx - 1

    scenarios: list[dict[str, Any]] = []

    # --- TEXT OPERATIONS ---

    # 1. Simple text insert at end
    scenarios.append(
        {
            "name": "Insert simple text at end",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "MOCK_TEST_1",
                    }
                },
            ],
        }
    )

    # 2. Insert text with newline (creates new paragraph)
    scenarios.append(
        {
            "name": "Insert text with newline",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nMOCK_TEST_2",
                    }
                },
            ],
        }
    )

    # 3. Insert + delete (insert then delete what was inserted)
    scenarios.append(
        {
            "name": "Insert then delete same text",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "TEMPTEXT",
                    }
                },
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": insert_idx,
                            "endIndex": insert_idx + 8,
                            "tabId": tab_id,
                        },
                    }
                },
            ],
        }
    )

    # 4. Insert text and make it bold
    scenarios.append(
        {
            "name": "Insert text and apply bold",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "BOLDTEXT",
                    }
                },
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_idx,
                            "endIndex": insert_idx + 8,
                            "tabId": tab_id,
                        },
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                },
            ],
        }
    )

    # 5. Insert text and apply multiple styles
    scenarios.append(
        {
            "name": "Insert text with bold+italic+underline",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "STYLED",
                    }
                },
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_idx,
                            "endIndex": insert_idx + 6,
                            "tabId": tab_id,
                        },
                        "textStyle": {"bold": True, "italic": True, "underline": True},
                        "fields": "bold,italic,underline",
                    }
                },
            ],
        }
    )

    # 6. Insert and set paragraph style to HEADING_1
    scenarios.append(
        {
            "name": "Insert text as heading",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nHeading Test",
                    }
                },
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": insert_idx + 1,
                            "endIndex": insert_idx + 13,
                            "tabId": tab_id,
                        },
                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                        "fields": "namedStyleType",
                    }
                },
            ],
        }
    )

    # 7. Insert text and create bullet list
    scenarios.append(
        {
            "name": "Insert text as bullet list",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nBullet item",
                    }
                },
                {
                    "createParagraphBullets": {
                        "range": {
                            "startIndex": insert_idx + 1,
                            "endIndex": insert_idx + 12,
                            "tabId": tab_id,
                        },
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                },
            ],
        }
    )

    # 8. Apply link to inserted text
    scenarios.append(
        {
            "name": "Insert text with hyperlink",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "click here",
                    }
                },
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_idx,
                            "endIndex": insert_idx + 10,
                            "tabId": tab_id,
                        },
                        "textStyle": {
                            "link": {"url": "https://example.com"},
                        },
                        "fields": "link",
                    }
                },
            ],
        }
    )

    # 9. Paragraph alignment change on existing paragraph
    if len(paragraphs) > 2:
        p = paragraphs[1]  # Second paragraph
        scenarios.append(
            {
                "name": "Change paragraph alignment to CENTER",
                "requests": [
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": p["start"],
                                "endIndex": p["end"],
                                "tabId": tab_id,
                            },
                            "paragraphStyle": {"alignment": "CENTER"},
                            "fields": "alignment",
                        }
                    },
                ],
            }
        )

    # 10. Set line spacing on existing paragraph
    if len(paragraphs) > 2:
        p = paragraphs[1]
        scenarios.append(
            {
                "name": "Change paragraph line spacing",
                "requests": [
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": p["start"],
                                "endIndex": p["end"],
                                "tabId": tab_id,
                            },
                            "paragraphStyle": {
                                "lineSpacing": 200,
                                "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            },
                            "fields": "lineSpacing,spaceAbove",
                        }
                    },
                ],
            }
        )

    # 11. Update text style on existing text (font size + color)
    if len(paragraphs) > 2:
        p = paragraphs[1]
        text_end = min(p["start"] + 5, p["end"] - 1)
        if text_end > p["start"]:
            scenarios.append(
                {
                    "name": "Change font size and color on existing text",
                    "requests": [
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": p["start"],
                                    "endIndex": text_end,
                                    "tabId": tab_id,
                                },
                                "textStyle": {
                                    "fontSize": {"magnitude": 18, "unit": "PT"},
                                    "foregroundColor": {
                                        "color": {
                                            "rgbColor": {
                                                "red": 1.0,
                                                "green": 0,
                                                "blue": 0,
                                            }
                                        },
                                    },
                                },
                                "fields": "fontSize,foregroundColor",
                            }
                        },
                    ],
                }
            )

    # 12. Insert multiple paragraphs with newlines
    scenarios.append(
        {
            "name": "Insert multiple paragraphs with newlines",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nPara one\nPara two\nPara three",
                    }
                },
            ],
        }
    )

    # 13. Delete content range from middle of a paragraph
    if len(paragraphs) > 3:
        p = paragraphs[2]
        del_start = p["start"]
        del_end = min(p["start"] + 3, p["end"] - 1)
        if del_end > del_start:
            scenarios.append(
                {
                    "name": "Delete a few chars from middle of paragraph",
                    "requests": [
                        {
                            "deleteContentRange": {
                                "range": {
                                    "startIndex": del_start,
                                    "endIndex": del_end,
                                    "tabId": tab_id,
                                },
                            }
                        },
                    ],
                }
            )

    # 14. Insert at beginning of document (index 1)
    scenarios.append(
        {
            "name": "Insert text at beginning of document",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": tab_id},
                        "text": "START ",
                    }
                },
            ],
        }
    )

    # 15. Set text to strikethrough
    if len(paragraphs) > 2:
        p = paragraphs[1]
        text_end = min(p["start"] + 5, p["end"] - 1)
        if text_end > p["start"]:
            scenarios.append(
                {
                    "name": "Apply strikethrough to existing text",
                    "requests": [
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": p["start"],
                                    "endIndex": text_end,
                                    "tabId": tab_id,
                                },
                                "textStyle": {"strikethrough": True},
                                "fields": "strikethrough",
                            }
                        },
                    ],
                }
            )

    # 16. Clear all formatting (reset to defaults)
    if len(paragraphs) > 2:
        p = paragraphs[1]
        text_end = min(p["start"] + 5, p["end"] - 1)
        if text_end > p["start"]:
            scenarios.append(
                {
                    "name": "Clear text formatting to defaults",
                    "requests": [
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": p["start"],
                                    "endIndex": text_end,
                                    "tabId": tab_id,
                                },
                                "textStyle": {},
                                "fields": "bold,italic,underline,strikethrough,fontSize,foregroundColor",
                            }
                        },
                    ],
                }
            )

    # 17. Insert and then change to HEADING_2 with alignment
    scenarios.append(
        {
            "name": "Insert heading with center alignment",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nCentered Heading",
                    }
                },
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": insert_idx + 1,
                            "endIndex": insert_idx + 17,
                            "tabId": tab_id,
                        },
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_2",
                            "alignment": "CENTER",
                        },
                        "fields": "namedStyleType,alignment",
                    }
                },
            ],
        }
    )

    # 18. Delete an entire paragraph (start to end)
    if len(paragraphs) > 5:
        p = paragraphs[-2]  # Second to last
        scenarios.append(
            {
                "name": "Delete entire paragraph",
                "requests": [
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": p["start"]
                                - 1,  # Include preceding newline
                                "endIndex": p["end"] - 1,  # Exclude final newline
                                "tabId": tab_id,
                            },
                        }
                    },
                ],
            }
        )

    # 19. Set superscript on text
    if len(paragraphs) > 2:
        p = paragraphs[1]
        text_end = min(p["start"] + 3, p["end"] - 1)
        if text_end > p["start"]:
            scenarios.append(
                {
                    "name": "Apply superscript to text",
                    "requests": [
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": p["start"],
                                    "endIndex": text_end,
                                    "tabId": tab_id,
                                },
                                "textStyle": {"baselineOffset": "SUPERSCRIPT"},
                                "fields": "baselineOffset",
                            }
                        },
                    ],
                }
            )

    # 20. Complex: insert + style + paragraph style in one batch
    scenarios.append(
        {
            "name": "Complex: insert + bold + heading in one batch",
            "requests": [
                {
                    "insertText": {
                        "location": {"index": insert_idx, "tabId": tab_id},
                        "text": "\nComplex Test",
                    }
                },
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": insert_idx + 1,
                            "endIndex": insert_idx + 13,
                            "tabId": tab_id,
                        },
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                },
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": insert_idx + 1,
                            "endIndex": insert_idx + 13,
                            "tabId": tab_id,
                        },
                        "paragraphStyle": {"namedStyleType": "HEADING_3"},
                        "fields": "namedStyleType",
                    }
                },
            ],
        }
    )

    return scenarios


async def run_scenario(
    composite: CompositeTransport,
    document_id: str,
    scenario: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Run a single scenario. Returns (passed, diffs)."""
    requests = scenario["requests"]
    try:
        await composite.batch_update(document_id, requests)
    except Exception as e:
        return False, [f"Exception: {e}"]

    # Check if mismatch was logged
    if composite.mismatch_logger.mismatch_count > 0:
        return False, ["Mismatch detected (see output above)"]
    return True, []


async def main(doc_url: str) -> None:
    document_id = extract_document_id(doc_url)
    manager = CredentialsManager()
    token = manager.get_token()

    mismatch_dir = Path("mismatch_logs/scenarios")
    results: list[tuple[str, bool]] = []

    print("=" * 70)
    print("MOCK API SCENARIO TESTING")
    print("=" * 70)

    # We need to pull fresh for each scenario since each modifies the doc
    scenarios_to_run: list[dict[str, Any]] = []

    # First pull to build scenarios
    print("\nPulling document to build scenarios...")
    transport = GoogleDocsTransport(token.access_token)
    doc_data = await transport.get_document(document_id)
    await transport.close()
    info = get_doc_info(doc_data.raw)
    scenarios_to_run = build_scenarios(info)
    print(f"Built {len(scenarios_to_run)} scenarios")
    print(
        f"Document has {len(info['paragraphs'])} paragraphs, "
        f"{len(info['tables'])} tables, last_index={info['last_index']}"
    )

    for i, scenario in enumerate(scenarios_to_run):
        name = scenario["name"]
        print(f"\n{'─' * 70}")
        print(f"[{i + 1}/{len(scenarios_to_run)}] {name}")
        print(f"{'─' * 70}")

        # Fresh transport + composite for each scenario
        logger = MismatchLogger(mismatch_dir / f"scenario_{i + 1:02d}")
        transport = GoogleDocsTransport(token.access_token)
        composite = CompositeTransport(transport, logger)

        # Pull fresh (initializes mock with current state)
        await composite.get_document(document_id)

        # Print requests
        for req in scenario["requests"]:
            req_type = next(k for k in req if k != "writeControl")
            print(f"  -> {req_type}")

        passed, diffs = await run_scenario(composite, document_id, scenario)

        if passed:
            print("  PASS")
        else:
            print("  FAIL")
            for d in diffs:
                print(f"    {d}")

        results.append((name, passed))
        await composite.close()

    # Summary
    print(f"\n{'=' * 70}")
    print("RESULTS SUMMARY")
    print(f"{'=' * 70}")
    passed_count = sum(1 for _, p in results if p)
    failed_count = len(results) - passed_count

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\n{passed_count}/{len(results)} passed, {failed_count} failed")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_mock_scenarios.py <google_doc_url>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
