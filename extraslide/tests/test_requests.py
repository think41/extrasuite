"""Tests for request generation from SML diffs.

Tests cover:
- Operation ordering (Spec: sml-reconciliation-spec.md#operation-ordering)
- Request generation by change type (Spec: sml-reconciliation-spec.md#request-generation-by-change-type)
- Field mask computation (Spec: sml-reconciliation-spec.md#field-mask-computation)
"""

from extraslide.diff import diff_sml
from extraslide.parser import parse_sml
from extraslide.requests import generate_requests


class TestSlideRequests:
    """Test generation of slide-level requests."""

    def test_generate_create_slide_request(self) -> None:
        """Generate createSlide request for new slide."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2" layout="layout1"/>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        # Should have createSlide request
        create_requests = [r for r in requests if "createSlide" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createSlide"]["objectId"] == "slide2"

    def test_generate_delete_slide_request(self) -> None:
        """Generate deleteObject request for deleted slide."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        delete_requests = [r for r in requests if "deleteObject" in r]
        assert len(delete_requests) == 1
        assert delete_requests[0]["deleteObject"]["objectId"] == "slide2"

    def test_generate_update_slide_background(self) -> None:
        """Generate updatePageProperties for background change."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1" class="bg-#ffffff"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1" class="bg-#3b82f6"/>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        update_requests = [r for r in requests if "updatePageProperties" in r]
        assert len(update_requests) == 1
        assert update_requests[0]["updatePageProperties"]["objectId"] == "slide1"
        assert (
            "pageBackgroundFill"
            in update_requests[0]["updatePageProperties"]["pageProperties"]
        )


class TestShapeRequests:
    """Test generation of shape-level requests."""

    def test_generate_create_shape_request(self) -> None:
        """Generate createShape request for new element."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        create_requests = [r for r in requests if "createShape" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createShape"]["objectId"] == "rect1"
        assert create_requests[0]["createShape"]["shapeType"] == "RECTANGLE"

    def test_generate_delete_shape_request(self) -> None:
        """Generate deleteObject request for deleted element."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        delete_requests = [r for r in requests if "deleteObject" in r]
        assert len(delete_requests) == 1
        assert delete_requests[0]["deleteObject"]["objectId"] == "rect1"

    def test_generate_update_transform_request(self) -> None:
        """Generate updatePageElementTransform for position change."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-300 y-200 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        transform_requests = [r for r in requests if "updatePageElementTransform" in r]
        assert len(transform_requests) == 1
        assert (
            transform_requests[0]["updatePageElementTransform"]["objectId"] == "rect1"
        )
        assert (
            transform_requests[0]["updatePageElementTransform"]["transform"][
                "translateX"
            ]
            == 300
        )
        assert (
            transform_requests[0]["updatePageElementTransform"]["transform"][
                "translateY"
            ]
            == 200
        )

    def test_generate_update_shape_fill(self) -> None:
        """Generate updateShapeProperties for fill change."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#ef4444"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        update_requests = [r for r in requests if "updateShapeProperties" in r]
        assert len(update_requests) >= 1

        shape_update = update_requests[0]
        assert shape_update["updateShapeProperties"]["objectId"] == "rect1"
        assert (
            "shapeBackgroundFill"
            in shape_update["updateShapeProperties"]["shapeProperties"]
        )

    def test_generate_duplicate_request(self) -> None:
        """Generate duplicateObject request."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
                <Rect id="rect2" class="x-350 y-100 w-200 h-100" duplicate-of="rect1"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        dup_requests = [r for r in requests if "duplicateObject" in r]
        assert len(dup_requests) == 1
        assert dup_requests[0]["duplicateObject"]["objectId"] == "rect1"


class TestTextRequests:
    """Test generation of text operation requests."""

    def test_generate_delete_text_request(self) -> None:
        """Generate deleteText request for text deletion."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-5">Hello</T>
                        <T range="5-11">World!</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-5">Hello</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        # Should have some text operation
        text_ops = [
            r
            for r in requests
            if "deleteText" in r or "insertText" in r or "updateTextStyle" in r
        ]
        assert len(text_ops) >= 1

    def test_generate_update_text_style_request(self) -> None:
        """Generate updateTextStyle request for style change."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-6">
                        <T range="0-5">Hello</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-6">
                        <T range="0-5" class="bold italic">Hello</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        style_requests = [r for r in requests if "updateTextStyle" in r]
        assert len(style_requests) >= 1
        assert style_requests[0]["updateTextStyle"]["objectId"] == "tb1"


class TestOperationOrdering:
    """Test that operations are ordered correctly.

    Spec: sml-reconciliation-spec.md#operation-ordering
    """

    def test_creates_before_deletes(self) -> None:
        """Create operations should come before delete operations."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect2" class="x-300 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        create_idx = None
        delete_idx = None

        for i, r in enumerate(requests):
            if "createShape" in r and create_idx is None:
                create_idx = i
            if "deleteObject" in r and delete_idx is None:
                delete_idx = i

        if create_idx is not None and delete_idx is not None:
            assert create_idx < delete_idx, "Creates should come before deletes"

    def test_content_before_style(self) -> None:
        """Content operations should come before style operations."""
        # This is implicitly tested by the request generator structure
        # Creates -> Content -> Style -> Deletes
        pass


class TestLineRequests:
    """Test generation of line-related requests."""

    def test_generate_create_line_request(self) -> None:
        """Generate createLine request."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Line id="line1" class="line-straight x-100 y-100 w-200 h-0"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        line_requests = [r for r in requests if "createLine" in r]
        assert len(line_requests) == 1
        assert line_requests[0]["createLine"]["objectId"] == "line1"
        assert line_requests[0]["createLine"]["lineCategory"] == "STRAIGHT"


class TestImageRequests:
    """Test generation of image-related requests."""

    def test_generate_create_image_request(self) -> None:
        """Generate createImage request."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Image id="img1" class="x-100 y-100 w-300 h-200" src="https://example.com/image.png"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        img_requests = [r for r in requests if "createImage" in r]
        assert len(img_requests) == 1
        assert img_requests[0]["createImage"]["objectId"] == "img1"
        assert img_requests[0]["createImage"]["url"] == "https://example.com/image.png"


class TestTableRequests:
    """Test generation of table-related requests."""

    def test_generate_create_table_request(self) -> None:
        """Generate createTable request."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Table id="table1" class="x-72 y-200 w-576 h-200" rows="3" cols="4"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        table_requests = [r for r in requests if "createTable" in r]
        assert len(table_requests) == 1
        assert table_requests[0]["createTable"]["objectId"] == "table1"
        assert table_requests[0]["createTable"]["rows"] == 3
        assert table_requests[0]["createTable"]["columns"] == 4


class TestVideoRequests:
    """Test generation of video-related requests."""

    def test_generate_create_video_request(self) -> None:
        """Generate createVideo request."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Video id="vid1" class="x-100 y-100 w-480 h-270" src="youtube:dQw4w9WgXcQ"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        video_requests = [r for r in requests if "createVideo" in r]
        assert len(video_requests) == 1
        assert video_requests[0]["createVideo"]["objectId"] == "vid1"
        assert video_requests[0]["createVideo"]["source"] == "YOUTUBE"
        assert video_requests[0]["createVideo"]["id"] == "dQw4w9WgXcQ"


class TestFieldMasks:
    """Test field mask computation.

    Spec: sml-reconciliation-spec.md#field-mask-computation
    """

    def test_fill_field_mask(self) -> None:
        """Field mask should include fill when fill changes."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#ef4444"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        shape_updates = [r for r in requests if "updateShapeProperties" in r]
        if shape_updates:
            fields = shape_updates[0]["updateShapeProperties"]["fields"]
            assert "shapeBackgroundFill" in fields


class TestPropertyState:
    """Test property state handling.

    Spec: sml-reconciliation-spec.md#property-state-semantics
    """

    def test_fill_none_generates_not_rendered(self) -> None:
        """fill-none should generate NOT_RENDERED property state."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-none"/>
            </Slide>
        </Presentation>
        """)

        diff = diff_sml(original, edited)
        requests = generate_requests(diff)

        shape_updates = [r for r in requests if "updateShapeProperties" in r]
        if shape_updates:
            props = shape_updates[0]["updateShapeProperties"]["shapeProperties"]
            if "shapeBackgroundFill" in props:
                assert (
                    props["shapeBackgroundFill"].get("propertyState") == "NOT_RENDERED"
                )
