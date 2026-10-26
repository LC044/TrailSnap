const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');

function harness(clipboard, legacyResult = true) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/clipboard.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const calls = [];
  let attached = false;
  const textarea = {
    value: '', style: {},
    focus: () => {}, select: () => {},
    setSelectionRange: (start, end) => calls.push(['selection', start, end]),
    remove: () => { attached = false; },
  };
  const module = { exports: {} };
  vm.runInNewContext(`(function(module, exports) { ${code}\n})`, {
    navigator: { clipboard },
    document: {
      activeElement: { focus: () => calls.push(['restore-focus']) },
      createElement: () => textarea,
      body: { appendChild: () => { attached = true; } },
      execCommand: command => {
        assert.equal(attached, true);
        calls.push([command, textarea.value]);
        if (legacyResult instanceof Error) throw legacyResult;
        return legacyResult;
      },
    },
  })(module, module.exports);
  return { copy: module.exports.copyTextToClipboard, calls, attached: () => attached };
}

test('modern clipboard copies the exact multiline prompt without legacy copy', async () => {
  let copied;
  const h = harness({ writeText: async text => { copied = text; } });
  assert.equal(await h.copy('想法\n需求链接'), true);
  assert.equal(copied, '想法\n需求链接');
  assert.deepEqual(h.calls, []);
});

test('HTTP pages without clipboard API copy through a selected textarea', async () => {
  const h = harness(undefined);
  assert.equal(await h.copy('第一行\n第二行'), true);
  assert.deepEqual(h.calls, [['selection', 0, 7], ['copy', '第一行\n第二行'], ['restore-focus']]);
  assert.equal(h.attached(), false);
});

test('denied clipboard permission falls back to selection copy', async () => {
  const h = harness({ writeText: async () => { throw Error('NotAllowedError'); } });
  assert.equal(await h.copy('完整提示词'), true);
  assert.ok(h.calls.some(call => call[0] === 'copy'));
  assert.equal(h.attached(), false);
});

test('blocked legacy copy reports failure and always removes its temporary textarea', async () => {
  for (const result of [false, new Error('copy blocked')]) {
    const h = harness(undefined, result);
    assert.equal(await h.copy('手动复制'), false);
    assert.equal(h.attached(), false);
    assert.deepEqual(h.calls.at(-1), ['restore-focus']);
  }
});
