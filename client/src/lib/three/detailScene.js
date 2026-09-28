import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import {
  featureModelPath,
  planetPreviewPath,
  planetTypeArtPath,
  resolveFeatureKey,
  resolvePlanetTypeKey,
  resolveStarTypeKey,
  starColor,
  starFallbackKey,
  starModelPath,
  starPreviewPath,
  starTypeArtPath,
} from '../galaxy/modelCatalog.js'

const gltfLoader = new GLTFLoader()
const textureLoader = new THREE.TextureLoader()
const glbCache = new Map()
const texCache = new Map()

function loadTexture(url) {
  if (texCache.has(url)) return texCache.get(url)
  const promise = new Promise((resolve, reject) => {
    textureLoader.load(
      url,
      (texture) => {
        texture.colorSpace = THREE.SRGBColorSpace
        resolve(texture)
      },
      undefined,
      reject,
    )
  })
  texCache.set(url, promise)
  return promise
}

function loadGlb(url) {
  if (glbCache.has(url)) return glbCache.get(url)
  const promise = new Promise((resolve) => {
    gltfLoader.load(
      url,
      (gltf) => resolve(gltf.scene),
      undefined,
      () => resolve(null),
    )
  })
  glbCache.set(url, promise)
  return promise
}

/**
 * Measure XZ radial span of a mesh (ignore near-center noise).
 */
function measureRadialExtents(object) {
  object.updateMatrixWorld(true)
  let rMin = Infinity
  let rMax = 0
  const v = new THREE.Vector3()
  object.traverse((child) => {
    if (!child.isMesh || !child.geometry?.attributes?.position) return
    const pos = child.geometry.attributes.position
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i)
      child.localToWorld(v)
      const r = Math.hypot(v.x, v.z)
      if (r < 0.02) continue
      if (r < rMin) rMin = r
      if (r > rMax) rMax = r
    }
  })
  if (!Number.isFinite(rMin) || rMax <= rMin) return { rMin: 0.65, rMax: 1 }
  return { rMin, rMax }
}

/**
 * Textured Meshy asteroid-belt GLB scaled so its inner edge stays outside planet orbits.
 */
async function createAsteroidBelt(featureKey = 'asteroid_belt', { minInner = 4 } = {}) {
  const group = new THREE.Group()
  const scene = await loadGlb(featureModelPath(featureKey))
  if (scene) {
    const root = scene.clone(true)
    root.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = false
        child.receiveShadow = false
        if (child.material) {
          const mats = Array.isArray(child.material) ? child.material : [child.material]
          for (const mat of mats) {
            mat.side = THREE.DoubleSide
          }
        }
      }
    })

    // Normalize around origin before measuring radii.
    let box = new THREE.Box3().setFromObject(root)
    const center0 = box.getCenter(new THREE.Vector3())
    root.position.sub(center0)

    const { rMin, rMax } = measureRadialExtents(root)
    // Keep asteroids outside planet orbits: scale by inner radius.
    const scale = minInner / Math.max(rMin, 1e-3)
    root.scale.setScalar(scale)
    root.scale.y *= 0.32

    box = new THREE.Box3().setFromObject(root)
    const center = box.getCenter(new THREE.Vector3())
    root.position.x -= center.x
    root.position.y -= center.y
    root.position.z -= center.z
    group.add(root)

    const beltInner = rMin * scale
    const beltOuter = rMax * scale
    const beltMid = (beltInner + beltOuter) * 0.5
    group.userData.beltInner = beltInner
    group.userData.beltOuter = beltOuter
    group.userData.beltOrbit = beltMid
    group.userData.beltSpin = { mesh: group, speed: 0.035 / Math.sqrt(Math.max(beltMid, 1)) }
    return group
  }

  const mid = minInner + 0.35
  const dust = new THREE.Mesh(
    new THREE.RingGeometry(minInner, minInner + 0.7, 96),
    new THREE.MeshBasicMaterial({
      color: 0x8a7a58,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  )
  dust.rotation.x = -Math.PI / 2
  dust.raycast = () => {}
  group.add(dust)
  group.userData.beltInner = minInner
  group.userData.beltOuter = minInner + 0.7
  group.userData.beltOrbit = mid
  return group
}

async function createTexturedSphere({ typeKey, radius, kind }) {
  const isStarLike = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStarLike ? resolveStarTypeKey(typeKey, kind) : resolvePlanetTypeKey(typeKey)
  const previewUrl = isStarLike ? starPreviewPath(key) : planetPreviewPath(key)
  const artUrl = isStarLike ? starTypeArtPath(key) : planetTypeArtPath(key)

  let texture = null
  // Prefer full type art for a clear textured star/planet look.
  try {
    texture = await loadTexture(artUrl)
  } catch {
    try {
      texture = await loadTexture(previewUrl)
    } catch {
      texture = null
    }
  }

  if (kind === 'black_hole' || kind === 'well') {
    const group = new THREE.Group()
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(radius * 0.7, 48, 32),
      new THREE.MeshBasicMaterial({ color: 0x000000 }),
    )
    let haloTexture = texture
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 48, 32),
      new THREE.MeshStandardMaterial({
        map: haloTexture || null,
        color: haloTexture ? 0xffffff : kind === 'well' ? 0xff88cc : 0xff5588,
        emissive: new THREE.Color(kind === 'well' ? 0xff66aa : 0xff3366),
        emissiveIntensity: 0.45,
        transparent: true,
        opacity: 0.85,
        roughness: 0.4,
      }),
    )
    group.add(core, glow)
    return group
  }

  return new THREE.Mesh(
    new THREE.SphereGeometry(radius, 64, 48),
    new THREE.MeshStandardMaterial({
      map: texture || null,
      color: texture ? 0xffffff : starColor(key),
      emissive: isStarLike ? new THREE.Color(starColor(key)) : new THREE.Color(0x111122),
      emissiveMap: isStarLike && texture ? texture : null,
      emissiveIntensity: isStarLike ? 0.65 : 0.08,
      roughness: isStarLike ? 0.4 : 0.7,
      metalness: 0.05,
    }),
  )
}

async function createBodyMesh({ kind, typeKey, radius, preferGlb = false }) {
  const isStarLike = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStarLike ? resolveStarTypeKey(typeKey, kind) : resolvePlanetTypeKey(typeKey)

  // Stars/planets: textured spheres from canon type art. Optional GLB for black holes only.
  if (preferGlb && (kind === 'black_hole' || kind === 'well')) {
    const modelUrl = starModelPath(key)
    const scene = await loadGlb(modelUrl)
    if (scene) {
      const root = scene.clone(true)
      const box = new THREE.Box3().setFromObject(root)
      const size = new THREE.Vector3()
      box.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z) || 1
      root.scale.setScalar((radius * 2) / maxDim)
      return root
    }
  }

  return createTexturedSphere({ typeKey: key, radius, kind })
}

function collectBodies(detail) {
  const bodies = []
  for (const world of detail.worlds || []) {
    bodies.push({
      id: `world:${world.token}`,
      kind: 'world',
      inhabited: true,
      nameEn: world.nameEn,
      nameRu: world.nameRu,
      planetType: world.planetType,
      planetTypeKey: world.planetTypeKey || 'continental',
      role: world.role || '',
    })
  }
  for (const body of detail.uninhabited || []) {
    bodies.push({
      id: `uninhabited:${body.nameEn}`,
      kind: 'uninhabited',
      inhabited: false,
      nameEn: body.nameEn,
      nameRu: body.nameRu,
      planetType: body.planetType,
      planetTypeKey: body.planetTypeKey || 'barren',
      role: '',
    })
  }
  return bodies
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

function neighborSystems(detail, galaxy) {
  if (!detail?.id || !galaxy?.byId) return []
  const edges = galaxy.edgesDisplay?.length ? galaxy.edgesDisplay : galaxy.edgesCanon || []
  const out = []
  const seen = new Set()
  for (const edge of edges) {
    let otherId = null
    if (edge.a === detail.id) otherId = edge.b
    else if (edge.b === detail.id) otherId = edge.a
    if (!otherId || seen.has(otherId)) continue
    const other = galaxy.byId.get(otherId)
    if (!other) continue
    seen.add(otherId)
    out.push(other)
  }
  return out
}

/** Stellaris-style hyperlane chevron pointing along local +Z. */
function createHyperlaneArrowMesh() {
  const group = new THREE.Group()
  const mat = new THREE.MeshBasicMaterial({
    color: 0x7ec8ff,
    transparent: true,
    opacity: 0.88,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x9fd6ff,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  const shaft = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.045, 0.85), mat)
  shaft.position.z = 0.15
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.28, 0.5, 3), mat)
  head.rotation.x = Math.PI / 2
  head.position.z = 0.82
  const glow = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.7, 3), glowMat)
  glow.rotation.x = Math.PI / 2
  glow.position.z = 0.78
  group.add(glow, shaft, head)
  return group
}

/**
 * Create a detail scene for one star / black-hole system.
 */
export function createSystemDetailScene(canvas, detail, callbacks = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setClearColor(0x03050c, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
  camera.position.set(0, 12, 5)

  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.target.set(0, 0, 0)
  controls.minDistance = 3
  controls.maxDistance = 28
  controls.zoomSpeed = 1.2
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.PAN,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.ROTATE,
  }
  controls.touches = {
    ONE: THREE.TOUCH.PAN,
    TWO: THREE.TOUCH.DOLLY_PAN,
  }

  const pressedKeys = new Set()
  const panOffset = new THREE.Vector3()
  const panRight = new THREE.Vector3()
  const panForward = new THREE.Vector3()
  const pickHelper = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  const hyperlaneTargets = []
  let pointerDown = null
  let arrowRadius = 8

  function onWheel(event) {
    if (event.deltaY <= 0) return
    const distance = camera.position.distanceTo(controls.target)
    // After zooming out to the system overview, further scroll-back returns to the galaxy.
    if (distance >= controls.maxDistance * 0.9) {
      callbacks.onZoomOut?.()
    }
  }
  canvas.addEventListener('wheel', onWheel, { passive: true })

  function onKeyDown(event) {
    if (isTypingTarget(event.target)) return
    if (event.key === 'Escape') {
      event.preventDefault()
      callbacks.onZoomOut?.()
      return
    }
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

  function onBlur() {
    pressedKeys.clear()
  }

  function applyKeyboardPan() {
    if (!pressedKeys.size) return
    const dist = Math.max(camera.position.distanceTo(controls.target), 1)
    const step = THREE.MathUtils.clamp(dist * 0.018, 0.08, 0.85)
    panOffset.set(0, 0, 0)
    // Screen-relative pan on the system XZ orbital plane.
    panRight.setFromMatrixColumn(camera.matrixWorld, 0)
    panRight.y = 0
    if (panRight.lengthSq() < 1e-6) panRight.set(1, 0, 0)
    else panRight.normalize()
    panForward.set(-panRight.z, 0, panRight.x)

    if (pressedKeys.has('ArrowLeft') || pressedKeys.has('a')) panOffset.addScaledVector(panRight, -step)
    if (pressedKeys.has('ArrowRight') || pressedKeys.has('d')) panOffset.addScaledVector(panRight, step)
    if (pressedKeys.has('ArrowUp') || pressedKeys.has('w')) panOffset.addScaledVector(panForward, step)
    if (pressedKeys.has('ArrowDown') || pressedKeys.has('s')) panOffset.addScaledVector(panForward, -step)

    if (panOffset.lengthSq() < 1e-8) return
    camera.position.add(panOffset)
    controls.target.add(panOffset)
  }

  function setPointer(event) {
    const rect = canvas.getBoundingClientRect()
    pointer.x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1
    pointer.y = -((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 + 1
  }

  function pickHyperlane(clientX, clientY) {
    if (!hyperlaneTargets.length) return null
    setPointer({ clientX, clientY })
    pickHelper.setFromCamera(pointer, camera)
    const meshes = hyperlaneTargets.map((entry) => entry.mesh)
    const hits = pickHelper.intersectObjects(meshes, true)
    if (!hits.length) return null
    let obj = hits[0].object
    while (obj && !obj.userData?.hyperlaneSystem) obj = obj.parent
    return obj?.userData?.hyperlaneSystem || null
  }

  function onPointerDown(event) {
    pointerDown = { x: event.clientX, y: event.clientY, id: pickHyperlane(event.clientX, event.clientY)?.id || null }
  }

  function onPointerUp(event) {
    if (!pointerDown) return
    const dx = event.clientX - pointerDown.x
    const dy = event.clientY - pointerDown.y
    const moved = dx * dx + dy * dy > 36
    const system = !moved ? pickHyperlane(event.clientX, event.clientY) : null
    pointerDown = null
    if (system) callbacks.onTravelTo?.(system)
  }

  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('blur', onBlur)
  canvas.addEventListener('pointerdown', onPointerDown)
  canvas.addEventListener('pointerup', onPointerUp)

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const light = new THREE.PointLight(0xffffff, detail.kind === 'black_hole' || detail.kind === 'well' ? 1.2 : 2.4, 100)
  light.position.set(0, 0, 0.2)
  scene.add(light)

  const root = new THREE.Group()
  scene.add(root)

  let raf = 0
  let frameCount = 0
  let disposed = false
  const animated = []
  const labelAnchors = []
  const zAxis = new THREE.Vector3(0, 0, 1)

  async function build() {
    const hostKind = detail.kind === 'black_hole' || detail.kind === 'well' ? detail.kind : 'star'
    const hostTypeKey = resolveStarTypeKey(detail.starTypeKey, hostKind)
    const hostRadius = hostKind === 'well' ? 2.1 : hostKind === 'black_hole' ? 1.55 : 1.35
    const host = await createBodyMesh({
      kind: hostKind,
      typeKey: hostTypeKey,
      radius: hostRadius,
      preferGlb: hostKind === 'black_hole' || hostKind === 'well',
    })
    root.add(host)
    animated.push({ mesh: host, orbit: 0, speed: 0 })
    labelAnchors.push({
      id: `host:${detail.token}`,
      mesh: host,
      nameEn: detail.nameEn,
      nameRu: detail.nameRu,
      kind: hostKind,
      inhabited: false,
      planetType: detail.starType,
    })

    // Textured host star/black hole; planets keep visible orbit rings.

    const planets = collectBodies(detail)
    const featureBelts = detail.features || []
    const ORBIT_START = 2.6
    const ORBIT_STEP = 1.5
    const PLANET_CLEARANCE = 0.9
    const BELT_GAP = 0.65
    const planetOrbits = planets.map((_, index) => ORBIT_START + index * ORBIT_STEP)

    await Promise.all(
      planets.map(async (planet, index) => {
        const orbit = planetOrbits[index]
        const radius = planet.planetTypeKey === 'gas_giant' ? 0.62 : planet.inhabited ? 0.4 : 0.3
        const mesh = await createBodyMesh({
          kind: 'planet',
          typeKey: planet.planetTypeKey,
          radius,
          preferGlb: false,
        })
        if (disposed) return
        const angle = (index / Math.max(planets.length, 1)) * Math.PI * 2
        // Horizontal XZ orbits around the textured host star.
        mesh.position.set(Math.cos(angle) * orbit, 0, Math.sin(angle) * orbit)
        root.add(mesh)

        const ring = new THREE.Mesh(
          new THREE.RingGeometry(orbit - 0.02, orbit + 0.02, 128),
          new THREE.MeshBasicMaterial({
            color: planet.inhabited ? 0x8ec7ff : 0x6f8fb8,
            transparent: true,
            opacity: planet.inhabited ? 0.45 : 0.28,
            side: THREE.DoubleSide,
          }),
        )
        ring.rotation.x = -Math.PI / 2
        root.add(ring)

        animated.push({
          mesh,
          orbit,
          speed: 0.35 / Math.sqrt(index + 1),
          angle,
        })
        labelAnchors.push({
          id: planet.id,
          mesh,
          nameEn: planet.nameEn,
          nameRu: planet.nameRu,
          kind: planet.kind,
          inhabited: planet.inhabited,
          planetType: planet.planetType,
        })
      }),
    )

    // Place belts sequentially outside planet orbits (and outside previous belts).
    let clearAfter =
      planetOrbits.length > 0
        ? planetOrbits[planetOrbits.length - 1] + PLANET_CLEARANCE
        : ORBIT_START + PLANET_CLEARANCE
    let farthest = clearAfter

    for (let index = 0; index < featureBelts.length; index += 1) {
      const feature = featureBelts[index]
      const featureKey = resolveFeatureKey(feature.feature || feature.nameEn)
      const belt = await createAsteroidBelt(featureKey, { minInner: clearAfter })
      if (disposed) return
      root.add(belt)
      if (belt.userData.beltSpin) {
        animated.push({ beltSpin: belt.userData.beltSpin })
      }

      const beltOrbit = belt.userData.beltOrbit || clearAfter + 0.4
      const beltOuter = belt.userData.beltOuter || beltOrbit + 0.5
      farthest = Math.max(farthest, beltOuter)

      const labelPivot = new THREE.Object3D()
      const labelAngle = Math.PI * 0.25 + index * 0.55
      labelPivot.position.set(Math.cos(labelAngle) * beltOrbit, 0.08, Math.sin(labelAngle) * beltOrbit)
      root.add(labelPivot)
      labelAnchors.push({
        id: `feature:${feature.nameEn}`,
        mesh: labelPivot,
        nameEn: feature.nameEn,
        nameRu: feature.nameRu,
        kind: 'feature',
        inhabited: false,
        planetType: feature.feature,
      })

      clearAfter = beltOuter + BELT_GAP
    }

    // Look down onto the orbital plane (XZ).
    const span = Math.max(8, farthest + 2.4)
    camera.position.set(0, span * 0.95, span * 0.35)
    controls.target.set(0, 0, 0)
    controls.maxDistance = Math.max(28, span * 2.2)
    controls.update()

    // Stellaris-style hyperlane arrows toward connected systems.
    const neighbors = neighborSystems(detail, callbacks.galaxy)
    arrowRadius = Math.max(span * 0.92, farthest + 1.35)
    const dir = new THREE.Vector3()
    for (const neighbor of neighbors) {
      dir.set(neighbor.x - detail.x, 0, -(neighbor.y - detail.y))
      if (dir.lengthSq() < 1e-10) dir.set(1, 0, 0)
      else dir.normalize()

      const arrow = createHyperlaneArrowMesh()
      arrow.position.copy(dir).multiplyScalar(arrowRadius)
      arrow.quaternion.setFromUnitVectors(zAxis, dir)
      arrow.userData.hyperlaneSystem = neighbor
      root.add(arrow)
      hyperlaneTargets.push({ mesh: arrow, system: neighbor })

      const labelPivot = new THREE.Object3D()
      labelPivot.position.copy(dir).multiplyScalar(arrowRadius + 0.85)
      root.add(labelPivot)
      labelAnchors.push({
        id: `hyperlane:${neighbor.id}`,
        mesh: labelPivot,
        nameEn: neighbor.nameEn,
        nameRu: neighbor.nameRu,
        kind: 'hyperlane',
        inhabited: false,
        planetType: '',
      })
    }
  }

  function emitLabels() {
    const width = canvas.clientWidth || 1
    const height = canvas.clientHeight || 1
    const labels = labelAnchors.map((anchor) => {
      const vector = anchor.mesh.getWorldPosition(new THREE.Vector3())
      vector.project(camera)
      return {
        id: anchor.id,
        nameEn: anchor.nameEn,
        nameRu: anchor.nameRu,
        kind: anchor.kind,
        inhabited: anchor.inhabited,
        planetType: anchor.planetType,
        x: (vector.x * 0.5 + 0.5) * width,
        y: (-vector.y * 0.5 + 0.5) * height,
        visible: vector.z < 1,
      }
    })
    callbacks.onLabels?.(labels)
  }

  function resize() {
    const width = canvas.clientWidth || canvas.parentElement?.clientWidth || 640
    const height = canvas.clientHeight || canvas.parentElement?.clientHeight || 420
    renderer.setSize(width, height, false)
    camera.aspect = width / Math.max(height, 1)
    camera.updateProjectionMatrix()
  }

  function frame() {
    if (disposed) return
    raf = requestAnimationFrame(frame)
    frameCount += 1
    for (const body of animated) {
      if (body.beltSpin) {
        body.beltSpin.mesh.rotation.y += body.beltSpin.speed * 0.016
        continue
      }
      if (body.spin) {
        body.mesh.rotation.y += body.spin
      }
      if (!body.orbit) {
        body.mesh.rotation.y += 0.0025
        continue
      }
      body.angle += body.speed * 0.016
      body.mesh.position.x = Math.cos(body.angle) * body.orbit
      body.mesh.position.y = 0
      body.mesh.position.z = Math.sin(body.angle) * body.orbit
      body.mesh.rotation.y += 0.012
    }
    applyKeyboardPan()
    controls.update()
    renderer.render(scene, camera)
    if (frameCount % 2 === 0) emitLabels()
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    window.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('keyup', onKeyUp)
    window.removeEventListener('blur', onBlur)
    canvas.removeEventListener('wheel', onWheel)
    canvas.removeEventListener('pointerdown', onPointerDown)
    canvas.removeEventListener('pointerup', onPointerUp)
    controls.dispose()
    renderer.dispose()
  }

  window.addEventListener('resize', resize)
  resize()
  build()
  raf = requestAnimationFrame(frame)

  return { dispose, resize }
}
