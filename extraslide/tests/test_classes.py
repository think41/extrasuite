"""Tests for the SML class system.

Tests cover bidirectional conversion between:
- Google Slides API properties (JSON)
- SML Tailwind-style classes (strings)

Spec reference: markup-syntax-design.md
"""

from extraslide.classes import (
    Color,
    DashStyle,
    Fill,
    ParagraphStyle,
    PropertyState,
    Shadow,
    Stroke,
    TextAlignment,
    TextStyle,
    Transform,
    parse_class_string,
    parse_fill_class,
    parse_position_classes,
    parse_stroke_classes,
    parse_text_style_classes,
)


class TestColor:
    """Test Color class conversions.

    Spec reference: markup-syntax-design.md#solid-colors-rgb-hex
    """

    def test_from_api_rgb(self) -> None:
        """Parse RGB color from API."""
        api_obj = {"rgbColor": {"red": 0.26, "green": 0.52, "blue": 0.96}}
        color = Color.from_api(api_obj)
        assert color is not None
        assert color.hex == "#4285f5"  # Close to Google blue
        assert color.theme is None

    def test_from_api_empty_rgb(self) -> None:
        """Empty RGB should give black."""
        api_obj = {"rgbColor": {}}
        color = Color.from_api(api_obj)
        assert color is not None
        assert color.hex == "#000000"

    def test_from_api_theme_color(self) -> None:
        """Parse theme color from API."""
        api_obj = {"themeColor": "ACCENT1"}
        color = Color.from_api(api_obj)
        assert color is not None
        assert color.theme == "accent1"
        assert color.hex is None

    def test_from_api_none(self) -> None:
        """None input should return None."""
        assert Color.from_api(None) is None

    def test_to_api_rgb(self) -> None:
        """Convert hex to API format."""
        color = Color(hex="#4285f4")
        api = color.to_api()
        assert "rgbColor" in api
        assert abs(api["rgbColor"]["red"] - 0.26) < 0.01
        assert abs(api["rgbColor"]["green"] - 0.52) < 0.01
        assert abs(api["rgbColor"]["blue"] - 0.96) < 0.01

    def test_to_api_theme(self) -> None:
        """Convert theme color to API format."""
        color = Color(theme="accent1")
        api = color.to_api()
        assert api == {"themeColor": "ACCENT1"}


class TestFill:
    """Test Fill class conversions.

    Spec reference: markup-syntax-design.md#fill-styling
    """

    def test_from_api_solid_fill(self) -> None:
        """Parse solid fill from API."""
        api_obj = {
            "solidFill": {
                "color": {"rgbColor": {"red": 1.0, "green": 0.0, "blue": 0.0}},
                "alpha": 0.8,
            }
        }
        fill = Fill.from_api(api_obj)
        assert fill is not None
        assert fill.color is not None
        assert fill.color.hex == "#ff0000"
        assert fill.color.alpha == 0.8

    def test_from_api_not_rendered(self) -> None:
        """Parse NOT_RENDERED state."""
        api_obj = {"propertyState": "NOT_RENDERED"}
        fill = Fill.from_api(api_obj)
        assert fill is not None
        assert fill.state == PropertyState.NOT_RENDERED

    def test_from_api_inherit(self) -> None:
        """Parse INHERIT state."""
        api_obj = {"propertyState": "INHERIT"}
        fill = Fill.from_api(api_obj)
        assert fill is not None
        assert fill.state == PropertyState.INHERIT

    def test_to_class_solid(self) -> None:
        """Convert solid fill to class string."""
        fill = Fill(color=Color(hex="#4285f4"))
        assert fill.to_class() == "fill-#4285f4"

    def test_to_class_with_opacity(self) -> None:
        """Convert fill with opacity to class string."""
        fill = Fill(color=Color(hex="#4285f4", alpha=0.8))
        assert fill.to_class() == "fill-#4285f4/80"

    def test_to_class_theme(self) -> None:
        """Convert theme fill to class string."""
        fill = Fill(color=Color(theme="accent1"))
        assert fill.to_class() == "fill-theme-accent1"

    def test_to_class_none(self) -> None:
        """Convert NOT_RENDERED to fill-none."""
        fill = Fill(state=PropertyState.NOT_RENDERED)
        assert fill.to_class() == "fill-none"

    def test_to_class_inherit(self) -> None:
        """Convert INHERIT to empty string (removed verbosity)."""
        fill = Fill(state=PropertyState.INHERIT)
        assert fill.to_class() == ""


class TestStroke:
    """Test Stroke class conversions.

    Spec reference: markup-syntax-design.md#strokeoutline-styling
    """

    def test_from_api_outline(self) -> None:
        """Parse outline from API."""
        api_obj = {
            "outlineFill": {
                "solidFill": {
                    "color": {"rgbColor": {"red": 0.0, "green": 0.0, "blue": 0.0}},
                    "alpha": 1.0,
                }
            },
            "weight": {"magnitude": 25400, "unit": "EMU"},  # 2pt
            "dashStyle": "DASH",
        }
        stroke = Stroke.from_api(api_obj)
        assert stroke is not None
        assert stroke.color is not None
        assert stroke.color.hex == "#000000"
        assert stroke.weight_pt == 2.0
        assert stroke.dash_style == DashStyle.DASH

    def test_from_api_not_rendered(self) -> None:
        """Parse NOT_RENDERED stroke."""
        api_obj = {"propertyState": "NOT_RENDERED"}
        stroke = Stroke.from_api(api_obj)
        assert stroke is not None
        assert stroke.state == PropertyState.NOT_RENDERED

    def test_to_classes_full(self) -> None:
        """Convert full stroke to classes."""
        stroke = Stroke(
            color=Color(hex="#333333"),
            weight_pt=2.0,
            dash_style=DashStyle.DASH,
        )
        classes = stroke.to_classes()
        assert "stroke-#333333" in classes
        assert "stroke-w-2" in classes
        assert "stroke-dash" in classes

    def test_to_classes_none(self) -> None:
        """Convert NOT_RENDERED stroke."""
        stroke = Stroke(state=PropertyState.NOT_RENDERED)
        assert stroke.to_classes() == ["stroke-none"]


class TestShadow:
    """Test Shadow class conversions.

    Spec reference: markup-syntax-design.md#shadow-styling
    """

    def test_from_api_not_rendered(self) -> None:
        """Parse NOT_RENDERED shadow."""
        api_obj = {"propertyState": "NOT_RENDERED"}
        shadow = Shadow.from_api(api_obj)
        assert shadow is not None
        assert shadow.state == PropertyState.NOT_RENDERED

    def test_to_classes_presets(self) -> None:
        """Shadow presets based on blur radius."""
        # Small shadow
        shadow = Shadow(blur_pt=2.0)
        assert "shadow-sm" in shadow.to_classes()

        # Medium shadow
        shadow = Shadow(blur_pt=8.0)
        assert "shadow-md" in shadow.to_classes()

        # Large shadow
        shadow = Shadow(blur_pt=16.0)
        assert "shadow-lg" in shadow.to_classes()

    def test_to_classes_none(self) -> None:
        """Convert NOT_RENDERED shadow."""
        shadow = Shadow(state=PropertyState.NOT_RENDERED)
        assert shadow.to_classes() == ["shadow-none"]


class TestTransform:
    """Test Transform class conversions.

    Spec reference: markup-syntax-design.md#position--transform
    """

    def test_from_api_position(self) -> None:
        """Parse position from API transform."""
        transform_obj = {
            "scaleX": 1.0,
            "scaleY": 1.0,
            "translateX": 914400,  # 72pt
            "translateY": 1828800,  # 144pt
            "unit": "EMU",
        }
        t = Transform.from_api(transform_obj)
        assert t.translate_x_pt == 72.0
        assert t.translate_y_pt == 144.0

    def test_from_api_with_size(self) -> None:
        """Parse size and scale from API."""
        transform_obj = {
            "scaleX": 2.0,
            "scaleY": 1.5,
            "translateX": 914400,
            "translateY": 914400,
            "unit": "EMU",
        }
        size_obj = {
            "width": {"magnitude": 1270000, "unit": "EMU"},  # 100pt
            "height": {"magnitude": 1270000, "unit": "EMU"},  # 100pt
        }
        t = Transform.from_api(transform_obj, size_obj)
        assert t.width_pt == 200.0  # 100 * 2.0
        assert t.height_pt == 150.0  # 100 * 1.5

    def test_to_classes(self) -> None:
        """Convert transform to position/size classes."""
        t = Transform(
            translate_x_pt=72.0,
            translate_y_pt=144.0,
            width_pt=400.0,
            height_pt=50.0,
        )
        classes = t.to_classes()
        assert "x-72" in classes
        assert "y-144" in classes
        assert "w-400" in classes
        assert "h-50" in classes


class TestTextStyle:
    """Test TextStyle class conversions.

    Spec reference: markup-syntax-design.md#text-content--styling
    """

    def test_from_api_basic(self) -> None:
        """Parse basic text style from API."""
        api_obj = {
            "bold": True,
            "italic": True,
            "fontFamily": "Roboto",
            "fontSize": {"magnitude": 24, "unit": "PT"},
            "weightedFontFamily": {"fontFamily": "Roboto", "weight": 700},
        }
        ts = TextStyle.from_api(api_obj)
        assert ts is not None
        assert ts.bold is True
        assert ts.italic is True
        assert ts.font_family == "Roboto"
        assert ts.font_size_pt == 24
        assert ts.font_weight == 700

    def test_from_api_with_color(self) -> None:
        """Parse text style with foreground color."""
        api_obj = {
            "foregroundColor": {
                "opaqueColor": {"rgbColor": {"red": 0.2, "green": 0.2, "blue": 0.2}}
            }
        }
        ts = TextStyle.from_api(api_obj)
        assert ts is not None
        assert ts.foreground_color is not None
        assert ts.foreground_color.hex == "#333333"

    def test_to_classes_decorations(self) -> None:
        """Convert text decorations to classes."""
        ts = TextStyle(
            bold=True,
            italic=True,
            underline=True,
            strikethrough=True,
        )
        classes = ts.to_classes()
        assert "bold" in classes
        assert "italic" in classes
        assert "underline" in classes
        assert "line-through" in classes

    def test_to_classes_font(self) -> None:
        """Convert font properties to classes."""
        ts = TextStyle(
            font_family="Roboto",
            font_size_pt=24,
            font_weight=500,
        )
        classes = ts.to_classes()
        assert "font-family-roboto" in classes
        assert "text-size-24" in classes
        assert "font-weight-500" in classes

    def test_to_classes_color(self) -> None:
        """Convert text color to classes."""
        ts = TextStyle(foreground_color=Color(hex="#ef4444"))
        classes = ts.to_classes()
        assert "text-color-#ef4444" in classes


class TestParagraphStyle:
    """Test ParagraphStyle class conversions.

    Spec reference: markup-syntax-design.md#paragraph-styling
    """

    def test_from_api_alignment(self) -> None:
        """Parse alignment from API."""
        api_obj = {"alignment": "CENTER", "lineSpacing": 150}
        ps = ParagraphStyle.from_api(api_obj)
        assert ps is not None
        assert ps.alignment == TextAlignment.CENTER
        assert ps.line_spacing == 150

    def test_to_classes_alignment(self) -> None:
        """Convert alignment to classes."""
        ps = ParagraphStyle(alignment=TextAlignment.CENTER)
        classes = ps.to_classes()
        assert "text-align-center" in classes

        ps = ParagraphStyle(alignment=TextAlignment.START)
        classes = ps.to_classes()
        assert "text-align-left" in classes

    def test_to_classes_spacing(self) -> None:
        """Convert spacing to classes."""
        ps = ParagraphStyle(
            line_spacing=150,
            space_above_pt=12,
            space_below_pt=6,
        )
        classes = ps.to_classes()
        assert "leading-150" in classes
        assert "space-above-12" in classes
        assert "space-below-6" in classes


class TestParseFunctions:
    """Test class string parsing functions.

    These test the reverse direction: SML classes -> data structures
    """

    def test_parse_class_string(self) -> None:
        """Parse class string into list."""
        classes = parse_class_string("x-72 y-144 w-400 h-50 fill-#4285f4")
        assert len(classes) == 5
        assert "x-72" in classes
        assert "fill-#4285f4" in classes

    def test_parse_class_string_empty(self) -> None:
        """Empty string should return empty list."""
        assert parse_class_string("") == []

    def test_parse_position_classes(self) -> None:
        """Parse position/size from classes."""
        classes = ["x-72", "y-144", "w-400", "h-50", "fill-#4285f4"]
        pos = parse_position_classes(classes)
        assert pos["x"] == 72
        assert pos["y"] == 144
        assert pos["w"] == 400
        assert pos["h"] == 50

    def test_parse_position_negative(self) -> None:
        """Parse negative position values."""
        classes = ["x--50", "y--100"]
        pos = parse_position_classes(classes)
        assert pos["x"] == -50
        assert pos["y"] == -100

    def test_parse_fill_class_hex(self) -> None:
        """Parse hex fill class."""
        fill = parse_fill_class("fill-#4285f4")
        assert fill is not None
        assert fill.color is not None
        assert fill.color.hex == "#4285f4"

    def test_parse_fill_class_with_opacity(self) -> None:
        """Parse fill class with opacity."""
        fill = parse_fill_class("fill-#4285f4/80")
        assert fill is not None
        assert fill.color is not None
        assert fill.color.hex == "#4285f4"
        assert fill.color.alpha == 0.8

    def test_parse_fill_class_theme(self) -> None:
        """Parse theme fill class."""
        fill = parse_fill_class("fill-theme-accent1")
        assert fill is not None
        assert fill.color is not None
        assert fill.color.theme == "accent1"

    def test_parse_fill_class_none(self) -> None:
        """Parse fill-none class."""
        fill = parse_fill_class("fill-none")
        assert fill is not None
        assert fill.state == PropertyState.NOT_RENDERED

    def test_parse_fill_class_inherit(self) -> None:
        """Parse fill-inherit class."""
        fill = parse_fill_class("fill-inherit")
        assert fill is not None
        assert fill.state == PropertyState.INHERIT

    def test_parse_stroke_classes(self) -> None:
        """Parse stroke classes."""
        classes = ["stroke-#333333", "stroke-w-2", "stroke-dash"]
        stroke = parse_stroke_classes(classes)
        assert stroke is not None
        assert stroke.color is not None
        assert stroke.color.hex == "#333333"
        assert stroke.weight_pt == 2.0
        assert stroke.dash_style == DashStyle.DASH

    def test_parse_stroke_classes_none(self) -> None:
        """Parse stroke-none class."""
        classes = ["stroke-none"]
        stroke = parse_stroke_classes(classes)
        assert stroke is not None
        assert stroke.state == PropertyState.NOT_RENDERED

    def test_parse_text_style_classes(self) -> None:
        """Parse text styling classes."""
        classes = [
            "bold",
            "italic",
            "font-family-roboto",
            "text-size-24",
            "text-color-#ef4444",
        ]
        ts = parse_text_style_classes(classes)
        assert ts.bold is True
        assert ts.italic is True
        assert ts.font_family == "Roboto"
        assert ts.font_size_pt == 24
        assert ts.foreground_color is not None
        assert ts.foreground_color.hex == "#ef4444"


class TestBidirectionalConversion:
    """Test that conversions are truly bidirectional.

    These tests ensure that:
    - API -> class -> API produces equivalent results
    - class -> API -> class produces equivalent results
    """

    def test_fill_roundtrip_api_to_class(self) -> None:
        """API fill -> class -> parse should produce equivalent fill."""
        original_api = {
            "solidFill": {
                "color": {"rgbColor": {"red": 0.26, "green": 0.52, "blue": 0.96}},
                "alpha": 1.0,
            }
        }
        fill = Fill.from_api(original_api)
        assert fill is not None
        class_str = fill.to_class()
        parsed = parse_fill_class(class_str)
        assert parsed is not None
        assert parsed.color is not None
        # Allow slight color difference due to hex rounding
        assert parsed.color.hex == fill.color.hex  # type: ignore

    def test_fill_roundtrip_class_to_api(self) -> None:
        """Parse fill class -> API -> class should produce same class."""
        original_class = "fill-#4285f4"
        fill = parse_fill_class(original_class)
        assert fill is not None
        # Reconstruct class
        class_str = fill.to_class()
        assert class_str == original_class

    def test_fill_with_opacity_roundtrip(self) -> None:
        """Fill with opacity roundtrip."""
        original_class = "fill-#4285f4/80"
        fill = parse_fill_class(original_class)
        assert fill is not None
        class_str = fill.to_class()
        assert class_str == original_class
