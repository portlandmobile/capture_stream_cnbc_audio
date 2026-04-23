#!/usr/bin/env python3
"""Inspect the TuneIn iframe inside CNBC live audio for the play button."""

from playwright.sync_api import sync_playwright

URL = "https://www.cnbc.com/live-audio/"

def dismiss_dialogs(page):
    for selector in [
        "button:has-text('Continue')",
        "button.save-preference-btn-handler",
        "button:has-text('Confirm My Choice')",
        "button:has-text('Accept All')",
        ".onetrust-accept-btn-handler",
        "#onetrust-accept-btn-handler",
    ]:
        try:
            page.click(selector, timeout=2000)
            print(f"  Closed dialog via: {selector}")
            page.wait_for_timeout(1500)
            break
        except Exception:
            pass

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page()
        print(f"Opening {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        dismiss_dialogs(page)
        page.wait_for_timeout(2000)

        # Find the TuneIn iframe
        tunein_frame = None
        for frame in page.frames:
            if "tunein" in frame.url:
                tunein_frame = frame
                print(f"\nFound TuneIn frame: {frame.url}")
                break

        if not tunein_frame:
            print("TuneIn frame not found yet, waiting...")
            page.wait_for_timeout(3000)
            for frame in page.frames:
                if "tunein" in frame.url:
                    tunein_frame = frame
                    print(f"Found TuneIn frame: {frame.url}")
                    break

        if not tunein_frame:
            print("ERROR: Could not find TuneIn frame.")
            input("Press Enter to close.")
            browser.close()
            return

        # Dump everything inside the TuneIn iframe
        print("\n--- All buttons/interactive elements in TuneIn iframe ---")
        elements = tunein_frame.query_selector_all("button, [role='button'], [class*='play' i], [aria-label*='play' i], svg, [class*='btn' i]")
        for el in elements[:30]:
            tag = el.evaluate("e => e.tagName")
            cls = el.get_attribute("class") or ""
            label = el.get_attribute("aria-label") or ""
            eid = el.get_attribute("id") or ""
            role = el.get_attribute("role") or ""
            try:
                text = (el.text_content() or "").strip()[:40]
            except Exception:
                text = ""
            visible = el.is_visible()
            print(f"  <{tag.lower()}> id={eid!r} role={role!r} class={cls[:70]!r} "
                  f"aria-label={label!r} text={text!r} visible={visible}")

        print("\n--- Full iframe HTML (first 3000 chars) ---")
        html = tunein_frame.evaluate("() => document.body.innerHTML")
        print(html[:3000])

        print("\nPress Enter to close.")
        input()
        browser.close()

if __name__ == "__main__":
    main()
