import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { mapTexturePath, starColor } from '../galaxy/modelCatalog.js'
import polityLabelAnchors from '../galaxy/polityLabelAnchors.json'
import {
  centroidsFromOwnerRaster,
  centroidsFromSystems,
  fitLabelFontToClearance,
  polityLabelFontSize,
  resolvePolityLabelAnchors,
} from '../galaxy/polityTerritoryAnchors.js'
import { buildSpatialIndex } from '../galaxy/spatialIndex.js'
import { estimateZoom, pickLabels } from '../galaxy/labelLod.js'
import {
  boundsFromCameraView,
  tileKey,
  tilesForBounds,
} from '../galaxy/mapTiles.js'
import {
  getCachedPoliticalPlate,
  PLATE_BITMAP_OPTIONS,
  setCachedPoliticalPlate,
} from '../galaxy/tileCache.js'

const GALAXY_SCALE = 42
const DEFAULT_MAP_LIM = 1.06
const textureLoader = new THREE.TextureLoader()
textureLoader.setCrossOrigin('anonymous')

function basePlateUrl() {
  return mapTexturePath('galaxy_base_plate_v5.png', 'v=8')
}

function mapLimitFor(galaxy) {
  const value = Number(galaxy?.meta?.mapLim)
  return Number.isFinite(value) && value >= DEFAULT_MAP_LIM ? value : DEFAULT_MAP_LIM
}

function systemsFrame(systems) {
  if (!systems?.length) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const system of systems) {
    minX = Math.min(minX, system.x)
    minY = Math.min(minY, system.y)
    maxX = Math.max(maxX, system.x)
    maxY = Math.max(maxY, system.y)
  }
  const cx = ((minX + maxX) / 2) * GALAXY_SCALE
  const cy = ((minY + maxY) / 2) * GALAXY_SCALE
  const span = Math.max(maxX - minX, maxY - minY, 0.12) * GALAXY_SCALE
  const dist = THREE.MathUtils.clamp(span * 2.6, 16, 120)
  return {
    target: new THREE.Vector3(cx, cy, 0),
    position: new THREE.Vector3(cx, cy - dist * 0.22, dist),
    span,
  }
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
/**
 * Start building/decoding the political plate as soon as the catalog is ready,
 * even before the WebGL scene mounts — so fill races with star buffer setup.
 */
export function prefetchPoliticalPlate(galaxy, locale = 'ru') {
  if (!galaxy?.systems?.length) return null
  if (galaxy._politicalPlatePromise) return galaxy._politicalPlatePromise
  const canCache =
    Boolean(galaxy._cachedPoliticalPlate?.blob) ||
    Boolean(galaxy.meta?.hasPoliticalPlate) ||
    Boolean(galaxy.cacheRevision)
  const ready =
    Boolean(galaxy.meta?.systemsHydrated) ||
    canCache ||
    !galaxy.tileGrid
  if (!ready) return null
  galaxy._politicalPlatePromise = createPoliticalPlate(galaxy, locale, {
    allowCache: true,
  }).catch((err) => {
    if (galaxy._politicalPlatePromise) galaxy._politicalPlatePromise = null
    throw err
  })
  return galaxy._politicalPlatePromise
}

export async function createGalaxyScene(canvas, galaxy, callbacks = {}) {
  const mapLim = mapLimitFor(galaxy)
  const overviewScale = mapLim / DEFAULT_MAP_LIM
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
  // The galaxy lies in the XY plane. OrbitControls otherwise assumes Y-up,
  // allowing a simple dolly to retain an almost edge-on, distorted view.
  camera.up.set(0, 0, 1)
  camera.position.set(0, -12 * overviewScale, 66 * overviewScale)

  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.enableZoom = true
  controls.zoomSpeed = 1.15
  controls.minDistance = 4
  controls.maxDistance = Math.max(110, 110 * overviewScale)
  controls.minPolarAngle = 0.01
  controls.maxPolarAngle = Math.PI - 0.01
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
  const overviewPosition = new THREE.Vector3(0, -12 * overviewScale, 66 * overviewScale)
  const overviewTarget = new THREE.Vector3(0, 0, 0)
  const fullSystemCount = Number(galaxy?.meta?.systemCount) || galaxy.systems.length
  const isPolitySubset =
    Boolean(galaxy?.meta?.polityFiltered) ||
    (galaxy.systems.length > 0 && galaxy.systems.length < fullSystemCount * 0.9)
  if (isPolitySubset) {
    const frame = systemsFrame(galaxy.systems)
    if (frame) {
      overviewTarget.copy(frame.target)
      overviewPosition.copy(frame.position)
      camera.position.copy(frame.position)
      controls.target.copy(frame.target)
      controls.minDistance = Math.min(controls.minDistance, Math.max(3, frame.span * 0.35))
      controls.maxDistance = Math.max(controls.maxDistance, frame.span * 6)
    }
  }

  const root = new THREE.Group()
  scene.add(root)

  const ambient = new THREE.AmbientLight(0xffffff, 0.55)
  scene.add(ambient)
  const keyLight = new THREE.DirectionalLight(0xffffff, 0.85)
  keyLight.position.set(20, -30, 50)
  scene.add(keyLight)

  // Base plate + systems first so the map is interactive before the heavy
  // political raster finishes (and before edges/search finish hydrating).
  let disposed = false
  let politicalMapVisible = true
  let plate = new THREE.Group()
  plate.visible = politicalMapVisible
  let politicalBuildVersion = 0

  function disposePoliticalPlate(target) {
    target.traverse((child) => {
      if (child.geometry) child.geometry.dispose()
      const materials = Array.isArray(child.material) ? child.material : [child.material]
      for (const material of materials) {
        if (!material) continue
        if (material.map) material.map.dispose()
        material.dispose()
      }
    })
  }

  let politicalPlateBuilt = false
  const attachPoliticalPlate = (nextPlate, buildVersion) => {
    if (disposed || buildVersion !== politicalBuildVersion) {
      disposePoliticalPlate(nextPlate)
      return false
    }
    if (plate === nextPlate) return true
    root.remove(plate)
    disposePoliticalPlate(plate)
    plate = nextPlate
    plate.visible = politicalMapVisible
    root.add(plate)
    politicalPlateBuilt = true
    return true
  }
  const bootstrapPoliticalPlate = async ({ allowCache = true } = {}) => {
    const buildVersion = ++politicalBuildVersion
    const locale = callbacks.locale || 'ru'
    let nextPlate = null
    // Prefer a plate already baking during boot / catalog hydrate.
    if (galaxy._politicalPlatePromise) {
      try {
        nextPlate = await galaxy._politicalPlatePromise
      } catch {
        nextPlate = null
      }
    }
    if (!nextPlate) {
      nextPlate = await createPoliticalPlate(galaxy, locale, {
        allowCache,
        // Paint borders as soon as the raster is ready; labels follow.
        onTerritoriesReady: (partial) => {
          attachPoliticalPlate(partial, buildVersion)
        },
      })
    }
    attachPoliticalPlate(nextPlate, buildVersion)
  }
  // Cached plate can paint before systems finish hydrating — no need to wait.
  const hasCachedPlate =
    Boolean(galaxy?._cachedPoliticalPlate?.blob) ||
    Boolean(galaxy?.meta?.hasPoliticalPlate)
  const deferPoliticalPlate =
    Boolean(galaxy?.tileGrid) &&
    !galaxy?.meta?.systemsHydrated &&
    !hasCachedPlate
  // Plate + base texture + star buffer all overlap on the main thread yields.
  if (!deferPoliticalPlate) void bootstrapPoliticalPlate({ allowCache: true })
  const basePlatePromise = createBasePlate(mapLim)
  root.add(plate)

  const color = new THREE.Color()
  const geometry = new THREE.BufferGeometry()
  // Chunk star buffer fills so the political raster (same main thread) can keep
  // progressing between slices instead of waiting on a 9k-point sync burst.
  const STAR_WRITE_CHUNK = 768
  let systemsWriteVersion = 0

  async function writeSystemAttributes(systems, isCancelled = () => false) {
    const list = Array.isArray(systems) ? systems : []
    const positions = new Float32Array(list.length * 3)
    const colors = new Float32Array(list.length * 3)
    const sizes = new Float32Array(list.length)
    const kinds = new Float32Array(list.length)
    for (let index = 0; index < list.length; index += 1) {
      const system = list[index]
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
        color.setHex(kind === MARKER.well ? 0xffbe6a : 0xff9a3c)
      } else if (kind === MARKER.capital) {
        const stem = system.stem || ''
        color.setHex(stem.includes('Miradin') ? 0xffd0dc : 0xffe566)
      } else {
        color.setHex(starColor(system.starTypeKey))
      }

      colors[i] = color.r
      colors[i + 1] = color.g
      colors[i + 2] = color.b

      if (index > 0 && index % STAR_WRITE_CHUNK === 0) {
        await yieldToBrowser()
        if (isCancelled()) return false
      }
    }
    if (isCancelled()) return false
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
    geometry.setAttribute('kind', new THREE.BufferAttribute(kinds, 1))
    geometry.computeBoundingSphere()
    return true
  }

  await writeSystemAttributes(galaxy.systems, () => disposed)

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

  const basePlate = await basePlatePromise
  root.add(basePlate)

  const edgeMat = new THREE.LineBasicMaterial({
    color: 0x8aa4bc,
    transparent: true,
    opacity: 0.12,
    depthWrite: false,
    fog: false,
  })
  let edgeGeom = new THREE.BufferGeometry()
  edgeGeom.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(0), 3))
  let lanes = new THREE.LineSegments(edgeGeom, edgeMat)
  lanes.renderOrder = 1
  lanes.visible = false
  root.add(lanes)

  function setEdges(edgesDisplay = []) {
    const edgePositions = []
    for (const edge of edgesDisplay || []) {
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
    const nextGeom = new THREE.BufferGeometry()
    nextGeom.setAttribute(
      'position',
      new THREE.Float32BufferAttribute(
        edgePositions.length ? edgePositions : new Float32Array(0),
        3,
      ),
    )
    root.remove(lanes)
    edgeGeom.dispose()
    edgeGeom = nextGeom
    lanes = new THREE.LineSegments(edgeGeom, edgeMat)
    lanes.renderOrder = 1
    lanes.visible = edgePositions.length > 0
    root.add(lanes)
    galaxy.edgesDisplay = edgesDisplay || []
  }

  if ((galaxy.edgesDisplay || []).length) {
    setEdges(galaxy.edgesDisplay)
  }

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
  let spatial = buildSpatialIndex(galaxy.systems)

  let systemsFingerprint = `${galaxy.systems.length}:${galaxy.systems[0]?.id || ''}:${galaxy.systems[galaxy.systems.length - 1]?.id || ''}`

  async function setSystems(systems = []) {
    const nextSystems = Array.isArray(systems) ? systems : []
    const fingerprint = `${nextSystems.length}:${nextSystems[0]?.id || ''}:${nextSystems[nextSystems.length - 1]?.id || ''}`
    if (fingerprint === systemsFingerprint) return
    systemsFingerprint = fingerprint
    const writeVersion = ++systemsWriteVersion
    galaxy.systems = nextSystems
    galaxy.byId = new Map(nextSystems.map((system) => [system.id, system]))
    const wrote = await writeSystemAttributes(
      nextSystems,
      () => disposed || writeVersion !== systemsWriteVersion,
    )
    if (!wrote || disposed || writeVersion !== systemsWriteVersion) return
    spatial = buildSpatialIndex(nextSystems)
    emitLabels()
  }

  let selectedId = null
  let hoveredId = null
  let raf = 0
  let frameCount = 0
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
    politicalMapVisible = !!visible
    plate.visible = politicalMapVisible
  }

  function setLocale(locale) {
    callbacks.locale = locale
    plate.userData.setLocale?.(locale)
  }

  async function rebuildPoliticalOwnership(nextGalaxy, { allowCache = false } = {}) {
    if (nextGalaxy) {
      galaxy.systems = nextGalaxy.systems
      galaxy.byId = nextGalaxy.byId
      galaxy.search = nextGalaxy.search
      if (nextGalaxy.polityByStem) galaxy.polityByStem = nextGalaxy.polityByStem
      if (nextGalaxy.polities) galaxy.polities = nextGalaxy.polities
      if (nextGalaxy.edgesDisplay) galaxy.edgesDisplay = nextGalaxy.edgesDisplay
      if (nextGalaxy.edgesCanon) galaxy.edgesCanon = nextGalaxy.edgesCanon
      if (nextGalaxy.meta) galaxy.meta = nextGalaxy.meta
      if (nextGalaxy.cacheRevision) galaxy.cacheRevision = nextGalaxy.cacheRevision
    }
    // First hydrate after warm/partial load may reuse a cached plate; ownership
    // edits must always regenerate and overwrite the cache.
    if (politicalPlateBuilt && allowCache) {
      emitLabels()
      return
    }
    await bootstrapPoliticalPlate({ allowCache })
    emitLabels()
  }

  function setSystemOwner(systemId, stem) {
    const system = galaxy.byId.get(systemId)
    if (!system || !stem || system.kind === 'well') return
    system.canonicalStem = system.canonicalStem || system.stem
    system.stem = stem
    rebuildPoliticalOwnership()
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
    const viewOffset = startPos.clone().sub(startTarget)
    if (viewOffset.lengthSq() < 1e-8) {
      viewOffset.copy(overviewPosition).sub(overviewTarget)
    }
    // Move towards the selected system along the current line of sight.
    // A fixed offset here would rotate the camera whenever a star is clicked.
    const endPos = target.clone().add(viewOffset.setLength(8.1))
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
    const dragThreshold = event.pointerType === 'touch' ? 14 : 6
    const dragged = Math.hypot(dx, dy) > dragThreshold
    pointerDown = null
    if (dragged) return

    const system = pickSystem(event.clientX, event.clientY)
    if (!system) return

    const now = performance.now()
    const doubleWindow = event.pointerType === 'touch' ? 520 : 350
    const isDouble = lastClickId === system.id && now - lastClickAt < doubleWindow
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

  let lastTileEmitAt = 0
  let lastTileSignature = ''

  function emitViewportTiles(force = false) {
    const grid = galaxy?.tileGrid
    if (!grid || typeof callbacks.onViewportTiles !== 'function') return
    const now = performance.now()
    if (!force && now - lastTileEmitAt < 120) return
    lastTileEmitAt = now
    const distanceGalaxy = cameraDistance() / GALAXY_SCALE
    const bounds = boundsFromCameraView(
      {
        x: controls.target.x / GALAXY_SCALE,
        y: controls.target.y / GALAXY_SCALE,
      },
      distanceGalaxy,
      grid.mapLim,
    )
    const tiles = tilesForBounds(
      bounds.minX,
      bounds.maxX,
      bounds.minY,
      bounds.maxY,
      grid.mapLim,
      grid.size,
    )
    const signature = tiles.map((tile) => tileKey(tile.tx, tile.ty)).join('|')
    if (!force && signature === lastTileSignature) return
    lastTileSignature = signature
    callbacks.onViewportTiles(tiles)
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
    emitViewportTiles()
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

  function onWheel() {
    focusTween = null
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
  emitViewportTiles(true)
  raf = requestAnimationFrame(frame)

  return {
    focusSystem,
    setSelected,
    setStorms,
    setPoliticalMap,
    setLocale,
    setSystemOwner,
    setSystems,
    setEdges,
    rebuildPoliticalOwnership,
    resetView,
    dispose,
  }
}

function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    if (typeof canvas.toBlob === 'function') {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob)
        else reject(new Error('Failed to encode political plate canvas'))
      }, 'image/png')
      return
    }
    try {
      const dataUrl = canvas.toDataURL('image/png')
      const bytes = atob(dataUrl.split(',')[1] || '')
      const arr = new Uint8Array(bytes.length)
      for (let i = 0; i < bytes.length; i += 1) arr[i] = bytes.charCodeAt(i)
      resolve(new Blob([arr], { type: 'image/png' }))
    } catch (err) {
      reject(err)
    }
  })
}

async function plateMeshFromCachedBlob(cached, mapLim, predecodedBitmap = null) {
  // ImageBitmap must be created with imageOrientation:'flipY' — Texture.flipY
  // is ignored for bitmaps. Prefer a warm-start predecoded bitmap when present.
  let bitmap = predecodedBitmap
  if (!bitmap && typeof createImageBitmap === 'function') {
    bitmap = await createImageBitmap(cached.blob, PLATE_BITMAP_OPTIONS)
  }
  if (bitmap) {
    const texture = new THREE.Texture(bitmap)
    texture.colorSpace = THREE.SRGBColorSpace
    texture.needsUpdate = true
    texture.generateMipmaps = false
    texture.minFilter = THREE.LinearFilter
    texture.magFilter = THREE.LinearFilter
    const mesh = makePlateMeshFromTexture(texture, mapLim)
    mesh.userData.labelAnchors = cached.labelAnchors || {}
    mesh.userData.territoryAreas = cached.territoryAreas || {}
    mesh.userData.labelMetrics = cached.labelMetrics || {}
    mesh.userData.rasterSize =
      cached.rasterSize || bitmap.width || 1
    mesh.userData.fromCache = true
    return mesh
  }
  const image = await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = URL.createObjectURL(cached.blob)
  })
  const canvas = document.createElement('canvas')
  canvas.width = image.width
  canvas.height = image.height
  canvas.getContext('2d').drawImage(image, 0, 0)
  const mesh = makePlateMeshFromCanvas(canvas, mapLim)
  mesh.userData.labelAnchors = cached.labelAnchors || {}
  mesh.userData.territoryAreas = cached.territoryAreas || {}
  mesh.userData.labelMetrics = cached.labelMetrics || {}
  mesh.userData.rasterSize = cached.rasterSize || canvas.width || 1
  mesh.userData.sourceCanvas = canvas
  mesh.userData.fromCache = true
  return mesh
}

async function createPoliticalPlate(
  galaxy,
  initialLocale = 'ru',
  { allowCache = true, onTerritoriesReady = null } = {},
) {
  const mapLim = mapLimitFor(galaxy)
  const group = new THREE.Group()
  const revision = galaxy?.cacheRevision || null
  const canUsePlateCache =
    allowCache && Boolean(revision) && !galaxy?.meta?.polityFiltered

  let territories = null
  if (canUsePlateCache) {
    const cached =
      galaxy?._cachedPoliticalPlate?.blob
        ? galaxy._cachedPoliticalPlate
        : await getCachedPoliticalPlate(revision)
    if (cached?.blob) {
      try {
        const predecoded = galaxy?._plateBitmapPromise
          ? await galaxy._plateBitmapPromise
          : null
        if (galaxy) {
          galaxy._plateBitmapPromise = null
          galaxy._cachedPoliticalPlate = cached
        }
        territories = await plateMeshFromCachedBlob(cached, mapLim, predecoded)
      } catch {
        territories = null
      }
    }
  }
  if (!territories) {
    territories = await createProceduralPoliticalPlate(galaxy)
    if (Boolean(revision) && !galaxy?.meta?.polityFiltered && territories.userData.sourceCanvas) {
      try {
        const blob = await canvasToBlob(territories.userData.sourceCanvas)
        void setCachedPoliticalPlate(revision, {
          blob,
          labelAnchors: territories.userData.labelAnchors,
          territoryAreas: territories.userData.territoryAreas,
          labelMetrics: territories.userData.labelMetrics,
          rasterSize: territories.userData.rasterSize,
          mapLim,
        })
      } catch {
        // Keep the live plate even if persistence fails.
      }
    }
  }
  territories.renderOrder = -90
  group.add(territories)
  group.userData.fromCache = Boolean(territories.userData.fromCache)
  // Let the scene show borders before the heavy label atlas is built.
  onTerritoriesReady?.(group)
  await yieldToBrowser()

  const presentStems = new Set(
    (galaxy.systems || []).map((system) => system.stem).filter(Boolean),
  )
  const labelPolities = (galaxy.polities || []).filter((polity) =>
    presentStems.has(polity.stem),
  )
  // Full-map seed anchors place every polity name across the disk. On a zoomed
  // polity filter those distant glyphs become huge blurred streaks — only use
  // seeds for the complete catalog view.
  const seedAnchors = galaxy?.meta?.polityFiltered ? {} : polityLabelAnchors
  const anchors = resolvePolityLabelAnchors(
    territories.userData.labelAnchors || {},
    centroidsFromSystems(galaxy, mapLim),
    seedAnchors,
    labelPolities,
  )
  const labels = createPolityLabelMesh(
    { ...galaxy, polities: labelPolities },
    initialLocale,
    anchors,
    mapLim,
    territories.userData.territoryAreas || {},
    territories.userData.labelMetrics || {},
    territories.userData.rasterSize || 1,
    Boolean(galaxy?.meta?.polityFiltered),
  )
  group.add(labels)
  group.userData.setLocale = (locale) => labels.userData.setLocale(locale)
  group.userData.labelAnchors = anchors
  return group
}

function labelLineVariants(text, maxLines = 4) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return []
  if (words.length === 1) return [words]
  const variants = []
  const breakCount = words.length - 1
  for (let mask = 0; mask < 2 ** breakCount; mask += 1) {
    const lines = []
    let line = words[0]
    for (let index = 0; index < breakCount; index += 1) {
      if (mask & (1 << index)) {
        lines.push(line)
        line = words[index + 1]
      } else {
        line += ` ${words[index + 1]}`
      }
    }
    lines.push(line)
    if (lines.length <= maxLines) variants.push(lines)
  }
  return variants
}

function createPolityLabelMesh(
  galaxy,
  initialLocale = 'ru',
  anchors = polityLabelAnchors,
  mapLim = mapLimitFor(galaxy),
  territoryAreas = {},
  labelMetrics = {},
  territoryRasterSize = 1,
  polityFiltered = false,
) {
  const size = 2048
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const largestTerritoryArea = Math.max(0, ...Object.values(territoryAreas))
  texture.generateMipmaps = false
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter

  const draw = (locale) => {
    context.clearRect(0, 0, size, size)
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.lineJoin = 'round'
    for (const polity of galaxy.polities || []) {
      const anchor = anchors[polity.stem]
      if (!anchor) continue
      const variants = labelLineVariants(
        locale === 'en' ? polity.nameEn : polity.nameRu,
      )
      if (!variants.length) continue
      const suzerain = polity.kind === 'suzerain'
      // Filtered views zoom in; bump the glyph so one polity name stays sharp
      // instead of a few texture pixels smeared across the viewport.
      const preferredFontSize = polityFiltered
        ? Math.max(
            28,
            polityLabelFontSize(
              territoryAreas[polity.stem] || largestTerritoryArea || 1,
              Math.max(largestTerritoryArea, territoryAreas[polity.stem] || 1),
              28,
              48,
            ),
          )
        : polityLabelFontSize(
            territoryAreas[polity.stem] || 0,
            largestTerritoryArea,
          )
      const weight = suzerain ? 700 : 600
      const fontFamily = '"Arial Narrow", "Roboto Condensed", "Segoe UI", Arial, sans-serif'
      context.font = `${weight} 100px ${fontFamily}`
      const clearanceCanvasPx =
        ((labelMetrics[polity.stem]?.clearancePx || 0) / territoryRasterSize) * size
      let lines = variants[0]
      let fontSize = 0
      for (const candidate of variants) {
        const widthPerFontPx =
          Math.max(...candidate.map((line) => context.measureText(line).width)) / 100
        const candidateSize = fitLabelFontToClearance(
          preferredFontSize,
          clearanceCanvasPx,
          widthPerFontPx,
          candidate.length,
          0,
        )
        if (
          candidateSize > fontSize + 0.05 ||
          (Math.abs(candidateSize - fontSize) <= 0.05 &&
            candidate.length < lines.length)
        ) {
          lines = candidate
          fontSize = candidateSize
        }
      }
      fontSize = Math.max(3, fontSize)
      const lineHeight = fontSize * 1.12
      const x = anchor[0] * size
      const y = anchor[1] * size
      context.font = `${weight} ${fontSize}px ${fontFamily}`
      context.strokeStyle = 'rgba(0, 0, 0, 0.92)'
      context.lineWidth = Math.max(0.55, Math.min(3, fontSize * 0.16))
      context.fillStyle = '#ffffff'
      lines.forEach((line, index) => {
        const lineY = y + (index - (lines.length - 1) / 2) * lineHeight
        context.strokeText(line, x, lineY)
        context.fillText(line, x, lineY)
      })
    }
    texture.needsUpdate = true
  }

  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    fog: false,
    side: THREE.DoubleSide,
  })
  const span = GALAXY_SCALE * 2 * mapLim
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(span, span), material)
  mesh.position.z = -0.79
  mesh.renderOrder = -80
  mesh.raycast = () => {}
  mesh.userData.setLocale = draw
  draw(initialLocale)
  return mesh
}

function createBasePlate(mapLim = DEFAULT_MAP_LIM) {
  return loadTexture(basePlateUrl(), { crisp: true }).then((texture) => {
    const mesh = makePlateMeshFromTexture(texture, mapLim)
    mesh.position.z = -0.82
    mesh.renderOrder = -100
    return mesh
  })
}

function makePlateMeshFromTexture(texture, mapLim = DEFAULT_MAP_LIM) {
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    fog: false,
    side: THREE.DoubleSide,
  })
  const span = GALAXY_SCALE * 2 * mapLim
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(span, span), material)
  mesh.position.z = -0.8
  mesh.raycast = () => {}
  return mesh
}

// Kept as an offline-capable splitter for future independent border styling.
// Runtime political-map toggling hides the complete plate and does not need it.
function makeSplitPlateMeshFromTexture(texture, mapLim = DEFAULT_MAP_LIM) {
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
  const span = GALAXY_SCALE * 2 * mapLim
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

function yieldToBrowser() {
  // Prefer scheduler.yield when available so star chunks and territory raster
  // can interleave without waiting a full animation frame each slice.
  if (typeof scheduler !== 'undefined' && typeof scheduler.yield === 'function') {
    return scheduler.yield()
  }
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => resolve())
      return
    }
    setTimeout(resolve, 0)
  })
}

async function createProceduralPoliticalPlate(galaxy) {
  const mapLim = mapLimitFor(galaxy)
  const centralDiskR = Number(galaxy?.meta?.centralDiskR) || 1.02
  const size = mapLim > DEFAULT_MAP_LIM ? 1200 : 900
  const canvas2d = document.createElement('canvas')
  canvas2d.width = size
  canvas2d.height = size
  const ctx = canvas2d.getContext('2d')

  const cx = size / 2
  const cy = size / 2
  const lim = mapLim
  // Fixed claim radius around every host system (stars, black holes, junctions).
  // Large enough to keep interior cells contiguous (NN ~0.02–0.04), small enough
  // that rim fill hugs the constellation instead of the circular galaxy disk.
  const claimR = 0.034
  const frontierClaimMin = 0.07
  const frontierClaimMax = 0.17
  const neutralClaimR = 0.14
  // Systems this close to the Axis Well use full Voronoi cells so claim-radius
  // circles do not leave arc-shaped traces beside the well.
  const wellRingR = 0.2
  const centerZoneR = 0.14

  const isUnnamedNeutralStar = (system) =>
    system.kind === 'star' &&
    !system.stem &&
    !system.token?.trim() &&
    !system.nameEn?.trim() &&
    !system.nameRu?.trim()
  const owned = galaxy.systems.filter(
    (system) =>
      system.kind === 'well' ||
      isUnnamedNeutralStar(system) ||
      (system.stem &&
        system.territoryAnchor !== false &&
        (system.kind === 'star' ||
          system.kind === 'black_hole' ||
          system.kind === 'junction')),
  )
  if (!owned.length) {
    const mesh = makePlateMeshFromCanvas(canvas2d, mapLim)
    mesh.userData.labelAnchors = {}
    mesh.userData.territoryAreas = {}
    mesh.userData.labelMetrics = {}
    mesh.userData.rasterSize = size
    return mesh
  }

  const neutralOwned = owned.filter(isUnnamedNeutralStar)
  const politicalOwned = owned.filter((system) => !isUnnamedNeutralStar(system))
  // Only systems that can paint the legacy disk belong in the central spatial
  // index. A polity filter with a few rim stars otherwise forces every central
  // pixel to expand the NN search across the whole map and freezes the scene.
  const wellSystem = owned.find((system) => system.kind === 'well') || null
  const centralInfluenceR =
    centralDiskR + Math.max(claimR, frontierClaimMax, neutralClaimR)
  const centralSeed = []
  if (wellSystem) centralSeed.push(wellSystem)
  for (const system of politicalOwned) {
    if (Math.hypot(system.x, system.y) <= centralInfluenceR) centralSeed.push(system)
  }
  for (const system of neutralOwned) {
    if (Math.hypot(system.x, system.y) <= centralInfluenceR) centralSeed.push(system)
  }
  // Polity filters (and any other catalog subset) must not run full-disk
  // nearest-neighbor fill: sparse in-disk seeds make every central pixel expand
  // the search and freeze the tab. Bounded claim paint is enough for those views.
  const catalogSystemCount = Number(galaxy?.meta?.systemCount) || owned.length
  const sparsePolitical =
    Boolean(galaxy?.meta?.polityFiltered) ||
    (owned.length > 0 && owned.length < catalogSystemCount * 0.9) ||
    (!wellSystem && politicalOwned.length > 0 && politicalOwned.length < 500)
  const centralSpatial =
    !sparsePolitical && centralSeed.length
      ? buildSpatialIndex([
          ...new Map(centralSeed.map((system) => [system.id, system])).values(),
        ])
      : null
  const frontierOwned = politicalOwned.filter((system) =>
    system.id.startsWith('frontier:'),
  )
  const frontierSpatial = frontierOwned.length ? buildSpatialIndex(frontierOwned) : null
  const frontierByStem = new Map()
  for (const system of frontierOwned) {
    if (!frontierByStem.has(system.stem)) frontierByStem.set(system.stem, [])
    frontierByStem.get(system.stem).push(system)
  }
  const frontierClaimByStem = new Map()
  for (const [stem, systems] of frontierByStem) {
    let widestNearestGap = 0
    if (systems.length > 1) {
      for (const system of systems) {
        const nearestGap = Math.min(
          ...systems
            .filter((other) => other.id !== system.id)
            .map((other) => Math.hypot(system.x - other.x, system.y - other.y)),
        )
        widestNearestGap = Math.max(widestNearestGap, nearestGap)
      }
    }
    frontierClaimByStem.set(
      stem,
      THREE.MathUtils.clamp(
        widestNearestGap * 0.58 + 0.012,
        frontierClaimMin,
        frontierClaimMax,
      ),
    )
  }
  const wellX = wellSystem?.x || 0
  const wellY = wellSystem?.y || 0

  const image = ctx.createImageData(size, size)
  const data = image.data
  const owner = new Int32Array(size * size)
  owner.fill(-1)
  const territoryAreas = {}

  const systemIndex = new Map(owned.map((system, index) => [system.id, index]))
  const systemMeta = owned.map((system) => {
    const isWell = system.kind === 'well'
    const isUnnamedNeutral = isUnnamedNeutralStar(system)
    const neutral = isWell || isUnnamedNeutral
    const polity = !neutral && system.stem ? galaxy.polityByStem.get(system.stem) : null
    const color = new THREE.Color(neutral ? '#667080' : polity?.color || '#7aa0c8')
    return {
      polityStem: neutral ? '__neutral__' : system.stem,
      isWell,
      isNeutral: neutral,
      isUnnamedNeutral,
      claimRadius:
        neutral && system.id.startsWith('frontier:')
          ? neutralClaimR
          : system.id.startsWith('frontier:')
            ? frontierClaimByStem.get(system.stem) || frontierClaimMin
            : claimR,
      r: Math.round(color.r * 255),
      g: Math.round(color.g * 255),
      b: Math.round(color.b * 255),
    }
  })

  // Precompute which systems sit in the well ring (full Voronoi, no claim cut).
  const fullVoronoi = owned.map((system) => {
    if (system.kind === 'well') return true
    if (!wellSystem) return false
    return Math.hypot(system.x - wellX, system.y - wellY) <= wellRingR
  })

  if (centralSpatial) {
    for (let py = 0; py < size; py += 1) {
      if (py > 0 && py % 32 === 0) await yieldToBrowser()
      for (let px = 0; px < size; px += 1) {
        const gx = ((px + 0.5) / size) * 2 * lim - lim
        const gy = -(((py + 0.5) / size) * 2 * lim - lim)
        const insideCentralDisk = Math.hypot(gx, gy) <= centralDiskR
        if (!insideCentralDisk) continue
        // The expanded map is mostly empty. Searching every increasingly large
        // grid ring for each void pixel blocks the browser for minutes. Central
        // territory remains continuous. Bounded arm claims are rasterized
        // directly after this pass instead of querying every empty outer pixel.
        let nearest = centralSpatial.queryNearestAny(gx, gy)
        let dist = nearest ? Math.hypot(nearest.x - gx, nearest.y - gy) : Infinity
        let idx = nearest ? systemIndex.get(nearest.id) : null
        let nearestIsWell = nearest?.kind === 'well'
        let useVoronoi = idx != null && (nearestIsWell || fullVoronoi[idx])
        let effectiveClaimR = idx != null ? systemMeta[idx].claimRadius : 0
        // At an arm root, the nearest legacy-disk system can be just outside its
        // small claim while a slightly farther frontier system still legitimately
        // covers the pixel. Fall back to that frontier claim to stitch the arm to
        // the old disk without globally inflating legacy territories.
        if (
          insideCentralDisk &&
          !useVoronoi &&
          dist > effectiveClaimR &&
          frontierSpatial
        ) {
          const frontierNearest = frontierSpatial.queryNearest(
            gx,
            gy,
            frontierClaimMax,
          )
          if (frontierNearest) {
            const frontierIdx = systemIndex.get(frontierNearest.id)
            const frontierDist = Math.hypot(
              frontierNearest.x - gx,
              frontierNearest.y - gy,
            )
            const frontierClaimR = systemMeta[frontierIdx]?.claimRadius || 0
            if (frontierIdx != null && frontierDist <= frontierClaimR) {
              nearest = frontierNearest
              idx = frontierIdx
              dist = frontierDist
              nearestIsWell = false
              useVoronoi = fullVoronoi[idx]
              effectiveClaimR = frontierClaimR
            }
          }
        }

        if (!nearest || idx == null) continue
        if (!useVoronoi && dist > effectiveClaimR) continue

        const i = py * size + px
        owner[i] = idx
        const meta = systemMeta[idx]
        let fade = 1
        if (!useVoronoi) {
          const fadeWidth = effectiveClaimR * 0.22
          fade = Math.max(
            0.4,
            Math.min(1, (effectiveClaimR - dist) / fadeWidth + 0.4),
          )
        }
        const o = i * 4
        data[o] = meta.r
        data[o + 1] = meta.g
        data[o + 2] = meta.b
        data[o + 3] = Math.round(
          (meta.isUnnamedNeutral ? 120 : meta.isNeutral ? 100 : 120) * fade,
        )
      }
    }
  }

  const paintBoundedClaims = async (systems, claimRadiusOverride = null) => {
    const nearestDistance = new Float32Array(size * size)
    nearestDistance.fill(Infinity)
    for (let systemNumber = 0; systemNumber < systems.length; systemNumber += 1) {
      if (systemNumber > 0 && systemNumber % 512 === 0) await yieldToBrowser()
      const system = systems[systemNumber]
      const idx = systemIndex.get(system.id)
      if (idx == null) continue
      const meta = systemMeta[idx]
      const claimRadius = claimRadiusOverride || meta.claimRadius
      const centerPx = ((system.x + lim) / (2 * lim)) * size - 0.5
      const centerPy = ((lim - system.y) / (2 * lim)) * size - 0.5
      const pixelRadius = (claimRadius / (2 * lim)) * size
      const minPx = Math.max(0, Math.floor(centerPx - pixelRadius))
      const maxPx = Math.min(size - 1, Math.ceil(centerPx + pixelRadius))
      const minPy = Math.max(0, Math.floor(centerPy - pixelRadius))
      const maxPy = Math.min(size - 1, Math.ceil(centerPy + pixelRadius))

      for (let py = minPy; py <= maxPy; py += 1) {
        for (let px = minPx; px <= maxPx; px += 1) {
          const dx = ((px - centerPx) / size) * 2 * lim
          const dy = ((py - centerPy) / size) * 2 * lim
          const dist = Math.hypot(dx, dy)
          if (dist > claimRadius) continue
          const i = py * size + px
          // Preserve the continuous central-disk result. Among bounded claims,
          // retain the nearest system so neighboring polity borders stay exact.
          if (owner[i] >= 0 && nearestDistance[i] === Infinity) continue
          if (dist >= nearestDistance[i]) continue
          nearestDistance[i] = dist
          owner[i] = idx
          const fadeWidth = claimRadius * 0.22
          const fade = Math.max(
            0.4,
            Math.min(1, (claimRadius - dist) / fadeWidth + 0.4),
          )
          const o = i * 4
          data[o] = meta.r
          data[o + 1] = meta.g
          data[o + 2] = meta.b
          data[o + 3] = Math.round(
            (meta.isUnnamedNeutral ? 120 : meta.isNeutral ? 100 : 120) * fade,
          )
        }
      }
    }
  }

  // One shared bounded Voronoi pass gives the 21 frontier polities and neutral
  // stars equal cells. Reassigning a star therefore recolors its existing cell
  // instead of layering a second claim over the previous territory.
  // Sparse filters paint every remaining political system the same way so the
  // polity still gets a visible claim without the central-disk NN pass.
  await paintBoundedClaims(
    sparsePolitical
      ? [...politicalOwned, ...neutralOwned]
      : [...frontierOwned, ...neutralOwned],
    frontierClaimMax,
  )

  // Cream outline: single-sided between polities, around the Axis Well, and against void.
  // Void-cream inside the well ring stays suppressed (kills leftover claim arcs).
  for (let py = 0; py < size; py += 1) {
    if (py > 0 && py % 48 === 0) await yieldToBrowser()
    for (let px = 0; px < size; px += 1) {
      const i = py * size + px
      const current = owner[i]
      if (current < 0) continue
      const currentMeta = systemMeta[current]
      const currentStem = currentMeta.polityStem
      if (currentMeta.isWell) continue
      territoryAreas[currentStem] = (territoryAreas[currentStem] || 0) + 1

      const neighborIndexes = []
      if (px > 0) neighborIndexes.push(i - 1)
      if (px + 1 < size) neighborIndexes.push(i + 1)
      if (py > 0) neighborIndexes.push(i - size)
      if (py + 1 < size) neighborIndexes.push(i + size)

      const gx = ((px + 0.5) / size) * 2 * lim - lim
      const gy = -(((py + 0.5) / size) * 2 * lim - lim)
      const distToWell = Math.hypot(gx - wellX, gy - wellY)

      let border = false
      for (const ni of neighborIndexes) {
        const other = owner[ni]
        if (other === current) continue
        if (other < 0) {
          // Suppress void outlines near the well — those were the leftover claim arcs.
          if (distToWell <= wellRingR + claimR) continue
          if (Math.hypot(gx, gy) <= centerZoneR) continue
          border = true
          break
        }
        const otherMeta = systemMeta[other]
        if (otherMeta.polityStem === currentStem) continue
        // Single cream ring on the polity side of the Axis Well.
        if (otherMeta.isWell) {
          border = true
          break
        }
        if (currentStem < otherMeta.polityStem) {
          border = true
          break
        }
      }
      if (!border) continue
      const o = i * 4
      data[o] = 242
      data[o + 1] = 235
      data[o + 2] = 209
      data[o + 3] = 200
    }
  }

  ctx.putImageData(image, 0, 0)
  const mesh = makePlateMeshFromCanvas(canvas2d, mapLim)
  const labelMetrics = {}
  mesh.userData.labelAnchors = centroidsFromOwnerRaster(
    owner,
    systemMeta,
    size,
    labelMetrics,
  )
  mesh.userData.territoryAreas = territoryAreas
  mesh.userData.labelMetrics = labelMetrics
  mesh.userData.rasterSize = size
  mesh.userData.sourceCanvas = canvas2d
  return mesh
}

function makePlateMeshFromCanvas(canvas2d, mapLim = DEFAULT_MAP_LIM) {
  const texture = new THREE.CanvasTexture(canvas2d)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return makePlateMeshFromTexture(texture, mapLim)
}
