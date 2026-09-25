#!/usr/bin/env python3
"""
PlayIT tunnel automation module.

Drives a headless Chromium browser to log into playit.gg and manage tunnels.

Public functions:
    create_tunnel(tunnel_name, tunnel_port, protocol="java") -> str | None
        Provision a new Minecraft Java or Bedrock tunnel and return its
        public address.

    delete_tunnel(tunnel_name) -> bool
        Delete an existing tunnel by its display name.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from logger import get_logger

load_dotenv()

log = get_logger("playit")

PLAYIT_EMAIL        = os.getenv("PLAYIT_EMAIL")
PLAYIT_PASSWORD     = os.getenv("PLAYIT_PASSWORD")
PLAYIT_SUBSCRIPTION = os.getenv("PLAYIT_SUBSCRIPTION", "premium").lower()  # premium | free
PLAYIT_REGION       = os.getenv("PLAYIT_REGION", "Germany")  # Germany, Seattle, Los Angeles, Denver, Dallas, Chicago, New York, Miami, United Kingdom, Sweden, Poland, Spain, Singapore, Japan, Australia, Sao Paulo, Chile, India
PLAYIT_AGENT        = os.getenv("PLAYIT_AGENT", "").strip()  # Agent name (optional)
TUNNEL_NAME         = os.getenv("TUNNEL_NAME", "minecraft-tunnel")
TUNNEL_PORT         = os.getenv("TUNNEL_PORT", "25565")

# Milliseconds to wait for page elements before raising a timeout error
TIMEOUT = 30000


async def create_tunnel(tunnel_name: str, tunnel_port: int | str, region: str | None = None, subscription: str | None = None, agent: str | None = None, protocol: str = "java") -> str | None:
    """Create a PlayIT tunnel with the given name and local port.

    Drives the playit.gg web UI to provision a new Minecraft tunnel.

    Args:
        tunnel_name: Human-readable label for the tunnel (used as the tunnel
                     name inside the playit.gg dashboard).
        tunnel_port: Local port the Minecraft server is listening on.
        region: Server region (e.g., "Germany", "Seattle", "Japan").
                Defaults to PLAYIT_REGION env var or "Germany".
        subscription: Network subscription level: "premium" or "free".
                Defaults to PLAYIT_SUBSCRIPTION env var or "premium".
        agent: Agent name to use for the tunnel (e.g., "US-East", "EU-Central").
               Defaults to PLAYIT_AGENT env var or first available agent.
        protocol: "java" or "bedrock" — selects the matching protocol tile
                  in the playit.gg tunnel wizard.

    Returns:
        The allocated public address — e.g. ``abc123.joinmc.link`` for Java
        (no port; SRV discovery handles that), or e.g.
        ``cheap-throughout.deu.at.playit.plus:1037`` for Bedrock, which has
        no SRV-based port discovery so playit embeds the port directly.
        ``None`` on failure.
    """
    if not PLAYIT_EMAIL or not PLAYIT_PASSWORD:
        log.error("PLAYIT_EMAIL and PLAYIT_PASSWORD environment variables are required")
        return None

    selected_region = region or PLAYIT_REGION
    selected_subscription = (subscription or PLAYIT_SUBSCRIPTION).lower()
    selected_agent = agent or PLAYIT_AGENT
    selected_protocol = (protocol or "java").lower()

    headless = os.getenv("PLAYIT_HEADLESS", "true").strip().lower() != "false"
    log.debug("Browser headless mode: %s", headless)

    try:
        async with async_playwright() as pw:
            log.info("Launching Chromium browser")
            browser = await pw.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                storage_state=None,
            )
            page = await context.new_page()

            if not await _login(page):
                await context.close()
                await browser.close()
                return None

            await asyncio.sleep(1)

            log.debug("Navigating to Tunnels section")
            await page.goto("https://playit.gg/account/tunnels", wait_until="networkidle")
            await asyncio.sleep(1)

            await page.wait_for_selector('a[href="/account/setup/new-tunnel"]', timeout=TIMEOUT)
            await asyncio.sleep(0.5)

            log.info("Creating new tunnel: name=%s, port=%s", tunnel_name, tunnel_port)
            await page.click('a[href="/account/setup/new-tunnel"]')
            await asyncio.sleep(1)

            await page.fill('input[name="name"]', tunnel_name)
            await asyncio.sleep(0.5)

            # Confirm tunnel name
            await page.click('button[type="submit"]')
            await asyncio.sleep(1)

            # Select protocol tile. All protocol tiles share the "_15pr4g97"
            # class (e.g. <div class="_15pr4g97"><img .../><span
            # class="_15pr4g9d">Minecraft Bedrock</span></div>); the label
            # text is what distinguishes them, so filter on it explicitly
            # rather than relying on DOM order.
            protocol_label = "Minecraft Bedrock" if selected_protocol == "bedrock" else "Minecraft Java"
            log.debug("Selecting %s protocol", protocol_label)
            try:
                await page.click(f'div._15pr4g97:has-text("{protocol_label}")', timeout=TIMEOUT)
            except PlaywrightTimeoutError:
                log.warning("Could not find '%s' protocol tile via CSS selector; trying text search", protocol_label)
                if not await _click_by_text(page, protocol_label):
                    log.warning("Falling back to first protocol tile — may select the wrong protocol")
                    await page.click('div._15pr4g97')
            await asyncio.sleep(1)
            await page.click('button[type="submit"]')
            await asyncio.sleep(1)

            # Select network (Premium or Free)
            log.debug("Selecting %s network", selected_subscription.upper())
            if selected_subscription == "free":
                await page.click('button.zrkgene:has-text("Free Network")')
            else:
                await page.click('button.zrkgene:has-text("Premium Network")')
            await asyncio.sleep(1)

            # Select region
            log.debug("Selecting region: %s", selected_region)
            await page.evaluate(f"""
                () => {{
                    const regions = Array.from(document.querySelectorAll('div._15pr4g9g'));
                    const target = regions.find(el => el.textContent.includes('{selected_region}'));
                    if (target) target.click();
                }}
            """)
            await asyncio.sleep(1)
            await page.click('button.maeflab')
            await asyncio.sleep(1)

            # Select agent
            if not await _select_agent(page, selected_agent):
                log.warning("Agent selection may have failed; continuing anyway")
            await asyncio.sleep(1)

            # Click Next after agent selection
            log.debug("Clicking Next after agent selection")
            await page.click('button.maeflab')
            await asyncio.sleep(1)

            # Set local port
            log.debug("Setting local port: %s", tunnel_port)
            await page.fill('input[placeholder="NULL"]', str(tunnel_port))
            await asyncio.sleep(0.5)
            submit_buttons = await page.query_selector_all('button[type="submit"]')
            if submit_buttons:
                await submit_buttons[-1].click()
            await asyncio.sleep(1)

            # Submit tunnel creation
            await page.click('button[type="submit"]')
            await asyncio.sleep(2)

            log.info("Waiting for tunnel address allocation")
            # Java addresses look like "abc123.joinmc.link" (no port — SRV
            # discovery handles that); Bedrock addresses embed the port
            # directly, e.g. "cheap-throughout.deu.at.playit.plus:1037".
            # Match on the general host[:port] shape instead of hardcoding
            # domain suffixes, since the two protocols use different domains.
            await page.wait_for_function("""
                () => {
                    const el = document.querySelector('span.lm6flc4');
                    if (!el) return null;
                    const text = el.textContent.trim();
                    return /^[\\w.-]+\\.[a-z]{2,}(?::\\d+)?$/i.test(text) ? text : null;
                }
            """, timeout=TIMEOUT * 2)

            address = await page.evaluate(
                "() => document.querySelector('span.lm6flc4').textContent.trim()"
            )

            log.info("Tunnel created successfully: address=%s, port=%s", address, tunnel_port)
            await context.close()
            await browser.close()
            return address

    except PlaywrightTimeoutError:
        log.error("Tunnel creation timed out waiting for a page element")
        return None
    except Exception as exc:
        log.exception("Unexpected error during tunnel creation: %s", exc)
        return None


async def _click_by_text(page, text: str) -> bool:
    """Best-effort click on any element containing the given visible text.

    Used for UI elements (like protocol tiles) whose CSS classes are
    generated build hashes and can't be relied on across playit.gg deploys.
    """
    try:
        locator = page.get_by_text(text, exact=False)
        if await locator.count() > 0:
            await locator.first.click(timeout=4000)
            return True
    except Exception:
        pass

    try:
        return await page.evaluate(
            """
            (text) => {
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, null, false
                );
                let node;
                while ((node = walker.nextNode())) {
                    if (node.textContent.trim().includes(text)) {
                        let el = node.parentElement;
                        for (let i = 0; i < 6 && el; i++) {
                            const tag = el.tagName;
                            const role = el.getAttribute('role') || '';
                            const cur = window.getComputedStyle(el).cursor;
                            if (tag === 'BUTTON' || tag === 'A' ||
                                role === 'button' || cur === 'pointer') {
                                el.click();
                                return true;
                            }
                            el = el.parentElement;
                        }
                    }
                }
                return false;
            }
            """,
            text,
        )
    except Exception:
        return False


async def _select_agent(page, agent_name: str | None) -> bool:
    """Select a PlayIT agent during tunnel creation.

    Tries four strategies in order and returns True when one succeeds.
    Falls back to "first available" if the named agent cannot be found.

    Strategies:
      1. Playwright get_by_text — most reliable when text is accessible.
      2. href-based anchor tag — stable because PlayIT agent links always
         contain '/account/agents/' in their href.
      3. JavaScript text-node walk — works when the element is not in the
         Playwright accessibility tree but exists in the DOM.
      4. First visible interactive element — last resort.
    """
    await asyncio.sleep(0.5)
    log.debug("Selecting agent: %s", agent_name or "first available")

    async def _try_name(name: str) -> bool:
        # Strategy 1: Playwright locator by visible text
        try:
            locator = page.get_by_text(name, exact=False)
            if await locator.count() > 0:
                await locator.first.click(timeout=4000)
                log.debug("Agent selected via get_by_text: %s", name)
                return True
        except Exception:
            pass

        # Strategy 2: anchor tag whose href references the agent
        # (e.g. <a href="/account/agents/{uuid}">…<span>Agent name</span>…</a>)
        try:
            clicked = await page.evaluate(f"""
                (name) => {{
                    const anchors = Array.from(document.querySelectorAll('a[href*="/account/agents/"]'));
                    const match = anchors.find(el => el.textContent.includes(name));
                    if (match) {{ match.click(); return true; }}
                    return false;
                }}
            """, name)
            if clicked:
                log.debug("Agent selected via href anchor: %s", name)
                return True
        except Exception:
            pass

        # Strategy 3: generic text-node walk for any clickable parent
        try:
            clicked = await page.evaluate(f"""
                (name) => {{
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null, false
                    );
                    let node;
                    while ((node = walker.nextNode())) {{
                        if (node.textContent.trim().includes(name)) {{
                            let el = node.parentElement;
                            for (let i = 0; i < 6 && el; i++) {{
                                const tag = el.tagName;
                                const role = el.getAttribute('role') || '';
                                const cur = window.getComputedStyle(el).cursor;
                                if (tag === 'BUTTON' || tag === 'A' ||
                                    role === 'button' || cur === 'pointer') {{
                                    el.click();
                                    return true;
                                }}
                                el = el.parentElement;
                            }}
                        }}
                    }}
                    return false;
                }}
            """, name)
            if clicked:
                log.debug("Agent selected via text-node walk: %s", name)
                return True
        except Exception:
            pass

        return False

    # --- Named agent path ---
    if agent_name:
        if await _try_name(agent_name):
            return True
        log.warning("Agent '%s' not found; trying first available instead", agent_name)

    # --- First available path (also fallback for named) ---
    # Strategy 4a: first anchor tag linking to an agent page
    try:
        first = await page.query_selector('a[href*="/account/agents/"]')
        if first:
            await first.click()
            log.debug("Clicked first agent anchor (href strategy)")
            return True
    except Exception:
        pass

    # Strategy 4b: first visible interactive element on the step
    try:
        clicked = await page.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll(
                    'button, a[href], [role="button"]'
                ));
                const candidate = els.find(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 80 && r.height > 30;
                });
                if (candidate) { candidate.click(); return true; }
                return false;
            }
        """)
        if clicked:
            log.debug("Clicked first large interactive element as agent fallback")
            return True
    except Exception:
        pass

    return False


async def _login(page) -> bool:
    """Navigate to playit.gg and authenticate.

    Args:
        page: A Playwright Page instance.

    Returns:
        ``True`` on successful login, ``False`` on failure.
    """
    log.debug("Navigating to playit.gg")
    await page.goto("https://playit.gg", wait_until="load")
    await asyncio.sleep(1)

    log.debug("Opening login page")
    await page.click('a[href="/login"]')
    await asyncio.sleep(1)

    log.debug("Entering credentials")
    await page.fill('input[id="email"]', PLAYIT_EMAIL)
    await asyncio.sleep(0.5)
    await page.fill('input[id="password"]', PLAYIT_PASSWORD)
    await asyncio.sleep(0.5)

    log.info("Submitting login form")
    await page.click('button[type="submit"]')

    try:
        await page.wait_for_selector('span._11qktlo8', timeout=TIMEOUT)
        log.debug("Login successful")
        return True
    except PlaywrightTimeoutError:
        log.error("Login failed — dashboard did not appear within timeout")
        return False


async def delete_tunnel(tunnel_name: str) -> bool:
    """Delete an existing PlayIT tunnel by its display name.

    Navigates the playit.gg dashboard to find the tunnel with the given name,
    then triggers the delete flow: tunnel detail -> options menu -> delete
    button -> confirmation dialog.

    Args:
        tunnel_name: The exact display name of the tunnel to delete
                     (case-sensitive, as shown in the dashboard).

    Returns:
        ``True`` if the tunnel was deleted, ``False`` on failure.
    """
    if not PLAYIT_EMAIL or not PLAYIT_PASSWORD:
        log.error("PLAYIT_EMAIL and PLAYIT_PASSWORD environment variables are required")
        return False

    headless = os.getenv("PLAYIT_HEADLESS", "true").strip().lower() != "false"
    log.info("Deleting PlayIT tunnel: name=%s", tunnel_name)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                storage_state=None,
            )
            page = await context.new_page()

            # Authenticate
            if not await _login(page):
                await context.close()
                await browser.close()
                return False

            await asyncio.sleep(1)

            # Navigate to Tunnels list
            log.debug("Opening Tunnels list")
            await page.goto("https://playit.gg/account/tunnels", wait_until="networkidle")
            await asyncio.sleep(1)

            # Find and click the tunnel link by its display name
            log.debug("Locating tunnel: %s", tunnel_name)
            tunnel_link = await page.wait_for_function(
                f"""
                () => {{
                    const containers = Array.from(document.querySelectorAll('div._17i11qw3'));
                    return containers.find(el => el.textContent.includes({repr(tunnel_name)})) || null;
                }}
                """,
                timeout=TIMEOUT,
            )
            if not tunnel_link:
                log.error("Tunnel not found in dashboard: %s", tunnel_name)
                await context.close()
                await browser.close()
                return False

            await tunnel_link.click()
            await asyncio.sleep(1)

            # Open the options menu — the list-ul icon button
            log.debug("Opening options menu (list-ul button)")
            await page.wait_for_selector('button:has(svg[data-icon="list-ul"])', timeout=TIMEOUT)
            await page.click('button:has(svg[data-icon="list-ul"])')
            await asyncio.sleep(0.5)

            # Click the Delete option specifically (by visible text)
            log.debug("Clicking Delete option")
            delete_option = await page.wait_for_selector(
                'button:has-text("Delete")', timeout=TIMEOUT
            )
            await delete_option.click()
            await asyncio.sleep(0.5)

            # Confirm deletion — click the confirm Delete button in the dialog
            log.debug("Confirming deletion")
            confirm_btn = await page.wait_for_selector(
                'button:has-text("Delete")', timeout=TIMEOUT
            )
            await confirm_btn.click()
            await asyncio.sleep(1)

            log.info("Tunnel deleted successfully: name=%s", tunnel_name)
            await context.close()
            await browser.close()
            return True

    except PlaywrightTimeoutError:
        log.error("Tunnel deletion timed out waiting for a page element")
        return False
    except Exception as exc:
        log.exception("Unexpected error during tunnel deletion: %s", exc)
        return False


async def _main() -> None:
    """Standalone entry point — reads configuration from environment variables."""
    result = await create_tunnel(tunnel_name=TUNNEL_NAME, tunnel_port=TUNNEL_PORT)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
