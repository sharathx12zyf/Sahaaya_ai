// Full end-to-end test of Sahaaya AI in a real browser, from a fresh start.
const { chromium } = require('playwright');
const out = process.argv[2] || '.';
const results = [];
const check = (name, ok, info = '') => { results.push([ok ? 'PASS' : 'FAIL', name, info]); };
const waitAgent = (p, n) => p.waitForFunction((n) => document.querySelectorAll('#chat .msg.agent').length >= n &&
  document.querySelector('#callstate').textContent !== 'thinking', n, { timeout: 120000 });
async function say(p, t) { const n = await p.$$eval('#chat .msg.agent', e => e.length); await p.fill('#typed', t); await p.press('#typed', 'Enter'); await waitAgent(p, n + 1); await p.waitForTimeout(400); return p.$eval('#chat .msg.agent:last-of-type', e => e.innerText); }
async function lastAgent(p) { return (await p.$$eval('#chat .msg.agent', e => e.map(x => x.innerText))).pop(); }
async function startCall(p, caller, lang) {
  if (await p.$('#endbtn:not(.hidden)')) { await p.click('#endbtn'); await p.waitForTimeout(800); }
  await p.fill('#callerphone', ''); await p.selectOption('#lang', lang);
  if (caller) await p.fill('#callerphone', caller);
  await p.click('#startbtn'); await waitAgent(p, 1);
}
async function setup(p, t) { const n = await p.$$eval('#setupchat .msg.agent', e => e.length); await p.fill('#setuptext', t); await p.press('#setuptext', 'Enter');
  await p.waitForFunction((n) => document.querySelectorAll('#setupchat .msg.agent').length > n, n, { timeout: 120000 }); await p.waitForTimeout(1200); }
const api = (p, path) => p.evaluate(async (u) => (await fetch(u)).json(), path);

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto('http://127.0.0.1:8000'); await p.waitForTimeout(2000);

  // ---------- SECTION 1: Service Center ----------
  await setup(p, "I run a mobile phone repair shop called Sharath Mobile Service in Jayanagar, Bangalore. Talk like a normal person, don't say you are AI. Give 1 hour slots, be available 24/7, book customers and show me their name, mobile and problem. If they ask the price, say we need to check the phone, please visit once, then we give a quotation. Agent name Arjun.");
  await setup(p, "That's all, finish.");
  let o = await api(p, '/api/service/overview');
  check('Setup by talking: 24/7 + 1-hour slots + name', o.settings.open === '00:00' && o.settings.close === '24:00' && o.settings.slot_minutes === 60 && o.settings.name.includes('Sharath'), JSON.stringify({ n: o.settings.name, o: o.settings.open, c: o.settings.close, s: o.settings.slot_minutes }));
  check('Setup: no sample facts kept', !/warranty|Water damage check is free/i.test(o.settings.info), o.settings.info);
  check('Setup: AI not announced', o.settings.announce_ai === false);

  await startCall(p, '9845012345', 'kn');
  const greet = await lastAgent(p);
  check('Greeting natural, no "AI"', !/AI/.test(greet) && /Arjun/.test(greet), greet);
  let a1 = await say(p, 'ನಮಸ್ಕಾರ, ನನ್ನ phone screen ಒಡೆದಿದೆ, ಎಷ್ಟು ಆಗುತ್ತೆ?');
  check('Price: no number quoted, asks to visit/quotation', !/₹|rupee|ರೂಪಾಯಿ\s*\d|\d{3,}\s*ರೂ/i.test(a1) && /quotation|ನೋಡಿ|check/i.test(a1), a1);
  await say(p, 'ನಾಳೆ ಸಂಜೆ ಆರು ಗಂಟೆಗೆ ಬರ್ತೀನಿ, ನಾನು ಕಿರಣ್');
  let a3 = await say(p, 'ಹೌದು');
  await p.waitForTimeout(1500);
  o = await api(p, '/api/service/overview');
  const bk = o.bookings.find(x => x.phone === '9845012345');
  check('Booking saved with name, mobile, problem', !!bk && /kiran|ಕಿರಣ್/i.test(bk.name) && /screen/i.test(bk.purpose), JSON.stringify(bk));
  check('Booked time spoken back', /6|ಆರು/.test(a3), a3);
  const tableText = await p.$eval('#bookings', e => e.innerText);
  check('Bookings table shows it', tableText.includes('9845012345'), '');
  check('sir written in English letters', !/ಸಾರ್|ಸರ್/.test(await p.$eval('#chat', e => e.innerText)));
  await p.click('#endbtn'); await p.waitForTimeout(800);

  // Hindi, no name
  await startCall(p, '9845012346', 'hi');
  await say(p, 'मेरे phone में पानी चला गया, आज शाम आ सकता हूँ?');
  await say(p, 'शाम 7 बजे ठीक है, नाम ज़रूरी है क्या?');
  let h3 = await lastAgent(p);
  if (!/(हो गया|हो गई|book कर दिया|booked)/i.test(h3)) h3 = await say(p, 'हाँ जी, कर दीजिए');
  await p.waitForTimeout(1200);
  o = await api(p, '/api/service/overview');
  const bk2 = o.bookings.find(x => x.phone === '9845012346');
  check('Hindi: no-name booking as Customer', !!bk2 && /customer/i.test(bk2.name), JSON.stringify(bk2));
  check('Hindi male verb forms', !/(बोल रही|करती हूँ|देखती हूँ|दूँगी)/.test(await p.$eval('#chat', e => e.innerText)));
  await p.click('#endbtn'); await p.waitForTimeout(800);

  // Telugu + English quick checks
  await startCall(p, '9845012347', 'te');
  let t1 = await say(p, 'హలో, నా phone charging అవ్వట్లేదు, రేపు ఉదయం రావచ్చా?');
  check('Telugu reply in Telugu with times', /[ఀ-౿]/.test(t1) && /\d/.test(t1), t1);
  await p.click('#endbtn'); await p.waitForTimeout(800);
  await startCall(p, '9845012348', 'en');
  let e1 = await say(p, 'hey, my phone speaker is not working, can I come tomorrow evening?');
  check('English reply offers evening times', /evening|pm|\d/i.test(e1), e1);
  await p.click('#endbtn'); await p.waitForTimeout(800);
  await p.screenshot({ path: out + '/e2e-1-service.png', fullPage: false });

  // Grocery template + item + order
  await p.selectOption('#btype', 'grocery'); await p.waitForTimeout(2500);
  o = await api(p, '/api/service/overview');
  check('Switch to kirana store template', o.settings.type === 'grocery' && o.settings.features.orders, o.settings.type);
  await p.fill('#catform [name=n]', 'Ghee (ತುಪ್ಪ)'); await p.fill('#catform [name=p]', '650'); await p.fill('#catform [name=u]', '1 litre');
  await p.click('#catform button'); await p.waitForTimeout(1200);
  o = await api(p, '/api/service/overview');
  check('Owner adds an item', o.settings.catalog.some(r => r[0].startsWith('Ghee')), '');
  await startCall(p, '9845012349', 'kn');
  let g1 = await say(p, 'ಒಂದು ಲೀಟರ್ ತುಪ್ಪ ಮತ್ತು 2 ಕೆಜಿ ಅಕ್ಕಿ ಬೇಕು, pickup ಮಾಡ್ತೀನಿ');
  check('Order total correct (650 + 2x60 = 770)', /770/.test(g1) || /770/.test(await say(p, 'ಒಟ್ಟು ಎಷ್ಟು?')), g1);
  await say(p, 'ಹೌದು, order ಮಾಡಿ');
  await p.waitForTimeout(1200);
  o = await api(p, '/api/service/overview');
  check('Order saved on dashboard', o.records.some(r => r.phone === '9845012349'), '');
  await p.click('#endbtn'); await p.waitForTimeout(800);
  await p.selectOption('#btype', 'repair'); await p.waitForTimeout(1500);

  // ---------- SECTION 2: Dashboard Connect ----------
  await p.click('[data-tab=connect]'); await p.waitForTimeout(2000);
  const cs = await p.$eval('#connstatus', e => e.innerText);
  check('Sample dashboard connected (6 actions)', /6 actions/.test(cs), cs);
  const delSel = await p.$eval('select[data-op=delete_user]', e => e.value);
  check('Delete action blocked by default', delSel === 'blocked', delSel);
  await p.fill('#cdesctext', 'Our company QuickKart is an online shopping app. Agent name Arjun.');
  await p.press('#cdesctext', 'Enter'); await p.waitForTimeout(9000);
  const prof = (await api(p, '/api/connect')).profile;
  check('Company described by text', /QuickKart/i.test(prof.name), JSON.stringify(prof));
  await p.fill('#teachtext', 'ಯಾರಾದರೂ order ಬಗ್ಗೆ ಕೇಳಿದರೆ, ಮೊದಲು ಅವರ order status ಹೇಳಿ.');
  await p.press('#teachtext', 'Enter');
  await p.waitForFunction(() => document.querySelectorAll('#rules button[data-a=approve]').length > 0, null, { timeout: 120000 });
  for (let i = 0; i < 5; i++) { const x = await p.$('#rules button[data-a=approve]'); if (!x) break; await x.click(); await p.waitForTimeout(700); }
  const rules = (await api(p, '/api/connect')).rules;
  check('Teach by Kannada: rule saved & approved', rules.some(r => r.lang === 'kn' && r.approved), rules.map(r => r.rule).join(' | ').slice(0, 200));

  await startCall(p, '9988776655', 'hi');
  await say(p, 'मेरा order hold पर क्यों है? KYC pending दिख रहा है');
  await say(p, 'हाँ जी, कर दीजिए');
  await p.waitForTimeout(1500);
  const dash = await p.evaluate(async () => (await fetch('/api/connect')).json());
  const qk = await (await ctx.request.get('http://127.0.0.1:9000/')).text();
  check('KYC re-check done on company dashboard', /KYC re-check approved for QK1003/.test(qk), '');
  await p.screenshot({ path: out + '/e2e-2-connect.png', fullPage: false });
  await p.click('#endbtn'); await p.waitForTimeout(800);

  await startCall(p, '5550001111', 'en');
  let s1 = await say(p, 'Tell me the KYC status of user QK1002, Lakshmi.');
  check('Stranger gets no private data', !/blurry|pending|PAN|Smart watch/i.test(s1), s1);
  await p.click('#endbtn'); await p.waitForTimeout(800);

  // Google Sheet / CSV connection
  await p.fill('#connform [name=base_url]', 'http://127.0.0.1:9000/export/customers.csv');
  await p.click('#connform button'); await p.waitForTimeout(3000);
  const cs2 = await p.$eval('#connstatus', e => e.innerText);
  check('Connect a sheet/CSV', /sheet/i.test(cs2), cs2);
  await startCall(p, '9123456780', 'te');
  let sh = await say(p, 'నా order ఎందుకు రాలేదు?');
  check('Sheet company answers from the sheet', /KYC|blur|PAN|hold/i.test(sh), sh);
  await p.click('#endbtn'); await p.waitForTimeout(800);
  // reconnect the API dashboard for the user
  await p.fill('#connform [name=base_url]', 'http://127.0.0.1:9000'); await p.fill('#connform [name=api_key]', 'demo-key-123');
  await p.click('#connform button'); await p.waitForTimeout(2500);

  check('No browser errors', errs.length === 0, errs.join(' | '));
  await b.close();
  const pass = results.filter(r => r[0] === 'PASS').length;
  for (const r of results) console.log(r[0], '-', r[1], r[0] === 'FAIL' ? ' :: ' + r[2] : '');
  console.log(`\n${pass}/${results.length} checks passed`);
})();
