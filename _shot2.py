import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1200,"height":900})
        errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto("http://localhost:5181/",wait_until="networkidle")
        box=await pg.evaluate("(()=>{const r=document.querySelector('.chart[data-k=\"nav\"] svg').getBoundingClientRect();return [r.left,r.top,r.width,r.height];})()")
        await pg.evaluate("document.querySelector('.chart[data-k=\"nav\"]').scrollIntoView({block:'center'})")
        await pg.wait_for_timeout(300)
        box=await pg.evaluate("(()=>{const r=document.querySelector('.chart[data-k=\"nav\"] svg').getBoundingClientRect();return [r.left,r.top,r.width,r.height];})()")
        await pg.mouse.move(box[0]+box[2]*0.55, box[1]+box[3]*0.4)
        await pg.wait_for_timeout(400)
        await pg.screenshot(path="_local_hover2.png")
        tip=await pg.evaluate("document.querySelector('.chart[data-k=\"nav\"] .tooltip').textContent")
        print("tip:",' '.join(tip.split()), "box", box)
        await b.close()
asyncio.run(main())
