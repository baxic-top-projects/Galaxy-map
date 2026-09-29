import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { mapTexturePath, starColor } from '../galaxy/modelCatalog.js'
import { buildSpatialIndex } from '../galaxy/spatialIndex.js'
import { estimateZoom, pickLabels } from '../galaxy/labelLod.js'

const GALAXY_SCALE = 42
const MAP_LIM = 1.06
const textureLoader = new THREE.TextureLoader()
textureLoader.setCrossOrigin('anonymous')

function territoryPlateUrl() {
  // Resolve at use-time so applyAssetManifest / VITE_ASSETS_BASE are already applied.
  return mapTexturePath('galaxy_territory_plate.png', 'v=57')
}

function basePlateUrl() {
  return mapTexturePath('galaxy_base_plate.png', 'v=1')
}

function polityAnchorsForGalaxy(galaxy) {
  return (galaxy.polities || [])
    .map((polity) => {
      const systems = galaxy.systems.filter((system) => system.stem === polity.stem)
      if (!systems.length) return null
      const meanX = systems.reduce((sum, system) => sum + system.x, 0) / systems.length
      const meanY = systems.reduce((sum, system) => sum + system.y, 0) / systems.length
      const anchor = systems.reduce((best, system) => {
        const distance = (system.x - meanX) ** 2 + (system.y - meanY) ** 2
        return !best || distance < best.distance ? { system, distance } : best
      }, null)?.system
      return {
        polity,
        x: anchor?.x ?? meanX,
        y: anchor?.y ?? meanY,
      }
    })
    .filter(Boolean)
}

function loadTexture(url, { crisp = false } = {}) {
  return new Promise((resolve, reject) => {
    textureLoader.load(
      url,
      (texture) => {
        texture.colorSpace = THREE.SRGBColorSpace
        texture.anisotropy = 8
        if (crisp) {
          // Keep cream polity borders from being washed into territory paint by mipmaps.
          texture.generateMipmaps = false
          texture.minFilter = THREE.LinearFilter
          texture.magFilter = THREE.LinearFilter
        } else {
          texture.generateMipmaps = true
          texture.minFilter = THREE.LinearMipmapLinearFilter
          texture.magFilter = THREE.LinearFilter
        }
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
  junction: 4,
}

function markerKind(system) {
  if (system.kind === 'junction') return MARKER.junction
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
  if (kind === MARKER.junction) return 7.5
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

  const [basePlate, plate] = await Promise.all([
    createBasePlate(),
    createPoliticalPlate(galaxy),
  ])
  root.add(basePlate, plate)

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

    if (kind === MARKER.junction) {
      color.setHex(0xa8e2dd)
    } else if (kind === MARKER.blackHole || kind === MARKER.well) {
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
        else if (vKind > 2.5 && vKind < 3.5) cap = 16.0;  // well
        else if (vKind >= 3.5) cap = 10.0;                // junction
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

        // Empty hypercorridor junction: small hollow diamond.
        if (vKind >= 3.5) {
          float diamond = abs(uv.x) + abs(uv.y);
          float rim = smoothstep(0.28, 0.34, diamond) * (1.0 - smoothstep(0.43, 0.49, diamond));
          float core = 1.0 - smoothstep(0.07, 0.13, d);
          if (rim < 0.02 && core < 0.02) discard;
          gl_FragColor = vec4(vColor, max(rim * 0.9, core));
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

  const stormGroup = new THREE.Group()
  stormGroup.renderOrder = 3
  root.add(stormGroup)
  let stormPoints = null
  let stormMaterial = null
  let stormGeometry = null
  let stormEyes = []
  let stormEyePoints = null
  let stormEyeMaterial = null
  let stormEyeGeometry = null
  // Match storm-service defaults: crawl one hyperlane over move_interval ticks.
  const STORM_TICK_SECONDS = 2
  const STORM_MOVE_INTERVAL_TICKS = 3
  let lastFrameTime = performance.now()

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
  const stormColor = new THREE.Color()

  function clearStormMeshes(group) {
    while (group.children.length) {
      const child = group.children.pop()
      child.geometry?.dispose()
      child.material?.dispose()
    }
  }

  function worldPosForSystem(system) {
    return new THREE.Vector3(
      system.x * GALAXY_SCALE,
      system.y * GALAXY_SCALE,
      system.z * GALAXY_SCALE,
    )
  }

  function rebuildAffectedStormPoints(systems) {
    if (stormPoints) {
      stormGroup.remove(stormPoints)
      stormGeometry?.dispose()
      stormMaterial?.dispose()
      stormPoints = null
      stormGeometry = null
      stormMaterial = null
    }
    if (!systems.length) return

    const count = systems.length
    const stormPositions = new Float32Array(count * 3)
    const stormColors = new Float32Array(count * 3)
    const stormSizes = new Float32Array(count)
    const stormIntensity = new Float32Array(count)

    systems.forEach((entry, index) => {
      const system = galaxy.byId.get(entry.systemId)
      if (!system) return
      const i = index * 3
      stormPositions[i] = system.x * GALAXY_SCALE
      stormPositions[i + 1] = system.y * GALAXY_SCALE
      stormPositions[i + 2] = system.z * GALAXY_SCALE
      stormColor.set(entry.color || '#6ec8ff')
      stormColors[i] = stormColor.r
      stormColors[i + 1] = stormColor.g
      stormColors[i + 2] = stormColor.b
      const intensity = THREE.MathUtils.clamp(Number(entry.intensity) || 0.4, 0.15, 1)
      stormIntensity[index] = intensity
      stormSizes[index] = 14 + intensity * 18
    })

    stormGeometry = new THREE.BufferGeometry()
    stormGeometry.setAttribute('position', new THREE.BufferAttribute(stormPositions, 3))
    stormGeometry.setAttribute('color', new THREE.BufferAttribute(stormColors, 3))
    stormGeometry.setAttribute('size', new THREE.BufferAttribute(stormSizes, 1))
    stormGeometry.setAttribute('intensity', new THREE.BufferAttribute(stormIntensity, 1))

    stormMaterial = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
      uniforms: {
        uTime: { value: 0 },
        uScale: { value: 1 },
      },
      vertexShader: `
        attribute float size;
        attribute float intensity;
        varying vec3 vColor;
        varying float vIntensity;
        uniform float uScale;
        uniform float uTime;
        void main() {
          vColor = color;
          vIntensity = intensity;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          float pulse = 1.0 + 0.12 * sin(uTime * 1.8 + intensity * 6.0);
          float dist = max(-mvPosition.z, 6.0);
          float atten = clamp(52.0 / dist, 0.7, 1.25);
          gl_PointSize = clamp(size * uScale * atten * pulse, 8.0, 48.0);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vIntensity;
        uniform float uTime;
        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }
        void main() {
          vec2 uv = gl_PointCoord - vec2(0.5);
          float d = length(uv);
          if (d > 0.5) discard;
          float n = hash(uv * 8.0 + uTime * 0.35);
          float swirl = 0.55 + 0.45 * sin((atan(uv.y, uv.x) + uTime) * 3.0 + n * 6.2831);
          float core = 1.0 - smoothstep(0.08, 0.42, d);
          float haze = (1.0 - smoothstep(0.2, 0.5, d)) * swirl;
          float alpha = (core * 0.45 + haze * 0.55) * (0.28 + vIntensity * 0.55);
          vec3 col = mix(vColor * 0.55, vColor * 1.25, core);
          gl_FragColor = vec4(col, alpha);
        }
      `,
    })

    stormPoints = new THREE.Points(stormGeometry, stormMaterial)
    stormPoints.frustumCulled = false
    stormGroup.add(stormPoints)
  }

  function rebuildStormEyes(storms) {
    if (stormEyePoints) {
      stormGroup.remove(stormEyePoints)
      stormEyeGeometry?.dispose()
      stormEyeMaterial?.dispose()
      stormEyePoints = null
      stormEyeGeometry = null
      stormEyeMaterial = null
    }

    stormEyes = []
    for (const storm of storms || []) {
      const from = galaxy.byId.get(storm.currentSystemId)
      const to = galaxy.byId.get(storm.nextSystemId || storm.currentSystemId) || from
      if (!from) continue
      const progress = THREE.MathUtils.clamp(Number(storm.pathProgress) || 0, 0, 1)
      stormEyes.push({
        id: storm.id,
        from,
        to: to || from,
        progress,
        displayProgress: progress,
        color: storm.color || '#6ec8ff',
        intensity: THREE.MathUtils.clamp(Number(storm.intensity) || 0.5, 0.2, 1),
        stage: storm.stage || 'active',
      })
    }
    if (!stormEyes.length) return

    const count = stormEyes.length
    stormEyeGeometry = new THREE.BufferGeometry()
    stormEyeGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
    stormEyeGeometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
    stormEyeGeometry.setAttribute('size', new THREE.BufferAttribute(new Float32Array(count), 1))
    stormEyeGeometry.setAttribute('intensity', new THREE.BufferAttribute(new Float32Array(count), 1))

    stormEyeMaterial = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
      uniforms: {
        uTime: { value: 0 },
        uScale: { value: 1 },
      },
      vertexShader: `
        attribute float size;
        attribute float intensity;
        varying vec3 vColor;
        varying float vIntensity;
        uniform float uScale;
        uniform float uTime;
        void main() {
          vColor = color;
          vIntensity = intensity;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          float pulse = 1.0 + 0.18 * sin(uTime * 2.4 + intensity * 5.0);
          float dist = max(-mvPosition.z, 6.0);
          float atten = clamp(52.0 / dist, 0.7, 1.25);
          gl_PointSize = clamp(size * uScale * atten * pulse, 14.0, 72.0);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vIntensity;
        uniform float uTime;
        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }
        void main() {
          vec2 uv = gl_PointCoord - vec2(0.5);
          float d = length(uv);
          if (d > 0.5) discard;
          float n = hash(uv * 10.0 + uTime * 0.55);
          float swirl = 0.5 + 0.5 * sin((atan(uv.y, uv.x) * 4.0) - uTime * 2.2 + n * 6.2831);
          float core = 1.0 - smoothstep(0.05, 0.28, d);
          float rim = (1.0 - smoothstep(0.18, 0.5, d)) * swirl;
          float alpha = (core * 0.85 + rim * 0.75) * (0.45 + vIntensity * 0.55);
          vec3 col = mix(vColor * 0.7, vec3(1.0), core * 0.45);
          gl_FragColor = vec4(col, alpha);
        }
      `,
    })

    stormEyePoints = new THREE.Points(stormEyeGeometry, stormEyeMaterial)
    stormEyePoints.frustumCulled = false
    stormGroup.add(stormEyePoints)
    writeStormEyePositions()
  }

  function writeStormEyePositions() {
    if (!stormEyeGeometry || !stormEyes.length) return
    const positions = stormEyeGeometry.attributes.position.array
    const colors = stormEyeGeometry.attributes.color.array
    const sizes = stormEyeGeometry.attributes.size.array
    const intensities = stormEyeGeometry.attributes.intensity.array
    const from = new THREE.Vector3()
    const to = new THREE.Vector3()
    const pos = new THREE.Vector3()

    stormEyes.forEach((eye, index) => {
      from.copy(worldPosForSystem(eye.from))
      to.copy(worldPosForSystem(eye.to))
      const t = eye.from.id === eye.to.id ? 0 : eye.displayProgress
      pos.lerpVectors(from, to, t)
      const i = index * 3
      positions[i] = pos.x
      positions[i + 1] = pos.y
      positions[i + 2] = pos.z
      stormColor.set(eye.color)
      colors[i] = stormColor.r
      colors[i + 1] = stormColor.g
      colors[i + 2] = stormColor.b
      const stageBoost = eye.stage === 'forming' ? 0.75 : eye.stage === 'dissipating' ? 0.85 : 1
      intensities[index] = eye.intensity * stageBoost
      sizes[index] = 26 + eye.intensity * 34
    })

    stormEyeGeometry.attributes.position.needsUpdate = true
    stormEyeGeometry.attributes.color.needsUpdate = true
    stormEyeGeometry.attributes.size.needsUpdate = true
    stormEyeGeometry.attributes.intensity.needsUpdate = true
  }

  function setStorms(stormSnapshot) {
    rebuildAffectedStormPoints(stormSnapshot?.systems || [])
    rebuildStormEyes(stormSnapshot?.storms || [])
  }

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

  function setPoliticalMap(visible) {
    plate.visible = !!visible
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
    const now = performance.now()
    const dt = Math.min(0.05, (now - lastFrameTime) / 1000)
    lastFrameTime = now
    if (focusTween) focusTween()
    applyKeyboardPan()
    controls.update()
    const scale = THREE.MathUtils.clamp(Math.sqrt(18 / Math.max(cameraDistance(), 1)), 0.75, 1.25)
    for (const layer of starLayers) {
      layer.material.uniforms.uScale.value = scale
    }
    // Smooth crawl along the current hyperlane between server ticks.
    const crawlPerSecond = 1 / Math.max(0.001, STORM_TICK_SECONDS * STORM_MOVE_INTERVAL_TICKS)
    let eyesMoved = false
    for (const eye of stormEyes) {
      if (eye.from.id === eye.to.id) continue
      const next = Math.min(1, eye.displayProgress + dt * crawlPerSecond)
      if (next !== eye.displayProgress) {
        eye.displayProgress = next
        eyesMoved = true
      }
    }
    if (eyesMoved) writeStormEyePositions()
    if (stormMaterial?.uniforms?.uTime) {
      stormMaterial.uniforms.uTime.value = now * 0.001
      stormMaterial.uniforms.uScale.value = scale
    }
    if (stormEyeMaterial?.uniforms?.uTime) {
      stormEyeMaterial.uniforms.uTime.value = now * 0.001
      stormEyeMaterial.uniforms.uScale.value = scale
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
    setStorms(null)
    stormEyes = []
    edgeGeom.dispose()
    edgeMat.dispose()
    const plateGeometries = new Set()
    const plateMaterials = new Set()
    const plateTextures = new Set()
    for (const mapPlate of [basePlate, plate]) {
      mapPlate.traverse((child) => {
        if (child.geometry) plateGeometries.add(child.geometry)
        const materials = Array.isArray(child.material) ? child.material : [child.material]
        for (const material of materials) {
          if (!material) continue
          plateMaterials.add(material)
          if (material.map) plateTextures.add(material.map)
        }
      })
    }
    plateGeometries.forEach((geometry) => geometry.dispose())
    plateMaterials.forEach((material) => material.dispose())
    plateTextures.forEach((texture) => texture.dispose())
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
    setStorms,
    setPoliticalMap,
    resetView,
    dispose,
  }
}

function createPoliticalPlate(galaxy) {
  // Prefer the canon territory plate (same paint as galaxy_political_map.png).
  return loadTexture(territoryPlateUrl(), { crisp: true })
    .then((texture) => {
      const mesh = makePlateMeshFromTexture(texture)
      mesh.renderOrder = -90
      return mesh
    })
    .catch((err) => {
      console.warn('Galaxy territory plate failed, using procedural fallback', territoryPlateUrl(), err)
      return createProceduralPoliticalPlate(galaxy)
    })
}

function createBasePlate() {
  return loadTexture(basePlateUrl(), { crisp: true }).then((texture) => {
    const mesh = makePlateMeshFromTexture(texture)
    mesh.position.z = -0.82
    mesh.renderOrder = -100
    return mesh
  })
}

function makePlateMeshFromTexture(texture, galaxy = null) {
  if (galaxy && texture.image) {
    const width = texture.image.width || 1024
    const height = texture.image.height || 1024
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    context.drawImage(texture.image, 0, 0, width, height)
    const scale = width / 1024
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.lineJoin = 'round'

    for (const anchor of polityAnchorsForGalaxy(galaxy)) {
      const source = String(anchor.polity.label || anchor.polity.nameRu || '').trim()
      if (!source) continue
      let lines = source.split(/\n+/)
      if (lines.length === 1) {
        const words = source.split(/\s+/)
        lines = words.length > 1 ? [words[0], words.slice(1).join(' ')] : words
      }
      const isSuzerain = anchor.polity.kind === 'suzerain'
      const fontSize = (isSuzerain ? 15 : 8.5) * scale
      const lineHeight = fontSize * 1.12
      const x = ((anchor.x + MAP_LIM) / (MAP_LIM * 2)) * width
      const y = (1 - (anchor.y + MAP_LIM) / (MAP_LIM * 2)) * height
      context.font = `${isSuzerain ? 700 : 400} ${fontSize}px "Segoe UI", Arial, sans-serif`
      context.strokeStyle = 'rgba(0, 0, 0, 0.82)'
      context.lineWidth = (isSuzerain ? 3.2 : 2.4) * scale
      context.fillStyle = '#ffffff'
      lines.forEach((line, index) => {
        const lineY = y + (index - (lines.length - 1) / 2) * lineHeight
        context.strokeText(line, x, lineY)
        context.fillText(line, x, lineY)
      })
    }

    const bakedTexture = new THREE.CanvasTexture(canvas)
    bakedTexture.colorSpace = THREE.SRGBColorSpace
    bakedTexture.generateMipmaps = false
    bakedTexture.minFilter = THREE.LinearFilter
    bakedTexture.magFilter = THREE.LinearFilter
    texture.dispose()
    texture = bakedTexture
  }
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
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

// Kept as an offline-capable splitter for future independent border styling.
// Runtime political-map toggling hides the complete plate and does not need it.
function makeSplitPlateMeshFromTexture(texture) {
  const image = texture.image
  const width = image?.width || 1024
  const height = image?.height || 1024
  const sourceCanvas = document.createElement('canvas')
  sourceCanvas.width = width
  sourceCanvas.height = height
  const sourceContext = sourceCanvas.getContext('2d', { willReadFrequently: true })
  sourceContext.drawImage(image, 0, 0, width, height)
  const sourceImage = sourceContext.getImageData(0, 0, width, height)
  const source = sourceImage.data
  const borderMask = new Uint8Array(width * height)

  const colorDistance = (offset, r, g, b) =>
    Math.hypot(source[offset] - r, source[offset + 1] - g, source[offset + 2] - b)

  for (let index = 0; index < borderMask.length; index += 1) {
    const offset = index * 4
    if (
      source[offset + 3] > 100 &&
      (colorDistance(offset, 247, 240, 214) < 24 ||
        colorDistance(offset, 242, 235, 209) < 24)
    ) {
      borderMask[index] = 1
    }
  }

  // Include anti-aliased pixels around the solid cream centerline.
  const solidMask = borderMask.slice()
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x
      if (!solidMask[index]) continue
      for (let dy = -2; dy <= 2; dy += 1) {
        for (let dx = -2; dx <= 2; dx += 1) {
          borderMask[(y + dy) * width + x + dx] = 1
        }
      }
    }
  }

  const fillImage = new ImageData(new Uint8ClampedArray(source), width, height)
  const borderImage = new ImageData(width, height)
  const fill = fillImage.data
  const border = borderImage.data
  const directions = [
    [-1, 0],
    [1, 0],
    [0, -1],
    [0, 1],
    [-1, -1],
    [1, -1],
    [-1, 1],
    [1, 1],
  ]

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x
      if (!borderMask[index]) continue
      const offset = index * 4
      border[offset] = source[offset]
      border[offset + 1] = source[offset + 1]
      border[offset + 2] = source[offset + 2]
      border[offset + 3] = source[offset + 3]

      let red = 0
      let green = 0
      let blue = 0
      let alpha = 0
      let samples = 0
      for (const [dx, dy] of directions) {
        for (let radius = 3; radius <= 12; radius += 1) {
          const sampleX = x + dx * radius
          const sampleY = y + dy * radius
          if (sampleX < 0 || sampleX >= width || sampleY < 0 || sampleY >= height) break
          const sampleIndex = sampleY * width + sampleX
          if (borderMask[sampleIndex]) continue
          const sampleOffset = sampleIndex * 4
          red += source[sampleOffset]
          green += source[sampleOffset + 1]
          blue += source[sampleOffset + 2]
          alpha += source[sampleOffset + 3]
          samples += 1
          break
        }
      }
      if (samples > 0) {
        fill[offset] = red / samples
        fill[offset + 1] = green / samples
        fill[offset + 2] = blue / samples
        fill[offset + 3] = alpha / samples
      }
    }
  }

  const fillCanvas = document.createElement('canvas')
  fillCanvas.width = width
  fillCanvas.height = height
  fillCanvas.getContext('2d').putImageData(fillImage, 0, 0)
  const borderCanvas = document.createElement('canvas')
  borderCanvas.width = width
  borderCanvas.height = height
  borderCanvas.getContext('2d').putImageData(borderImage, 0, 0)

  const makeCanvasTexture = (canvas) => {
    const canvasTexture = new THREE.CanvasTexture(canvas)
    canvasTexture.colorSpace = THREE.SRGBColorSpace
    canvasTexture.generateMipmaps = false
    canvasTexture.minFilter = THREE.LinearFilter
    canvasTexture.magFilter = THREE.LinearFilter
    return canvasTexture
  }

  const fillTexture = makeCanvasTexture(fillCanvas)
  const borderTexture = makeCanvasTexture(borderCanvas)
  texture.dispose()
  const span = GALAXY_SCALE * 2 * MAP_LIM
  const group = new THREE.Group()
  const fillMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(span, span),
    new THREE.MeshBasicMaterial({
      map: fillTexture,
      transparent: true,
      depthWrite: false,
      fog: false,
      side: THREE.DoubleSide,
    }),
  )
  fillMesh.position.z = -0.8
  fillMesh.raycast = () => {}
  const borderMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(span, span),
    new THREE.MeshBasicMaterial({
      map: borderTexture,
      transparent: true,
      depthWrite: false,
      fog: false,
      side: THREE.DoubleSide,
    }),
  )
  borderMesh.position.z = -0.79
  borderMesh.raycast = () => {}
  group.add(fillMesh, borderMesh)
  group.userData.borderLayer = borderMesh
  return group
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
  if (!owned.length) return makePlateMeshFromCanvas(canvas2d, galaxy)

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
  return makePlateMeshFromCanvas(canvas2d, galaxy)
}

function makePlateMeshFromCanvas(canvas2d, galaxy = null) {
  const texture = new THREE.CanvasTexture(canvas2d)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return makePlateMeshFromTexture(texture, galaxy)
}
