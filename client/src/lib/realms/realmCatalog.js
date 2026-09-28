export const REALMS = {
  heaven: {
    path: '/heaven',
    nameRu: 'Рай',
    nameEn: 'Heaven',
    subtitleRu: 'Карта небесных пределов',
    subtitleEn: 'Map of the celestial reaches',
    accent: '#d9f4ff',
    glow: '#7bdcff',
    background: '#07131d',
  },
  hell: {
    path: '/hell',
    nameRu: 'Ад',
    nameEn: 'Hell',
    subtitleRu: 'Карта инфернальных владений',
    subtitleEn: 'Map of the infernal dominions',
    accent: '#ffb07a',
    glow: '#ff3d1f',
    background: '#190705',
  },
  void: {
    path: '/void',
    nameRu: 'Воид',
    nameEn: 'Void',
    subtitleRu: 'Карта пространства за гранью',
    subtitleEn: 'Map of the space beyond',
    accent: '#c8a7ff',
    glow: '#7044ff',
    background: '#080514',
  },
  astral: {
    path: '/astral',
    nameRu: 'Астрал',
    nameEn: 'Astral',
    subtitleRu: 'Карта астральных течений',
    subtitleEn: 'Map of the astral currents',
    accent: '#9dffe1',
    glow: '#31d8b0',
    background: '#041512',
  },
}

export function pageFromPath(pathname = '/') {
  const normalized = pathname.replace(/\/+$/, '') || '/'
  if (normalized === '/') return 'universe'
  return Object.entries(REALMS).find(([, realm]) => realm.path === normalized)?.[0] || 'universe'
}

