import { expect, test } from "@playwright/test"

test.describe("Nightly view coverage — StatsMonthlyRadarCard @views-coverage", () => {
  test("month button emits a padded month range from the most recent year", async ({ page }) => {
    await page.goto("/")
    await page.evaluate(async () => {
      const vue = await import("/node_modules/vue/dist/vue.runtime.esm-browser.js")
      const [component, themeModule] = await Promise.all([
        import("/src/views/album/location/stats/StatsMonthlyRadarCard.vue"),
        import("/src/composables/useTheme.ts"),
      ])
      const host = document.createElement("div")
      document.body.append(host)
      const data = Array.from({ length: 12 }, (_, index) => ({
        month: index + 1,
        photo_count: index + 1,
        activity_score: index + 1,
      }))
      const app = vue.createApp({
        setup() { themeModule.provideTheme() }, render: () => vue.h(component.default, {
          data,
          mostRecentYear: 2025,
          loading: false,
          error: false,
          onNarrowRange: (start: string, end: string) => {
            (window as typeof window & { __radarRange?: string[] }).__radarRange = [start, end]
          },
        }),
      })
      app.mount(host)
    })

    await expect(page.getByRole("heading", { name: "月度出行雷达" })).toBeVisible()
    await page.getByRole("button", { name: "2月", exact: true }).click()
    await expect.poll(() => page.evaluate(() => (window as typeof window & { __radarRange?: string[] }).__radarRange)).toEqual(["2025-02-01", "2025-02-28"])
  })
})
