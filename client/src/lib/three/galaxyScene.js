import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { starColor } from '../galaxy/modelCatalog.js'
import { buildSpatialIndex } from '../galaxy/spatialIndex.js'
import { estimateZoom, pickLabels } from '../galaxy/labelLod.js'

const GALAXY_SCALE = 42

/**
 * Create an imperative Three.js galaxy scene attached to a canvas.
 */
export function createGalaxyScene(canvas, galaxy, callbacks = {}) {
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
  const overviewPosition = new THREE.Vector3(0, -58, 34)
  const overviewTarget = new THREE.Vector3(0, 0, 0)

  const root = new THREE.Group()
  scene.add(root)

  const ambient = new THREE.AmbientLight(0xffffff, 0.55)
  scene.add(ambient)
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.85)
  keyLight.position.set(20, -30, 50)
  scene.add(keyLight)

  const plate = createPoliticalPlate()
  root.add(plate)

  const systemIndex = new Map(galaxy.systems.map((system, index) => [system.id, index]))
  const positions = new Float32Array(galaxy.systems.length * 3)
  const colors = new Float32Array(galaxy.systems.length * 3)
  const sizes = new Float32Array(galaxy.systems.length)
  const color = new THREE.Color()

  galaxy.systems.forEach((system, index) => {
    const i = index * 3
    positions[i] = system.x * GALAXY_SCALE
    positions[i + 1] = system.y * GALAXY_SCALE
    positions[i + 2] = system.z * GALAXY_SCALE

    const polity = system.stem ? galaxy.polityByStem.get(system.stem) : null
    if (system.kind === 'black_hole' || system.kind === 'well') {
      color.setHex(0xff66aa)
    } else if (polity?.color) {
      color.set(polity.color)
      if (system.capital) color.offsetHSL(0, 0.05, 0.18)
    } else {
      color.setHex(starColor(system.starTypeKey))
    }

    colors[i] = color.r
    colors[i + 1] = color.g
    colors[i + 2] = color.b
    sizes[index] =
      system.capital ? 5.2 : system.kind === 'well' ? 6.2 : system.kind === 'black_hole' ? 3.4 : 2.35 + Math.min(system.worldCount || 0, 4) * 0.22
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))

  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexColors: true,
    uniforms: {
      uScale: { value: 1 },
    },
    vertexShader: `
      attribute float size;
      varying vec3 vColor;
      uniform float uScale;
      void main() {
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * uScale * (180.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      void main() {
        vec2 uv = gl_PointCoord - vec2(0.5);
        float d = length(uv);
        float alpha = smoothstep(0.5, 0.0, d);
        gl_FragColor = vec4(vColor, alpha);
      }
    `,
  })

  const points = new THREE.Points(geometry, material)
  root.add(points)

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
    color: 0x7aa0c8,
    transparent: true,
    opacity: 0.18,
  })
  const lanes = new THREE.LineSegments(edgeGeom, edgeMat)
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

  function frame() {
    if (disposed) return
    raf = requestAnimationFrame(frame)
    frameCount += 1
    if (focusTween) focusTween()
    controls.update()
    material.uniforms.uScale.value = THREE.MathUtils.clamp(22 / cameraDistance(), 0.7, 3.0)
    renderer.render(scene, camera)
    if (frameCount % 2 === 0) emitLabels()
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', resize)
    canvas.removeEventListener('pointermove', onPointerMove)
    canvas.removeEventListener('pointerdown', onPointerDown)
    canvas.removeEventListener('pointerup', onPointerUp)
    canvas.removeEventListener('dblclick', onDblClick)
    canvas.removeEventListener('wheel', onWheel)
    controls.dispose()
    geometry.dispose()
    material.dispose()
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

function createPoliticalPlate() {
  const size = 1024
  const canvas2d = document.createElement('canvas')
  canvas2d.width = size
  canvas2d.height = size
  const ctx = canvas2d.getContext('2d')
  ctx.fillStyle = '#05070f'
  ctx.fillRect(0, 0, size, size)

  const cx = size / 2
  const cy = size / 2
  const radius = size * 0.48

  const arms = ctx.createRadialGradient(cx, cy, radius * 0.05, cx, cy, radius)
  arms.addColorStop(0, 'rgba(255, 210, 140, 0.28)')
  arms.addColorStop(0.18, 'rgba(180, 120, 170, 0.16)')
  arms.addColorStop(0.45, 'rgba(70, 100, 170, 0.12)')
  arms.addColorStop(0.78, 'rgba(30, 50, 90, 0.06)')
  arms.addColorStop(1, 'rgba(5, 7, 15, 0)')
  ctx.fillStyle = arms
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.fill()

  ctx.globalCompositeOperation = 'lighter'
  for (let i = 0; i < 4; i += 1) {
    const grad = ctx.createRadialGradient(
      cx + Math.cos((i * Math.PI) / 2) * radius * 0.28,
      cy + Math.sin((i * Math.PI) / 2) * radius * 0.18,
      0,
      cx,
      cy,
      radius * 0.85,
    )
    grad.addColorStop(0, 'rgba(90, 130, 200, 0.05)')
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, size, size)
  }
  ctx.globalCompositeOperation = 'source-over'

  const texture = new THREE.CanvasTexture(canvas2d)
  texture.colorSpace = THREE.SRGBColorSpace
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 0.9,
    depthWrite: false,
  })
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(GALAXY_SCALE * 2.0, GALAXY_SCALE * 2.0), material)
  mesh.position.z = -0.8
  mesh.raycast = () => {}
  return mesh
}
