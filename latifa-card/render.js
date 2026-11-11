// Renders index.html to latifa-card.png at exactly 1920x1080.
// Usage: node render.js            (from this folder)
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(__dirname, 'index.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(__dirname, 'latifa-card.png') });
  await browser.close();
  console.log('Wrote latifa-card.png');
})();
