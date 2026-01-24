"""Create a focused 3-slide deck for fintech founder meeting."""

from gslidesx.client import SlidesClient

# Configuration
GATEWAY_URL = "https://extrasuite.think41.com"
PRESENTATION_URL = "https://docs.google.com/presentation/d/1ympcBjPuQOzBKCfEPMMLlUPWAg65qivhQOPU6zfknRc/edit"


def main():
    client = SlidesClient(gateway_url=GATEWAY_URL)

    # 1. Fetch the presentation as SML
    print("Fetching presentation...")
    original_sml = client.fetch(PRESENTATION_URL)
    print(f"Fetched {len(original_sml)} characters of SML")

    # 2. Create 3 new focused slides for the fintech meeting
    # Using same layout/master as existing slides for consistency

    new_slides = """
  <!-- FINTECH MEETING DECK - 3 Simple Slides -->

  <!-- Slide 1: About Think41 -->
  <Slide id="fintech_slide_1" layout="g32614932996_0_9265" master="g32614932996_0_9034" class="bg-#efefef">
    <!-- Title bar accent -->
    <Rect id="ft1_accent" class="x-25.82 y-0 w-14.17 h-46.23 fill-theme-light2 stroke-none shadow-none content-middle autofit-none"/>

    <!-- Title -->
    <TextBox id="ft1_title1" class="x-15.46 y-5.38 w-200 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-6">
        <T range="0-5" class="bold font-family-roboto text-size-16 text-color-theme-dark1">ABOUT</T>
      </P>
    </TextBox>
    <TextBox id="ft1_title2" class="x-15.46 y-29.13 w-200 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-16 text-color-#0060c7">THINK41</T>
      </P>
    </TextBox>

    <!-- Main tagline -->
    <TextBox id="ft1_tagline" class="x-40 y-80 w-640 h-50 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-80">
        <T range="0-9" class="font-family-montserrat text-size-18 text-color-#434343">We are an </T>
        <T range="9-35" class="bold font-family-montserrat text-size-18 text-color-#1155cc">AI-first engineering firm</T>
        <T range="35-79" class="font-family-montserrat text-size-18 text-color-#434343"> built to push enterprises into real-world AI impact</T>
      </P>
    </TextBox>

    <!-- Key Stats Row -->
    <Rect id="ft1_stat1_box" class="x-60 y-150 w-130 h-80 fill-#ffffff stroke-#e0e0e0 stroke-w-1 shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-28 text-color-#1155cc">2024</T>
      </P>
      <P range="8-20">
        <T range="8-19" class="font-family-roboto text-size-10 text-color-#595959">Year Founded</T>
      </P>
    </Rect>

    <Rect id="ft1_stat2_box" class="x-210 y-150 w-130 h-80 fill-#ffffff stroke-#e0e0e0 stroke-w-1 shadow-none content-middle autofit-none">
      <P range="0-4">
        <T range="0-3" class="bold font-family-roboto text-size-28 text-color-#38761d">80+</T>
      </P>
      <P range="4-18">
        <T range="4-17" class="font-family-roboto text-size-10 text-color-#595959">Team Members</T>
      </P>
    </Rect>

    <Rect id="ft1_stat3_box" class="x-360 y-150 w-130 h-80 fill-#ffffff stroke-#e0e0e0 stroke-w-1 shadow-none content-middle autofit-none">
      <P range="0-4">
        <T range="0-3" class="bold font-family-roboto text-size-28 text-color-#f1c232">10+</T>
      </P>
      <P range="4-23">
        <T range="4-22" class="font-family-roboto text-size-10 text-color-#595959">AI Implementations</T>
      </P>
    </Rect>

    <Rect id="ft1_stat4_box" class="x-510 y-150 w-150 h-80 fill-#ffffff stroke-#e0e0e0 stroke-w-1 shadow-none content-middle autofit-none">
      <P range="0-10">
        <T range="0-9" class="bold font-family-roboto text-size-16 text-color-#674ea7">Bangalore</T>
      </P>
      <P range="10-16">
        <T range="10-15" class="font-family-roboto text-size-10 text-color-#595959">Based</T>
      </P>
    </Rect>

    <!-- Founding Team Highlight -->
    <Rect id="ft1_team_box" class="x-40 y-260 w-640 h-100 fill-#f8f9fa stroke-none shadow-none content-top autofit-none">
      <P range="0-20">
        <T range="0-19" class="bold font-family-roboto text-size-12 text-color-#434343">Leadership Team</T>
      </P>
      <P range="20-120">
        <T range="20-119" class="font-family-roboto text-size-10 text-color-#595959">Ex-Deloitte leaders who built HashedIn (acquired by Deloitte US in 2021) and scaled it to 3500+ members. Now building Think41 - a GenAI-specialized firm.</T>
      </P>
      <P range="120-220">
        <T range="120-219" class="font-family-roboto text-size-9 text-color-#888888">Harshit (Strategy, ISB), Himanshu (Engineering, IIT Guwahati), Sripathi (CTO, RedisLabs founder), Anshuman (Product, IIT BHU)</T>
      </P>
    </Rect>

    <!-- Think41 logo footer -->
    <TextBox id="ft1_footer" class="x-630 y-380 w-80 h-20 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-8 text-color-#0060c7">Think41</T>
      </P>
    </TextBox>
  </Slide>

  <!-- Slide 2: What We Can Do For You -->
  <Slide id="fintech_slide_2" layout="g32614932996_0_9265" master="g32614932996_0_9034" class="bg-#efefef">
    <!-- Title bar accent -->
    <Rect id="ft2_accent" class="x-25.82 y-0 w-14.17 h-46.23 fill-theme-light2 stroke-none shadow-none content-middle autofit-none"/>

    <!-- Title -->
    <TextBox id="ft2_title1" class="x-15.46 y-5.38 w-250 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-7">
        <T range="0-6" class="bold font-family-roboto text-size-16 text-color-theme-dark1">AI FOR</T>
      </P>
    </TextBox>
    <TextBox id="ft2_title2" class="x-15.46 y-29.13 w-250 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-16 text-color-#0060c7">FINTECH</T>
      </P>
    </TextBox>

    <!-- Subtitle -->
    <TextBox id="ft2_subtitle" class="x-40 y-70 w-640 h-30 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-60">
        <T range="0-59" class="font-family-roboto text-size-11 text-color-#595959">We build AI agents that automate complex financial workflows with compliance built-in</T>
      </P>
    </TextBox>

    <!-- Three capability boxes -->
    <Rect id="ft2_cap1_header" class="x-40 y-110 w-200 h-30 fill-#1155cc stroke-none shadow-none content-middle autofit-none">
      <P range="0-15">
        <T range="0-14" class="bold font-family-open-sans text-size-11 text-color-#ffffff">Voice AI Agents</T>
      </P>
    </Rect>
    <Rect id="ft2_cap1_body" class="x-40 y-140 w-200 h-100 fill-#ffffff stroke-#1155cc stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-9 text-color-#595959">Conversational AI for customer service, loan queries, and account support. Natural speech with context awareness.</T>
      </P>
    </Rect>

    <Rect id="ft2_cap2_header" class="x-260 y-110 w-200 h-30 fill-#38761d stroke-none shadow-none content-middle autofit-none">
      <P range="0-20">
        <T range="0-19" class="bold font-family-open-sans text-size-11 text-color-#ffffff">Workflow Automation</T>
      </P>
    </Rect>
    <Rect id="ft2_cap2_body" class="x-260 y-140 w-200 h-100 fill-#ffffff stroke-#38761d stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-110">
        <T range="0-109" class="font-family-roboto text-size-9 text-color-#595959">AI agents that handle mortgage modifications, KYC onboarding, loan processing. Human-in-loop for critical decisions.</T>
      </P>
    </Rect>

    <Rect id="ft2_cap3_header" class="x-480 y-110 w-200 h-30 fill-#f1c232 stroke-none shadow-none content-middle autofit-none">
      <P range="0-22">
        <T range="0-21" class="bold font-family-open-sans text-size-11 text-color-#ffffff">Document Intelligence</T>
      </P>
    </Rect>
    <Rect id="ft2_cap3_body" class="x-480 y-140 w-200 h-100 fill-#ffffff stroke-#f1c232 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-100">
        <T range="0-99" class="font-family-roboto text-size-9 text-color-#595959">Automated extraction and analysis for contracts, invoices, compliance docs. Audit trails for regulatory needs.</T>
      </P>
    </Rect>

    <!-- Why Finance is Different -->
    <Rect id="ft2_diff_box" class="x-40 y-260 w-640 h-100 fill-#f8f9fa stroke-none shadow-none content-top autofit-none">
      <P range="0-35">
        <T range="0-34" class="bold font-family-roboto text-size-11 text-color-#434343">Why AI in Finance is Different</T>
      </P>
      <P range="35-150">
        <T range="35-149" class="font-family-roboto text-size-9 text-color-#595959">We understand BFSI demands: strict data privacy, auditability, high cost of errors, and regulatory compliance. Our agents are built with:</T>
      </P>
      <P range="150-250">
        <T range="150-249" class="font-family-roboto text-size-9 text-color-#434343">Privacy (on-premise/VPC) | Explainability (audit trails) | Control (bounded decisions) | Human-in-loop checkpoints</T>
      </P>
    </Rect>

    <!-- Think41 logo footer -->
    <TextBox id="ft2_footer" class="x-630 y-380 w-80 h-20 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-8 text-color-#0060c7">Think41</T>
      </P>
    </TextBox>
  </Slide>

  <!-- Slide 3: How We Work -->
  <Slide id="fintech_slide_3" layout="g32614932996_0_9265" master="g32614932996_0_9034" class="bg-#efefef">
    <!-- Title bar accent -->
    <Rect id="ft3_accent" class="x-25.82 y-0 w-14.17 h-46.23 fill-theme-light2 stroke-none shadow-none content-middle autofit-none"/>

    <!-- Title -->
    <TextBox id="ft3_title1" class="x-15.46 y-5.38 w-250 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-16 text-color-theme-dark1">HOW WE</T>
      </P>
    </TextBox>
    <TextBox id="ft3_title2" class="x-15.46 y-29.13 w-250 h-36.35 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-5">
        <T range="0-4" class="bold font-family-roboto text-size-16 text-color-#0060c7">WORK</T>
      </P>
    </TextBox>

    <!-- Subtitle -->
    <TextBox id="ft3_subtitle" class="x-40 y-70 w-640 h-30 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-55">
        <T range="0-54" class="font-family-roboto text-size-11 text-color-#595959">Pod-based deployment model for focused, outcome-driven delivery</T>
      </P>
    </TextBox>

    <!-- Five pillars of engagement -->
    <Rect id="ft3_pillar1" class="x-40 y-110 w-125 h-90 fill-#1155cc stroke-none shadow-none content-middle autofit-none">
      <P range="0-20">
        <T range="0-19" class="bold font-family-roboto text-size-11 text-color-#ffffff">Dedicated Pod</T>
      </P>
      <P range="20-60">
        <T range="20-59" class="font-family-roboto text-size-9 text-color-#ffffff">Minimum 5 member team assigned to you</T>
      </P>
    </Rect>

    <Rect id="ft3_pillar2" class="x-175 y-110 w-125 h-90 fill-#38761d stroke-none shadow-none content-middle autofit-none">
      <P range="0-20">
        <T range="0-19" class="bold font-family-roboto text-size-11 text-color-#ffffff">Weekly Billing</T>
      </P>
      <P range="20-70">
        <T range="20-69" class="font-family-roboto text-size-9 text-color-#ffffff">Transparent weekly cycles. No long-term lock-ins.</T>
      </P>
    </Rect>

    <Rect id="ft3_pillar3" class="x-310 y-110 w-125 h-90 fill-#f1c232 stroke-none shadow-none content-middle autofit-none">
      <P range="0-20">
        <T range="0-19" class="bold font-family-roboto text-size-10 text-color-#ffffff">Defined Objective</T>
      </P>
      <P range="20-70">
        <T range="20-69" class="font-family-roboto text-size-9 text-color-#ffffff">Clear scope and measurable outcomes agreed upfront</T>
      </P>
    </Rect>

    <Rect id="ft3_pillar4" class="x-445 y-110 w-125 h-90 fill-#674ea7 stroke-none shadow-none content-middle autofit-none">
      <P range="0-15">
        <T range="0-14" class="bold font-family-roboto text-size-10 text-color-#ffffff">Embedded Team</T>
      </P>
      <P range="15-60">
        <T range="15-59" class="font-family-roboto text-size-9 text-color-#ffffff">Works alongside your team, not in isolation</T>
      </P>
    </Rect>

    <Rect id="ft3_pillar5" class="x-580 y-110 w-100 h-90 fill-#cc0000 stroke-none shadow-none content-middle autofit-none">
      <P range="0-15">
        <T range="0-14" class="bold font-family-roboto text-size-10 text-color-#ffffff">AI-Native</T>
      </P>
      <P range="15-50">
        <T range="15-49" class="font-family-roboto text-size-9 text-color-#ffffff">GenAI tools in our DNA</T>
      </P>
    </Rect>

    <!-- What you get -->
    <Rect id="ft3_details_box" class="x-40 y-220 w-640 h-140 fill-#ffffff stroke-#e0e0e0 stroke-w-1 shadow-none content-top autofit-none">
      <P range="0-25">
        <T range="0-24" class="bold font-family-roboto text-size-12 text-color-#434343">Typical Engagement</T>
      </P>
      <P range="25-50">
        <T range="25-49" class="font-family-roboto text-size-10 text-color-#595959"> </T>
      </P>
      <P range="50-130">
        <T range="50-54" class="bold font-family-roboto text-size-10 text-color-#1155cc">Pod:</T>
        <T range="54-129" class="font-family-roboto text-size-10 text-color-#595959"> 1 Tech PM + 4-5 Engineers (AI/ML, Backend, Frontend as needed)</T>
      </P>
      <P range="130-200">
        <T range="130-140" class="bold font-family-roboto text-size-10 text-color-#38761d">Duration:</T>
        <T range="140-199" class="font-family-roboto text-size-10 text-color-#595959"> Typically 8-12 weeks for initial AI agent deployment</T>
      </P>
      <P range="200-280">
        <T range="200-210" class="bold font-family-roboto text-size-10 text-color-#f1c232">Cadence:</T>
        <T range="210-279" class="font-family-roboto text-size-10 text-color-#595959"> Weekly demos, daily standups with your team, sprint-based delivery</T>
      </P>
      <P range="280-380">
        <T range="280-290" class="bold font-family-roboto text-size-10 text-color-#674ea7">Outcome:</T>
        <T range="290-379" class="font-family-roboto text-size-10 text-color-#595959"> Production-ready AI agent with monitoring, eval framework, and handover docs</T>
      </P>
    </Rect>

    <!-- Think41 logo footer -->
    <TextBox id="ft3_footer" class="x-630 y-380 w-80 h-20 fill-none stroke-none shadow-none content-middle autofit-none">
      <P range="0-8">
        <T range="0-7" class="bold font-family-roboto text-size-8 text-color-#0060c7">Think41</T>
      </P>
    </TextBox>
  </Slide>
"""

    # Insert new slides before closing </Presentation> tag
    edited_sml = original_sml.replace(
        "</Presentation>", new_slides + "\n</Presentation>"
    )

    # 3. Preview changes
    print("\n--- PREVIEW CHANGES ---")
    requests = client.preview(original_sml, edited_sml)
    print(f"Generated {len(requests)} API requests:")

    # Summarize request types
    req_types = {}
    for req in requests:
        req_type = next(iter(req.keys()))
        req_types[req_type] = req_types.get(req_type, 0) + 1

    for req_type, count in sorted(req_types.items()):
        print(f"  {req_type}: {count}")

    # 4. Ask for confirmation before pushing
    print("\n" + "=" * 50)
    response = input("Push these 3 new slides to Google Slides? (yes/no): ")

    if response.lower() == "yes":
        print("\nPushing changes...")
        result = client.push(PRESENTATION_URL, original_sml, edited_sml)
        print(f"Success! API response: {len(result.get('replies', []))} replies")
        print(f"\nView your presentation: {PRESENTATION_URL}")
        print("\nThe 3 new slides have been added at the end:")
        print("  1. About Think41 - Company overview and key stats")
        print("  2. AI for Fintech - What we can do for you")
        print("  3. How We Work - Pod-based engagement model")
    else:
        print("Cancelled.")


if __name__ == "__main__":
    main()
