# DocumentStyle

The style of the document.

**Type:** object

## Properties

- **background** ([Background](background.md)): The background of the document. Documents cannot have a transparent background color.
- **defaultHeaderId** (string): The ID of the default header. If not set, there's no default header. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **defaultFooterId** (string): The ID of the default footer. If not set, there's no default footer. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **evenPageHeaderId** (string): The ID of the header used only for even pages. The value of use_even_page_header_footer determines whether to use the default_header_id or this value for the header on even pages. If not set, there's no even page header. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **evenPageFooterId** (string): The ID of the footer used only for even pages. The value of use_even_page_header_footer determines whether to use the default_footer_id or this value for the footer on even pages. If not set, there's no even page footer. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **firstPageHeaderId** (string): The ID of the header used only for the first page. If not set then a unique header for the first page does not exist. The value of use_first_page_header_footer determines whether to use the default_header_id or this value for the header on the first page. If not set, there's no first page header. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **firstPageFooterId** (string): The ID of the footer used only for the first page. If not set then a unique footer for the first page does not exist. The value of use_first_page_header_footer determines whether to use the default_footer_id or this value for the footer on the first page. If not set, there's no first page footer. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **useFirstPageHeaderFooter** (boolean): Indicates whether to use the first page header / footer IDs for the first page. If DocumentMode is PAGELESS, this property will not be rendered.
- **useEvenPageHeaderFooter** (boolean): Indicates whether to use the even page header / footer IDs for the even pages. If DocumentMode is PAGELESS, this property will not be rendered.
- **pageNumberStart** (integer): The page number from which to start counting the number of pages. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginTop** ([Dimension](dimension.md)): The top page margin. Updating the top page margin on the document style clears the top page margin on all section styles. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginBottom** ([Dimension](dimension.md)): The bottom page margin. Updating the bottom page margin on the document style clears the bottom page margin on all section styles. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginRight** ([Dimension](dimension.md)): The right page margin. Updating the right page margin on the document style clears the right page margin on all section styles. It may also cause columns to resize in all sections. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginLeft** ([Dimension](dimension.md)): The left page margin. Updating the left page margin on the document style clears the left page margin on all section styles. It may also cause columns to resize in all sections. If DocumentMode is PAGELESS, this property will not be rendered.
- **pageSize** ([Size](size.md)): The size of a page in the document. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginHeader** ([Dimension](dimension.md)): The amount of space between the top of the page and the contents of the header. If DocumentMode is PAGELESS, this property will not be rendered.
- **marginFooter** ([Dimension](dimension.md)): The amount of space between the bottom of the page and the contents of the footer. If DocumentMode is PAGELESS, this property will not be rendered.
- **useCustomHeaderFooterMargins** (boolean): Indicates whether DocumentStyle margin_header, SectionStyle margin_header and DocumentStyle margin_footer, SectionStyle margin_footer are respected. When false, the default values in the Docs editor for header and footer margin is used. If DocumentMode is PAGELESS, this property will not be rendered. This property is read-only.
- **flipPageOrientation** (boolean): Optional. Indicates whether to flip the dimensions of the page_size, which allows changing the page orientation between portrait and landscape. If DocumentMode is PAGELESS, this property will not be rendered.
- **documentFormat** ([DocumentFormat](documentformat.md)): Specifies document-level format settings, such as the document mode (pages vs pageless).
