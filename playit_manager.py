#!/usr/bin/env python3
"""
PlayIT tunnel automation module.

Drives a headless Chromium browser to log into playit.gg and create a
new Minecraft Java tunnel for a given local port.  Returns the allocated
public tunnel address (e.g. ``abc.deu.mcjoin.link``) on success.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from logger import get_logger

load_dotenv()

log = get_logger("playit")

PLAYIT_EMAIL    = os.getenv("PLAYIT_EMAIL")
PLAYIT_PASSWORD = os.getenv("PLAYIT_PASSWORD")
TUNNEL_NAME     = os.getenv("TUNNEL_NAME", "minecraft-tunnel")
TUNNEL_PORT     = os.getenv("TUNNEL_PORT", "25565")

# Milliseconds to wait for page elements before raising a timeout error
TIMEOUT = 30000


async def create_tunnel(tunnel_name: str, tunnel_port: int | str) -> str | None:
    """Create a PlayIT tunnel with the given name and local port.

    Drives the playit.gg web UI to provision a new Minecraft Java tunnel.

    Args:
        tunnel_name: Human-readable label for the tunnel (used as the tunnel
                     name inside the playit.gg dashboard).
        tunnel_port: Local port the Minecraft server is listening on.

    Returns:
        The allocated public address (e.g. ``abc.deu.mcjoin.link``),
        or ``None`` on failure.
    """
    if not PLAYIT_EMAIL or not PLAYIT_PASSWORD:
        log.error("PLAYIT_EMAIL and PLAYIT_PASSWORD environment variables are required")
        return None

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
            page = await browser.new_page(viewport={"width": 1280, "height": 720})

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

            log.debug("Waiting for dashboard")
            await page.wait_for_selector('span._11qktlo8', timeout=TIMEOUT)
            await asyncio.sleep(1)

            log.debug("Navigating to Tunnels section")
            await page.click('span._11qktlo8')
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

            # Select Minecraft Java protocol
            log.debug("Selecting Minecraft Java protocol")
            await page.click('div._15pr4g97')
            await asyncio.sleep(1)
            await page.click('button[type="submit"]')
            await asyncio.sleep(1)

            # Select Premium Network
            log.debug("Selecting Premium Network")
            await page.click('button.zrkgene')
            await asyncio.sleep(1)

            # Select Germany / Europe region
            log.debug("Selecting Germany / Europe region")
            await page.evaluate("""
                () => {
                    const regions = Array.from(document.querySelectorAll('div._15pr4g9g'));
                    const target = regions.find(el => el.textContent.includes('Germany'));
                    if (target) target.click();
                }
            """)
            await asyncio.sleep(1)
            await page.click('button.maeflab')
            await asyncio.sleep(1)

            # Select agent
            log.debug("Selecting agent")
            await page.click('div._15pr4g9v')
            await asyncio.sleep(1)
            buttons = await page.query_selector_all('button.maeflab')
            if buttons:
                await buttons[-1].click()
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
            await page.wait_for_function("""
                () => {
                    const el = document.querySelector('span.lm6flc4');
                    return el && el.textContent.includes('.mcjoin.link')
                        ? el.textContent.trim()
                        : null;
                }
            """, timeout=TIMEOUT * 2)

            address = await page.evaluate(
                "() => document.querySelector('span.lm6flc4').textContent.trim()"
            )

            log.info("Tunnel created successfully: address=%s, port=%s", address, tunnel_port)
            await browser.close()
            return address

    except PlaywrightTimeoutError:
        log.error("Tunnel creation timed out waiting for a page element")
        return None
    except Exception as exc:
        log.exception("Unexpected error during tunnel creation: %s", exc)
        return None


async def _main() -> None:
    """Standalone entry point — reads configuration from environment variables."""
    result = await create_tunnel(tunnel_name=TUNNEL_NAME, tunnel_port=TUNNEL_PORT)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
