import json
import re
from pathlib import Path
from typing import Dict, Final

import translators
from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.imagenarator import imagemaker
from utils.playwright import clear_cookie_by_name
from utils.videos import save_data

__all__ = ["get_screenshots_of_reddit_posts"]


def get_screenshots_of_reddit_posts(reddit_object: dict, screenshot_num: int):
    """Downloads screenshots of reddit posts as seen on the web. Downloads to assets/temp/png

    Args:
        reddit_object (Dict): Reddit object received from reddit/subreddit.py
        screenshot_num (int): Number of screenshots to download
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    lang: Final[str] = settings.config["reddit"]["thread"]["post_lang"]
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    print_step("Downloading screenshots of reddit posts...")
    reddit_id = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
    # ! Make sure the reddit screenshots folder exists
    Path(f"assets/temp/{reddit_id}/png").mkdir(parents=True, exist_ok=True)

    # set the theme and turn off non-essential cookies
    if settings.config["settings"]["theme"] == "dark":
        cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
    elif settings.config["settings"]["theme"] == "transparent":
        if storymode:
            # Transparent theme
            bgcolor = (0, 0, 0, 0)
            txtcolor = (255, 255, 255)
            transparent = True
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        else:
            # Switch to dark theme
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
            bgcolor = (33, 33, 36, 255)
            txtcolor = (240, 240, 240)
            transparent = False
    else:
        cookie_file = open("./video_creation/data/cookie-light-mode.json", encoding="utf-8")
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False

    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        print_substep("Generating images...")
        return imagemaker(
            theme=bgcolor,
            reddit_obj=reddit_object,
            txtclr=txtcolor,
            transparent=transparent,
        )

    screenshot_num: int
    # Reuse the shared headed browser session (already past Reddit's JS challenge).
    if True:
        from utils import reddit_browser

        print_substep("Using shared Reddit browser session...")
        context = reddit_browser.get_context()
        reddit_browser._warmup(context)

        cookies = json.load(cookie_file)
        cookie_file.close()
        context.add_cookies(cookies)  # load preference (theme) cookies

        page = context.new_page()
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.wait_for_load_state()
        # Handle the redesign
        # Check if the redesign optout cookie is set
        if page.locator("#redesign-beta-optin-btn").is_visible():
            # Clear the redesign optout cookie
            clear_cookie_by_name(context, "redesign_optout")
            # Reload the page for the redesign to take effect
            page.reload()
        # Get the thread screenshot
        page.goto(reddit_object["thread_url"], timeout=0)
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.wait_for_load_state()
        page.wait_for_timeout(5000)

        # Dismiss NSFW / content gate if present (current Reddit DOM).
        try:
            gate = page.locator('shreddit-async-loader[bundlename="content_warning"] button, [data-testid="content-gate"] button').first
            if gate.is_visible():
                print_substep("Post is NSFW. You are spicy...")
                gate.click()
                page.wait_for_load_state()
        except Exception:
            pass

        if lang:
            print_substep("Translating post...")
            texts_in_tl = translators.translate_text(
                reddit_object["thread_title"],
                to_language=lang,
                translator="google",
            )

            page.evaluate(
                "tl_content => { const h = document.querySelector('shreddit-post h1') || document.querySelector('h1'); if (h) h.textContent = tl_content; }",
                texts_in_tl,
            )
        else:
            print_substep("Skipping translation...")

        postcontentpath = f"assets/temp/{reddit_id}/png/title.png"
        try:
            if settings.config["settings"]["zoom"] != 1:
                # store zoom settings
                zoom = settings.config["settings"]["zoom"]
                # zoom the body of the page
                page.evaluate("document.body.style.zoom=" + str(zoom))
                # as zooming the body doesn't change the properties of the divs, we need to adjust for the zoom
                location = page.locator("shreddit-post").bounding_box()
                for i in location:
                    location[i] = float("{:.2f}".format(location[i] * zoom))
                page.screenshot(clip=location, path=postcontentpath)
            else:
                page.locator("shreddit-post").screenshot(path=postcontentpath)
        except Exception as e:
            print_substep("Something went wrong!", style="red")
            resp = input(
                "Something went wrong with making the screenshots! Do you want to skip the post? (y/n) "
            )

            if resp.casefold().startswith("y"):
                save_data("", "", "skipped", reddit_id, "")
                print_substep(
                    "The post is successfully skipped! You can now restart the program and this post will skipped.",
                    "green",
                )

            resp = input("Do you want the error traceback for debugging purposes? (y/n)")
            if not resp.casefold().startswith("y"):
                exit()

            raise e

        if storymode:
            page.locator("shreddit-post").first.screenshot(
                path=f"assets/temp/{reddit_id}/png/story_content.png"
            )
        else:
            for idx, comment in enumerate(
                track(
                    reddit_object["comments"][:screenshot_num],
                    "Downloading screenshots...",
                )
            ):
                # Stop if we have reached the screenshot_num
                if idx >= screenshot_num:
                    break

                if page.locator('[data-testid="content-gate"]').is_visible():
                    page.locator('[data-testid="content-gate"] button').click()

                page.goto(f"https://www.reddit.com{comment['comment_url']}")
                page.wait_for_load_state()
                page.wait_for_timeout(2000)

                # translate code

                if settings.config["reddit"]["thread"]["post_lang"]:
                    comment_tl = translators.translate_text(
                        comment["comment_body"],
                        translator="google",
                        to_language=settings.config["reddit"]["thread"]["post_lang"],
                    )
                    page.evaluate(
                        '([tl_content, tl_id]) => { const el = document.querySelector(`shreddit-comment[thingid="t1_${tl_id}"] [id$="-comment-rtjson-content"]`) || document.querySelector(`shreddit-comment[thingid="t1_${tl_id}"]`); if (el) el.textContent = tl_content; }',
                        [comment_tl, comment["comment_id"]],
                    )
                try:
                    comment_selector = (
                        f'shreddit-comment[thingid="t1_{comment["comment_id"]}"]'
                    )
                    # Prepare the page so a screenshot of the comment element
                    # captures ONLY this comment:
                    #   - hide the sticky top header (otherwise it overlaps the
                    #     comment when the comment sits at the top of the page)
                    #   - hide any nested replies so the element's own bounding
                    #     box doesn't include the whole reply tree
                    #   - hide cookie/login banners and overlays
                    # scroll the comment into view first so clip coords are valid
                    page.locator(comment_selector).scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    found = page.evaluate(
                        """(cid) => {
                            const c = document.querySelector(`shreddit-comment[thingid="t1_${cid}"]`);
                            if (!c) return false;
                            // 1) hide sticky / fixed headers and known overlays so
                            //    they don't overlap the comment when it's at the top.
                            const killSelectors = [
                                'reddit-header-large', 'shreddit-app > header', 'header',
                                'shreddit-async-loader[bundlename="desktop_banner"]',
                                'xpromo-nsfw-blocking-container', 'shreddit-experience-tree',
                                'reddit-sticky-header'
                            ];
                            killSelectors.forEach(sel => document.querySelectorAll(sel).forEach(e => {
                                const cs = getComputedStyle(e);
                                if (cs.position === 'fixed' || cs.position === 'sticky' || e.tagName.includes('HEADER')) {
                                    e.style.display = 'none';
                                }
                            }));
                            // 2) hide everything that isn't this comment's own
                            //    content. The current Reddit DOM lays out a
                            //    comment as direct children with slots:
                            //      commentAvatar / commentMeta / comment /
                            //      actionRow  -> KEEP
                            //      next-reply / children-* /
                            //      more-comments-permalink -> HIDE (reply tree)
                            [...c.children].forEach(el => {
                                const slot = el.getAttribute && el.getAttribute('slot');
                                if (!slot) return;
                                if (slot.startsWith('children-') ||
                                    slot === 'next-reply' ||
                                    slot === 'more-comments-permalink') {
                                    el.style.display = 'none';
                                }
                            });
                            // also hide any deeper #comment-children / details
                            // variants just in case the DOM differs.
                            c.querySelectorAll(':scope > details > #comment-children, :scope > details > div > #comment-children').forEach(e => e.style.display = 'none');

                            // Compute a TIGHT clip box from only the visible
                            // own-content slots. The shreddit-comment element's
                            // box still reserves space for the (now hidden)
                            // reply tree, so screenshotting the element itself
                            // leaves white space — we measure the kept slots
                            // instead.
                            const keep = ['commentAvatar','commentMeta','comment','actionRow'];
                            let x1=Infinity, y1=Infinity, x2=-Infinity, y2=-Infinity;
                            [...c.children].forEach(el => {
                                const slot = el.getAttribute && el.getAttribute('slot');
                                if (!keep.includes(slot)) return;
                                const r = el.getBoundingClientRect();
                                if (r.width === 0 || r.height === 0) return;
                                x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);
                                x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
                            });
                            if (!isFinite(x1)) return null;
                            // small padding around the content
                            const pad = 8;
                            return {
                                x: Math.max(0, x1 - pad),
                                y: Math.max(0, y1 - pad),
                                width: (x2 - x1) + pad * 2,
                                height: (y2 - y1) + pad * 2,
                            };
                        }""",
                        comment["comment_id"],
                    )
                    if not found:
                        raise TimeoutError("comment element not found")

                    zoom = settings.config["settings"]["zoom"]
                    if zoom != 1:
                        page.evaluate("document.body.style.zoom=" + str(zoom))
                        for k in found:
                            found[k] = float("{:.2f}".format(found[k] * zoom))

                    # Clip-screenshot the tight content box (no reserved reply
                    # space, no header overlap).
                    page.screenshot(
                        clip=found,
                        path=f"assets/temp/{reddit_id}/png/comment_{idx}.png",
                    )
                except TimeoutError:
                    del reddit_object["comments"]
                    screenshot_num += 1
                    print("TimeoutError: Skipping screenshot...")
                    continue

        # close only the page; the shared browser session stays alive
        page.close()

    print_substep("Screenshots downloaded Successfully.", style="bold green")
