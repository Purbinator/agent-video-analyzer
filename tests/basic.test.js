import test from 'node:test';
import assert from 'node:assert/strict';

test('basic environment sanity check', () => {
  assert.ok(process.version.startsWith('v18.'), `Expected Node 18.x, got ${process.version}`);
  assert.ok(typeof process.platform === 'string');
});
