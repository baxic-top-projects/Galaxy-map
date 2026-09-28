import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { starColor } from '../galaxy/modelCatalog.js'
import { buildSpatialIndex } from '../galaxy/spatialIndex.js'
import { estimateZoom, pickLabels } from '../galaxy/labelLod.js'

const GALAXY_SCALE = 42
const MAP_LIM = 1.06
const TERRITORY_PLATE_URL = '/textures/galaxy_territory_plate.png?v=36'
const textureLoader = new THREE.TextureLoader()

function loadTexture(url) {
  return new Promise((resolve, reject) => {
    textureLoader.load(
      url,
      (texture) => {
        texture.colorSpace = THREE.SRGBColorSpace
        texture.anisotropy = 8
        texture.generateMipmaps = true
        texture.minFilter = THREE.LinearMipmapLinearFilter
        texture.magFilter = THREE.LinearFilter
        resolve(texture)
      },
      undefined,
      reject,
    )
  })
}

/** Marker style matching EfolsMiradinsPact galaxy_political_map.png */
const MARKER = {
  star: 0,
  blackHole: 1,
  capital: 2,
  well: 3,
}

function markerKind(system) {
  if (system.kind === 'well') return MARKER.well
  if (system.kind === 'black_hole') return MARKER.blackHole
  if (system.capital) return MARKER.capital
  return MARKER.star
}

function pointSizeFor(system) {
  const kind = markerKind(system)
  if (kind === MARKER.well) return 14
  if (kind === MARKER.capital) return 12
  if (kind === MARKER.blackHole) return 9.5
  return 5.2
}

/**
 * Create an imperative Three.js galaxy scene attached to a canvas.
 */
export async function createGalaxyScene(canvas, galaxy, callbacks = {}) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: false,
    powerPreference: 'high-performance',
  })
  renderer.setClearColor(0x05070f, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))

  const scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x05070f, 0.012)

  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 500)
  camera.position.set(0, -58, 34)

  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.enableZoom = true
  controls.zoomSpeed = 1.15
  controls.minDistance = 4
  controls.maxDistance = 110
  controls.maxPolarAngle = Math.PI * 0.495
  controls.target.set(0, 0, 0)
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.PAN,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.ROTATE,
  }
  controls.touches = {
    ONE: THREE.TOUCH.PAN,
    TWO: THREE.TOUCH.DOLLY_PAN,
  }
  const overviewPosition = new THREE.Vector3(0, -58, 34)
  const overviewTarget = new THREE.Vector3(0, 0, 0)

  const root = new THREE.Group()
  scene.add(root)

  const ambient = new THREE.AmbientLight(0xffffff, 0.55)
  scene.add(ambient)
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.85)
  keyLight.position.set(20, -30, 50)
  scene.add(keyLight)

  const plate = await createPoliticalPlate(galaxy)
  root.add(plate)

  const positions = new Float32Array(galaxy.systems.length * 3)
  const colors = new Float32Array(galaxy.systems.length * 3)
  const sizes = new Float32Array(galaxy.systems.length)
  const kinds = new Float32Array(galaxy.systems.length)
  const color = new THREE.Color()

  galaxy.systems.forEach((system, index) => {
    const i = index * 3
    positions[i] = system.x * GALAXY_SCALE
    positions[i + 1] = system.y * GALAXY_SCALE
    positions[i + 2] = system.z * GALAXY_SCALE

    const kind = markerKind(system)
    kinds[index] = kind
    sizes[index] = pointSizeFor(system)

    if (kind === MARKER.blackHole || kind === MARKER.well) {
      // Core is dark; rim color carried in vertex color for the shader.
      color.setHex(kind === MARKER.well ? 0xffbe6a : 0xff9a3c)
    } else if (kind === MARKER.capital) {
      // Efol gold / Miradin pink from the political map.
      const stem = system.stem || ''
      color.setHex(stem.includes('Miradin') ? 0xffd0dc : 0xffe566)
    } else {
      color.setHex(starColor(system.starTypeKey))
    }

    colors[i] = color.r
    colors[i + 1] = color.g
    colors[i + 2] = color.b
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
  geometry.setAttribute('kind', new THREE.BufferAttribute(kinds, 1))

  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.NormalBlending,
    vertexColors: true,
    uniforms: {
      uScale: { value: 1 },
    },
      vertexShader: `
      attribute float size;
      attribute float kind;
      varying vec3 vColor;
      varying float vKind;
      uniform float uScale;
      void main() {
        vColor = color;
        vKind = kind;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        // Keep all map markers near-constant on screen when zooming.
        float dist = max(-mvPosition.z, 6.0);
        float atten = clamp(52.0 / dist, 0.75, 1.15);
        float px = size * uScale * atten;
        float cap = 9.5;
        if (vKind > 0.5 && vKind < 1.5) cap = 13.0;       // black hole
        else if (vKind > 1.5 && vKind < 2.5) cap = 15.0;  // capital
        else if (vKind >= 2.5) cap = 16.0;                // well
        gl_PointSize = clamp(px, 2.5, cap);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vKind;
      void main() {
        vec2 uv = gl_PointCoord - vec2(0.5);
        float d = length(uv);

        // Ordinary stars: tiny filled dots (political map style)
        if (vKind < 0.5) {
          if (d > 0.5) discard;
          float a = 0.88 * (1.0 - smoothstep(0.35, 0.5, d));
          gl_FragColor = vec4(vColor, a);
          return;
        }

        // Black holes: dark core + thin bright/orange rim
        if (vKind < 1.5) {
          if (d > 0.5) discard;
          float rim = smoothstep(0.34, 0.40, d) * (1.0 - smoothstep(0.46, 0.5, d));
          float core = 1.0 - smoothstep(0.32, 0.38, d);
          vec3 col = mix(vec3(0.04, 0.04, 0.05), vColor, rim);
          float a = max(core, rim);
          gl_FragColor = vec4(col, a);
          return;
        }

        // Capitals: bright center + hollow circle ring
        if (vKind < 2.5) {
          float ring = smoothstep(0.36, 0.40, d) * (1.0 - smoothstep(0.46, 0.5, d));
          float core = 1.0 - smoothstep(0.12, 0.18, d);
          if (ring < 0.02 && core < 0.02) discard;
          vec3 col = mix(vColor * 0.55, vColor, max(core, ring));
          gl_FragColor = vec4(col, max(core, ring * 0.95));
          return;
        }

        // Axis Well: larger dark core + warm rim + outer ring
        if (d > 0.5) discard;
        float rim = smoothstep(0.30, 0.36, d) * (1.0 - smoothstep(0.42, 0.48, d));
        float outer = smoothstep(0.44, 0.46, d) * (1.0 - smoothstep(0.49, 0.5, d));
        float core = 1.0 - smoothstep(0.28, 0.34, d);
        vec3 col = mix(vec3(0.02, 0.02, 0.025), vColor, max(rim, outer));
        gl_FragColor = vec4(col, max(core, max(rim, outer)));
      }
    `,
  })

  const points = new THREE.Points(geometry, material)
  points.renderOrder = 2
  root.add(points)
  const starLayers = [{ points, geometry, material }]

  const edgePositions = []
  for (const edge of galaxy.edgesDisplay) {
    const a = galaxy.byId.get(edge.a)
    const b = galaxy.byId.get(edge.b)
    if (!a || !b) continue
    edgePositions.push(
      a.x * GALAXY_SCALE,
      a.y * GALAXY_SCALE,
      a.z * GALAXY_SCALE,
      b.x * GALAXY_SCALE,
      b.y * GALAXY_SCALE,
      b.z * GALAXY_SCALE,
    )
  }
  const edgeGeom = new THREE.BufferGeometry()
  edgeGeom.setAttribute('position', new THREE.Float32BufferAttribute(edgePositions, 3))
  const edgeMat = new THREE.LineBasicMaterial({
    color: 0x8aa4bc,
    transparent: true,
    opacity: 0.12,
    depthWrite: false,
    fog: false,
  })
  const lanes = new THREE.LineSegments(edgeGeom, edgeMat)
  lanes.renderOrder = 1
  root.add(lanes)

  const pickHelper = new THREE.Raycaster()
  pickHelper.params.Points = { threshold: 0.9 }
  const pointer = new THREE.Vector2()
  const spatial = buildSpatialIndex(galaxy.systems)

  let selectedId = null
  let hoveredId = null
  let raf = 0
  let frameCount = 0
  let disposed = false
  let focusTween = null
  let lastClickAt = 0
  let lastClickId = null
  let pointerDown = null
  const pressedKeys = new Set()
  const panOffset = new THREE.Vector3()
  const panRight = new THREE.Vector3()
  const panForward = new THREE.Vector3()

  function resize() {
    const width = canvas.clientWidth || canvas.parentElement?.clientWidth || window.innerWidth
    const height = canvas.clientHeight || canvas.parentElement?.clientHeight || window.innerHeight
    renderer.setSize(width, height, false)
    camera.aspect = width / Math.max(height, 1)
    camera.updateProjectionMatrix()
  }

  function cameraDistance() {
    return camera.position.distanceTo(controls.target)
  }

  function emitLabels() {
    const zoom = estimateZoom(cameraDistance())
    const labels = pickLabels(galaxy.systems, {
      zoom,
      selectedId,
      hoveredId,
      maxLabels: zoom > 5 ? 64 : 40,
    }).map(({ system }) => {
      const projected = projectSystem(system)
      return {
        id: system.id,
        system,
        x: projected.x,
        y: projected.y,
        visible: projected.visible,
      }
    })
    callbacks.onLabels?.(labels, zoom)
  }

  function projectSystem(system) {
    const vector = new THREE.Vector3(
      system.x * GALAXY_SCALE,
      system.y * GALAXY_SCALE,
      system.z * GALAXY_SCALE,
    )
    vector.project(camera)
    const width = canvas.clientWidth || 1
    const height = canvas.clientHeight || 1
    return {
      x: (vector.x * 0.5 + 0.5) * width,
      y: (-vector.y * 0.5 + 0.5) * height,
      visible: vector.z < 1,
    }
  }

  function pickSystem(clientX, clientY) {
    const rect = canvas.getBoundingClientRect()
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1
    pickHelper.setFromCamera(pointer, camera)

    // Prefer plane+spatial picking so every star and black hole is hittable,
    // not the decorative dots baked into the background texture.
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)
    const hit = new THREE.Vector3()
    if (pickHelper.ray.intersectPlane(plane, hit)) {
      const maxDist = THREE.MathUtils.clamp(cameraDistance() * 0.00135, 0.03, 0.11)
      const nearest = spatial.queryNearest(hit.x / GALAXY_SCALE, hit.y / GALAXY_SCALE, maxDist)
      if (nearest) return nearest
    }

    pickHelper.params.Points.threshold = THREE.MathUtils.clamp(cameraDistance() * 0.05, 1.5, 5)
    const hits = pickHelper.intersectObject(points, false)
    if (hits.length) {
      const index = hits[0].index
      return galaxy.systems[index] || null
    }
    return null
  }

  function setSelected(id) {
    selectedId = id
    callbacks.onSelect?.(id ? galaxy.byId.get(id) : null)
    emitLabels()
  }

  function focusSystem(system, { enterSystem = false } = {}) {
    if (!system) return
    setSelected(system.id)
    if (enterSystem) {
      // Enter immediately so the system view can load all planets without waiting on orbit tween.
      callbacks.onEnterSystem?.(system)
      return
    }
    const target = new THREE.Vector3(
      system.x * GALAXY_SCALE,
      system.y * GALAXY_SCALE,
      system.z * GALAXY_SCALE,
    )
    const startTarget = controls.target.clone()
    const startPos = camera.position.clone()
    const endPos = target.clone().add(new THREE.Vector3(0, -6.5, 4.8))
    const started = performance.now()
    focusTween = () => {
      const t = Math.min(1, (performance.now() - started) / 900)
      const e = 1 - Math.pow(1 - t, 3)
      controls.target.lerpVectors(startTarget, target, e)
      camera.position.lerpVectors(startPos, endPos, e)
      if (t >= 1) focusTween = null
    }
  }

  function onPointerMove(event) {
    const system = pickSystem(event.clientX, event.clientY)
    const nextId = system?.id || null
    if (nextId !== hoveredId) {
      hoveredId = nextId
      callbacks.onHover?.(system)
      canvas.style.cursor = system ? 'pointer' : 'grab'
      emitLabels()
    }
  }

  function onPointerDown(event) {
    if (event.button !== 0) return
    pointerDown = { x: event.clientX, y: event.clientY, at: performance.now() }
    canvas.style.cursor = 'grabbing'
  }

  function onPointerUp(event) {
    canvas.style.cursor = hoveredId ? 'pointer' : 'grab'
    if (event.button !== 0 || !pointerDown) return
    const dx = event.clientX - pointerDown.x
    const dy = event.clientY - pointerDown.y
    const dragged = Math.hypot(dx, dy) > 6
    pointerDown = null
    if (dragged) return

    const system = pickSystem(event.clientX, event.clientY)
    if (!system) return

    const now = performance.now()
    const isDouble = lastClickId === system.id && now - lastClickAt < 350
    lastClickAt = now
    lastClickId = system.id
    focusSystem(system, { enterSystem: isDouble })
  }

  function onDblClick(event) {
    event.preventDefault()
    const system = pickSystem(event.clientX, event.clientY)
    if (system) focusSystem(system, { enterSystem: true })
  }

  function isTypingTarget(target) {
    if (!target || !(target instanceof Element)) return false
    const tag = target.tagName
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
  }

  function normalizePanKey(raw) {
    const key = raw.length === 1 ? raw.toLowerCase() : raw
    // Russian layout: ЦЫФВ sit on the same physical keys as WASD.
    if (key === 'ц') return 'w'
    if (key === 'ы') return 's'
    if (key === 'ф') return 'a'
    if (key === 'в') return 'd'
    return key
  }

  function onKeyDown(event) {
    if (isTypingTarget(event.target)) return
    const key = normalizePanKey(event.key)
    if (
      key === 'ArrowUp' ||
      key === 'ArrowDown' ||
      key === 'ArrowLeft' ||
      key === 'ArrowRight' ||
      key === 'w' ||
      key === 'a' ||
      key === 's' ||
      key === 'd'
    ) {
      event.preventDefault()
      pressedKeys.add(key)
    }
  }

  function onKeyUp(event) {
    pressedKeys.delete(normalizePanKey(event.key))
  }

  function applyKeyboardPan() {
    if (!pressedKeys.size) return
    const dist = cameraDistance()
    const step = THREE.MathUtils.clamp(dist * 0.018, 0.12, 1.4)
    panOffset.set(0, 0, 0)
    // Screen-relative pan on the galaxy XY plane
    panRight.setFromMatrixColumn(camera.matrixWorld, 0)
    panRight.z = 0
    if (panRight.lengthSq() < 1e-6) panRight.set(1, 0, 0)
    else panRight.normalize()
    panForward.set(-panRight.y, panRight.x, 0)

    if (pressedKeys.has('ArrowLeft') || pressedKeys.has('a')) panOffset.addScaledVector(panRight, -step)
    if (pressedKeys.has('ArrowRight') || pressedKeys.has('d')) panOffset.addScaledVector(panRight, step)
    if (pressedKeys.has('ArrowUp') || pressedKeys.has('w')) panOffset.addScaledVector(panForward, step)
    if (pressedKeys.has('ArrowDown') || pressedKeys.has('s')) panOffset.addScaledVector(panForward, -step)

    if (panOffset.lengthSq() < 1e-8) return
    focusTween = null
    camera.position.add(panOffset)
    controls.target.add(panOffset)
  }

  function frame() {
    if (disposed) return
    raf = requestAnimationFrame(frame)
    frameCount += 1
    if (focusTween) focusTween()
    applyKeyboardPan()
    controls.update()
    const scale = THREE.MathUtils.clamp(Math.sqrt(18 / Math.max(cameraDistance(), 1)), 0.75, 1.25)
    for (const layer of starLayers) {
      layer.material.uniforms.uScale.value = scale
    }
    renderer.render(scene, camera)
    if (frameCount % 2 === 0) emitLabels()
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    window.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('keyup', onKeyUp)
    canvas.removeEventListener('pointermove', onPointerMove)
    canvas.removeEventListener('pointerdown', onPointerDown)
    canvas.removeEventListener('pointerup', onPointerUp)
    canvas.removeEventListener('dblclick', onDblClick)
    canvas.removeEventListener('wheel', onWheel)
    controls.dispose()
    for (const layer of starLayers) {
      layer.geometry.dispose()
      layer.material.dispose()
    }
    edgeGeom.dispose()
    edgeMat.dispose()
    plate.geometry.dispose()
    plate.material.map?.dispose()
    plate.material.dispose()
    renderer.dispose()
  }

  function resetView(animate = false) {
    selectedId = null
    focusTween = null
    if (!animate) {
      controls.target.copy(overviewTarget)
      camera.position.copy(overviewPosition)
      callbacks.onSelect?.(null)
      emitLabels()
      return
    }
    const startTarget = controls.target.clone()
    const startPos = camera.position.clone()
    const started = performance.now()
    focusTween = () => {
      const t = Math.min(1, (performance.now() - started) / 700)
      const e = 1 - Math.pow(1 - t, 3)
      controls.target.lerpVectors(startTarget, overviewTarget, e)
      camera.position.lerpVectors(startPos, overviewPosition, e)
      if (t >= 1) focusTween = null
    }
    callbacks.onSelect?.(null)
    emitLabels()
  }

  function onWheel(event) {
    if (event.deltaY <= 0) return
    const distance = cameraDistance()
    const awayFromCenter = controls.target.length() > 2.5
    if (distance >= 72 || awayFromCenter) {
      const pull = THREE.MathUtils.clamp((distance - 55) / 40, 0.08, 0.35)
      controls.target.lerp(overviewTarget, pull)
      if (distance >= 95 || (awayFromCenter && distance >= 80)) {
        resetView(true)
      }
    }
  }

  window.addEventListener('resize', resize)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  canvas.addEventListener('pointermove', onPointerMove)
  canvas.addEventListener('pointerdown', onPointerDown)
  canvas.addEventListener('pointerup', onPointerUp)
  canvas.addEventListener('dblclick', onDblClick)
  canvas.addEventListener('wheel', onWheel, { passive: true })
  resize()
  raf = requestAnimationFrame(frame)

  return {
    focusSystem,
    setSelected,
    resetView,
    dispose,
  }
}

function createPoliticalPlate(galaxy) {
  // Prefer the canon territory plate (same paint as galaxy_political_map.png).
  return loadTexture(TERRITORY_PLATE_URL)
    .then((texture) => makePlateMeshFromTexture(texture))
    .catch(() => createProceduralPoliticalPlate(galaxy))
}

function makePlateMeshFromTexture(texture) {
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    fog: false,
    side: THREE.DoubleSide,
  })
  const span = GALAXY_SCALE * 2 * MAP_LIM
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(span, span), material)
  mesh.position.z = -0.8
  mesh.raycast = () => {}
  return mesh
}

function createProceduralPoliticalPlate(galaxy) {
  const size = 900
  const canvas2d = document.createElement('canvas')
  canvas2d.width = size
  canvas2d.height = size
  const ctx = canvas2d.getContext('2d')
  ctx.fillStyle = '#05070f'
  ctx.fillRect(0, 0, size, size)

  const cx = size / 2
  const cy = size / 2
  const diskR = size * 0.48
  const lim = MAP_LIM

  const arms = ctx.createRadialGradient(cx, cy, diskR * 0.04, cx, cy, diskR)
  arms.addColorStop(0, 'rgba(255, 210, 140, 0.18)')
  arms.addColorStop(0.25, 'rgba(150, 95, 145, 0.10)')
  arms.addColorStop(0.6, 'rgba(60, 90, 150, 0.07)')
  arms.addColorStop(1, 'rgba(5, 7, 15, 0)')
  ctx.fillStyle = arms
  ctx.beginPath()
  ctx.arc(cx, cy, diskR, 0, Math.PI * 2)
  ctx.fill()

  const owned = galaxy.systems.filter(
    (system) => system.kind === 'star' || system.kind === 'black_hole',
  )
  if (!owned.length) return makePlateMeshFromCanvas(canvas2d)

  const spatial = buildSpatialIndex(owned)

  const image = ctx.createImageData(size, size)
  const data = image.data
  const owner = new Int32Array(size * size)
  owner.fill(-1)

  const systemIndex = new Map(owned.map((system, index) => [system.id, index]))
  const systemMeta = owned.map((system) => {
    const polity = system.stem ? galaxy.polityByStem.get(system.stem) : null
    const color = new THREE.Color(polity?.color || '#7aa0c8')
    return {
      polityStem: system.stem || '',
      r: Math.round(color.r * 255),
      g: Math.round(color.g * 255),
      b: Math.round(color.b * 255),
    }
  })

  for (let py = 0; py < size; py += 1) {
    for (let px = 0; px < size; px += 1) {
      const dx = px - cx
      const dy = py - cy
      const rr = Math.hypot(dx, dy)
      if (rr > diskR) continue

      const gx = ((px + 0.5) / size) * 2 * lim - lim
      const gy = -(((py + 0.5) / size) * 2 * lim - lim)
      const nearest = spatial.queryNearestAny(gx, gy)
      if (!nearest) continue
      const idx = systemIndex.get(nearest.id)
      if (idx == null) continue

      const i = py * size + px
      owner[i] = idx
      const meta = systemMeta[idx]
      const edgeFade = Math.max(0, Math.min(1, (diskR - rr) / (diskR * 0.06)))
      const o = i * 4
      data[o] = meta.r
      data[o + 1] = meta.g
      data[o + 2] = meta.b
      data[o + 3] = Math.round(120 * edgeFade)
    }
  }

  for (let py = 1; py < size - 1; py += 1) {
    for (let px = 1; px < size - 1; px += 1) {
      const i = py * size + px
      const current = owner[i]
      if (current < 0) continue
      const neighbors = [owner[i - 1], owner[i + 1], owner[i - size], owner[i + size]]
      let polityBorder = false
      for (const other of neighbors) {
        if (other < 0 || other === current) continue
        if (systemMeta[other].polityStem !== systemMeta[current].polityStem) {
          polityBorder = true
          break
        }
      }
      if (!polityBorder) continue
      const o = i * 4
      data[o] = 242
      data[o + 1] = 235
      data[o + 2] = 209
      data[o + 3] = 220
    }
  }

  ctx.putImageData(image, 0, 0)
  return makePlateMeshFromCanvas(canvas2d)
}

function makePlateMeshFromCanvas(canvas2d) {
  const texture = new THREE.CanvasTexture(canvas2d)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return makePlateMeshFromTexture(texture)
}
