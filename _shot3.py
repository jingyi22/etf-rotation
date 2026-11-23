import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":1000})
        errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://localhost:5181/",wait_until="networkidle")
        await pg.click("#theme"); await pg.wait_for_timeout(300)
        await pg.evaluate("document.querySelectorAll('.card')[1].scrollIntoView()")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path="_dark.png")
        await pg.evaluate("document.querySelectorAll('.card')[4].scrollIntoView()")
        await pg.wait_for_timeout(300)
        await pg.screenshot(path="_dark2.png")
        print(errs)
        await b.close()
asyncio.run(main())
