"""Tests for the form transformer."""

from __future__ import annotations

from extraform.transformer import FormTransformer


class TestFormTransformer:
    """Tests for FormTransformer."""

    def test_transform_basic_form(self) -> None:
        """Test transforming a basic form with one question."""
        form_data = {
            "formId": "test_form_id",
            "revisionId": "00000001",
            "responderUri": "https://docs.google.com/forms/d/e/test/viewform",
            "info": {
                "title": "Test Form",
                "documentTitle": "Test Form Doc",
                "description": "A test form",
            },
            "items": [
                {
                    "itemId": "item1",
                    "title": "What is your name?",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "required": True,
                            "textQuestion": {"paragraph": False},
                        }
                    },
                }
            ],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        assert "form.json" in files
        form = files["form.json"]

        assert form["formId"] == "test_form_id"
        assert form["info"]["title"] == "Test Form"
        assert len(form["items"]) == 1
        assert form["items"][0]["title"] == "What is your name?"

    def test_transform_with_settings(self) -> None:
        """Test transforming form with settings."""
        form_data = {
            "formId": "test_form_id",
            "info": {"title": "Quiz Form"},
            "settings": {
                "quizSettings": {"isQuiz": True},
                "emailCollectionType": "VERIFIED",
            },
            "items": [],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        form = files["form.json"]
        assert form["settings"]["quizSettings"]["isQuiz"] is True
        assert form["settings"]["emailCollectionType"] == "VERIFIED"

    def test_transform_choice_question(self) -> None:
        """Test transforming a multiple choice question."""
        form_data = {
            "formId": "test_form_id",
            "info": {"title": "Choice Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Favorite color?",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [
                                    {"value": "Red"},
                                    {"value": "Blue"},
                                    {"value": "Other", "isOther": True},
                                ],
                            },
                        }
                    },
                }
            ],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        form = files["form.json"]
        question = form["items"][0]["questionItem"]["question"]
        assert question["choiceQuestion"]["type"] == "RADIO"
        assert len(question["choiceQuestion"]["options"]) == 3

    def test_transform_scale_question(self) -> None:
        """Test transforming a scale question."""
        form_data = {
            "formId": "test_form_id",
            "info": {"title": "Scale Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Rate your experience",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "scaleQuestion": {
                                "low": 1,
                                "high": 5,
                                "lowLabel": "Poor",
                                "highLabel": "Excellent",
                            },
                        }
                    },
                }
            ],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        form = files["form.json"]
        question = form["items"][0]["questionItem"]["question"]
        assert question["scaleQuestion"]["low"] == 1
        assert question["scaleQuestion"]["high"] == 5

    def test_transform_page_break(self) -> None:
        """Test transforming a page break item."""
        form_data = {
            "formId": "test_form_id",
            "info": {"title": "Multi-section Form"},
            "items": [
                {
                    "itemId": "section1",
                    "title": "Section 1",
                    "description": "First section",
                    "pageBreakItem": {},
                }
            ],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        form = files["form.json"]
        assert "pageBreakItem" in form["items"][0]

    def test_transform_with_responses(self) -> None:
        """Test transforming form with responses."""
        form_data = {
            "formId": "test_form_id",
            "info": {"title": "Response Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Name",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "textQuestion": {"paragraph": False},
                        }
                    },
                }
            ],
        }

        responses_data = {
            "responses": [
                {
                    "responseId": "resp1",
                    "createTime": "2024-01-15T10:30:00Z",
                    "respondentEmail": "alice@example.com",
                    "answers": {
                        "q1": {
                            "questionId": "q1",
                            "textAnswers": {"answers": [{"value": "Alice"}]},
                        }
                    },
                }
            ]
        }

        transformer = FormTransformer(form_data, responses_data)
        files = transformer.transform()

        assert "form.json" in files
        assert "responses.tsv" in files
        assert "resp1" in files["responses.tsv"]
        assert "Alice" in files["responses.tsv"]

    def test_transform_empty_form(self) -> None:
        """Test transforming an empty form."""
        form_data = {
            "formId": "empty_form",
            "info": {"title": "Empty Form"},
            "items": [],
        }

        transformer = FormTransformer(form_data)
        files = transformer.transform()

        form = files["form.json"]
        assert form["items"] == []


class TestResponsesTransform:
    """Tests for responses transformation."""

    def test_sanitize_header_with_special_chars(self) -> None:
        """Test that headers are sanitized properly."""
        form_data = {
            "formId": "test",
            "info": {"title": "Test"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Name\twith\ttabs",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "textQuestion": {"paragraph": False},
                        }
                    },
                }
            ],
        }

        responses_data = {
            "responses": [
                {
                    "responseId": "resp1",
                    "answers": {
                        "q1": {"textAnswers": {"answers": [{"value": "Test"}]}},
                    },
                }
            ]
        }

        transformer = FormTransformer(form_data, responses_data)
        files = transformer.transform()

        # Header should not contain tabs
        tsv = files["responses.tsv"]
        lines = tsv.split("\n")
        header = lines[0]
        assert "\t\t" not in header  # No double tabs from sanitization

    def test_multiple_answers(self) -> None:
        """Test extracting multiple answers (checkboxes)."""
        form_data = {
            "formId": "test",
            "info": {"title": "Test"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Hobbies",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "choiceQuestion": {"type": "CHECKBOX"},
                        }
                    },
                }
            ],
        }

        responses_data = {
            "responses": [
                {
                    "responseId": "resp1",
                    "answers": {
                        "q1": {
                            "textAnswers": {
                                "answers": [
                                    {"value": "Reading"},
                                    {"value": "Gaming"},
                                ]
                            }
                        },
                    },
                }
            ]
        }

        transformer = FormTransformer(form_data, responses_data)
        files = transformer.transform()

        tsv = files["responses.tsv"]
        assert "Reading; Gaming" in tsv
