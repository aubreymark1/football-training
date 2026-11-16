import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function environment() {
  const listeners = new WeakMap();
  function target(extra = {}) {
    const node = {textContent: '', hidden: true, style: {}, dataset: {},
      classList: {toggle() {}, add() {}, remove() {}},
      addEventListener(type, listener) {
        const list = listeners.get(this) || {};
        (list[type] ||= []).push(listener); listeners.set(this, list);
      },
      async emit(type, event = {}) {
        await Promise.all((listeners.get(this)?.[type] || []).map(fn => fn(event)));
      }, ...extra};
    return node;
  }
  const input = target({files: []}), sport = target({value: ''});
  const button = target({textContent: '提交记录', disabled: false});
  const filename = target(), meta = target(), error = target();
  const nodes = {'.upload': target(), '.upload-thumb': target(),
    '.upload-text strong': filename, '.upload-text small': meta,
    '.form-error': error, '.effort output': target(), 'button.primary': button};
  const form = target({elements: {sport, image: input},
    querySelector: selector => nodes[selector] || null, querySelectorAll: () => []});
  const bitmaps = new Map();
  const document = target({querySelectorAll: selector => selector === 'form[data-record-form]' ? [form] : [],
    createElement: () => ({getContext: () => ({drawImage() {}}), toBlob: cb => cb({size: 1000})})});
  class DataTransfer {
    constructor() { this.files = []; this.items = {add: file => this.files.push(file)}; }
  }
  const context = {document, window: target(), DataTransfer, setTimeout,
    createImageBitmap: file => new Promise((resolve, reject) => bitmaps.set(file.name, {resolve, reject})),
    URL: {createObjectURL: file => file.name, revokeObjectURL() {}},
    File: class { constructor(parts, name, options) { this.name=name; this.size=parts[0].size; this.type=options.type; } }};
  vm.runInNewContext(fs.readFileSync(process.env.SITE_SCRIPT || new URL('./static/site.js', import.meta.url), 'utf8'), context);
  return {input, button, filename, error, form, bitmaps};
}

test('an older compression cannot replace a newer chosen screenshot', async () => {
  const env=environment();
  env.input.files=[{name:'old.png',size:9*1024*1024}];
  const old=env.input.emit('change');
  env.input.files=[{name:'latest.png',size:1000}]; await env.input.emit('change');
  env.bitmaps.get('old.png').resolve({width:3000,height:3000}); await old;
  assert.equal(env.input.files[0].name,'latest.png');
  assert.equal(env.filename.textContent,'latest.png');
  assert.equal(env.button.disabled,false);
});

test('submission waits for the currently selected image to finish processing', async () => {
  const env=environment();env.input.files=[{name:'large.png',size:9*1024*1024}];
  const processing=env.input.emit('change');
  const event={defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};
  await env.form.emit('submit',event);
  assert.equal(event.defaultPrevented,true);
  assert.equal(env.button.disabled,true);
  env.bitmaps.get('large.png').resolve({width:3000,height:3000});await processing;
  assert.equal(env.button.disabled,false);
  assert.equal(env.input.files[0].name,'large.jpg');
});

test('failure of an obsolete image leaves the new screenshot intact', async () => {
  const env=environment();env.input.files=[{name:'old.png',size:9*1024*1024}];
  const old=env.input.emit('change');
  env.input.files=[{name:'latest.png',size:1000}];await env.input.emit('change');
  env.bitmaps.get('old.png').reject(new Error('decode failed'));await old;
  assert.equal(env.filename.textContent,'latest.png');
  assert.equal(env.error.hidden,true);
});
