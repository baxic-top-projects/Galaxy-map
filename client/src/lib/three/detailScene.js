import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import {
  planetPreviewPath,
  planetTypeArtPath,
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

async function createTexturedSphere({ typeKey, radius, kind }) {
  const isStarLike = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStarLike ? resolveStarTypeKey(typeKey, kind) : resolvePlanetTypeKey(typeKey)
  const previewUrl = isStarLike ? starPreviewPath(key) : planetPreviewPath(key)
  const artUrl = isStarLike ? starTypeArtPath(key) : planetTypeArtPath(key)

  let texture = null
  try {
    texture = await loadTexture(previewUrl)
  } catch {
    try {
      texture = await loadTexture(artUrl)
    } catch {
      texture = null
    }
  }

  if (kind === 'black_hole' || kind === 'well') {
    const group = new THREE.Group()
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(radius * 0.72, 48, 32),
      new THREE.MeshBasicMaterial({ color: 0x000000 }),
    )
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 48, 32),
      new THREE.MeshBasicMaterial({
        color: kind === 'well' ? 0xff88cc : 0xff5588,
        transparent: true,
        opacity: 0.22,
      }),
    )
    group.add(core, glow)
    return group
  }

  return new THREE.Mesh(
    new THREE.SphereGeometry(radius, 48, 32),
    new THREE.MeshStandardMaterial({
      map: texture || null,
      color: texture ? 0xffffff : starColor(key),
      emissive: isStarLike ? new THREE.Color(starColor(key)) : new THREE.Color(0x111122),
      emissiveIntensity: isStarLike ? 0.55 : 0.08,
      roughness: isStarLike ? 0.35 : 0.7,
      metalness: 0.1,
    }),
  )
}

async function createBodyMesh({ kind, typeKey, radius, preferGlb = false }) {
  const isStarLike = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStarLike ? resolveStarTypeKey(typeKey, kind) : resolvePlanetTypeKey(typeKey)

  if (preferGlb) {
    const modelUrl = isStarLike ? starModelPath(key) : planetModelPath(key)
    const fallbackKey = starFallbackKey(key)
    const fallbackModel =
      isStarLike && fallbackKey !== key ? starModelPath(fallbackKey) : null
    let scene = await loadGlb(modelUrl)
    if (!scene && fallbackModel) scene = await loadGlb(fallbackModel)
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

/**
 * Create a detail scene for one star / black-hole system.
 */
export function createSystemDetailScene(canvas, detail, callbacks = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setClearColor(0x03050c, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
  camera.position.set(0, -11, 7)

  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.target.set(0, 0, 0)
  controls.minDistance = 3
  controls.maxDistance = 28
  controls.zoomSpeed = 1.2

  function onWheel(event) {
    if (event.deltaY <= 0) return
    const distance = camera.position.distanceTo(controls.target)
    // After zooming out to the system overview, further scroll-back returns to the galaxy.
    if (distance >= controls.maxDistance * 0.9) {
      callbacks.onZoomOut?.()
    }
  }
  canvas.addEventListener('wheel', onWheel, { passive: true })

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

  async function build() {
    const hostKind = detail.kind === 'black_hole' || detail.kind === 'well' ? detail.kind : 'star'
    const hostTypeKey = resolveStarTypeKey(detail.starTypeKey, hostKind)
    const hostRadius = hostKind === 'well' ? 2.1 : hostKind === 'black_hole' ? 1.55 : 1.35
    const host = await createBodyMesh({
      kind: hostKind,
      typeKey: hostTypeKey,
      radius: hostRadius,
      preferGlb: true,
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

    if (hostKind === 'black_hole' || hostKind === 'well') {
      const disk = new THREE.Mesh(
        new THREE.RingGeometry(hostRadius * 1.25, hostRadius * 2.35, 96),
        new THREE.MeshBasicMaterial({
          color: hostKind === 'well' ? 0xff88cc : 0xff6699,
          transparent: true,
          opacity: 0.4,
          side: THREE.DoubleSide,
        }),
      )
      disk.rotation.x = Math.PI / 2
      root.add(disk)
      animated.push({ mesh: disk, orbit: 0, speed: 0, spin: 0.004 })
    }

    const planets = collectBodies(detail)
    const featureBelts = detail.features || []

    await Promise.all(
      planets.map(async (planet, index) => {
        const orbit = 2.6 + index * 1.35
        const radius = planet.planetTypeKey === 'gas_giant' ? 0.62 : planet.inhabited ? 0.4 : 0.3
        const mesh = await createBodyMesh({
          kind: 'planet',
          typeKey: planet.planetTypeKey,
          radius,
          preferGlb: false,
        })
        if (disposed) return
        const angle = (index / Math.max(planets.length, 1)) * Math.PI * 2
        mesh.position.set(Math.cos(angle) * orbit, Math.sin(angle) * orbit, 0)
        root.add(mesh)

        const ring = new THREE.Mesh(
          new THREE.RingGeometry(orbit - 0.015, orbit + 0.015, 96),
          new THREE.MeshBasicMaterial({
            color: planet.inhabited ? 0x8ec7ff : 0x6f8fb8,
            transparent: true,
            opacity: planet.inhabited ? 0.4 : 0.22,
            side: THREE.DoubleSide,
          }),
        )
        ring.rotation.x = Math.PI / 2
        root.add(ring)

        animated.push({
          mesh,
          orbit,
          speed: 0.22 / (index + 1),
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

    featureBelts.forEach((feature, index) => {
      const orbit = 2.6 + planets.length * 1.35 + 0.7 + index * 0.55
      const belt = new THREE.Mesh(
        new THREE.RingGeometry(orbit - 0.18, orbit + 0.18, 96),
        new THREE.MeshBasicMaterial({
          color: 0xc2b280,
          transparent: true,
          opacity: 0.28,
          side: THREE.DoubleSide,
        }),
      )
      belt.rotation.x = Math.PI / 2
      root.add(belt)
      labelAnchors.push({
        id: `feature:${feature.nameEn}`,
        mesh: belt,
        nameEn: feature.nameEn,
        nameRu: feature.nameRu,
        kind: 'feature',
        inhabited: false,
        planetType: feature.feature,
      })
    })

    // Frame the whole system if there are many bodies.
    const span = Math.max(8, 2.6 + Math.max(planets.length - 1, 0) * 1.35 + 3)
    camera.position.set(0, -span * 0.95, span * 0.55)
    controls.target.set(0, 0, 0)
    controls.update()
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
      if (body.spin) {
        body.mesh.rotation.z += body.spin
      }
      if (!body.orbit) {
        body.mesh.rotation.y += 0.0025
        continue
      }
      body.angle = (body.angle || 0) + body.speed * 0.01
      body.mesh.position.x = Math.cos(body.angle) * body.orbit
      body.mesh.position.y = Math.sin(body.angle) * body.orbit
      body.mesh.rotation.y += 0.01
    }
    controls.update()
    renderer.render(scene, camera)
    if (frameCount % 2 === 0) emitLabels()
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    canvas.removeEventListener('wheel', onWheel)
    controls.dispose()
    renderer.dispose()
  }

  window.addEventListener('resize', resize)
  resize()
  build()
  raf = requestAnimationFrame(frame)

  return { dispose, resize }
}
