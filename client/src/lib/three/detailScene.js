import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import {
  featureModelPath,
  planetModelPath,
  planetPreviewPath,
  planetTypeArtPath,
  resolveFeatureKey,
  resolvePlanetTypeKey,
  resolveStarTypeKey,
  starColor,
  starFallbackKey,
  starPreviewPath,
  starTypeArtPath,
} from '../galaxy/modelCatalog.js'

const gltfLoader = new GLTFLoader()
gltfLoader.setCrossOrigin('anonymous')
const textureLoader = new THREE.TextureLoader()
textureLoader.setCrossOrigin('anonymous')
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
      (err) => {
        console.warn('GLB load failed', url, err)
        resolve(null)
      },
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

function addBeltDust(group, inner, outer) {
  const uniforms = { uTime: { value: 0 } }
  const dust = new THREE.Mesh(
    new THREE.RingGeometry(inner, outer, 192, 8),
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: `
        varying vec2 vBelt;
        void main() {
          vBelt = position.xy;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        varying vec2 vBelt;
        float hash21(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
        }
        float smoothNoise(vec2 p) {
          vec2 cell = floor(p);
          vec2 local = fract(p);
          local = local * local * (3.0 - 2.0 * local);
          float a = hash21(cell);
          float b = hash21(cell + vec2(1.0, 0.0));
          float c = hash21(cell + vec2(0.0, 1.0));
          float d = hash21(cell + vec2(1.0, 1.0));
          return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
        }
        void main() {
          vec2 drift = vBelt + vec2(uTime * 0.003, -uTime * 0.002);
          float coarse = smoothNoise(drift * 10.0);
          float fine = smoothNoise(drift * 32.0 + 19.7);
          float flecks = smoothstep(0.72, 0.94, coarse * fine);
          float alpha = 0.018 + flecks * 0.14;
          vec3 color = mix(vec3(0.34, 0.29, 0.23), vec3(0.76, 0.68, 0.52), flecks);
          gl_FragColor = vec4(color, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    }),
  )
  dust.rotation.x = -Math.PI / 2
  dust.position.y = 0.015
  dust.raycast = () => {}
  group.add(dust)

  const particleCount = Math.min(900, Math.max(260, Math.round((outer - inner) * 520)))
  const particlePositions = new Float32Array(particleCount * 3)
  let seed = 0x9e3779b9
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
    return seed / 0x100000000
  }
  for (let index = 0; index < particleCount; index += 1) {
    const angle = random() * Math.PI * 2
    const radial = Math.sqrt(inner * inner + random() * (outer * outer - inner * inner))
    particlePositions[index * 3] = Math.cos(angle) * radial
    particlePositions[index * 3 + 1] = (random() - 0.5) * 0.13
    particlePositions[index * 3 + 2] = Math.sin(angle) * radial
  }
  const particleGeometry = new THREE.BufferGeometry()
  particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3))
  const particles = new THREE.Points(
    particleGeometry,
    new THREE.ShaderMaterial({
      vertexShader: `
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = clamp(22.0 / max(-mv.z, 1.0), 1.15, 3.2);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        void main() {
          float distanceToCenter = length(gl_PointCoord - vec2(0.5));
          if (distanceToCenter > 0.5) discard;
          float alpha = (1.0 - smoothstep(0.18, 0.5, distanceToCenter)) * 0.52;
          gl_FragColor = vec4(0.78, 0.72, 0.62, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  )
  particles.raycast = () => {}
  group.add(particles)

  group.userData.updateVisual = (time) => {
    uniforms.uTime.value = time
  }
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
    addBeltDust(group, beltInner, beltOuter)
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
  group.userData.beltSpin = { mesh: group, speed: 0.035 / Math.sqrt(Math.max(mid, 1)) }
  addBeltDust(group, minInner, minInner + 0.7)
  return group
}

function createBlackHoleVisual(radius, kind) {
  const group = new THREE.Group()
  const isWell = kind === 'well'
  const hot = new THREE.Color(isWell ? 0xffc27a : 0xff9a52)
  const warm = new THREE.Color(isWell ? 0xff6ea8 : 0xff3f70)

  const core = new THREE.Mesh(
    new THREE.SphereGeometry(radius * 0.72, 64, 48),
    new THREE.MeshBasicMaterial({ color: 0x000000 }),
  )
  core.renderOrder = 3

  const diskUniforms = {
    uTime: { value: 0 },
    uHot: { value: hot },
    uWarm: { value: warm },
  }
  const disk = new THREE.Mesh(
    new THREE.RingGeometry(radius * 0.76, radius * 2.35, 192, 12),
    new THREE.ShaderMaterial({
      uniforms: diskUniforms,
      vertexShader: `
        varying vec2 vDisk;
        void main() {
          vDisk = position.xy;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform vec3 uHot;
        uniform vec3 uWarm;
        varying vec2 vDisk;
        void main() {
          float r = length(vDisk) / ${radius.toFixed(6)};
          float angle = atan(vDisk.y, vDisk.x);
          float inner = smoothstep(0.76, 0.84, r);
          float outer = 1.0 - smoothstep(1.65, 2.35, r);
          float diskMask = inner * outer;
          float spiral = 0.5 + 0.5 * sin(angle * 7.0 - uTime * 1.7 + r * 13.0);
          float grain = 0.5 + 0.5 * sin(angle * 19.0 + r * 31.0 + uTime * 0.8);
          float photon = exp(-pow((r - 0.84) / 0.075, 2.0));
          float flow = 0.32 + spiral * 0.42 + grain * 0.16;
          float alpha = diskMask * flow + photon * 0.72;
          vec3 color = mix(uWarm, uHot, clamp(photon + (2.35 - r) * 0.42, 0.0, 1.0));
          color *= 0.62 + photon * 1.5 + spiral * 0.28;
          if (alpha < 0.015) discard;
          gl_FragColor = vec4(color, clamp(alpha, 0.0, 0.94));
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    }),
  )
  disk.rotation.x = -Math.PI / 2
  disk.scale.z = 0.22
  disk.renderOrder = 1

  const lensUniforms = {
    uTime: { value: 0 },
    uHot: { value: hot },
    uWarm: { value: warm },
  }
  const lens = new THREE.Mesh(
    new THREE.PlaneGeometry(radius * 4.5, radius * 4.5),
    new THREE.ShaderMaterial({
      uniforms: lensUniforms,
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv * 2.0 - 1.0;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform vec3 uHot;
        uniform vec3 uWarm;
        varying vec2 vUv;
        void main() {
          float r = length(vUv);
          float angle = atan(vUv.y, vUv.x);
          float photon = exp(-pow((r - 0.345) / 0.018, 2.0));
          float lensArc = exp(-pow((r - 0.43) / 0.065, 2.0));
          lensArc *= 0.45 + 0.55 * pow(abs(sin(angle)), 2.0);
          float corona = exp(-r * 4.6) * smoothstep(0.30, 0.39, r);
          float shimmer = 0.88 + 0.12 * sin(angle * 11.0 + uTime * 1.25);
          float alpha = (photon * 0.92 + lensArc * 0.32 + corona * 0.18) * shimmer;
          vec3 color = mix(uWarm, uHot, clamp(photon + corona, 0.0, 1.0));
          if (alpha < 0.008) discard;
          gl_FragColor = vec4(color, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    }),
  )
  lens.renderOrder = 2
  lens.raycast = () => {}

  group.add(disk, lens, core)
  group.userData.disableSpin = true
  group.userData.updateVisual = (time, camera) => {
    diskUniforms.uTime.value = time
    lensUniforms.uTime.value = time
    lens.quaternion.copy(camera.quaternion)
  }
  return group
}

function planetAtmosphereColor(key) {
  if (key === 'toxic') return 0x91d86b
  if (key === 'molten') return 0xff6a32
  if (key === 'desert' || key === 'arid' || key === 'savanna') return 0xffc078
  if (key === 'frozen' || key === 'arctic' || key === 'alpine') return 0xa9dcff
  if (key === 'gas_giant') return 0xe4b982
  if (key === 'ecumenopolis') return 0x7ac8ff
  return 0x75bfff
}

function addSurfaceEffects(group, surface, radius, key, isStarLike, lightColor = 0xffffff) {
  const cloudTypes = new Set([
    'continental',
    'ocean',
    'tropical',
    'gaia',
    'savanna',
    'arid',
    'tundra',
    'alpine',
    'gas_giant',
    'toxic',
  ])
  const oldMaterial = surface.material
  const uniforms = {
    uMap: { value: oldMaterial.map || null },
    uHasMap: { value: oldMaterial.map ? 1 : 0 },
    uTime: { value: 0 },
    uStar: { value: isStarLike ? 1 : 0 },
    uClouds: { value: !isStarLike && cloudTypes.has(key) ? 1 : 0 },
    uGas: { value: key === 'gas_giant' ? 1 : 0 },
    uBase: {
      value: new THREE.Color(isStarLike ? starColor(key) : oldMaterial.color || 0xffffff),
    },
    uAtmosphere: { value: new THREE.Color(planetAtmosphereColor(key)) },
    uLightColor: { value: new THREE.Color(lightColor) },
  }

  surface.material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: `
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vWorldPosition;
      varying vec3 vWorldNormal;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vNormal = normalize(normalMatrix * normal);
        vView = normalize(-mv.xyz);
        vWorldPosition = (modelMatrix * vec4(position, 1.0)).xyz;
        vWorldNormal = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      uniform sampler2D uMap;
      uniform float uHasMap;
      uniform float uTime;
      uniform float uStar;
      uniform float uClouds;
      uniform float uGas;
      uniform vec3 uBase;
      uniform vec3 uAtmosphere;
      uniform vec3 uLightColor;
      varying vec2 vUv;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vWorldPosition;
      varying vec3 vWorldNormal;
      void main() {
        // Type art is a square portrait with black space and baked lighting,
        // not an equirectangular map. Sample only the central surface.
        vec2 textureUv = vec2(0.255) + vUv * 0.49;
        vec3 texel = texture2D(uMap, textureUv).rgb;
        float bakedLuma = dot(texel, vec3(0.2126, 0.7152, 0.0722));
        float exposureCorrection = clamp(0.58 / max(bakedLuma, 0.08), 0.72, 1.65);
        // Suppress broad portrait lighting on planets while retaining local
        // color/detail. Stars stay fully emissive.
        texel *= mix(exposureCorrection, 1.0, uStar);
        // Star source files are portraits (and may contain two stars or a tiny
        // neutron star), so they cannot serve as spherical maps. Stars use
        // their canonical class color plus procedural plasma; planets retain
        // the sampled surface art.
        float useSurfaceMap = uHasMap * (1.0 - uStar);
        vec3 base = mix(uBase, texel, useSurfaceMap);
        float fresnel = pow(1.0 - max(dot(vNormal, vView), 0.0), 2.4);
        float plasmaA = 0.5 + 0.5 * sin(vUv.x * 52.0 + vUv.y * 21.0 - uTime * 0.9);
        float plasmaB = 0.5 + 0.5 * sin(vUv.y * 73.0 - vUv.x * 17.0 + uTime * 0.55);
        float plasma = plasmaA * plasmaB;

        float bands = 0.5 + 0.5 * sin(vUv.y * 82.0 + sin(vUv.x * 18.0 + uTime * 0.16) * 2.2);
        float cells = 0.5 + 0.5 * sin(vUv.x * 41.0 - vUv.y * 29.0 + uTime * 0.22);
        float cloudPattern = mix(bands * cells, bands, uGas);
        float cloud = smoothstep(0.60, 0.84, cloudPattern) * uClouds;

        vec3 lightDirection = normalize(-vWorldPosition);
        float starFacing = dot(normalize(vWorldNormal), lightDirection);
        float daylight = smoothstep(-0.08, 0.16, starFacing);
        float diffuse = max(starFacing, 0.0);
        vec3 planetColor = mix(base, vec3(0.96), cloud * 0.22);
        vec3 nightSide = planetColor * 0.025;
        vec3 daySide = planetColor * (0.42 + diffuse * 1.18) * mix(vec3(1.0), uLightColor, 0.48);
        planetColor = mix(nightSide, daySide, daylight);
        planetColor += uAtmosphere * fresnel * (0.045 + daylight * 0.235);

        // Preserve the sampled star hue: the shader changes only its
        // brightness/structure, never paints a separate corona color.
        vec3 starColorOut = base * (0.88 + plasma * 0.64 + fresnel * 0.68);
        vec3 color = mix(planetColor, starColorOut, uStar);
        gl_FragColor = vec4(color, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
    transparent: false,
    depthWrite: true,
  })
  oldMaterial.dispose()

  let corona = null
  let coronaUniforms = null
  if (isStarLike) {
    coronaUniforms = {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color(starColor(key)) },
    }
    corona = new THREE.Mesh(
      new THREE.PlaneGeometry(radius * 4.2, radius * 4.2),
      new THREE.ShaderMaterial({
        uniforms: coronaUniforms,
        vertexShader: `
          varying vec2 vUv;
          void main() {
            vUv = uv * 2.0 - 1.0;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          uniform float uTime;
          uniform vec3 uColor;
          varying vec2 vUv;
          void main() {
            float r = length(vUv);
            float angle = atan(vUv.y, vUv.x);
            float outside = smoothstep(0.31, 0.38, r);
            float fade = 1.0 - smoothstep(0.38, 1.0, r);
            float broadRays = 0.5 + 0.5 * sin(angle * 17.0 - uTime * 0.16);
            float middleRays = 0.5 + 0.5 * sin(angle * 31.0 + uTime * 0.31);
            float fineRays = 0.5 + 0.5 * sin(angle * 53.0 - uTime * 0.22);
            float hairRays = 0.5 + 0.5 * sin(angle * 79.0 + uTime * 0.12);
            float microA = 0.5 + 0.5 * sin(angle * 521.0 + uTime * 0.43);
            float microB = 0.5 + 0.5 * sin(angle * 997.0 - uTime * 0.29);
            float microC = 0.5 + 0.5 * sin(angle * 1597.0 + uTime * 0.17);
            float microRays = (microA + microB + microC) / 3.0;
            float denseRays = broadRays * 0.16 + middleRays * 0.18 + fineRays * 0.18 + hairRays * 0.14 + microRays * 0.34;
            float corona = exp(-r * 3.5) * outside;
            float alpha = outside * fade * (0.20 + denseRays * 0.52);
            alpha += corona * 0.46;
            if (alpha < 0.006) discard;
            gl_FragColor = vec4(uColor * (0.90 + denseRays * 0.72), alpha);
          }
        `,
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
      }),
    )
    corona.renderOrder = 2
    corona.raycast = () => {}
    group.add(corona)
  }

  group.userData.updateVisual = (time, camera) => {
    uniforms.uTime.value = time
    if (coronaUniforms) coronaUniforms.uTime.value = time
    if (corona) corona.quaternion.copy(camera.quaternion)
  }
}

async function createTexturedSphere({ typeKey, radius, kind, lightColor }) {
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

  const group = new THREE.Group()
  const surface = new THREE.Mesh(
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
  surface.castShadow = !isStarLike
  surface.receiveShadow = !isStarLike
  group.add(surface)
  addSurfaceEffects(group, surface, radius, key, isStarLike, lightColor)
  return group
}

async function createMultipleStarVisual(radius, lightColor, count) {
  const group = new THREE.Group()
  const componentRadius = radius * (count === 3 ? 0.52 : 0.64)
  const separation = radius * (count === 3 ? 0.78 : 0.72)
  const stars = await Promise.all(
    Array.from({ length: count }, (_, index) => createTexturedSphere({
      typeKey: 'class_g',
      radius: componentRadius * (1.0 - index * 0.035),
      kind: 'star',
      lightColor,
    })),
  )
  group.add(...stars)
  group.userData.disableSpin = true
  group.userData.updateVisual = (time, camera) => {
    const angle = time * 0.22
    stars.forEach((star, index) => {
      const componentAngle = angle + (index / count) * Math.PI * 2
      star.position.set(
        Math.cos(componentAngle) * separation,
        count === 3 && index === 2 ? radius * 0.1 : 0,
        Math.sin(componentAngle) * separation,
      )
      star.userData.updateVisual?.(time, camera)
    })
  }
  return group
}

async function createBodyMesh({ kind, typeKey, radius, lightColor }) {
  const isStarLike = kind === 'star' || kind === 'black_hole' || kind === 'well'
  const key = isStarLike ? resolveStarTypeKey(typeKey, kind) : resolvePlanetTypeKey(typeKey)

  // Black holes are layered shader effects; the old GLB baked its rings into
  // a rotating mesh and looked flat from oblique camera angles.
  if (kind === 'black_hole' || kind === 'well') return createBlackHoleVisual(radius, kind)
  if (kind === 'star' && key === 'binary_class_g') {
    return createMultipleStarVisual(radius, lightColor, 2)
  }
  if (kind === 'star' && (key === 'triple_class_g' || key === 'trinary_class_g')) {
    return createMultipleStarVisual(radius, lightColor, 3)
  }
  if (kind === 'planet' && key === 'moon') {
    const scene = await loadGlb(planetModelPath(key))
    if (scene) {
      const root = scene.clone(true)
      const box = new THREE.Box3().setFromObject(root)
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.y, size.z) || 1
      root.scale.setScalar((radius * 2) / maxDim)
      root.updateMatrixWorld(true)
      new THREE.Box3().setFromObject(root).getCenter(center)
      root.position.sub(center)
      root.traverse((child) => {
        if (!child.isMesh) return
        child.castShadow = true
        child.receiveShadow = true
      })
      return root
    }
  }

  return createTexturedSphere({ typeKey: key, radius, kind, lightColor })
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
      satellites: world.satellites || [],
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
      satellites: body.satellites || [],
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
/**
 * Stellaris-style storm rim: flat turbulent band + soft vertical shell at the system edge.
 * @param {{
 *   radius: number,
 *   color?: string,
 *   intensity?: number,
 *   stage?: string,
 *   type?: string,
 * }} options
 */
function createStormBoundary(options) {
  const {
    radius,
    color = '#6ec8ff',
    intensity = 0.6,
    stage = 'active',
    type = 'electric',
  } = options
  const stageBoost = stage === 'forming' ? 0.55 : stage === 'dissipating' ? 0.7 : 1
  const typeId = type === 'gravity' ? 1 : type === 'particle' ? 2 : type === 'shroud' ? 3 : 0
  const group = new THREE.Group()
  group.name = 'stormBoundary'
  group.renderOrder = 6

  const uniforms = {
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(color) },
    uIntensity: { value: THREE.MathUtils.clamp(Number(intensity) || 0.5, 0.15, 1) * stageBoost },
    uType: { value: typeId },
  }

  const sharedFragmentNoise = `
    float hash21(vec2 p) {
      return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
    }
    float noise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      f = f * f * (3.0 - 2.0 * f);
      float a = hash21(i);
      float b = hash21(i + vec2(1.0, 0.0));
      float c = hash21(i + vec2(0.0, 1.0));
      float d = hash21(i + vec2(1.0, 1.0));
      return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
    }
    float fbm(vec2 p) {
      float v = 0.0;
      float a = 0.5;
      for (int i = 0; i < 4; i++) {
        v += a * noise(p);
        p = p * 2.05 + 17.3;
        a *= 0.5;
      }
      return v;
    }
  `

  const inner = radius * 0.78
  const outer = radius * 1.08
  const band = new THREE.Mesh(
    new THREE.RingGeometry(inner, outer, 256, 48),
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: `
        varying vec2 vPos;
        void main() {
          vPos = position.xy;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform vec3 uColor;
        uniform float uIntensity;
        uniform float uType;
        varying vec2 vPos;
        ${sharedFragmentNoise}
        void main() {
          float r = length(vPos);
          float t = (r - ${inner.toFixed(4)}) / max(${(outer - inner).toFixed(4)}, 0.001);
          float angle = atan(vPos.y, vPos.x);
          float rim = smoothstep(0.0, 0.18, t) * (1.0 - smoothstep(0.72, 1.0, t));
          vec2 drift = vec2(angle * 2.2, t * 4.0) + vec2(uTime * (0.18 + uType * 0.04), -uTime * 0.11);
          float clouds = fbm(drift * 2.4);
          float bolts = smoothstep(0.78, 0.96, fbm(drift * 6.5 + 9.1));
          float swirl = 0.5 + 0.5 * sin(angle * (8.0 + uType) - uTime * 1.4 + clouds * 4.0);
          float glow = rim * (0.35 + clouds * 0.55 + swirl * 0.25) + bolts * rim * 0.85;
          vec3 tint = uColor;
          if (uType > 2.5) tint = mix(uColor, vec3(0.55, 1.0, 0.82), 0.35);
          else if (uType > 1.5) tint = mix(uColor, vec3(1.0, 0.86, 0.45), 0.3);
          else if (uType > 0.5) tint = mix(uColor, vec3(0.72, 0.55, 1.0), 0.28);
          float alpha = glow * uIntensity * 0.95;
          if (alpha < 0.012) discard;
          gl_FragColor = vec4(tint * (0.55 + bolts * 1.4 + clouds * 0.35), clamp(alpha, 0.0, 0.92));
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    }),
  )
  band.rotation.x = -Math.PI / 2
  band.position.y = 0.04
  band.raycast = () => {}
  group.add(band)

  const wallHeight = Math.max(1.8, radius * 0.22)
  const wall = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.96, radius * 1.02, wallHeight, 128, 1, true),
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: `
        varying vec2 vUv;
        varying float vY;
        void main() {
          vUv = uv;
          vY = position.y;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform vec3 uColor;
        uniform float uIntensity;
        uniform float uType;
        varying vec2 vUv;
        varying float vY;
        ${sharedFragmentNoise}
        void main() {
          float h = abs(vY) / ${wallHeight.toFixed(4)};
          float vertical = 1.0 - smoothstep(0.15, 0.55, h);
          vec2 drift = vec2(vUv.x * 18.0 + uTime * 0.25, vUv.y * 3.0 - uTime * 0.18);
          float clouds = fbm(drift);
          float arcs = smoothstep(0.82, 0.97, fbm(drift * 3.2 + 4.7));
          float pulse = 0.65 + 0.35 * sin(uTime * 2.1 + vUv.x * 40.0);
          float alpha = vertical * (0.22 + clouds * 0.48 + arcs * 0.55) * uIntensity * pulse;
          if (alpha < 0.02) discard;
          vec3 tint = mix(uColor, vec3(1.0), arcs * 0.45);
          gl_FragColor = vec4(tint, clamp(alpha, 0.0, 0.78));
        }
      `,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    }),
  )
  wall.raycast = () => {}
  group.add(wall)

  group.userData.radius = radius
  group.userData.updateVisual = (elapsed) => {
    uniforms.uTime.value = elapsed
  }
  group.userData.setStorm = (storm) => {
    if (!storm) return
    uniforms.uColor.value.set(storm.color || color)
    const nextStage = storm.stage === 'forming' ? 0.55 : storm.stage === 'dissipating' ? 0.7 : 1
    uniforms.uIntensity.value =
      THREE.MathUtils.clamp(Number(storm.intensity) || 0.5, 0.15, 1) * nextStage
    uniforms.uType.value =
      storm.type === 'gravity' ? 1 : storm.type === 'particle' ? 2 : storm.type === 'shroud' ? 3 : 0
  }

  return group
}

export function createSystemDetailScene(canvas, detail, callbacks = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setClearColor(0x000000, 0)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

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

  const hostKind =
    detail.kind === 'black_hole' || detail.kind === 'well' || detail.kind === 'junction'
      ? detail.kind
      : 'star'
  const hostDescription = String(detail.starType || '').toLowerCase()
  const resolvedHostTypeKey = resolveStarTypeKey(detail.starTypeKey, hostKind)
  const hostTypeKey =
    hostKind === 'star' && /(triple|trinary|three\s+suns|three\s+stars)/.test(hostDescription)
      ? 'triple_class_g'
      : resolvedHostTypeKey
  const systemLightColor = new THREE.Color(
    hostKind === 'star'
      ? starColor(hostTypeKey)
      : hostKind === 'well'
        ? 0xffb06a
        : hostKind === 'junction'
          ? 0x9fc9d8
          : 0xff7a62,
  )
  scene.add(new THREE.AmbientLight(0xffffff, 0.18))
  const light = new THREE.PointLight(
    systemLightColor,
    hostKind === 'junction' ? 0 : hostKind === 'black_hole' || hostKind === 'well' ? 1.2 : 3.2,
    100,
  )
  light.position.set(0, 0, 0)
  light.castShadow = true
  light.shadow.mapSize.set(1024, 1024)
  scene.add(light)

  const root = new THREE.Group()
  scene.add(root)

  let raf = 0
  let frameCount = 0
  let disposed = false
  const animated = []
  const labelAnchors = []
  const zAxis = new THREE.Vector3(0, 0, 1)
  let stormBoundary = null
  let stormRadius = 10
  let sceneReady = false
  let latestStorm = callbacks.storm || null

  function clearStormBoundary() {
    if (!stormBoundary) return
    root.remove(stormBoundary)
    stormBoundary.traverse((child) => {
      child.geometry?.dispose()
      if (child.material) {
        if (Array.isArray(child.material)) child.material.forEach((mat) => mat.dispose())
        else child.material.dispose()
      }
    })
    stormBoundary = null
  }

  function setStorm(storm, { forceRadius = false } = {}) {
    latestStorm = storm || null
    if (disposed || !sceneReady) return
    if (!latestStorm || !(Number(latestStorm.intensity) > 0.05)) {
      clearStormBoundary()
      return
    }
    const needsRebuild =
      forceRadius ||
      !stormBoundary ||
      Math.abs(Number(stormBoundary.userData.radius) - stormRadius) > 0.05
    if (needsRebuild) {
      clearStormBoundary()
      stormBoundary = createStormBoundary({
        radius: stormRadius,
        color: latestStorm.color,
        intensity: latestStorm.intensity,
        stage: latestStorm.stage,
        type: latestStorm.type,
      })
      stormBoundary.userData.radius = stormRadius
      root.add(stormBoundary)
    } else {
      stormBoundary.userData.setStorm?.(latestStorm)
    }
  }

  async function build() {
    let host
    const hostRadius = hostKind === 'well' ? 2.1 : hostKind === 'black_hole' ? 1.55 : 1.35
    if (hostKind === 'junction') {
      // Intentionally empty center: a junction is a location where corridors
      // meet, not a hidden star or black hole.
      host = new THREE.Object3D()
      root.add(host)
    } else {
      host = await createBodyMesh({
        kind: hostKind,
        typeKey: hostTypeKey,
        radius: hostRadius,
        lightColor: systemLightColor,
      })
      root.add(host)
      animated.push({ mesh: host, orbit: 0, speed: 0 })
    }
    if (hostKind !== 'junction') {
      labelAnchors.push({
        id: `host:${detail.token}`,
        mesh: host,
        nameEn: detail.nameEn,
        nameRu: detail.nameRu,
        kind: hostKind,
        inhabited: false,
        planetType: detail.starType,
      })
    }

    // Junctions deliberately have no host and no planets; optional feature
    // belts are still rendered below when present in canon.

    const planets = collectBodies(detail)
    const featureBelts = detail.features || []
    const ORBIT_START = 2.6
    const ORBIT_STEP = 1.5
    const PLANET_CLEARANCE = 0.9
    const BELT_GAP = 0.65
    const innerBelts = featureBelts.filter((feature) => feature.placement === 'inner')
    const middleBelts =
      planets.length >= 2
        ? featureBelts.filter((feature) => feature.placement === 'middle')
        : []
    const outerBelts = featureBelts.filter(
      (feature) =>
        feature.placement === 'outer' ||
        (feature.placement === 'middle' && planets.length < 2),
    )

    async function addFeatureBelt(feature, index, minInner) {
      const featureKey = resolveFeatureKey(feature.feature || feature.nameEn)
      const belt = await createAsteroidBelt(featureKey, { minInner })
      if (disposed) return null
      root.add(belt)
      if (belt.userData.beltSpin) {
        animated.push({ beltSpin: belt.userData.beltSpin })
      }

      const beltOrbit = belt.userData.beltOrbit || minInner + 0.4
      const beltOuter = belt.userData.beltOuter || beltOrbit + 0.5
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
      return { beltOuter }
    }

    const planetRadii = planets.map((planet) =>
      planet.planetTypeKey === 'gas_giant' ? 0.62 : planet.inhabited ? 0.4 : 0.3,
    )
    const satelliteExtents = planets.map((planet, index) => {
      const satellites = planet.satellites || []
      if (!satellites.length) return planetRadii[index]
      const outerIndex = satellites.length - 1
      const outerOrbit = planetRadii[index] * 1.65 + outerIndex * planetRadii[index] * 0.72
      const outerRadius = Math.max(
        0.075,
        planetRadii[index] *
          (satellites[outerIndex].planetTypeKey === 'gas_giant' ? 0.34 : 0.26),
      )
      return outerOrbit + outerRadius
    })

    let innerClearAfter = hostKind === 'junction' ? 0.55 : hostRadius + 0.45
    for (let index = 0; index < innerBelts.length; index += 1) {
      const result = await addFeatureBelt(innerBelts[index], index, innerClearAfter)
      if (!result) return
      innerClearAfter = result.beltOuter + BELT_GAP
    }

    const planetOrbits = []
    const middleInsertIndex = Math.max(1, Math.floor(planets.length / 2))
    let planetaryOuterEdge = innerClearAfter
    for (let index = 0; index < planets.length; index += 1) {
      if (index === middleInsertIndex) {
        for (let beltIndex = 0; beltIndex < middleBelts.length; beltIndex += 1) {
          const result = await addFeatureBelt(
            middleBelts[beltIndex],
            innerBelts.length + beltIndex,
            planetaryOuterEdge + BELT_GAP,
          )
          if (!result) return
          planetaryOuterEdge = result.beltOuter
        }
      }
      const orbit = Math.max(
        ORBIT_START + index * ORBIT_STEP,
        planetaryOuterEdge + satelliteExtents[index] + PLANET_CLEARANCE,
      )
      planetOrbits.push(orbit)
      planetaryOuterEdge = orbit + satelliteExtents[index]
    }

    await Promise.all(
      planets.map(async (planet, index) => {
        const orbit = planetOrbits[index]
        const radius = planetRadii[index]
        const mesh = await createBodyMesh({
          kind: 'planet',
          typeKey: planet.planetTypeKey,
          radius,
          lightColor: systemLightColor,
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

        await Promise.all(
          (planet.satellites || []).map(async (satellite, satelliteIndex) => {
            const satelliteRadius = Math.max(
              0.075,
              radius * (satellite.planetTypeKey === 'gas_giant' ? 0.34 : 0.26),
            )
            const satelliteOrbit = radius * 1.65 + satelliteIndex * radius * 0.72
            const satelliteMesh = await createBodyMesh({
              kind: 'planet',
              typeKey: satellite.planetTypeKey || 'moon',
              radius: satelliteRadius,
              lightColor: systemLightColor,
            })
            if (disposed) return
            const satelliteAngle =
              (satelliteIndex / Math.max(planet.satellites.length, 1)) * Math.PI * 2 + 0.65
            satelliteMesh.position.set(
              Math.cos(satelliteAngle) * satelliteOrbit,
              0,
              Math.sin(satelliteAngle) * satelliteOrbit,
            )
            mesh.add(satelliteMesh)

            const satelliteRing = new THREE.Mesh(
              new THREE.RingGeometry(satelliteOrbit - 0.006, satelliteOrbit + 0.006, 96),
              new THREE.MeshBasicMaterial({
                color: 0x7891ac,
                transparent: true,
                opacity: 0.24,
                side: THREE.DoubleSide,
                depthWrite: false,
              }),
            )
            satelliteRing.rotation.x = -Math.PI / 2
            satelliteRing.raycast = () => {}
            mesh.add(satelliteRing)

            animated.push({
              mesh: satelliteMesh,
              orbit: satelliteOrbit,
              speed: 0.9 / Math.sqrt(satelliteIndex + 1),
              angle: satelliteAngle,
            })
            labelAnchors.push({
              id: `${planet.id}:satellite:${satellite.nameEn}`,
              mesh: satelliteMesh,
              nameEn: satellite.nameEn,
              nameRu: satellite.nameRu,
              kind: 'satellite',
              inhabited: false,
              planetType: satellite.planetType,
            })
          }),
        )
      }),
    )

    // Place belts sequentially outside planet orbits (and outside previous belts).
    let clearAfter =
      planetOrbits.length > 0
        ? planetaryOuterEdge + PLANET_CLEARANCE
        : Math.max(innerClearAfter, hostKind === 'junction' ? 0.55 : ORBIT_START + PLANET_CLEARANCE)
    let farthest = Math.max(clearAfter, innerClearAfter)

    for (let index = 0; index < outerBelts.length; index += 1) {
      const result = await addFeatureBelt(
        outerBelts[index],
        innerBelts.length + middleBelts.length + index,
        clearAfter,
      )
      if (!result) return
      farthest = Math.max(farthest, result.beltOuter)
      clearAfter = result.beltOuter + BELT_GAP
    }

    // Look down onto the orbital plane (XZ).
    const span = Math.max(hostKind === 'junction' ? 4.2 : 8, farthest + 2.4)
    camera.position.set(0, span * 0.95, span * 0.35)
    controls.target.set(0, 0, 0)
    controls.maxDistance = Math.max(28, span * 2.2)
    controls.update()

    stormRadius = Math.max(span * 0.88, farthest + 1.1)
    sceneReady = true
    setStorm(latestStorm, { forceRadius: true })

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
    const elapsed = performance.now() * 0.001
    stormBoundary?.userData.updateVisual?.(elapsed)
    for (const body of animated) {
      body.mesh?.userData.updateVisual?.(elapsed, camera)
      if (body.beltSpin) {
        body.beltSpin.mesh.userData.updateVisual?.(elapsed, camera)
        body.beltSpin.mesh.rotation.y += body.beltSpin.speed * 0.016
        continue
      }
      if (body.spin) {
        body.mesh.rotation.y += body.spin
      }
      if (!body.orbit) {
        if (!body.mesh.userData.disableSpin) body.mesh.rotation.y += 0.0025
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
    clearStormBoundary()
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

  return { dispose, resize, setStorm }
}
