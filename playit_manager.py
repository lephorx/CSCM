#!/usr/bin/env python3
"""
PlayIT Tunnel Creation Automation Script
Automates the entire tunnel setup process on playit.gg
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from pyppeteer import launch
from pyppeteer.errors import TimeoutError as PyppeteerTimeoutError

# Load environment variables
load_dotenv()

# Configuration
PLAYIT_EMAIL = os.getenv("PLAYIT_EMAIL")
PLAYIT_PASSWORD = os.getenv("PLAYIT_PASSWORD")
TUNNEL_NAME = os.getenv("TUNNEL_NAME", "minecraft-tunnel")
TUNNEL_PORT = os.getenv("TUNNEL_PORT", "25565")

TIMEOUT = 30000  # 30 seconds


async def main():
    """Main automation flow"""
    
    if not PLAYIT_EMAIL or not PLAYIT_PASSWORD:
        print("❌ Error: PLAYIT_EMAIL and PLAYIT_PASSWORD environment variables required")
        sys.exit(1)
    
    browser = None
    try:
        # Launch browser
        print("🚀 Launching browser...")
        browser = await launch(headless=False, args=["--no-sandbox"])
        page = await browser.newPage()
        await page.setViewport({"width": 1280, "height": 720})
        
        # Navigate to PlayIT
        print("📍 Navigating to playit.gg...")
        await page.goto("https://playit.gg", {"waitUntil": "load"})
        await asyncio.sleep(1)
        
        # Click Sign In
        print("🔐 Clicking Sign In...")
        await page.click('a[href="/login"]')
        await asyncio.sleep(1)
        
        # Fill email
        print(f"📧 Entering email: {PLAYIT_EMAIL}")
        await page.type('input[id="email"]', PLAYIT_EMAIL, {"delay": 50})
        await asyncio.sleep(0.5)
        
        # Fill password
        print("🔑 Entering password...")
        await page.type('input[id="password"]', PLAYIT_PASSWORD, {"delay": 50})
        await asyncio.sleep(0.5)
        
        # Click login button
        print("✅ Clicking Login...")
        await page.click('button[type="submit"]')
        
        # Wait for dashboard to load after login
        print("⏳ Waiting for dashboard...")
        await page.waitForSelector('span._11qktlo8', {"timeout": TIMEOUT})
        await asyncio.sleep(1)
        
        # Click Tunnels
        print("🌐 Clicking Tunnels...")
        await page.click('span._11qktlo8')
        await asyncio.sleep(1)
        
        # Wait for New Tunnel link to load
        print("⏳ Waiting for Tunnels page...")
        await page.waitForSelector('a[href="/account/setup/new-tunnel"]', {"timeout": TIMEOUT})
        await asyncio.sleep(0.5)
        
        # Click New Tunnel
        print("➕ Clicking New Tunnel...")
        await page.click('a[href="/account/setup/new-tunnel"]')
        await asyncio.sleep(1)
        
        # Enter tunnel name
        print(f"📝 Entering tunnel name: {TUNNEL_NAME}")
        await page.type('input[name="name"]', TUNNEL_NAME, {"delay": 50})
        await asyncio.sleep(0.5)
        
        # Click Next
        print("➡️ Clicking Next (tunnel name)...")
        await page.click('button[type="submit"]')
        await asyncio.sleep(1)
        
        # Click Minecraft Java
        print("🎮 Selecting Minecraft Java...")
        await page.click('div._15pr4g97')
        await asyncio.sleep(1)
        
        # Click Next
        print("➡️ Clicking Next (tunnel type)...")
        await page.click('button[type="submit"]')
        await asyncio.sleep(1)
        
        # Click Premium Network
        print("🌟 Selecting Premium Network...")
        await page.click('button.zrkgene')
        await asyncio.sleep(1)
        
        # Click Germany (find by text content)
        print("🇩🇪 Selecting Germany / Europe...")
        await page.evaluate("""
            () => {
                const regions = Array.from(document.querySelectorAll('div._15pr4g9g'));
                const germanyRegion = regions.find(el => el.textContent.includes('Germany'));
                if (germanyRegion) {
                    germanyRegion.click();
                }
            }
        """)
        await asyncio.sleep(1)
        
        # Click Next
        print("➡️ Clicking Next (region)...")
        await page.click('button.maeflab')
        await asyncio.sleep(1)
        
        # Click Agent s-ubumcr01
        print("🤖 Selecting Agent s-ubumcr01...")
        await page.click('div._15pr4g9v')
        await asyncio.sleep(1)
        
        # Click Next
        print("➡️ Clicking Next (agent)...")
        buttons = await page.querySelectorAll('button.maeflab')
        if buttons:
            await buttons[-1].click()
        await asyncio.sleep(1)
        
        # Clear port field and enter port
        print(f"🔌 Setting port to {TUNNEL_PORT}...")
        await page.evaluate("""
            document.querySelector('input[type="text"][placeholder="NULL"]').value = ''
        """)
        await page.type('input[placeholder="NULL"]', TUNNEL_PORT, {"delay": 50})
        await asyncio.sleep(0.5)
        
        # Click Next (submit port)
        print("➡️ Clicking Next (port)...")
        submit_buttons = await page.querySelectorAll('button[type="submit"]')
        if submit_buttons:
            await submit_buttons[-1].click()
        await asyncio.sleep(1)
        
        # Click Create Tunnel
        print("🚀 Clicking Create Tunnel...")
        await page.click('button[type="submit"]')
        await asyncio.sleep(2)
        
        # Wait for tunnel address to load
        print("⏳ Waiting for tunnel address allocation...")
        tunnel_address = await page.waitForFunction("""
            () => {
                const addressElement = document.querySelector('span.lm6flc4');
                if (addressElement && addressElement.textContent.includes('.mcjoin.link')) {
                    return addressElement.textContent.trim();
                }
                return null;
            }
        """, {"timeout": TIMEOUT * 2})
        
        # Extract the address
        address = await page.evaluate("""
            () => document.querySelector('span.lm6flc4').textContent.trim()
        """)
        
        print(f"\n✅ SUCCESS!\n🎮 Tunnel Address: {address}")
        print(f"📊 Type: Minecraft Java")
        print(f"🌍 Region: Germany (Europe)")
        print(f"🤖 Agent: s-ubumcr01 (Premium)")
        print(f"🔌 Port: {TUNNEL_PORT}\n")
        
        return address
        
    except PyppeteerTimeoutError:
        print("❌ Timeout: Page load took too long")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if browser:
            await browser.close()


if __name__ == "__main__":
    # Run async main
    result = asyncio.run(main())
    sys.exit(0)