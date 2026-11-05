const fs = require('fs');
const path = require('path');

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const { fileNodes, importEdges, allEdges } = data;

// A. Directory Grouping
const filePaths = fileNodes.map(n => n.filePath);

// Find common prefix
function commonPrefix(paths) {
  if (!paths.length) return '';
  const parts = paths.map(p => p.replace(/\\/g, '/').split('/'));
  const minLen = Math.min(...parts.map(p => p.length));
  let prefix = [];
  for (let i = 0; i < minLen - 1; i++) {
    const seg = parts[0][i];
    if (parts.every(p => p[i] === seg)) prefix.push(seg);
    else break;
  }
  return prefix.join('/');
}

const commonPfx = commonPrefix(filePaths);

function getGroup(filePath) {
  const normalized = filePath.replace(/\\/g, '/');
  const withoutPrefix = commonPfx ? normalized.slice(commonPfx.length + 1) : normalized;
  const parts = withoutPrefix.split('/');
  if (parts.length <= 1) return 'root';
  return parts[0];
}

const directoryGroups = {};
for (const node of fileNodes) {
  const group = getGroup(node.filePath);
  if (!directoryGroups[group]) directoryGroups[group] = [];
  directoryGroups[group].push(node.id);
}

// B. Node Type Grouping
const nodeTypeGroups = {};
for (const node of fileNodes) {
  if (!nodeTypeGroups[node.type]) nodeTypeGroups[node.type] = [];
  nodeTypeGroups[node.type].push(node.id);
}

// C. Import adjacency
const fanOut = {};
const fanIn = {};
for (const node of fileNodes) {
  fanOut[node.id] = 0;
  fanIn[node.id] = 0;
}
for (const edge of importEdges) {
  if (fanOut[edge.source] !== undefined) fanOut[edge.source]++;
  if (fanIn[edge.target] !== undefined) fanIn[edge.target]++;
}

// D. Cross-Category Dependency Analysis
const nodeTypeMap = {};
for (const node of fileNodes) nodeTypeMap[node.id] = node.type;

const crossCategoryMap = {};
for (const edge of allEdges) {
  const fromType = nodeTypeMap[edge.source] || 'unknown';
  const toType = nodeTypeMap[edge.target] || 'unknown';
  if (fromType === toType && fromType === 'file') continue; // skip file->file for cross-category
  const key = `${fromType}->${toType}:${edge.type}`;
  crossCategoryMap[key] = (crossCategoryMap[key] || 0) + 1;
}

const crossCategoryEdges = Object.entries(crossCategoryMap).map(([key, count]) => {
  const [types, edgeType] = key.split(':');
  const [fromType, toType] = types.split('->');
  return { fromType, toType, edgeType, count };
});

// E. Inter-Group Import Frequency
const idToGroup = {};
for (const node of fileNodes) {
  idToGroup[node.id] = getGroup(node.filePath);
}

const interGroupMap = {};
for (const edge of importEdges) {
  const fromGroup = idToGroup[edge.source];
  const toGroup = idToGroup[edge.target];
  if (!fromGroup || !toGroup || fromGroup === toGroup) continue;
  const key = `${fromGroup}->${toGroup}`;
  interGroupMap[key] = (interGroupMap[key] || 0) + 1;
}
const interGroupImports = Object.entries(interGroupMap).map(([key, count]) => {
  const [from, to] = key.split('->');
  return { from, to, count };
});

// F. Intra-Group Import Density
const intraGroupDensity = {};
for (const group of Object.keys(directoryGroups)) {
  const members = new Set(directoryGroups[group]);
  let internalEdges = 0;
  let totalEdges = 0;
  for (const edge of importEdges) {
    const srcInGroup = members.has(edge.source);
    const tgtInGroup = members.has(edge.target);
    if (srcInGroup || tgtInGroup) totalEdges++;
    if (srcInGroup && tgtInGroup) internalEdges++;
  }
  intraGroupDensity[group] = {
    internalEdges,
    totalEdges,
    density: totalEdges > 0 ? internalEdges / totalEdges : 0
  };
}

// G. Directory Pattern Matching
const dirPatterns = {
  routes: 'api', api: 'api', controllers: 'api', endpoints: 'api', handlers: 'api',
  services: 'service', core: 'service', lib: 'service', domain: 'service', logic: 'service',
  models: 'data', db: 'data', data: 'data', persistence: 'data', repository: 'data', entities: 'data',
  components: 'ui', views: 'ui', pages: 'ui', ui: 'ui', layouts: 'ui', screens: 'ui',
  middleware: 'middleware', plugins: 'middleware', interceptors: 'middleware', guards: 'middleware',
  utils: 'utility', helpers: 'utility', common: 'utility', shared: 'utility', tools: 'utility',
  config: 'config', constants: 'config', env: 'config', settings: 'config',
  __tests__: 'test', test: 'test', tests: 'test', spec: 'test', specs: 'test',
  types: 'types', interfaces: 'types', schemas: 'types', contracts: 'types', dtos: 'types',
  hooks: 'hooks',
  store: 'state', state: 'state', reducers: 'state', actions: 'state', slices: 'state',
  assets: 'assets', static: 'assets', public: 'assets',
  migrations: 'data', management: 'config', commands: 'config',
  templatetags: 'utility', signals: 'service', serializers: 'api',
  cmd: 'entry', internal: 'service', pkg: 'utility',
  dto: 'types', request: 'types', response: 'types',
  entity: 'data', controller: 'api', routers: 'api',
  composables: 'service', blueprints: 'api',
  mailers: 'service', jobs: 'service', channels: 'service',
  bin: 'entry',
  docs: 'documentation', documentation: 'documentation', wiki: 'documentation',
  deploy: 'infrastructure', deployment: 'infrastructure', infra: 'infrastructure', infrastructure: 'infrastructure',
  '.github': 'ci-cd', '.gitlab': 'ci-cd', '.circleci': 'ci-cd',
  k8s: 'infrastructure', kubernetes: 'infrastructure', helm: 'infrastructure', charts: 'infrastructure',
  terraform: 'infrastructure', tf: 'infrastructure', docker: 'infrastructure',
  sql: 'data', database: 'data', schema: 'data',
  root: 'config'
};

const patternMatches = {};
for (const group of Object.keys(directoryGroups)) {
  patternMatches[group] = dirPatterns[group.toLowerCase()] || 'unknown';
}

// Also check file-level patterns
const filePatternMatches = {};
for (const node of fileNodes) {
  const fp = node.filePath.replace(/\\/g, '/');
  const fname = fp.split('/').pop();
  if (/\.(test|spec)\.[^.]+$/.test(fname) || /^test_/.test(fname) || /_test\.[^.]+$/.test(fname)) {
    filePatternMatches[node.id] = 'test';
  } else if (/\.d\.ts$/.test(fname)) {
    filePatternMatches[node.id] = 'types';
  } else if (/^(Dockerfile|docker-compose)/.test(fname) || /docker-compose/.test(fname)) {
    filePatternMatches[node.id] = 'infrastructure';
  } else if (/\.(tf|tfvars)$/.test(fname)) {
    filePatternMatches[node.id] = 'infrastructure';
  } else if (/\.(sql)$/.test(fname)) {
    filePatternMatches[node.id] = 'data';
  } else if (/\.(graphql|gql|proto)$/.test(fname)) {
    filePatternMatches[node.id] = 'types';
  } else if (/\.(md|rst)$/.test(fname)) {
    filePatternMatches[node.id] = 'documentation';
  } else if (/^(Makefile|Cargo\.toml|go\.mod|Gemfile|pom\.xml|build\.gradle|composer\.json)$/.test(fname)) {
    filePatternMatches[node.id] = 'config';
  } else if (/^(\.gitattributes|\.python-version|pyproject\.toml)$/.test(fname)) {
    filePatternMatches[node.id] = 'config';
  }
}

// H. Deployment Topology Detection
const infraFiles = fileNodes.filter(n => {
  const fp = n.filePath.replace(/\\/g, '/');
  const fname = fp.split('/').pop();
  return /^Dockerfile/.test(fname) || /docker-compose/.test(fname) ||
    fp.includes('.github/') || fp.includes('.gitlab/') ||
    /\.(tf|tfvars)$/.test(fname) || fname === 'Makefile' ||
    fp.includes('k8s/') || fp.includes('kubernetes/');
}).map(n => n.filePath);

const deploymentTopology = {
  hasDockerfile: fileNodes.some(n => /^Dockerfile/.test(n.filePath.split('/').pop())),
  hasCompose: fileNodes.some(n => /docker-compose/.test(n.filePath)),
  hasK8s: fileNodes.some(n => n.filePath.includes('k8s/') || n.filePath.includes('kubernetes/')),
  hasTerraform: fileNodes.some(n => /\.(tf|tfvars)$/.test(n.filePath)),
  hasCI: fileNodes.some(n => n.filePath.includes('.github/') || n.filePath.includes('.gitlab-ci')),
  infraFiles
};

// I. Data Pipeline Detection
const schemaFiles = fileNodes.filter(n => /\.(graphql|gql|proto|sql)$/.test(n.filePath) || n.tags.includes('schema-definition')).map(n => n.filePath);
const migrationFiles = fileNodes.filter(n => n.filePath.includes('migration')).map(n => n.filePath);
const dataModelFiles = fileNodes.filter(n => n.tags.includes('data-model')).map(n => n.filePath);
const apiHandlerFiles = fileNodes.filter(n => n.tags.includes('api-handler')).map(n => n.filePath);

const dataPipeline = { schemaFiles, migrationFiles, dataModelFiles, apiHandlerFiles };

// J. Documentation Coverage
const groups = Object.keys(directoryGroups);
const groupsWithDocs = groups.filter(g => {
  return directoryGroups[g].some(id => {
    const node = fileNodes.find(n => n.id === id);
    return node && (node.type === 'document' || node.tags.includes('documentation'));
  });
});
const docCoverage = {
  groupsWithDocs: groupsWithDocs.length,
  totalGroups: groups.length,
  coverageRatio: groupsWithDocs.length / groups.length,
  undocumentedGroups: groups.filter(g => !groupsWithDocs.includes(g))
};

// K. Dependency Direction
const dependencyDirection = interGroupImports.map(({ from, to, count }) => ({
  dependent: from,
  dependsOn: to
}));

// File stats
const filesPerGroup = {};
for (const [group, ids] of Object.entries(directoryGroups)) {
  filesPerGroup[group] = ids.length;
}
const nodeTypeCounts = {};
for (const [type, ids] of Object.entries(nodeTypeGroups)) {
  nodeTypeCounts[type] = ids.length;
}

const result = {
  scriptCompleted: true,
  directoryGroups,
  nodeTypeGroups,
  crossCategoryEdges,
  interGroupImports,
  intraGroupDensity,
  patternMatches,
  filePatternMatches,
  deploymentTopology,
  dataPipeline,
  docCoverage,
  dependencyDirection,
  fileStats: {
    totalFileNodes: fileNodes.length,
    filesPerGroup,
    nodeTypeCounts
  },
  fileFanIn: fanIn,
  fileFanOut: fanOut
};

fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
console.log('Analysis complete. Total file nodes:', fileNodes.length);
process.exit(0);
