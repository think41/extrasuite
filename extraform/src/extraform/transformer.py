"""Transform Google Forms API response to local file format."""

from __future__ import annotations

import re
from typing import Any


class FormTransformer:
    """Transforms Google Forms API response to local file format."""

    def __init__(
        self,
        form_data: dict[str, Any],
        responses_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the transformer.

        Args:
            form_data: Raw form data from Google Forms API.
            responses_data: Optional responses data from API.
        """
        self._form_data = form_data
        self._responses_data = responses_data

    def transform(self) -> dict[str, Any]:
        """Transform API response to file format.

        Returns:
            Dictionary mapping file paths to their contents.
            - "form.json": The form structure as JSON-serializable dict.
            - "responses.tsv": Optional TSV of responses (if responses_data provided).
        """
        files: dict[str, Any] = {}

        # Transform form data to form.json
        files["form.json"] = self._transform_form()

        # Transform responses to TSV if available
        if self._responses_data and self._responses_data.get("responses"):
            files["responses.tsv"] = self._transform_responses()

        return files

    def _transform_form(self) -> dict[str, Any]:
        """Transform form data to form.json structure.

        The output closely mirrors the API response but is cleaned up
        for readability and editing.
        """
        form = self._form_data

        result: dict[str, Any] = {
            "formId": form.get("formId"),
            "revisionId": form.get("revisionId"),
        }

        # Include responder URI if present
        if form.get("responderUri"):
            result["responderUri"] = form["responderUri"]

        # Include linked sheet ID if present
        if form.get("linkedSheetId"):
            result["linkedSheetId"] = form["linkedSheetId"]

        # Transform info section
        if form.get("info"):
            result["info"] = self._transform_info(form["info"])

        # Transform settings
        if form.get("settings"):
            result["settings"] = self._transform_settings(form["settings"])

        # Include publish settings if present (read-only)
        if form.get("publishSettings"):
            result["publishSettings"] = form["publishSettings"]

        # Transform items (questions, sections, media)
        result["items"] = [self._transform_item(item) for item in form.get("items", [])]

        return result

    def _transform_info(self, info: dict[str, Any]) -> dict[str, Any]:
        """Transform form info section."""
        result: dict[str, Any] = {}

        if info.get("title"):
            result["title"] = info["title"]
        if info.get("documentTitle"):
            result["documentTitle"] = info["documentTitle"]
        if info.get("description"):
            result["description"] = info["description"]

        return result

    def _transform_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Transform form settings."""
        # Pass through settings as-is, they're already in a good format
        return settings

    def _transform_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Transform a single form item."""
        result: dict[str, Any] = {}

        # Item ID is always present
        if item.get("itemId"):
            result["itemId"] = item["itemId"]

        # Title and description
        if item.get("title"):
            result["title"] = item["title"]
        if item.get("description"):
            result["description"] = item["description"]

        # Item type - exactly one of these will be present
        # Use "key in item" instead of item.get() because empty dicts {} are falsy
        if "questionItem" in item:
            result["questionItem"] = item["questionItem"]
        elif "questionGroupItem" in item:
            result["questionGroupItem"] = item["questionGroupItem"]
        elif "pageBreakItem" in item:
            result["pageBreakItem"] = item["pageBreakItem"]
        elif "textItem" in item:
            result["textItem"] = item["textItem"]
        elif "imageItem" in item:
            result["imageItem"] = item["imageItem"]
        elif "videoItem" in item:
            result["videoItem"] = item["videoItem"]

        return result

    def _transform_responses(self) -> str:
        """Transform responses to TSV format.

        Returns:
            TSV string with headers derived from question titles.
        """
        responses = self._responses_data.get("responses", []) if self._responses_data else []
        if not responses:
            return ""

        # Build question ID to title mapping from form items
        question_map = self._build_question_map()

        # Build header row
        headers = ["responseId", "timestamp", "respondentEmail"]
        question_ids = list(question_map.keys())
        for qid in question_ids:
            # Sanitize title for TSV header
            title = question_map[qid]
            headers.append(self._sanitize_header(title))

        rows = ["\t".join(headers)]

        # Build data rows
        for response in responses:
            row = [
                response.get("responseId", ""),
                response.get("createTime", ""),
                response.get("respondentEmail", ""),
            ]

            answers = response.get("answers", {})
            for qid in question_ids:
                answer = answers.get(qid, {})
                value = self._extract_answer_value(answer)
                row.append(value)

            rows.append("\t".join(row))

        return "\n".join(rows)

    def _build_question_map(self) -> dict[str, str]:
        """Build mapping of question IDs to titles."""
        question_map: dict[str, str] = {}

        for item in self._form_data.get("items", []):
            if "questionItem" in item:
                question = item["questionItem"].get("question", {})
                qid = question.get("questionId")
                if qid:
                    title = item.get("title", f"Question_{qid[:8]}")
                    question_map[qid] = title
            elif "questionGroupItem" in item:
                # Handle grid questions - each row is a separate question
                group = item["questionGroupItem"]
                for q in group.get("questions", []):
                    qid = q.get("questionId")
                    if qid:
                        # Use row title if available
                        row_q = q.get("rowQuestion", {})
                        title = row_q.get("title", f"Question_{qid[:8]}")
                        question_map[qid] = title

        return question_map

    def _sanitize_header(self, title: str) -> str:
        """Sanitize a question title for use as TSV header."""
        # Remove or replace problematic characters
        sanitized = re.sub(r"[\t\n\r]", " ", title)
        # Limit length
        if len(sanitized) > 50:
            sanitized = sanitized[:47] + "..."
        return sanitized

    def _extract_answer_value(self, answer: dict[str, Any]) -> str:
        """Extract the answer value as a string."""
        if not answer:
            return ""

        # Text answers
        text_answers = answer.get("textAnswers", {})
        if text_answers:
            answers_list = text_answers.get("answers", [])
            values = [a.get("value", "") for a in answers_list]
            return "; ".join(values)

        # File upload answers
        file_answers = answer.get("fileUploadAnswers", {})
        if file_answers:
            answers_list = file_answers.get("answers", [])
            file_ids = [a.get("fileId", "") for a in answers_list]
            return "; ".join(file_ids)

        return ""
