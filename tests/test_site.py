import json
import html
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PAGES = ("index.html", "about.html", "contact.html")
PRODUCTION_ORIGIN = "https://www.sen-tutor.co.uk"


class ReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.ids = set()
        self.skill_buttons = []
        self.dialogs = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "button" and "data-skill-dialog" in attributes:
            self.skill_buttons.append(attributes)
        if tag == "dialog":
            self.dialogs.append(attributes)
        if tag == "img":
            self.images.append(attributes)
        for name in ("href", "src"):
            if attributes.get(name):
                self.references.append(attributes[name])


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.html_attributes = {}
        self.metas = []
        self.links = []
        self.title_parts = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.html_attributes = attributes
        elif tag == "meta":
            self.metas.append(attributes)
        elif tag == "link":
            self.links.append(attributes)
        elif tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return "".join(self.title_parts).strip()

    def meta(self, attribute, value):
        return [item for item in self.metas if item.get(attribute, "").lower() == value.lower()]

    def link(self, rel, **attributes):
        return [
            item for item in self.links
            if rel.lower() in item.get("rel", "").lower().split()
            and all(item.get(name) == value for name, value in attributes.items())
        ]


class HeadingParser(HTMLParser):
    LEVELS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.headings = []
        self._depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.LEVELS:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self.LEVELS and self._depth:
            self._depth -= 1
            if not self._depth:
                self.headings.append(" ".join("".join(self._parts).split()))
                self._parts = []

    def handle_data(self, data):
        if self._depth:
            self._parts.append(data)


def collect_headings(page):
    parser = HeadingParser()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser.headings


CLEAN_URLS = {"/": "index.html", "/about": "about.html", "/contact": "contact.html"}


def local_target(page, reference):
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or reference.startswith(("data:", "mailto:", "tel:")):
        return None
    path = unquote(parsed.path)
    if path in CLEAN_URLS:
        return (ROOT / CLEAN_URLS[path]).resolve(), parsed.fragment
    if path.startswith("/"):
        return (ROOT / path.lstrip("/")).resolve(), parsed.fragment
    target = (page.parent / path).resolve() if path else page.resolve()
    return target, parsed.fragment


class ModernSiteAcceptanceTests(unittest.TestCase):
    SKILL_TITLES = (
        "General SEN",
        "Dyslexia",
        "Dyspraxia",
        "Dyscalculia",
        "ADHD",
        "Autism",
        "Anxiety",
        "Executive functioning skills",
        "Visual impairment",
        "Social communication",
        "Other skills",
    )

    def test_github_pages_entrypoint_is_the_modern_standalone_homepage(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertTrue(homepage.lstrip().lower().startswith("<!doctype html>"))
        self.assertNotIn("layout:", homepage[:100])
        for text in ("Every child can", "Skills", "Testimonials", "Calm mode"):
            self.assertIn(text, homepage)

    def test_expected_pages_and_assets_are_at_root_paths(self):
        expected = [
            *PAGES,
            "css/style.css",
            "js/main.js",
            "images/profile.png",
            "images/linkedin-logo.png",
            "images/learning-pathways.webp",
            *(f"images/skill-{name}.webp" for name in (
                "general", "dyslexia", "dyspraxia", "dyscalculia", "adhd",
                "autism", "anxiety", "executive", "visual", "social", "other",
            )),
        ]
        for relative_path in expected:
            with self.subTest(path=relative_path):
                path = ROOT / relative_path
                self.assertTrue(path.is_file(), f"missing {relative_path}")
                self.assertGreater(path.stat().st_size, 0, f"empty {relative_path}")

    def test_local_page_asset_and_fragment_references_resolve(self):
        parsers = {}
        for page_name in PAGES:
            page = ROOT / page_name
            parser = ReferenceParser()
            parser.feed(page.read_text(encoding="utf-8"))
            parsers[page.resolve()] = parser

        failures = []
        for page, parser in parsers.items():
            for reference in parser.references:
                resolved = local_target(page, reference)
                if resolved is None:
                    continue
                target, fragment = resolved
                if not target.is_file():
                    failures.append(f"{page.name}: {reference} -> missing {target.relative_to(ROOT)}")
                    continue
                if fragment and target.suffix.lower() == ".html":
                    target_parser = parsers.get(target)
                    if target_parser is None:
                        target_parser = ReferenceParser()
                        target_parser.feed(target.read_text(encoding="utf-8"))
                    if fragment not in target_parser.ids:
                        failures.append(f"{page.name}: {reference} -> missing fragment #{fragment}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_css_local_urls_resolve(self):
        stylesheet = ROOT / "css" / "style.css"
        css = stylesheet.read_text(encoding="utf-8")
        failures = []
        for reference in re.findall(r"url\(\s*['\"]?([^)'\"]+)", css):
            if reference.startswith(("data:", "http://", "https://", "#")):
                continue
            target = (stylesheet.parent / unquote(urlsplit(reference).path)).resolve()
            if not target.is_file():
                failures.append(f"{reference} -> missing {target.relative_to(ROOT)}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_design_uses_colour_images_and_interactive_script(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r'<img\b', homepage, re.I)), 2)
        for colour in ("--coral", "--teal", "--sun", "--grape"):
            self.assertIn(colour, stylesheet)
        for feature in ("calm",):
            self.assertIn(feature, script.lower())

    def test_primary_actions_and_cta_use_verified_high_contrast_tokens(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(stylesheet, r"--accessible-action-bg:\s*#8b2437\s*;")
        self.assertRegex(stylesheet, r"(?i)--accessible-action-text:\s*#fff(?:fff)?\s*;")
        self.assertRegex(
            stylesheet,
            r"\.btn-primary\s*\{[^}]*background:\s*var\(--accessible-action-bg\)[^}]*"
            r"color:\s*var\(--accessible-action-text\)",
        )
        self.assertRegex(
            stylesheet,
            r"\.cta-banner\s*\{[^}]*color:\s*var\(--ink\)",
        )

    def test_reveals_are_progressively_enhanced_and_visible_without_javascript(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        self.assertRegex(stylesheet, r"\.reveal\s*\{[^}]*opacity:\s*1\s*;[^}]*transform:\s*none\s*;")
        self.assertRegex(stylesheet, r"\.js-ready\s+\.reveal\s*\{[^}]*opacity:\s*0\s*;")
        self.assertIn('document.documentElement.classList.add("js-ready")', script)

    def test_secondary_age_images_break_up_the_homepage_content(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('loading="lazy"', homepage)
        help_banner = homepage[
            homepage.index('<div class="help-banner'):
            homepage.index('</div>', homepage.index('<div class="banner-text"')) + len('</div>')
        ]
        self.assertIn('src="images/learning-pathways.webp"', help_banner)
        self.assertIn(
            'alt="Tangled study pathways becoming organised for secondary learners"',
            help_banner,
        )

    def test_philosophy_is_a_scannable_four_row_synthesis(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        philosophy = homepage[
            homepage.index('<section class="philosophy"'):
            homepage.index('<!-- ================= skills ================= -->')
        ]

        self.assertIn('class="philo-copy"', philosophy)
        self.assertEqual(4, philosophy.count('<section class="philo-story-block">'))
        self.assertNotIn('<details', philosophy)
        self.assertNotIn('<summary', philosophy)
        self.assertNotIn('Read full story', philosophy)
        self.assertNotRegex(philosophy, r'(?i)(?:philo-step|story-number|story-label|data-story-number|counter\s*\()')
        self.assertNotIn('class="philo-story-graphic"', philosophy)

        copy = re.search(r'<div class="philo-copy">(.*?)</div>\s*</div>', philosophy, re.S)
        self.assertIsNotNone(copy)
        copy_html = copy.group(1)
        story_grid = re.search(r'<div class="philo-story-grid">(.*?)</div>\s*<p class="philo-highlight">', copy_html, re.S)
        self.assertIsNotNone(story_grid)
        story_grid_html = story_grid.group(1)
        story_blocks = re.findall(r'<section class="philo-story-block">(.*?)</section>', story_grid_html, re.S)
        self.assertEqual(4, len(story_blocks))
        self.assertEqual(
            ("Removing barriers", "Broader perspective", "Individual expertise", "Multisensory & online"),
            tuple(
                html.unescape(heading)
                for heading in re.findall(r"<h3[^>]*>([^<]+)</h3>", story_grid_html)
            ),
        )

        expected_summaries = (
            "I remove barriers through specialist training, carefully chosen resources and teaching methods tailored to each learner.",
            "Working as both a teacher and classroom assistant broadened my understanding of the English curriculum and showed me that children can thrive beyond fixed programmes.",
            "My Ofsted-recognised teaching, Autism Resource Base experience and specialist autism and SpLD/dyslexia training shape an individual approach to adapted English and Maths.",
            "I deliver dynamic, multisensory online lessons and use technology to keep digital learning organised, accessible and purposeful.",
        )
        expected_markers = (
            ("Specialist training", "Selected materials", "Individual methods"),
            ("Dual perspective", "Curriculum insight", "Beyond one programme"),
            ("Learner first", "Autism expertise", "SpLD and dyslexia"),
            ("Multisensory learning", "Online teaching", "Organised workbooks"),
        )
        for position, (block, expected_summary, markers) in enumerate(zip(story_blocks, expected_summaries, expected_markers), start=1):
            with self.subTest(story_row=position):
                paragraphs = re.findall(r'<p class="philo-story-copy">(.*?)</p>', block, re.S)
                self.assertEqual((expected_summary,), tuple(re.sub(r"\s+", " ", item).strip() for item in paragraphs))
                marker_lists = re.findall(r'<ul class="philo-concepts"[^>]*>(.*?)</ul>', block, re.S)
                self.assertEqual(1, len(marker_lists))
                self.assertEqual(markers, tuple(re.findall(r'<li>(.*?)</li>', marker_lists[0], re.S)))

        self.assertIn(
            'Every child deserves to be heard, respected and given the right support to flourish.',
            copy_html,
        )
        self.assertIn(
            'When a learner meets a hurdle, I keep adapting until we find the right way forward.',
            copy_html,
        )

        grid_rule = re.search(r"\.philo-story-grid\s*\{([^}]*)\}", stylesheet)
        self.assertIsNotNone(grid_rule)
        self.assertRegex(grid_rule.group(1), r"display:\s*grid")
        self.assertRegex(
            grid_rule.group(1),
            r"grid-template-columns:\s*repeat\(\s*2\s*,\s*minmax\(\s*0\s*,\s*1fr\s*\)\)",
        )
        self.assertNotRegex(grid_rule.group(1), r"counter-(?:reset|increment)")
        self.assertNotRegex(stylesheet, r"counter-(?:reset|increment)\s*:\s*philo-step")

        card_rule = re.search(r"\.philo-story-block\s*\{([^}]*)\}", stylesheet)
        self.assertIsNotNone(card_rule)
        self.assertNotRegex(card_rule.group(1), r"border-radius:\s*var\(--r-(?:md|lg)\)")
        radius = re.search(r"border-radius:\s*(\d+)px", card_rule.group(1))
        self.assertIsNotNone(radius)
        self.assertLessEqual(int(radius.group(1)), 12)

        responsive_start = re.search(
            r"@media\s*\([^)]*(?:max-width\s*:\s*960px|width\s*<=\s*960px)[^)]*\)\s*\{",
            stylesheet,
        )
        self.assertIsNotNone(responsive_start)
        next_media = re.search(r"^@media\s*\(", stylesheet[responsive_start.end():], re.M)
        responsive_end = (
            responsive_start.end() + next_media.start()
            if next_media
            else len(stylesheet)
        )
        responsive_slice = stylesheet[responsive_start.end():responsive_end]
        mobile_grid = re.search(r"\.philo-story-grid\s*\{([^}]*)\}", responsive_slice)
        self.assertIsNotNone(mobile_grid)
        self.assertRegex(
            mobile_grid.group(1),
            r"grid-template-columns:\s*1fr(?:\s|;|$)",
        )

    def test_skills_cards_are_buttons_linked_to_native_dialogs(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        parser = ReferenceParser()
        parser.feed(homepage)

        self.assertIn('href="#skills"', homepage)
        self.assertIn('id="skills"', homepage)
        self.assertEqual(11, len(parser.skill_buttons))
        self.assertEqual(11, len(parser.dialogs))

        targets = {button["data-skill-dialog"] for button in parser.skill_buttons}
        dialog_ids = {dialog["id"] for dialog in parser.dialogs}
        self.assertEqual(dialog_ids, targets)
        for title in self.SKILL_TITLES:
            with self.subTest(title=title):
                self.assertIn(f">{title}<", homepage)

    def test_skills_preserve_original_content_and_use_unique_topic_illustrations(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        for original_text in (
            "Over the last 15 years, my career has been dedicated",
            "Dyslexia Specialism:",
            "Utilising tools such as speech-to-text",
            "Throughout my specialist training, I acquired extensive knowledge",
            "The Incredible 5-Point Scale",
            "Building Confidence and Self-Esteem:",
            "Executive Functioning Skills Support:",
            "Working with Partially Visually Impaired Students:",
            "Supporting Students with Social Communication Challenges:",
            "Supporting Students with Processing Difficulties:",
            "Dyscalculia Specialism:",
        ):
            with self.subTest(text=original_text):
                self.assertIn(original_text, homepage)

        card_block = homepage[homepage.index('<div class="skills-grid">'):homepage.index('</div>', homepage.index('<div class="skills-grid">'))]
        image_sources = re.findall(r'<img\s+src="([^"]+)"', card_block)
        expected = [f"images/skill-{name}.webp" for name in (
            "general", "dyslexia", "dyspraxia", "dyscalculia", "adhd",
            "autism", "anxiety", "executive", "visual", "social", "other",
        )]
        self.assertEqual(expected, image_sources)
        self.assertEqual(11, len(set(image_sources)))
        for source in expected:
            expected_uses = 2
            self.assertEqual(expected_uses, homepage.count(f'src="{source}"'))
        for old_image in (
            "skills-learning-differences", "skills-focus-planning",
            "skills-communication-access", "Dyslexia.png", "learning-landscape.png",
        ):
            self.assertNotIn(old_image, homepage)
        self.assertEqual(22, homepage.count('width="960" height="960"'))
        self.assertGreaterEqual(homepage.count('loading="lazy"'), 12)

    def test_all_skill_dialogs_have_scannable_summaries_and_sections(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertEqual(11, homepage.count('class="skill-at-glance"'))
        self.assertEqual(11, homepage.count(" at a glance</h3>"))
        self.assertGreaterEqual(homepage.count('class="skill-content-card"'), 10)
        # Every panel now carries real content; no placeholders remain.
        self.assertNotIn("Content coming soon", homepage)
        self.assertNotIn("coming-soon", homepage)

    def test_number_playground_and_all_game_only_code_are_removed(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        for marker in ("fun-zone", "game-shell", "game-tab", "game-panel", "dots-start", "ten-start", "bunch-start"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, homepage)
                self.assertNotIn(marker, stylesheet)
                self.assertNotIn(marker, script)
        self.assertNotIn("NUMBER FUN ZONE", script)
        self.assertNotIn("Play number games", homepage)
        self.assertRegex(homepage, r'class="btn btn-ghost" href="#skills"')

    def test_hero_learning_glyphs_are_present_and_randomized(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        self.assertIn('<div class="float-field" aria-hidden="true"></div>', homepage)
        self.assertRegex(script, r'createElement\(["\']span["\']\)')
        self.assertRegex(script, r'className\s*=\s*["\']float-num["\']')
        self.assertIn("Math.random()", script)
        for glyph in ("1", "9", "+", "=", "×", "★"):
            with self.subTest(glyph=glyph):
                self.assertIn(f'"{glyph}"', script)

    def test_hero_motion_is_gentle_and_fully_suppressed_when_requested(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        keyframes = set(re.findall(r"@keyframes\s+([\w-]+)", stylesheet))

        for selector, minimum_duration in (
            ("float-num", 1.5),
            ("hero-chip", 1.5),
            ("blob", 1.5),
            ("blob-ring", 20.0),
            ("pulse", 1.5),
        ):
            rules = re.findall(rf"\.{re.escape(selector)}\b[^{{}}]*\{{([^}}]*)\}}", stylesheet)
            animation = next(
                (match.group(1) for rule in rules if (match := re.search(r"\banimation:\s*([^;]+)", rule))),
                None,
            )
            with self.subTest(selector=selector):
                self.assertIsNotNone(animation, f".{selector} needs a default animation")
                durations = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)s\b", animation)]
                self.assertTrue(durations)
                self.assertGreaterEqual(max(durations), minimum_duration)
                self.assertTrue(keyframes.intersection(re.findall(r"[\w-]+", animation)))

        calm_rule = re.search(
            r"html\.calm\s+\*,\s*html\.calm\s+\*::before,\s*html\.calm\s+\*::after\s*\{([^}]*)\}",
            stylesheet,
        )
        self.assertIsNotNone(calm_rule)
        self.assertRegex(calm_rule.group(1), r"animation-duration:\s*0\.00\d+s\s*!important")
        self.assertRegex(stylesheet, r"html\.calm\s+\.float-field\s*\{[^}]*display:\s*none\s*;")

        reduced_start = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{", stylesheet)
        self.assertIsNotNone(reduced_start)
        reduced_css = stylesheet[reduced_start.start():]
        self.assertRegex(
            reduced_css,
            r"\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation-duration:\s*0\.00\d+s\s*!important",
        )

    def test_hero_portrait_keeps_its_full_intrinsic_image_in_a_square_frame(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        image = re.search(r'<img class="hero-photo"[^>]+>', homepage)
        self.assertIsNotNone(image)
        self.assertIn('width="463"', image.group(0))
        self.assertIn('height="520"', image.group(0))

        rule = re.search(r"\.hero-photo\s*\{([^}]*)\}", stylesheet)
        self.assertIsNotNone(rule)
        declarations = rule.group(1)
        width = re.search(r"\bwidth:\s*([^;]+)", declarations)
        height = re.search(r"\bheight:\s*([^;]+)", declarations)
        square_frame = re.search(r"\baspect-ratio:\s*1(?:\s*/\s*1)?\s*;", declarations)
        self.assertTrue(
            square_frame or (width and height and width.group(1).strip() == height.group(1).strip()),
            "hero portrait needs a responsive square frame",
        )
        self.assertRegex(declarations, r"\bobject-fit:\s*contain\s*;")
        self.assertRegex(declarations, r"\bobject-position:\s*(?:center\s+bottom|bottom\s+center)\s*;")

    def test_testimonials_are_a_static_four_item_layout(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        testimonial_section = homepage[
            homepage.index('<section class="testimonials"'):
            homepage.index('<!-- ================= CTA ================= -->')
        ]
        self.assertEqual(4, testimonial_section.count('class="t-card"'))
        self.assertIn('class="testimonials-grid', testimonial_section)
        for source in (testimonial_section, stylesheet, script):
            self.assertNotRegex(source, r"(?i)carousel|data-prev|data-next")

    def test_mobile_navigation_breakpoint_order_and_close_behaviour(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")

        nav_breakpoints = []
        media_matches = list(re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", stylesheet))
        for index, match in enumerate(media_matches):
            end = media_matches[index + 1].start() if index + 1 < len(media_matches) else len(stylesheet)
            if ".main-nav" in stylesheet[match.start():end]:
                nav_breakpoints.append(int(match.group(1)))
        self.assertTrue(nav_breakpoints, "mobile navigation needs a responsive breakpoint")
        self.assertGreaterEqual(max(nav_breakpoints), 900)

        expected_order = ("philosophy", "how-to-start", "skills", "testimonials", "/about", "/contact")
        for page_name in PAGES:
            page = (ROOT / page_name).read_text(encoding="utf-8")
            nav = re.search(r'<nav class="main-nav".*?</nav>', page, re.S).group(0)
            hrefs = re.findall(r'href="([^"]+)"', nav)
            actual = tuple(
                next(key for key in expected_order if href.endswith("#" + key) or href.endswith(key))
                for href in hrefs
            )
            with self.subTest(page=page_name):
                self.assertEqual(expected_order, actual)

        self.assertIn('addEventListener("keydown"', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('document.addEventListener("click"', script)
        self.assertIn("mainNav.contains(", script)

    def test_calm_toggle_exposes_and_synchronises_pressed_state(self):
        for page_name in PAGES:
            page = (ROOT / page_name).read_text(encoding="utf-8")
            button = re.search(r'<button class="calm-toggle".*?</button>', page, re.S)
            self.assertIsNotNone(button, page_name)
            self.assertIn('aria-pressed="false"', button.group(0))
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        self.assertIn('setAttribute("aria-pressed", isCalm() ? "true" : "false")', script)

    def test_all_skill_dialogs_share_the_same_summary_and_content_structure(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        dialogs = re.findall(r'<dialog class="skill-dialog".*?</dialog>', homepage, re.S)
        self.assertEqual(11, len(dialogs))
        for dialog in dialogs:
            dialog_id = re.search(r'id="([^"]+)"', dialog).group(1)
            with self.subTest(dialog=dialog_id):
                self.assertEqual(1, dialog.count('class="skill-dialog-hero'))
                self.assertEqual(1, dialog.count('class="skill-dialog-copy"'))
                self.assertEqual(1, dialog.count('class="skill-at-glance"'))
                self.assertEqual(1, dialog.count('class="skill-content-card"'))
                self.assertEqual(2, dialog.count('data-dialog-close'))

    def test_key_images_declare_their_actual_intrinsic_dimensions(self):
        expected = {
            "images/profile.png": ("463", "520"),
            "images/learning-pathways.webp": ("1400", "669"),
        }
        for page_name in PAGES:
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            for image in parser.images:
                if image.get("src") not in expected:
                    continue
                with self.subTest(page=page_name, image=image["src"]):
                    self.assertEqual(expected[image["src"]], (image.get("width"), image.get("height")))

    def test_removed_playground_has_no_residual_css_or_script_comment(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        for marker in ("ten-frame", "ten-cell", "star-jar"):
            self.assertNotIn(marker, stylesheet)
        self.assertNotRegex(script.split("*/", 1)[0], r"(?i)\bgames\b")

    def test_every_page_has_complete_distinct_uk_metadata(self):
        expected_urls = {
            "index.html": f"{PRODUCTION_ORIGIN}/",
            "about.html": f"{PRODUCTION_ORIGIN}/about",
            "contact.html": f"{PRODUCTION_ORIGIN}/contact",
        }
        expected_topic = {"index.html": "SEN", "about.html": "About", "contact.html": "Contact"}
        titles = []
        descriptions = []

        for page_name in PAGES:
            source = (ROOT / page_name).read_text(encoding="utf-8")
            parser = MetadataParser()
            parser.feed(source)
            titles.append(parser.title)
            self.assertEqual("en-GB", parser.html_attributes.get("lang"))
            self.assertIn("Eva Coates", parser.title)
            self.assertIn(expected_topic[page_name], parser.title)

            description = parser.meta("name", "description")
            self.assertEqual(1, len(description))
            descriptions.append(description[0].get("content", ""))
            self.assertIn("Eva Coates", description[0].get("content", ""))
            self.assertEqual([], parser.meta("name", "keywords"))

            author = parser.meta("name", "author")
            robots_meta = parser.meta("name", "robots")
            theme = parser.meta("name", "theme-color")
            self.assertEqual(["Eva Coates"], [item.get("content") for item in author])
            self.assertEqual(1, len(robots_meta))
            self.assertEqual(
                {"index", "follow", "max-image-preview:large", "max-snippet:-1", "max-video-preview:-1"},
                {part.strip().lower() for part in robots_meta[0]["content"].split(",")},
            )
            self.assertEqual(1, len(theme))
            self.assertRegex(theme[0].get("content", ""), r"^#[0-9a-fA-F]{6}$")

            canonical = parser.link("canonical")
            alternate = parser.link("alternate", hreflang="en-GB")
            default_alternate = parser.link("alternate", hreflang="x-default")
            icons = parser.link("icon")
            self.assertEqual([expected_urls[page_name]], [item.get("href") for item in canonical])
            self.assertEqual([expected_urls[page_name]], [item.get("href") for item in alternate])
            self.assertEqual([expected_urls[page_name]], [item.get("href") for item in default_alternate])
            self.assertEqual(1, len(icons))
            self.assertEqual("favicon.svg", icons[0].get("href", "").lstrip("/"))
            self.assertEqual("image/svg+xml", icons[0].get("type"))
            self.assertNotIn("data:", icons[0].get("href", ""))

            required_meta = {
                "og:title": "property", "og:description": "property", "og:type": "property",
                "og:url": "property", "og:image": "property", "og:image:alt": "property",
                "og:image:width": "property", "og:image:height": "property",
                "og:image:secure_url": "property", "og:image:type": "property",
                "og:site_name": "property", "og:locale": "property",
                "twitter:card": "name", "twitter:title": "name", "twitter:description": "name",
                "twitter:image": "name", "twitter:image:alt": "name",
            }
            values = {}
            for key, attribute in required_meta.items():
                items = parser.meta(attribute, key)
                with self.subTest(page=page_name, metadata=key):
                    self.assertEqual(1, len(items))
                    self.assertTrue(items[0].get("content", "").strip())
                values[key] = items[0].get("content", "") if items else ""
            self.assertEqual(expected_urls[page_name], values["og:url"])
            self.assertEqual("website", values["og:type"])
            self.assertEqual("en_GB", values["og:locale"])
            self.assertEqual("SEN Tutor", values["og:site_name"])
            self.assertEqual("summary_large_image", values["twitter:card"])
            self.assertEqual(parser.title, values["og:title"])
            self.assertEqual(description[0]["content"], values["og:description"])
            self.assertEqual(values["og:title"], values["twitter:title"])
            self.assertEqual(values["og:description"], values["twitter:description"])
            self.assertEqual(values["og:image"], values["twitter:image"])
            self.assertEqual(values["og:image"], values["og:image:secure_url"])
            self.assertEqual(values["og:image:alt"], values["twitter:image:alt"])
            self.assertEqual(f"{PRODUCTION_ORIGIN}/images/learning-pathways.webp", values["og:image"])
            self.assertEqual("1400", values["og:image:width"])
            self.assertEqual("669", values["og:image:height"])
            self.assertEqual("image/webp", values["og:image:type"])
            for image_key in ("og:image", "twitter:image"):
                image_url = urlsplit(values[image_key])
                self.assertEqual("https", image_url.scheme)
                self.assertEqual("www.sen-tutor.co.uk", image_url.netloc)

        self.assertEqual(len(PAGES), len(set(titles)))
        self.assertEqual(len(PAGES), len(set(descriptions)))

    def test_each_page_has_one_valid_connected_json_ld_graph(self):
        expected_urls = {
            "index.html": f"{PRODUCTION_ORIGIN}/",
            "about.html": f"{PRODUCTION_ORIGIN}/about",
            "contact.html": f"{PRODUCTION_ORIGIN}/contact",
        }
        stable_ids = {
            "website": f"{PRODUCTION_ORIGIN}/#website",
            "person": f"{PRODUCTION_ORIGIN}/#person",
            "image": f"{PRODUCTION_ORIGIN}/#primaryimage",
            "service": f"{PRODUCTION_ORIGIN}/#service",
        }
        visible_about = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (ROOT / "about.html").read_text(encoding="utf-8")))
        graphs = {}

        def node_types(node):
            value = node.get("@type", [])
            return {value} if isinstance(value, str) else set(value)

        for page_name in PAGES:
            source = (ROOT / page_name).read_text(encoding="utf-8")
            scripts = re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', source, re.S | re.I)
            self.assertEqual(1, len(scripts), f"{page_name} needs exactly one JSON-LD script")
            document = json.loads(scripts[0])
            self.assertEqual("https://schema.org", document.get("@context"))
            self.assertIsInstance(document.get("@graph"), list)
            self.assertTrue(document["@graph"])
            graphs[page_name] = document["@graph"]

            serialized = json.dumps(document)
            # Tuition is online and not limited to one country, so the graph
            # states no geography at all rather than narrowing the audience.
            for forbidden in ("address", "telephone", "email", "geo", "priceRange", "openingHours", "areaServed"):
                self.assertNotRegex(serialized, rf'"{forbidden}"\s*:')
            for node in document["@graph"]:
                self.assertTrue(node.get("@id", "").startswith(PRODUCTION_ORIGIN))

            all_types = set().union(*(node_types(node) for node in document["@graph"]))
            page_type = "WebPage" if page_name == "index.html" else ("AboutPage" if page_name == "about.html" else "ContactPage")
            self.assertIn(page_type, all_types)
            page_node = next(node for node in document["@graph"] if page_type in node_types(node))
            self.assertEqual(expected_urls[page_name], page_node.get("url"))
            self.assertEqual(stable_ids["website"], page_node.get("isPartOf", {}).get("@id"))

        home_types = set().union(*(node_types(node) for node in graphs["index.html"]))
        for required_type in ("WebSite", "WebPage", "Person", "ImageObject", "Service"):
            self.assertIn(required_type, home_types)
        home_by_id = {node["@id"]: node for node in graphs["index.html"]}
        self.assertTrue(set(stable_ids.values()).issubset(home_by_id))
        self.assertEqual("Eva Coates", home_by_id[stable_ids["person"]].get("name"))
        self.assertEqual("Special Needs Tutor", home_by_id[stable_ids["person"]].get("jobTitle"))
        self.assertEqual(stable_ids["person"], home_by_id[stable_ids["service"]].get("provider", {}).get("@id"))
        self.assertEqual(stable_ids["image"], home_by_id[f"{PRODUCTION_ORIGIN}/#webpage"].get("primaryImageOfPage", {}).get("@id"))
        self.assertTrue(home_by_id[stable_ids["image"]].get("contentUrl", "").startswith(f"{PRODUCTION_ORIGIN}/"))
        credentials = home_by_id[stable_ids["person"]].get("hasCredential", [])
        self.assertGreaterEqual(len(credentials), 2)
        for credential in credentials:
            self.assertIn("EducationalOccupationalCredential", node_types(credential))
            self.assertIn(credential.get("name", ""), visible_about)

        for page_name in ("about.html", "contact.html"):
            page_type = "AboutPage" if page_name == "about.html" else "ContactPage"
            page_id = f"{expected_urls[page_name]}#webpage"
            breadcrumb_id = f"{expected_urls[page_name]}#breadcrumb"
            nodes = {node["@id"]: node for node in graphs[page_name]}
            self.assertIn(page_id, nodes)
            self.assertIn(breadcrumb_id, nodes)
            self.assertIn(page_type, node_types(nodes[page_id]))
            self.assertIn("BreadcrumbList", node_types(nodes[breadcrumb_id]))
            self.assertEqual(breadcrumb_id, nodes[page_id].get("breadcrumb", {}).get("@id"))
            crumbs = nodes[breadcrumb_id].get("itemListElement", [])
            self.assertEqual([1, 2], [crumb.get("position") for crumb in crumbs])
            crumb_items = [item.get("@id") if isinstance(item, dict) else item for item in (crumb.get("item") for crumb in crumbs)]
            self.assertEqual([f"{PRODUCTION_ORIGIN}/", expected_urls[page_name]], crumb_items)

    def test_cname_robots_and_sitemap_define_the_exact_public_site(self):
        cname = ROOT / "CNAME"
        self.assertTrue(cname.is_file())
        self.assertEqual("www.sen-tutor.co.uk", cname.read_text(encoding="utf-8").strip())

        robots = ROOT / "robots.txt"
        self.assertTrue(robots.is_file())
        content = robots.read_text(encoding="utf-8")
        self.assertRegex(content, r"(?im)^User-agent:\s*\*$")
        self.assertRegex(content, r"(?im)^Allow:\s*/$")
        self.assertRegex(content, rf"(?im)^Sitemap:\s*{re.escape(PRODUCTION_ORIGIN)}/sitemap\.xml$")

        sitemap = ROOT / "sitemap.xml"
        self.assertTrue(sitemap.is_file())
        root = ET.parse(sitemap).getroot()
        self.assertEqual("urlset", root.tag.rsplit("}", 1)[-1])
        self.assertTrue(root.tag.startswith("{http://www.sitemaps.org/schemas/sitemap/0.9}"))
        urls = [child for child in root if child.tag.rsplit("}", 1)[-1] == "url"]
        self.assertEqual(3, len(urls))
        expected = [f"{PRODUCTION_ORIGIN}/", f"{PRODUCTION_ORIGIN}/about", f"{PRODUCTION_ORIGIN}/contact"]
        locations = []
        for entry in urls:
            fields = {child.tag.rsplit("}", 1)[-1]: child.text for child in entry}
            self.assertEqual({"loc", "lastmod"}, set(fields))
            self.assertEqual("2026-08-03", fields["lastmod"])
            locations.append(fields["loc"])
        self.assertEqual(expected, locations)

    def test_favicon_is_safe_scriptless_external_free_48px_svg(self):
        favicon = ROOT / "favicon.svg"
        self.assertTrue(favicon.is_file())
        source = favicon.read_text(encoding="utf-8")
        root = ET.fromstring(source)
        self.assertEqual("svg", root.tag.rsplit("}", 1)[-1])
        self.assertEqual("48", root.get("width"))
        self.assertEqual("48", root.get("height"))
        self.assertEqual("0 0 48 48", root.get("viewBox"))
        allowed_tags = {"svg", "title", "path", "circle", "rect", "polygon", "line", "polyline", "g"}
        for element in root.iter():
            self.assertIn(element.tag.rsplit("}", 1)[-1], allowed_tags)
            for attribute, value in element.attrib.items():
                self.assertFalse(attribute.lower().startswith("on"))
                self.assertNotIn(attribute.rsplit("}", 1)[-1].lower(), {"href", "src"})
                self.assertNotRegex(value, r"(?i)url\s*\(|javascript:")

    def test_contact_form_discloses_formspree_and_links_to_its_privacy_policy(self):
        contact = (ROOT / "contact.html").read_text(encoding="utf-8")
        form = re.search(r'<form\b.*?</form>', contact, re.S).group(0)
        self.assertIn("Formspree", form)
        self.assertRegex(
            form,
            r'href="https://formspree\.io/(?:legal/)?privacy(?:-policy)?/?"',
        )

    def test_contact_form_uses_native_email_validation_and_mobile_keyboard_hint(self):
        class ContactFormParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.contact_form = None
                self.email_input = None

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == "form" and attributes.get("id") == "contactForm":
                    self.contact_form = attributes
                if tag == "input" and attributes.get("id") == "email":
                    self.email_input = attributes

        parser = ContactFormParser()
        parser.feed((ROOT / "contact.html").read_text(encoding="utf-8"))
        self.assertIsNotNone(parser.contact_form)
        self.assertNotIn("novalidate", parser.contact_form)
        self.assertIsNotNone(parser.email_input)
        self.assertEqual("email", parser.email_input.get("type"))
        self.assertIn("required", parser.email_input)
        self.assertEqual("email", parser.email_input.get("autocomplete"))
        self.assertEqual("email", parser.email_input.get("inputmode"))

    def test_about_experience_is_a_readable_professional_editorial_section(self):
        about = (ROOT / "about.html").read_text(encoding="utf-8")
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        section = about[
            about.index("<!-- skills & experience -->"):
            about.index("<!-- qualifications -->")
        ]
        plain_text = re.sub(r"<[^>]+>", " ", section)
        plain_text = re.sub(r"\s+", " ", plain_text)

        factual_anchors = (
            r"15 years", r"5 to 18", r"KS1", r"KS5", r"mainstream", r"specialised",
            r"English", r"Mathematics", r"Science", r"educational psychologists",
            r"occupational therapists", r"speech and language therapists",
            r"parental (?:engagement|involvement)", r"good or outstanding",
        )
        for anchor in factual_anchors:
            with self.subTest(anchor=anchor):
                self.assertRegex(plain_text.lower(), anchor.lower())

        self.assertEqual(1, section.count('class="experience-intro'))
        cards = re.findall(r'<article class="exp-card\b.*?</article>', section, re.S)
        self.assertEqual(3, len(cards))
        for position, card in enumerate(cards[:2], start=1):
            with self.subTest(card=position):
                self.assertIn("<ul", card)
                self.assertGreaterEqual(card.count("<li"), 3)
                labels = re.findall(r"<li[^>]*>\s*<strong>([^<]+)</strong>", card)
                self.assertGreaterEqual(len(labels), 3)
                self.assertTrue(all(len(label.rstrip(":")) <= 32 for label in labels))

        grid_rule = re.search(r"\.exp-grid\s*\{([^}]*)\}", stylesheet)
        self.assertIsNotNone(grid_rule)
        self.assertIn("grid-template-columns", grid_rule.group(1))
        self.assertNotRegex(grid_rule.group(1), r"repeat\(\s*3\s*,")
        self.assertRegex(
            stylesheet,
            r"\.experience-intro\s*\{[^}]*max-width:\s*(?:[4-7]\d)ch\s*;[^}]*margin-bottom:",
        )
        self.assertRegex(stylesheet, r"\.exp-card\s+(?:p|li)[^{]*\{[^}]*max-width:\s*(?:[4-7]\d)ch\s*;")
        self.assertRegex(stylesheet, r"\.exp-card\s+ul\s*\{[^}]*display:\s*grid\s*;[^}]*gap:")
        self.assertRegex(
            stylesheet,
            r"@media\s*\(max-width:\s*(?:9\d\d|[1-9]\d{3,})px\)\s*\{"
            r"(?:(?!@media)[\s\S])*?\.exp-grid\s*\{[^}]*grid-template-columns:\s*1fr\s*;",
        )

    def test_skills_dialog_interaction_is_accessible(self):
        script = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        for feature in (
            "data-skill-dialog",
            "showModal()",
            'document.body.classList.add("dialog-open")',
            'document.body.classList.remove("dialog-open")',
            'addEventListener("close"',
            "returnFocus.focus()",
        ):
            with self.subTest(feature=feature):
                self.assertIn(feature, script)

    def test_skills_dialog_is_centered_despite_the_global_margin_reset(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(
            stylesheet,
            r"\.skill-dialog\s*\{[^}]*\bmargin:\s*auto(?:\s+auto)?\s*;",
        )

    def test_skill_at_glance_list_markers_stay_inside_their_grid_cells(self):
        stylesheet = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(
            stylesheet,
            r"\.skill-at-glance\s+ul\s*\{[^}]*\blist-style-position:\s*inside\s*;",
        )


class SeoHardeningTests(unittest.TestCase):
    def graph(self, page_name):
        source = (ROOT / page_name).read_text(encoding="utf-8")
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', source, re.DOTALL
        )
        self.assertEqual(1, len(blocks), f"{page_name} must have exactly one JSON-LD block")
        return json.loads(blocks[0])["@graph"]

    def test_missing_urls_get_a_real_noindex_404_page(self):
        page = ROOT / "404.html"
        self.assertTrue(page.is_file(), "404.html is required or the host serves a soft 404")
        source = page.read_text(encoding="utf-8")
        self.assertTrue(source.lstrip().lower().startswith("<!doctype html>"))

        parser = MetadataParser()
        parser.feed(source)
        robots = [meta for meta in parser.metas if meta.get("name") == "robots"]
        self.assertEqual(1, len(robots))
        self.assertIn("noindex", robots[0].get("content", ""))

        # A 404 must not claim to be another page, or it re-creates the soft 404.
        self.assertEqual([], [link for link in parser.links if link.get("rel") == "canonical"])

        self.assertIn('href="/"', source, "the 404 page must offer a route home")

        sitemap = ET.parse(ROOT / "sitemap.xml").getroot()
        locations = [
            child.text
            for entry in sitemap
            for child in entry
            if child.tag.rsplit("}", 1)[-1] == "loc"
        ]
        self.assertNotIn(f"{PRODUCTION_ORIGIN}/404", locations)
        self.assertNotIn(f"{PRODUCTION_ORIGIN}/404.html", locations)

    def test_credentials_are_fully_listed_with_their_issuers(self):
        person = next(
            node for node in self.graph("index.html") if node.get("@type") == "Person"
        )
        credentials = {item["name"]: item for item in person["hasCredential"]}
        expected = {
            "QTS (Qualified Teacher Status)": None,
            "OCR Level 5 Diploma": "Fairley House School, London",
            "Level 3 Diploma": "ELKLAN, London",
            "CELTA": "International House, London",
            "BA (Hons) English and French": None,
            "MA History of Art": None,
        }
        self.assertEqual(set(expected), set(credentials))
        for name, issuer in expected.items():
            with self.subTest(credential=name):
                self.assertEqual(
                    "EducationalOccupationalCredential", credentials[name]["@type"]
                )
                if issuer is not None:
                    self.assertEqual(issuer, credentials[name]["recognizedBy"]["name"])

        # Every credential on the About page must appear in the graph.
        about = (ROOT / "about.html").read_text(encoding="utf-8")
        for name in ("BA (Hons)", "MA", "Fairley House", "ELKLAN", "International House"):
            with self.subTest(shown=name):
                self.assertIn(name, about)

    def test_prose_uses_british_spellings(self):
        american = re.compile(
            r"\b\w*(?:iz(?:e|ed|es|ing|ation)|behavior|favorite)\w*\b", re.I
        )
        for page_name in (*PAGES, "404.html"):
            source = (ROOT / page_name).read_text(encoding="utf-8")
            # schema.org vocabulary (recognizedBy, EducationalOrganization) is a
            # fixed API spelling, so JSON-LD is excluded and only prose checked.
            source = re.sub(r"<script\b.*?</script>", " ", source, flags=re.S)
            prose = re.sub(r"<[^>]+>", " ", source)
            with self.subTest(page=page_name):
                self.assertEqual([], american.findall(prose))

    def test_every_page_offers_an_apple_touch_icon(self):
        icon = ROOT / "images" / "apple-touch-icon.png"
        self.assertTrue(icon.is_file())
        # iOS ignores SVG touch icons, so this must stay a real PNG.
        self.assertEqual(b"\x89PNG\r\n\x1a\n", icon.read_bytes()[:8])

        for page_name in (*PAGES, "404.html"):
            parser = MetadataParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            links = parser.link("apple-touch-icon")
            with self.subTest(page=page_name):
                self.assertEqual(1, len(links))
                self.assertEqual("/images/apple-touch-icon.png", links[0].get("href"))
                self.assertEqual("180x180", links[0].get("sizes"))

    def test_internal_links_use_clean_urls_and_never_redirect(self):
        # /about.html 308-redirects to /about in production, so linking to the
        # .html form makes every internal link cost an extra hop.
        failures = []
        for page_name in (*PAGES, "404.html"):
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme or parsed.netloc:
                    continue
                if parsed.path.endswith(".html"):
                    failures.append(f"{page_name}: {reference}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_every_page_links_to_the_canonical_form_of_its_siblings(self):
        for page_name in PAGES:
            parser = ReferenceParser()
            parser.feed((ROOT / page_name).read_text(encoding="utf-8"))
            paths = {urlsplit(reference).path for reference in parser.references}
            with self.subTest(page=page_name):
                self.assertTrue(
                    {"/about", "/contact"} <= paths,
                    f"{page_name} should link to /about and /contact",
                )

    def test_heading_text_is_unique_within_each_page(self):
        for page_name in (*PAGES, "404.html"):
            headings = collect_headings(ROOT / page_name)
            duplicates = sorted({text for text in headings if headings.count(text) > 1})
            with self.subTest(page=page_name):
                self.assertEqual([], duplicates, f"{page_name} repeats {duplicates}")

    def test_each_skill_panel_names_itself_in_its_summary_heading(self):
        headings = collect_headings(ROOT / "index.html")
        for title in ModernSiteAcceptanceTests.SKILL_TITLES:
            with self.subTest(skill=title):
                self.assertIn(f"{title} at a glance", headings)

    def test_font_stylesheet_does_not_block_first_paint(self):
        for page_name in (*PAGES, "404.html"):
            source = (ROOT / page_name).read_text(encoding="utf-8")
            with self.subTest(page=page_name):
                if "fonts.googleapis.com/css2" not in source:
                    continue
                tag = re.search(r"<link[^>]*fonts\.googleapis\.com/css2[^>]*>", source)
                self.assertIsNotNone(tag)
                markup = tag.group(0)
                self.assertIn('media="print"', markup)
                self.assertIn("this.media='all'", markup)
                self.assertRegex(source, r"<noscript>\s*<link[^>]*fonts\.googleapis\.com/css2")

    def test_homepage_faq_copy_and_faqpage_schema_stay_in_step(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        faq_nodes = [node for node in self.graph("index.html") if node.get("@type") == "FAQPage"]
        self.assertEqual(1, len(faq_nodes), "the homepage needs exactly one FAQPage node")
        questions = faq_nodes[0]["mainEntity"]
        self.assertGreaterEqual(len(questions), 4)

        self.assertIn('id="faq"', source)
        for entry in questions:
            self.assertEqual("Question", entry["@type"])
            answer = entry["acceptedAnswer"]
            self.assertEqual("Answer", answer["@type"])
            with self.subTest(question=entry["name"]):
                # Google requires the marked-up answer to be visible on the page.
                self.assertIn(entry["name"], source)
                self.assertIn(answer["text"], source)

    def test_faqpage_is_connected_to_the_homepage_graph(self):
        graph = self.graph("index.html")
        faq = next(node for node in graph if node.get("@type") == "FAQPage")
        self.assertEqual(f"{PRODUCTION_ORIGIN}/#faq", faq["@id"])
        self.assertEqual({"@id": f"{PRODUCTION_ORIGIN}/#webpage"}, faq["isPartOf"])

    def test_tuition_is_marked_up_as_online_with_no_country_limit(self):
        service = next(
            node for node in self.graph("index.html") if node.get("@type") == "Service"
        )
        # Online delivery means no geographic restriction should be claimed;
        # naming a country would narrow the audience for no benefit.
        self.assertNotIn("areaServed", service)
        channel = service["availableChannel"]
        self.assertEqual("ServiceChannel", channel["@type"])
        self.assertEqual(f"{PRODUCTION_ORIGIN}/contact", channel["serviceUrl"])

    def test_no_page_claims_a_physical_location(self):
        # Tuition is delivered online only; inventing geo signals would be a
        # misrepresentation and Google penalises it.
        forbidden = ("LocalBusiness", "PostalAddress", "GeoCoordinates", "addressLocality")
        for page_name in (*PAGES, "404.html"):
            source = (ROOT / page_name).read_text(encoding="utf-8")
            for term in forbidden:
                with self.subTest(page=page_name, term=term):
                    self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
