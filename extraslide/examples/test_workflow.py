"""Test the SML workflow with a real presentation."""

from gslidesx.client import SlidesClient

# Configuration
GATEWAY_URL = "https://extrasuite.think41.com"
PRESENTATION_URL = "https://docs.google.com/presentation/d/1uYM6hFtsldnV4Z1fM1ITob6gem9_nqtOKf-nlQ7hZyc/edit"


def main():
    client = SlidesClient(gateway_url=GATEWAY_URL)

    # 1. Fetch the presentation as SML
    print("Fetching presentation...")
    original_sml = client.fetch(PRESENTATION_URL)
    print(f"Fetched {len(original_sml)} characters of SML")

    # 2. Make edits to the SML
    edited_sml = original_sml

    # Change "90+" to "100+" team members
    edited_sml = edited_sml.replace(
        '<T range="0-1" class="font-family-roboto text-size-10.45 text-color-#000000">9</T>\n          <T range="1-3" class="font-family-roboto text-size-10.45 text-color-#000000">0+</T>',
        '<T range="0-4" class="font-family-roboto text-size-10.45 text-color-#000000">100+</T>',
    )

    # 3. Add a new "Focus Areas" slide at the end (before </Presentation>)
    new_slide = """
  <Slide id="focus_areas_slide" layout="g3b91ac73820_0_424" master="g3b91ac73820_0_404" class="bg-#efefef">
    <!-- Title bar accent -->
    <Rect id="focus_title_accent" class="x-25.82 y-0 w-14.17 h-46.23 fill-theme-light2 stroke-none shadow-none content-middle autofit-none"/>

    <!-- Title: FOCUS -->
    <TextBox id="focus_title1" class="x-15.46 y-5.38 w-154.61 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-6">
        <T range="0-5" class="bold font-family-roboto text-size-18 font-weight-900 text-color-theme-dark1">FOCUS</T>
      </P>
    </TextBox>

    <!-- Title: AREAS -->
    <TextBox id="focus_title2" class="x-15.46 y-29.13 w-154.61 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-6">
        <T range="0-5" class="bold font-family-roboto text-size-18 font-weight-900 text-color-#0d5cdf">AREAS</T>
      </P>
    </TextBox>

    <!-- Subtitle -->
    <TextBox id="focus_subtitle" class="x-200 y-15 w-400 h-30 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-50">
        <T range="0-49" class="font-family-roboto text-size-10 text-color-#595959">Generative AI domains where Think41 delivers impact</T>
      </P>
    </TextBox>

    <!-- Box 1: Voice AI -->
    <Rect id="focus_box1_header" class="x-40 y-70 w-200 h-30 fill-#1155cc stroke-none shadow-none content-middle autofit-none">
      <P range="0-9">
        <T range="0-8" class="bold font-family-open-sans text-size-12 text-color-#ffffff">Voice AI</T>
      </P>
    </Rect>
    <Rect id="focus_box1_body" class="x-40 y-100 w-200 h-80 fill-none stroke-#1155cc stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">Conversational AI agents for customer service, sales support, and enterprise workflows with natural speech.</T>
      </P>
    </Rect>

    <!-- Box 2: AI Agents -->
    <Rect id="focus_box2_header" class="x-260 y-70 w-200 h-30 fill-#38761d stroke-none shadow-none content-middle autofit-none">
      <P range="0-10">
        <T range="0-9" class="bold font-family-open-sans text-size-12 text-color-#ffffff">AI Agents</T>
      </P>
    </Rect>
    <Rect id="focus_box2_body" class="x-260 y-100 w-200 h-80 fill-none stroke-#38761d stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">Autonomous agents that execute complex tasks, integrate with enterprise systems, and learn from interactions.</T>
      </P>
    </Rect>

    <!-- Box 3: RAG & Knowledge -->
    <Rect id="focus_box3_header" class="x-480 y-70 w-200 h-30 fill-#f1c232 stroke-none shadow-none content-middle autofit-none">
      <P range="0-16">
        <T range="0-15" class="bold font-family-open-sans text-size-12 text-color-#ffffff">RAG &amp; Knowledge</T>
      </P>
    </Rect>
    <Rect id="focus_box3_body" class="x-480 y-100 w-200 h-80 fill-none stroke-#f1c232 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">Retrieval-augmented generation systems for enterprise knowledge bases, documentation, and support.</T>
      </P>
    </Rect>

    <!-- Box 4: Code Generation -->
    <Rect id="focus_box4_header" class="x-40 y-200 w-200 h-30 fill-#674ea7 stroke-none shadow-none content-middle autofit-none">
      <P range="0-16">
        <T range="0-15" class="bold font-family-open-sans text-size-12 text-color-#ffffff">Code Generation</T>
      </P>
    </Rect>
    <Rect id="focus_box4_body" class="x-40 y-230 w-200 h-80 fill-none stroke-#674ea7 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">AI-powered development tools, code review automation, and intelligent IDE integrations for faster delivery.</T>
      </P>
    </Rect>

    <!-- Box 5: Document Intelligence -->
    <Rect id="focus_box5_header" class="x-260 y-200 w-200 h-30 fill-#cc0000 stroke-none shadow-none content-middle autofit-none">
      <P range="0-22">
        <T range="0-21" class="bold font-family-open-sans text-size-12 text-color-#ffffff">Document Intelligence</T>
      </P>
    </Rect>
    <Rect id="focus_box5_body" class="x-260 y-230 w-200 h-80 fill-none stroke-#cc0000 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">Automated document processing, extraction, and analysis for contracts, invoices, and compliance.</T>
      </P>
    </Rect>

    <!-- Box 6: Multimodal AI -->
    <Rect id="focus_box6_header" class="x-480 y-200 w-200 h-30 fill-#0b5394 stroke-none shadow-none content-middle autofit-none">
      <P range="0-14">
        <T range="0-13" class="bold font-family-open-sans text-size-12 text-color-#ffffff">Multimodal AI</T>
      </P>
    </Rect>
    <Rect id="focus_box6_body" class="x-480 y-230 w-200 h-80 fill-none stroke-#0b5394 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-8 text-color-#595959">Vision, audio, and text models combined for rich enterprise applications and content understanding.</T>
      </P>
    </Rect>

    <!-- Think41 logo footer -->
    <TextBox id="focus_footer" class="x-630 y-380 w-80 h-20 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-8 text-color-#0060c7">Think41</T>
      </P>
    </TextBox>
  </Slide>
"""

    # Insert new slide before closing </Presentation> tag
    edited_sml = edited_sml.replace("</Presentation>", new_slide + "\n</Presentation>")

    # 4. Preview changes
    print("\n--- PREVIEW CHANGES ---")
    requests = client.preview(original_sml, edited_sml)
    print(f"Generated {len(requests)} API requests:")
    for i, req in enumerate(requests):
        req_type = next(iter(req.keys()))
        if req_type == "createSlide":
            print(f"  {i + 1}. {req_type}: {req[req_type].get('objectId', 'N/A')}")
        elif req_type == "createShape":
            print(
                f"  {i + 1}. {req_type}: {req[req_type].get('objectId', 'N/A')} ({req[req_type].get('shapeType', 'N/A')})"
            )
        elif req_type == "insertText":
            text = req[req_type].get("text", "")[:30]
            print(f"  {i + 1}. {req_type}: '{text}...'")
        elif req_type == "deleteObject":
            print(f"  {i + 1}. {req_type}: {req[req_type].get('objectId', 'N/A')}")
        else:
            print(f"  {i + 1}. {req_type}")

    # 5. Ask for confirmation before pushing
    print("\n" + "=" * 50)
    response = input("Push these changes to Google Slides? (yes/no): ")

    if response.lower() == "yes":
        print("\nPushing changes...")
        result = client.push(PRESENTATION_URL, original_sml, edited_sml)
        print(f"Success! API response: {len(result.get('replies', []))} replies")
        print(f"\nView your presentation: {PRESENTATION_URL}")
    else:
        print("Cancelled.")


if __name__ == "__main__":
    main()
