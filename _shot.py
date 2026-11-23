import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1200, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console:"+m.text) if m.type=="error" else None)
        await pg.goto("https://jingyi22.github.io/etf-rotation/", wait_until="networkidle")
        await pg.screenshot(path="_live_top.png")
        box = await pg.evaluate("(()=>{const r=document.querySelector('.chart[data-k='nav'] svg').getBoundingClientRect();return [r.left+r.width*0.55, r.top+r.height*0.4];})()")
        await pg.mouse.move(box[0], box[1])
        await pg.wait_for_timeout(400)
        await pg.screenshot(path="_live_hover.png")
        h = await pg.evaluate("[...document.querySelectorAll('.chart')].map(e=>{const r=e.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)]})")
        tip = await pg.evaluate("document.querySelector('.chart[data-k=\"nav\"] .tooltip').textContent.replace(/\s+/g,' ')")
        # dark
        await pg.click("#theme")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path="_live_dark.png")
        # mobile
        await pg.set_viewport_size({"width": 390, "height": 844})
        await pg.click("#theme")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path="_live_mobile.png", full_page=False)
        sw = await pg.evaluate("document.documentElement.scrollWidth")
        print("charts", h, "tip", tip, "scrollW", sw, "errs", errs)
        await b.close()
asyncio.run(main())
