import fs from 'node:fs'
import path from 'node:path'

const reportDir = path.resolve('.playwright-system/report')
const rows = []
const details = []
function visit(suites, parents = []) {
  for (const suite of suites ?? []) {
    const titles = [...parents, suite.title].filter(Boolean)
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests ?? []) {
        if (test.status === 'flaky' || test.results?.some(result => result.retry > 0) || test.status === 'unexpected' || test.status === 'skipped') {
          details.push(`- ${test.status}: ${[...titles, spec.title].join(' › ')} (${test.results?.map(result => `${result.status}, retry=${result.retry}`).join('; ')})`)
        }
      }
    }
    visit(suite.suites, titles)
  }
}
if (fs.existsSync(reportDir)) {
  for (const file of fs.readdirSync(reportDir).filter(file => file.endsWith('.json')).sort()) {
    const report = JSON.parse(fs.readFileSync(path.join(reportDir, file), 'utf8'))
    const stats = report.stats
    rows.push(`| ${path.basename(file, '.json')} | ${(stats.duration / 1000).toFixed(1)}s | ${stats.expected} | ${stats.unexpected} | ${stats.flaky} | ${stats.skipped} |`)
    visit(report.suites)
  }
}
const summary = [
  '### E2E timing and stability (2 CI workers)', '',
  '| Phase | Duration | Passed | Failed | Flaky | Skipped |',
  '|---|---:|---:|---:|---:|---:|', ...rows, '',
  ...(details.length ? ['Retry / failure / skip details:', '', ...details] : ['No retries, failures or skips recorded.']),
  ...(!rows.length ? ['No Playwright JSON reports found; check service/build logs.'] : []), '',
].join('\n')
console.log(summary)
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary)
