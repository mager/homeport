const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const { parseHTML } = require('linkedom');
function renderer() {
  const { document } = parseHTML('<html><body></body></html>');
  const window = {};
  let copied;
  runInNewContext(readFileSync('src/magerbot/static/markdown.js', 'utf8'), {
    document, window, URL, setTimeout: () => {},
    navigator: { clipboard: { writeText: async (value) => { copied = value; } } },
  });
  return { render: window.HomeportMarkdown.render, copied: () => copied };
}
test('model HTML remains text and unsafe links are never activated', () => {
  const { render } = renderer();
  const node = render('<img src=x onerror=alert(1)>\n\n[bad](javascript:alert) [bad](data:text/html,test) [file](file:///etc/passwd)\n\n**<script>alert(1)</script>**');
  assert.equal(node.querySelectorAll('img,script,iframe,a').length, 0);
  assert.match(node.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(node.querySelector('strong').textContent, '<script>alert(1)</script>');
});
test('readable headings, emphasis, lists and safe links', () => {
  const { render } = renderer();
  const node = render('## Findings\n\n**Useful** and `literal <code>`\n\n- First\n- Second\n\n3. Third\n4. Fourth\n\n[Docs](https://example.com/docs?q=one&v=2)');
  assert.equal(node.querySelector('h3').textContent, 'Findings');
  assert.equal(node.querySelector('code').textContent, 'literal <code>');
  assert.equal(node.querySelectorAll('li').length, 4);
  assert.equal(node.querySelector('ol').start, 3);
  const link = node.querySelector('a');
  assert.equal(link.href, 'https://example.com/docs?q=one&v=2');
  assert.equal(link.rel, 'noopener noreferrer');
});
test('code stays literal, copy is exact, and unfinished streaming fences render', async () => {
  const { render, copied } = renderer();
  const code = '<script>hello</script>\n  **literal**';
  const node = render('```html\n' + code);
  assert.equal(node.querySelector('pre').textContent, code);
  assert.equal(node.querySelectorAll('script,strong').length, 0);
  await node.querySelector('button').onclick();
  assert.equal(copied(), code);
  assert.equal(node.querySelector('button').textContent, 'Copied');
});
test('plain text and unsupported syntax stay visible', () => {
  const { render } = renderer();
  assert.equal(render('one\ntwo\n\n[local](/local/path)').textContent, 'one\ntwo[local](/local/path)');
});
