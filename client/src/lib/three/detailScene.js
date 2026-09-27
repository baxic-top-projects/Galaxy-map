import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import {
  planetFallbackKey,
  planetModelPath,
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
  const promise = new Promise((resolve, reject) => {
    gltfLoader.load(url, (gltf) => resolve(gltf.scene), undefined, reject)
  }).catch(() => null)
  glbCache.set(url, promise)
  return promise
}

async function createBodyMesh({ kind, typeKey, radius }) {
  const isStar = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStar ? resolveStarTypeKey(typeKey) : resolvePlanetTypeKey(typeKey)
  const modelUrl = isStar ? starModelPath(key) : planetModelPath(key)
  const previewUrl = isStar ? starPreviewPath(key) : planetPreviewPath(key)
  const artUrl = isStar ? starTypeArtPath(key) : planetTypeArtPath(key)
  const fallbackKey = isStar ? starFallbackKey(key) : planetFallbackKey(key)
  const fallbackModel = isStar ? starModelPath(fallbackKey) : planetModelPath(fallbackKey)

  let scene = await loadGlb(modelUrl)
  if (!scene && fallbackModel !== modelUrl) scene = await loadGlb(fallbackModel)

  if (scene) {
    const root = scene.clone(true)
    const box = new THREE.Box3().setFromObject(root)
    const size = new THREE.Vector3()
    box.getSize(size)
    const maxDim = Math.max(size.x, size.y, size.z) || 1
    root.scale.setScalar((radius * 2) / maxDim)
    root.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = false
        child.receiveShadow = false
      }
    })
    return root
  }

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

  const geometry = new THREE.SphereGeometry(radius, 48, 32)
  const material = new THREE.MeshStandardMaterial({
    map: texture || null,
    color: texture ? 0xffffff : starColor(key),
    emissive: isStar ? new THREE.Color(starColor(key)) : new THREE.Color(0x000000),
    emissiveIntensity: isStar ? 0.55 : 0.05,
    roughness: isStar ? 0.35 : 0.7,
    metalness: 0.1,
  })
  return new THREE.Mesh(geometry, material)
}

/**
 * Create a detail scene for one star system.
 */
export function createSystemDetailScene(canvas, detail) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setClearColor(0x03050c, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
  camera.position.set(0, -8, 5)

  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.target.set(0, 0, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.7))
  const light = new THREE.PointLight(0xffffff, 2.2, 80)
  light.position.set(0, 0, 0.2)
  scene.add(light)

  const root = new THREE.Group()
  scene.add(root)

  let raf = 0
  let disposed = false
  const bodies = []

  async function build() {
    const star = await createBodyMesh({
      kind: detail.kind === 'star' ? 'star' : detail.kind,
      typeKey: detail.starTypeKey,
      radius: detail.kind === 'well' ? 1.8 : 1.35,
    })
    root.add(star)
    bodies.push({ mesh: star, orbit: 0, speed: 0.05 })

    const planets = [...(detail.worlds || []), ...(detail.uninhabited || [])]
    planets.forEach((planet, index) => {
      const orbit = 2.8 + index * 1.15
      const radius = planet.planetTypeKey === 'gas_giant' ? 0.55 : 0.32
      createBodyMesh({
        kind: 'planet',
        typeKey: planet.planetTypeKey || 'continental',
        radius,
      }).then((mesh) => {
        if (disposed) return
        mesh.userData.orbit = orbit
        mesh.userData.speed = 0.18 / (index + 1)
        mesh.userData.angle = (index / Math.max(planets.length, 1)) * Math.PI * 2
        mesh.position.set(orbit, 0, 0)
        root.add(mesh)

        const ring = new THREE.Mesh(
          new THREE.RingGeometry(orbit - 0.01, orbit + 0.01, 64),
          new THREE.MeshBasicMaterial({
            color: 0x6f8fb8,
            transparent: true,
            opacity: 0.25,
            side: THREE.DoubleSide,
          }),
        )
        ring.rotation.x = Math.PI / 2
        root.add(ring)
        bodies.push({ mesh, orbit, speed: mesh.userData.speed, angle: mesh.userData.angle })
      })
    })
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
    const t = performance.now() * 0.001
    for (const body of bodies) {
      if (!body.orbit) {
        body.mesh.rotation.y += 0.0025
        continue
      }
      body.angle = (body.angle || 0) + body.speed * 0.01
      body.mesh.position.x = Math.cos(body.angle) * body.orbit
      body.mesh.position.y = Math.sin(body.angle) * body.orbit
      body.mesh.rotation.y += 0.01
    }
    root.rotation.z = Math.sin(t * 0.15) * 0.03
    controls.update()
    renderer.render(scene, camera)
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    controls.dispose()
    renderer.dispose()
  }

  window.addEventListener('resize', resize)
  resize()
  build()
  raf = requestAnimationFrame(frame)

  return { dispose, resize }
}
