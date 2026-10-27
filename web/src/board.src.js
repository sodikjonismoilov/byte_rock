// SignSafe case board: a small three.js scene.
// A building stands in the middle. Every record the Warden examines flies in as a card pinned to the
// building with red string. Accepted cards stay pinned, rejected cards snap their string and fall off,
// held cards stay but go amber. When the Assessor decides, the building glows with the verdict colour.
//
// Built into ../board.js with:  npx esbuild web/src/board.src.js --bundle --minify --format=esm --outfile=web/board.js
// (three is MIT licensed; only the classes imported below end up in the bundle.)
import {
  WebGLRenderer, Scene, PerspectiveCamera, Group, BoxGeometry, CylinderGeometry, ConeGeometry, CircleGeometry,
  RingGeometry, PlaneGeometry, MeshStandardMaterial, MeshBasicMaterial, Mesh, CanvasTexture, SRGBColorSpace,
  AmbientLight, DirectionalLight, PointLight, BufferGeometry, Float32BufferAttribute, Line, LineBasicMaterial,
  Points, PointsMaterial, Color, DoubleSide, RepeatWrapping, MathUtils,
} from 'three';

const VERDICT_COLORS = { walk: 0xe5534b, caution: 0xe8a93a, clear: 0x3fb8a0, nodata: 0x8d99ad };
const MAX_LIVE = 28;       // cards on the board at once (pinned + held); older pinned cards are retired into the building
const MAX_HELD = 8;        // held cards stay dim, but never crowd the board
const SLOT_POOL = 36;      // 2 sides x 3 columns x 6 rows: spare slots for cards still falling or retiring
const CARD_W = 0.9, CARD_H = 0.58;
const VIEW_Y = 1.0;        // the camera looks at the middle of the tower, roof included
const ANCHOR = [0, 0.9, 1.05];
const HELD_OPACITY = 0.5; // where the strings start on the building

function hash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967295;
}

function facadeTexture() {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 512;
  const g = c.getContext('2d');
  g.fillStyle = '#243049'; g.fillRect(0, 0, 256, 512);
  for (let y = 0; y < 16; y++) {
    for (let x = 0; x < 6; x++) {
      const lit = hash(`${x},${y}`) > 0.62;
      g.fillStyle = lit ? '#f1c76b' : '#1a2338';
      g.fillRect(14 + x * 40, 14 + y * 31, 24, 19);
    }
  }
  const t = new CanvasTexture(c);
  t.colorSpace = SRGBColorSpace; t.wrapS = t.wrapT = RepeatWrapping;
  return t;
}

function drawCard(texture, card) {
  const c = texture.image, g = c.getContext('2d'), W = c.width, H = c.height;
  const hue = Math.floor(hash(card.dataset || card.id) * 360);
  g.clearRect(0, 0, W, H);
  g.fillStyle = card.state === 'rejected' ? '#d9d2c3' : '#f2ede1';
  g.fillRect(0, 0, W, H);
  g.fillStyle = `hsl(${hue} 55% 45%)`; g.fillRect(0, 0, W, 30);
  g.fillStyle = '#e5534b'; g.beginPath(); g.arc(W / 2, 15, 8, 0, 7); g.fill();
  g.fillStyle = '#4a463d'; g.font = '600 22px ui-monospace, Menlo, Consolas, monospace';
  g.textAlign = 'left'; g.fillText((card.dataset || 'record').slice(0, 16), 14, 64);
  g.fillStyle = '#1c1a17'; g.font = '700 30px ui-monospace, Menlo, Consolas, monospace';
  g.fillText(String(card.shortId).slice(0, 12), 14, 104);
  if (card.state !== 'pending') {
    const style = {
      accepted: ['#1f7a5f', 'ACCEPTED'], rejected: ['#c23b33', 'REJECTED'], held: ['#9a6a12', 'HELD'],
    }[card.state];
    g.save(); g.translate(W / 2, H - 36); g.rotate(-0.09);
    g.strokeStyle = style[0]; g.fillStyle = style[0]; g.lineWidth = 4;
    g.font = '800 30px ui-sans-serif, system-ui, sans-serif'; g.textAlign = 'center';
    const w = g.measureText(style[1]).width + 24;
    g.strokeRect(-w / 2, -28, w, 42); g.fillText(style[1], 0, 3);
    g.restore();
    g.strokeStyle = style[0]; g.lineWidth = 8; g.strokeRect(4, 4, W - 8, H - 8);
  }
  texture.needsUpdate = true;
}

export function createBoard(canvas, options = {}) {
  let renderer;
  try {
    renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch (error) {
    return null; // no WebGL: the page keeps its plain record list
  }
  const reduced = !!options.reducedMotion;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new Scene();
  const camera = new PerspectiveCamera(38, 1, 0.1, 80);
  camera.position.set(0, 1.5, 12);
  const view = { dist: 12, y: 1.5 };
  scene.add(new AmbientLight(0xbcc8e0, 0.85));
  const key = new DirectionalLight(0xffffff, 1.25); key.position.set(3, 6, 5); scene.add(key);
  const glow = new PointLight(0xffffff, 0, 14); glow.position.set(0, 1.2, 2.2); scene.add(glow);

  // building
  const tower = new Group();
  const facade = facadeTexture();
  const bodyMat = new MeshStandardMaterial({ map: facade, roughness: 0.75, emissive: new Color(0x000000), emissiveIntensity: 0 });
  const body = new Mesh(new BoxGeometry(1.8, 3.4, 1.8), bodyMat); tower.add(body);
  const upper = new Mesh(new BoxGeometry(1.25, 0.8, 1.25), bodyMat); upper.position.y = 2.1; tower.add(upper);
  const tank = new Mesh(new CylinderGeometry(0.28, 0.28, 0.5, 14), new MeshStandardMaterial({ color: 0x6b5a46, roughness: 0.9 }));
  tank.position.set(0.3, 2.75, 0.1); tower.add(tank);
  const tankRoof = new Mesh(new ConeGeometry(0.34, 0.24, 14), new MeshStandardMaterial({ color: 0x4a3f33 }));
  tankRoof.position.set(0.3, 3.12, 0.1); tower.add(tankRoof);
  tower.position.y = 0.1; tower.scale.setScalar(1.12);
  scene.add(tower);

  const ground = new Mesh(new CircleGeometry(5.6, 64), new MeshBasicMaterial({ color: 0x121a28, transparent: true, opacity: 0.9 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -1.8; scene.add(ground);
  const halo = new Mesh(new RingGeometry(2.1, 2.22, 64), new MeshBasicMaterial({ color: 0x3a4a68, transparent: true, opacity: 0.8, side: DoubleSide }));
  halo.rotation.x = -Math.PI / 2; halo.position.y = -1.78; scene.add(halo);

  // drifting dust for depth
  const dustPositions = [];
  for (let i = 0; i < 90; i++) dustPositions.push((hash('x' + i) - 0.5) * 16, hash('y' + i) * 7 - 2, (hash('z' + i) - 0.5) * 12);
  const dustGeo = new BufferGeometry(); dustGeo.setAttribute('position', new Float32BufferAttribute(dustPositions, 3));
  const dust = new Points(dustGeo, new PointsMaterial({ color: 0x8fa3c7, size: 0.035, transparent: true, opacity: 0.55 }));
  scene.add(dust);

  const cards = new Map();   // id -> card
  const falling = new Set();
  const retiring = new Set();
  const freeSlots = []; let nextSlot = 0, live = 0;
  let verdictColor = null;
  let pointer = { x: 0, y: 0 };
  let raf = 0, running = true, last = performance.now(), clock = 0;

  // Cards hang in three columns either side of the tower, six rows each, alternating sides and staggered so
  // neighbours rarely overlap. Outer columns sit a little further back.
  function slot(index) {
    const side = index % 2 ? 1 : -1, k = Math.floor(index / 2), col = Math.floor(k / 6), row = (k % 6) * 5 % 6;
    const x = side * (1.85 + col * 1.3), y = -0.85 + row * 0.78 + (col % 2 ? 0.28 : 0);
    return [x, y, 0.55 - col * 0.5, side * (0.15 + col * 0.12)];
  }

  function stringGeometry() {
    const g = new BufferGeometry();
    g.setAttribute('position', new Float32BufferAttribute(new Float32Array(9 * 3), 3));
    return g;
  }
  function updateString(card) {
    const a = ANCHOR, b = [card.mesh.position.x, card.mesh.position.y + CARD_H / 2, card.mesh.position.z + 0.02];
    const attr = card.line.geometry.attributes.position;
    for (let i = 0; i < 9; i++) {
      const t = i / 8, sag = Math.sin(Math.PI * t) * 0.22 * card.sag;
      attr.setXYZ(i, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t - sag, a[2] + (b[2] - a[2]) * t);
    }
    attr.needsUpdate = true;
  }

  function addRecord(id, dataset) {
    if (cards.has(id)) return;
    if (live >= MAX_LIVE) retireOldest(['accepted', 'held', 'pending']);
    const index = freeSlots.length ? freeSlots.shift() : nextSlot < SLOT_POOL ? nextSlot++ : -1;
    if (index < 0) return;   // no free slot right now; the counters still count this record
    live++;
    const [x, y, z, theta] = slot(index);
    const c = document.createElement('canvas'); c.width = 256; c.height = 164;
    const texture = new CanvasTexture(c); texture.colorSpace = SRGBColorSpace;
    const card = { id, dataset, slot: index, shortId: String(id).split(':').pop(), state: 'pending', texture, target: [x, y, z], sag: 1, age: 0 };
    drawCard(texture, card);
    card.mesh = new Mesh(new PlaneGeometry(CARD_W, CARD_H), new MeshBasicMaterial({ map: texture, transparent: true, side: DoubleSide }));
    card.mesh.position.set(x, reduced ? y : -4.2, z + (reduced ? 0 : 2));
    card.mesh.rotation.set(0, -theta, (hash(id) - 0.5) * 0.12);
    card.line = new Line(stringGeometry(), new LineBasicMaterial({ color: 0xe5534b, transparent: true, opacity: 0.85 }));
    updateString(card);
    scene.add(card.mesh); scene.add(card.line);
    cards.set(id, card);
  }

  // The oldest card of the first matching state flies into the building and fades, freeing its slot.
  function retireOldest(states) {
    for (const state of states) {
      for (const card of cards.values()) {
        if (card.state !== state) continue;
        retire(card);
        return;
      }
    }
  }
  function dropString(card) {
    if (!card.line) return;
    if (card.line.parent) scene.remove(card.line);
    card.line.geometry.dispose(); card.line.material.dispose(); card.line = null;
  }
  function retire(card) {
    card.state = 'retired'; live--;
    dropString(card);
    card.fade = 1; retiring.add(card);
  }
  function removeCard(card) {
    scene.remove(card.mesh); card.mesh.geometry.dispose(); card.mesh.material.dispose(); card.texture.dispose();
    cards.delete(card.id); freeSlots.push(card.slot);
  }

  function resolveRecord(id, state) {
    const card = cards.get(id);
    if (!card || card.state === state || card.state === 'retired') return;
    card.state = state; drawCard(card.texture, card);
    if (state === 'accepted') card.target[2] += 0.25;
    if (state === 'held') {
      dropString(card);   // held records are not pinned: no string, and dimmer than the pinned ones
      card.mesh.material.opacity = HELD_OPACITY;
      let held = 0; for (const c of cards.values()) if (c.state === 'held') held++;
      if (held > MAX_HELD) retireOldest(['held']);
    }
    if (state === 'rejected') {
      live--;
      dropString(card);
      card.vy = 1.6; card.spin = (hash(id) - 0.5) * 3; card.fade = 1; falling.add(card);
    }
  }

  function setVerdict(level) {
    verdictColor = VERDICT_COLORS[level] ?? null;
    if (verdictColor !== null) {
      bodyMat.emissive.set(verdictColor); glow.color.set(verdictColor); halo.material.color.set(verdictColor);
    }
  }

  function reset() {
    for (const card of cards.values()) {
      scene.remove(card.mesh); card.mesh.geometry.dispose(); card.mesh.material.dispose(); card.texture.dispose();
      dropString(card);
    }
    cards.clear(); falling.clear(); retiring.clear(); freeSlots.length = 0; nextSlot = 0; live = 0; verdictColor = null;
    bodyMat.emissiveIntensity = 0; glow.intensity = 0; halo.material.color.set(0x3a4a68);
  }

  // Frame the whole scene: the tower from ground to roof (about 7 units tall with margin) and the card columns
  // (about 11 units wide), whichever needs the camera further back.
  function resize() {
    const box = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(280, box.width), h = Math.max(160, box.height);
    renderer.setSize(w, h, false); canvas.style.width = '100%'; canvas.style.height = '100%';
    camera.aspect = w / h;
    camera.fov = 38;
    camera.updateProjectionMatrix();
    const tan = Math.tan(camera.fov * Math.PI / 360);
    view.dist = Math.max(7.4 / 2 / tan, 11.6 / 2 / (tan * camera.aspect));
    view.y = VIEW_Y + 0.5;
  }
  const observer = new ResizeObserver(resize); observer.observe(canvas.parentElement); resize();
  canvas.parentElement.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    pointer = { x: ((e.clientX - r.left) / r.width - 0.5) * 2, y: ((e.clientY - r.top) / r.height - 0.5) * 2 };
  });

  function frame(now) {
    raf = requestAnimationFrame(frame);
    if (!running || document.hidden) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000); last = now; clock += dt;

    const sway = reduced ? 0 : 1;
    tower.rotation.y = Math.sin(clock * 0.35) * 0.22 * sway;
    camera.position.x += ((pointer.x * 0.9 + Math.sin(clock * 0.18) * 0.3 * sway) - camera.position.x) * 0.04;
    camera.position.y += ((view.y - pointer.y * 0.45) - camera.position.y) * 0.04;
    camera.position.z += (view.dist - camera.position.z) * 0.12;
    camera.lookAt(0, VIEW_Y, 0);
    dust.rotation.y += dt * 0.02 * sway;

    for (const card of cards.values()) {
      if (card.state === 'rejected' || card.state === 'retired') continue;
      card.age += dt;
      const m = card.mesh.position, t = card.target, k = reduced ? 1 : Math.min(1, dt * 5);
      m.x += (t[0] - m.x) * k; m.y += (t[1] - m.y) * k; m.z += (t[2] - m.z) * k;
      if (!reduced) card.mesh.rotation.z += (Math.sin(clock * 1.3 + card.age) * 0.012 - 0) * 0.02;
      if (card.line) updateString(card);
    }
    for (const card of [...falling]) {
      card.vy -= 9 * dt; card.mesh.position.y += card.vy * dt; card.mesh.position.z += dt * 0.6;
      card.mesh.rotation.z += card.spin * dt; card.fade -= dt * 0.75;
      card.mesh.material.opacity = Math.max(0, card.fade);
      if (card.fade <= 0) { falling.delete(card); removeCard(card); }
    }
    for (const card of [...retiring]) {
      const m = card.mesh.position, k = Math.min(1, dt * 4);
      m.x += (ANCHOR[0] - m.x) * k; m.y += (ANCHOR[1] - m.y) * k; m.z += (ANCHOR[2] - m.z) * k;
      card.fade -= dt * 2.2; card.mesh.material.opacity = Math.max(0, card.fade); card.mesh.scale.setScalar(Math.max(0.2, card.fade));
      if (card.fade <= 0) { retiring.delete(card); removeCard(card); }
    }
    if (verdictColor !== null) {
      const pulse = reduced ? 0.4 : 0.3 + Math.sin(clock * 2.2) * 0.12;
      bodyMat.emissiveIntensity = pulse; glow.intensity = 14 * pulse;
      halo.scale.setScalar(1 + (reduced ? 0 : Math.sin(clock * 1.6) * 0.04));
    }
    renderer.render(scene, camera);
  }
  raf = requestAnimationFrame(frame);

  return {
    addRecord, resolveRecord, setVerdict, reset,
    pause() { running = false; }, resume() { running = true; },
    destroy() {
      cancelAnimationFrame(raf); observer.disconnect(); reset(); renderer.dispose();
    },
    get cardCount() { return cards.size; },
  };
}