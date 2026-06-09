import { expect, test } from "@playwright/test";

test("walking skeleton renders the full chain", async ({ page }) => {
  await page.goto("/");
  const chain = page.getByTestId("chain");
  await expect(chain).toContainText('"from": "bff"');
  await expect(chain).toContainText('"from": "fastapi"');
  await expect(chain).toContainText('"db": "continuum"');
});
