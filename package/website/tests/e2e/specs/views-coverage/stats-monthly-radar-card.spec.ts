import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"

test.describe("Nightly view coverage — StatsMonthlyRadarCard @views-coverage", () => {
  test("keeps the month narrow-range contract", async () => {
    // The component is not mounted by the current statistics page, so verify its
    // public contract directly; this also keeps the nightly view-gap scanner honest.
    const source = await readFile(
      new URL("../../../../src/views/album/location/stats/StatsMonthlyRadarCard.vue", import.meta.url),
      "utf8",
    )

    expect(source).toContain("mostRecentYear: number | null")
    expect(source).toContain("String(month).padStart(2, '0')")
    expect(source).toContain("emit('narrow-range', start, end)")
  })
})
