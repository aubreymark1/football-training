(() => {
  const stage = document.getElementById('auth-crest');
  if (!stage) return;

  const scene = stage.querySelector('.slab-scene');
  const slab = stage.querySelector('.slab-3d');
  const edge = stage.querySelector('.edge-wall');
  const shadow = stage.querySelector('.ground-shadow');
  const sheen = stage.querySelector('.sheen-beam');
  const lights = stage.querySelectorAll('fePointLight');
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const lite = window.matchMedia('(pointer: coarse), (max-width: 679px)').matches;
  stage.classList.toggle('is-lite', lite);

  const facetCount = lite ? 24 : 72;
  const radius = 197.5;
  const facetWidth = 2 * radius * Math.tan(Math.PI / facetCount) + 1.8;
  const faces = [];
  const faceElements = document.createDocumentFragment();
  for (let index = 0; index < facetCount; index++) {
    const angle = index * 360 / facetCount;
    const radians = angle * Math.PI / 180;
    const element = document.createElement('div');
    element.className = 'edge-facet';
    element.style.width = facetWidth.toFixed(2) + 'px';
    element.style.marginLeft = (-facetWidth / 2).toFixed(2) + 'px';
    element.style.transform = 'rotateZ(' + angle + 'deg) translateY(-' + radius + 'px) rotateX(90deg)';
    if (lite) {
      const steel = Math.round(70 + 96 * (Math.cos(radians - 0.7) + 1) / 2);
      element.style.backgroundColor = `rgb(${steel},${steel + 7},${steel + 15})`;
    }
    faceElements.append(element);
    faces.push({element, x: Math.sin(radians), y: -Math.cos(radians), color: ''});
  }
  edge.append(faceElements);

  const unit = (x, y, z) => {
    const length = Math.hypot(x, y, z);
    return [x / length, y / length, z / length];
  };
  const [lightX, lightY, lightZ] = unit(-0.45, -0.52, 0.72);
  const [halfX, halfY, halfZ] = unit(lightX, lightY, lightZ + 1);
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const nearbyYaw = (target, current) => current + ((((target - current) % 360) + 540) % 360) - 180;

  let pitch = 14;
  let yaw = -22;
  let hover = null;
  let drag = null;
  let frame = 0;
  let visible = true;
  const startedAt = performance.now();
  let lastFrame = startedAt;

  function resize() {
    const size = Math.min(stage.clientWidth * 0.78, stage.clientHeight * 0.82, 560);
    stage.style.setProperty('--slab-scale', size / 400);
  }
  if (typeof ResizeObserver === 'function') new ResizeObserver(resize).observe(stage);
  else window.addEventListener('resize', resize);
  resize();

  function draw(floatY) {
    slab.style.transform = `translateY(${floatY.toFixed(2)}px) rotateX(${pitch.toFixed(2)}deg) rotateY(${yaw.toFixed(2)}deg)`;
    if (lite) return;
    const radX = pitch * Math.PI / 180;
    const radY = yaw * Math.PI / 180;
    const sinX = Math.sin(radX), cosX = Math.cos(radX);
    const sinY = Math.sin(radY), cosY = Math.cos(radY);

    for (const face of faces) {
      const x = face.x * cosY;
      const localZ = -face.x * sinY;
      const y = face.y * cosX - localZ * sinX;
      const z = face.y * sinX + localZ * cosX;
      const diffuse = 0.24 + Math.max(0, x * lightX + y * lightY + z * lightZ) * 0.72 + Math.max(0, -z) * 0.14;
      const specular = Math.pow(Math.max(0, x * halfX + y * halfY + z * halfZ), 18) * 0.95;
      const channel = (base, shine) => Math.min(255, Math.round(base * diffuse + shine * specular));
      const color = `rgb(${channel(158, 248)},${channel(168, 252)},${channel(182, 255)})`;
      if (color !== face.color) {
        face.element.style.backgroundColor = color;
        face.color = color;
      }
    }

    const x = clamp(sinY * 1.4, -1.2, 1.2);
    const y = clamp(-sinX * 1.4, -1.2, 1.2);
    for (const light of lights) {
      light.setAttribute('x', (250 + x * 210).toFixed(1));
      light.setAttribute('y', (250 + y * 210).toFixed(1));
    }
    sheen.style.transform = `translate3d(${(x * 36).toFixed(1)}%, ${(y * 36).toFixed(1)}%, 0)`;
    shadow.style.transform = `translate3d(${(-x * 32).toFixed(1)}px, ${(42 - y * 22 + floatY * 0.4).toFixed(1)}px, -110px) scale(${(0.96 - Math.abs(sinY) * 0.22).toFixed(3)}, ${(0.96 - Math.abs(sinX) * 0.18).toFixed(3)})`;
    shadow.style.opacity = (0.85 - Math.min(0.45, Math.hypot(x, y) * 0.25) * 0.3).toFixed(2);
  }

  function schedule() {
    if (!frame && visible && !document.hidden) frame = requestAnimationFrame(animate);
  }

  function animate(now) {
    frame = 0;
    if (!visible || document.hidden) return;
    const t = (now - startedAt) / 1000;
    const frameStep = clamp((now - lastFrame) * 0.06, 0.5, 4);
    lastFrame = now;
    const resting = motion.matches ? {pitch: 14, yaw: -22} : {pitch: Math.sin(t * 1.8) * 26, yaw: Math.sin(t * 0.9) * 52};
    const target = drag || hover || resting;
    const targetYaw = drag ? target.yaw : nearbyYaw(target.yaw, yaw);
    const ease = motion.matches ? 1 : 1 - Math.pow(drag ? 0.78 : 0.915, frameStep);
    pitch += (target.pitch - pitch) * ease;
    yaw += (targetYaw - yaw) * ease;
    draw(!motion.matches && !drag && !hover ? Math.sin(t * 1.5) * 5 : 0);
    if (!motion.matches) schedule();
  }

  scene.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0 || drag) return;
    hover = null;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, startPitch: pitch, startYaw: yaw, pitch, yaw};
    scene.setPointerCapture(event.pointerId);
    schedule();
  });
  scene.addEventListener('pointermove', (event) => {
    if (drag) {
      if (event.pointerId !== drag.id) return;
      drag.yaw = drag.startYaw + (event.clientX - drag.x) * 0.55;
      drag.pitch = clamp(drag.startPitch - (event.clientY - drag.y) * 0.55, -75, 75);
    } else {
      if (event.pointerType === 'touch') return;
      const box = scene.getBoundingClientRect();
      const x = clamp((event.clientX - box.left) / box.width * 2 - 1, -1, 1);
      const y = clamp((event.clientY - box.top) / box.height * 2 - 1, -1, 1);
      hover = {pitch: -y * 28, yaw: x * 28};
    }
    schedule();
  });

  const endDrag = (event) => {
    if (drag && event.pointerId === drag.id) {
      drag = null;
      schedule();
    }
  };
  scene.addEventListener('pointerup', endDrag);
  scene.addEventListener('pointercancel', endDrag);
  scene.addEventListener('lostpointercapture', endDrag);
  scene.addEventListener('pointerleave', () => {
    hover = null;
    schedule();
  });

  if (typeof IntersectionObserver === 'function') {
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      schedule();
    }).observe(scene);
  }
  if (motion.addEventListener) motion.addEventListener('change', schedule);
  document.addEventListener('visibilitychange', schedule);
  schedule();
})();
